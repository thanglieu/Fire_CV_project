# alert_app/services/camera_stream.py
import logging
import threading
import time

import cv2
import numpy as np

log = logging.getLogger(__name__)

DEFAULT_SOURCE = "http://192.168.1.102:4747/video"
COLORS = {"fire": (0, 0, 255), "smoke": (180, 180, 180), "human": (0, 200, 0)}


class CameraStream:
    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self, source, detector, on_alert=None, alert_names=None, cooldown=30.0,
                 infer_fps=5.0, stream_fps=30.0, jpeg_quality=75, max_width=960):
        self.source = int(source) if str(source).strip().isdigit() else source
        self.detector = detector
        self.on_alert = on_alert                       # hàm(annotated_frame, max_conf)
        self.alert_names = set(alert_names or getattr(detector, "alert_names", None) or [])
        self.cooldown = cooldown
        self.infer_interval = 1.0 / infer_fps
        self.stream_interval = 1.0 / stream_fps
        self.jpeg_quality = jpeg_quality
        self.max_width = max_width

        self._frame = None            # khung mới nhất (ndarray, không bao giờ sửa tại chỗ)
        self._seq = 0
        self._frame_lock = threading.Lock()
        self._last_frame_t = 0.0

        self._dets = ([], 0.0)        # (danh sách phát hiện, thời điểm)
        self._jpg = None
        self._jpg_id = 0
        self._cond = threading.Condition()

        self.connected = False
        self.alerts_sent = 0
        self._fps = 0.0
        self._infer_ms = 0.0
        self._last_alert = 0.0
        self._stop = threading.Event()
        self._started = False

    # ------------------------------------------------------------------ khởi tạo
    @classmethod
    def get_instance(cls):
        """Singleton: dù có bao nhiêu tab trình duyệt, chỉ mở camera + chạy YOLO MỘT lần."""
        with cls._instance_lock:
            if cls._instance is None:
                from django.conf import settings
                from .alerting import handle_fire_alert
                from .detector import FireDetector

                inst = cls(source=getattr(settings, "DROIDCAM_URL", DEFAULT_SOURCE),
                           detector=FireDetector.get_instance(), on_alert=handle_fire_alert)
                inst.start()
                cls._instance = inst
            return cls._instance

    def start(self):
        if self._started:
            return
        self._started = True
        for target in (self._reader, self._inference, self._publisher):
            threading.Thread(target=target, daemon=True, name=target.__name__).start()

    def stop(self):
        self._stop.set()

    # ------------------------------------------------------------------ luồng 1: đọc camera
    def _reader(self):
        while not self._stop.is_set():
            cap = cv2.VideoCapture(self.source)
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            if not cap.isOpened():
                self.connected = False
                cap.release()
                log.warning("Không mở được camera %s, thử lại sau 2s", self.source)
                self._stop.wait(2)
                continue
            log.info("Đã kết nối camera %s", self.source)
            fails = 0
            while not self._stop.is_set():
                ok, frame = cap.read()          # chặn tới khi có khung mới, luôn đọc hết tốc độ
                if not ok or frame is None:
                    fails += 1
                    if fails > 30:
                        break
                    time.sleep(0.02)
                    continue
                fails = 0
                with self._frame_lock:
                    self._frame, self._seq = frame, self._seq + 1
                self._last_frame_t = time.time()
                self.connected = True
            cap.release()
            self.connected = False
            log.warning("Mất kết nối camera, đang kết nối lại...")
            self._stop.wait(1)

    def _latest(self):
        with self._frame_lock:
            return self._frame, self._seq

    # ------------------------------------------------------------------ luồng 2: YOLO + báo động
    def _inference(self):
        last_seq = -1
        while not self._stop.is_set():
            t0 = time.time()
            frame, seq = self._latest()
            if frame is None or seq == last_seq:
                time.sleep(0.01)
                continue
            last_seq = seq
            try:
                dets = self.detector.detect(frame)
            except Exception:
                log.exception("Lỗi khi chạy YOLO")
                time.sleep(1)
                continue
            now = time.time()
            self._dets = (dets, now)
            self._infer_ms = (now - t0) * 1000

            alarm = [d for d in dets if d[0] in self.alert_names]
            if alarm and now - self._last_alert > self.cooldown:
                self._last_alert = now
                if self.on_alert:
                    try:
                        self.on_alert(self._draw(frame.copy(), dets), max(d[1] for d in alarm))
                    except Exception:
                        log.exception("Lỗi khi xử lý báo động")
                self.alerts_sent += 1          # tăng SAU khi đã ghi DB để web refresh danh sách đúng lúc

            # giới hạn tốc độ AI để nhường CPU cho việc nén/đẩy hình
            time.sleep(max(0.0, self.infer_interval - (time.time() - t0)))

    # ------------------------------------------------------------------ luồng 3: vẽ + nén + đẩy
    @staticmethod
    def _draw(img, dets, scale=1.0):
        for label, conf, (x1, y1, x2, y2) in dets:
            col = COLORS.get(label, (255, 200, 0))
            p1, p2 = (int(x1 * scale), int(y1 * scale)), (int(x2 * scale), int(y2 * scale))
            cv2.rectangle(img, p1, p2, col, 3)
            txt = f"{label.upper()} {conf:.2f}"
            (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(img, (p1[0], max(0, p1[1] - th - 8)), (p1[0] + tw + 6, p1[1]), col, -1)
            cv2.putText(img, txt, (p1[0] + 3, max(th, p1[1] - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return img

    def _publish(self, jpg):
        with self._cond:
            self._jpg, self._jpg_id = jpg, self._jpg_id + 1
            self._cond.notify_all()

    def _offline_jpg(self):
        img = np.zeros((480, 640, 3), np.uint8)
        cv2.putText(img, "DANG KET NOI LAI CAMERA...", (60, 245),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (80, 80, 255), 2, cv2.LINE_AA)
        return cv2.imencode(".jpg", img)[1].tobytes()

    def _publisher(self):
        last_seq, offline_jpg = -1, None
        fps_t, fps_n = time.time(), 0
        while not self._stop.is_set():
            t0 = time.time()
            frame, seq = self._latest()

            if frame is None or t0 - self._last_frame_t > 2.0:   # camera im quá 2 giây
                offline_jpg = offline_jpg or self._offline_jpg()
                self._publish(offline_jpg)
                self._fps = 0.0
                time.sleep(0.5)
                continue
            if seq == last_seq:
                time.sleep(0.004)
                continue
            last_seq = seq

            img, scale = frame, 1.0
            if self.max_width and img.shape[1] > self.max_width:
                scale = self.max_width / img.shape[1]
                img = cv2.resize(img, (self.max_width, int(img.shape[0] * scale)), interpolation=cv2.INTER_AREA)
            else:
                img = img.copy()
            dets, dt = self._dets
            if dets and t0 - dt < 1.5:                            # bỏ khung phát hiện quá cũ
                self._draw(img, dets, scale)
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
            if ok:
                self._publish(buf.tobytes())

            fps_n += 1
            if t0 - fps_t >= 1.0:
                self._fps, fps_t, fps_n = fps_n / (t0 - fps_t), t0, 0
            time.sleep(max(0.0, self.stream_interval - (time.time() - t0)))

    # ------------------------------------------------------------------ giao diện cho view
    def frames(self):
        """Generator cho StreamingHttpResponse. Chờ khung mới bằng Condition (không polling)."""
        last_id = 0
        while not self._stop.is_set():
            with self._cond:
                self._cond.wait_for(lambda: self._jpg_id != last_id, timeout=5)
                if self._jpg_id == last_id:
                    continue
                jpg, last_id = self._jpg, self._jpg_id
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"

    def status(self):
        dets, dt = self._dets
        names = {d[0] for d in dets} if time.time() - dt < 2 else set()
        return {
            "connected": self.connected and time.time() - self._last_frame_t < 2,
            "fps": round(self._fps, 1),
            "infer_ms": int(self._infer_ms),
            "detected": sorted(names),
            "fire": bool(names & self.alert_names),
            "alerts_sent": self.alerts_sent,
        }