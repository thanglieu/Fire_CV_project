#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hệ thống phát hiện cháy bằng YOLO (best.pt: fire / human / smoke)

Camera điện thoại --(Wi-Fi LAN)--> Máy tính chạy server (file này)
   --> nếu phát hiện cháy --> Telegram / ntfy --> điện thoại ở BẤT KỲ đâu có Internet
"""
import argparse
import datetime as dt
import logging
import os
import queue
import smtplib
import ssl
from email.message import EmailMessage
import sys
import threading
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import requests
import yaml

BASE_DIR = Path(__file__).resolve().parent
log = logging.getLogger("fire")

COLORS = {"fire": (0, 0, 255), "smoke": (170, 170, 170), "human": (0, 200, 0)}
VN_LABEL = {"fire": "CHÁY", "smoke": "KHÓI", "human": "NGƯỜI"}

DEFAULT_CONFIG = {
    "camera": {"name": "Camera 1", "source": 0, "reconnect_delay": 3, "loop_video": True},
    "model": {"path": "models/best.pt", "imgsz": 640, "device": "auto", "half": True, "process_fps": 5},
    "detection": {"fire_conf": 0.5, "smoke_conf": 0.5, "human_conf": 0.5,
                  "draw_human": True, "alert_classes": ["fire"]},
    "alert": {"window_seconds": 5, "min_hits": 8, "cooldown_seconds": 120,
              "save_snapshots": True, "keep_last_snapshots": 200,
              "camera_offline_alert_seconds": 60},
    "telegram": {"enabled": False, "bot_token": "", "chat_ids": [], "send_photo": True},
    "zalo": {"enabled": False, "bot_token": "", "chat_ids": []},
    "ntfy": {"enabled": False, "server": "https://ntfy.sh", "topic": ""},
    "discord": {"enabled": False, "webhook_url": ""},
    "email": {"enabled": False, "smtp_host": "smtp.gmail.com", "smtp_port": 465,
              "username": "", "password": "", "to": []},
    "web": {"enabled": True, "host": "0.0.0.0", "port": 5000, "max_width": 960},
}


# ----------------------------------------------------------------------------
# Cấu hình
# ----------------------------------------------------------------------------
def deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        user = yaml.safe_load(f) or {}
    return deep_merge(DEFAULT_CONFIG, user)


# ----------------------------------------------------------------------------
# Đọc camera (thread riêng, luôn giữ khung hình mới nhất => độ trễ thấp)
# ----------------------------------------------------------------------------
class CameraReader(threading.Thread):
    def __init__(self, source, reconnect_delay=3, loop_video=True):
        super().__init__(daemon=True)
        if isinstance(source, str) and source.strip().isdigit():
            source = int(source.strip())
        self.source = source
        self.reconnect_delay = reconnect_delay
        self.loop_video = loop_video
        self.is_file = isinstance(source, str) and Path(source).exists()
        self.frame = None
        self.seq = 0
        self.connected = False
        self.last_ok = time.time()
        self._lock = threading.Lock()
        self._stop_evt = threading.Event()

    def _open(self):
        if isinstance(self.source, str) and self.source.lower().startswith("rtsp"):
            # RTSP qua TCP ổn định hơn UDP
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
        cap = cv2.VideoCapture(self.source)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        return cap

    def run(self):
        while not self._stop_evt.is_set():
            cap = self._open()
            if not cap.isOpened():
                self.connected = False
                log.warning("Không mở được camera (%s). Thử lại sau %ss...", self.source, self.reconnect_delay)
                cap.release()
                self._stop_evt.wait(self.reconnect_delay)
                continue
            log.info("Đã kết nối camera: %s", self.source)
            fails = 0
            file_delay = 0.0
            if self.is_file:
                fps = cap.get(cv2.CAP_PROP_FPS) or 25
                file_delay = 1.0 / fps
            while not self._stop_evt.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    if self.is_file and self.loop_video:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    fails += 1
                    if fails > 30:
                        break
                    time.sleep(0.05)
                    continue
                fails = 0
                with self._lock:
                    self.frame = frame
                    self.seq += 1
                self.connected = True
                self.last_ok = time.time()
                if file_delay:
                    time.sleep(file_delay)
            self.connected = False
            cap.release()
            log.warning("Mất kết nối camera. Đang kết nối lại...")
            self._stop_evt.wait(self.reconnect_delay)

    def get(self):
        with self._lock:
            return (None if self.frame is None else self.frame.copy()), self.seq

    def stop(self):
        self._stop_evt.set()


# ----------------------------------------------------------------------------
# Gửi thông báo (Telegram / ntfy) - chạy nền, có thử lại
# ----------------------------------------------------------------------------
class Notifier:
    def __init__(self, cfg):
        self.tg = cfg.get("telegram", {})
        self.ntfy = cfg.get("ntfy", {})
        self.zalo = cfg.get("zalo", {})
        self.discord = cfg.get("discord", {})
        self.email = cfg.get("email", {})
        self.q = queue.Queue(maxsize=20)
        threading.Thread(target=self._worker, daemon=True).start()

    # --- cấu hình Telegram (ưu tiên biến môi trường) ---
    def _tg_params(self):
        if not self.tg.get("enabled"):
            return None, []
        token = os.getenv("TELEGRAM_BOT_TOKEN") or str(self.tg.get("bot_token", "")).strip()
        env_ids = os.getenv("TELEGRAM_CHAT_ID")
        ids = [c.strip() for c in env_ids.split(",") if c.strip()] if env_ids else \
            [str(c).strip() for c in (self.tg.get("chat_ids") or [])]
        if not token or token.startswith("YOUR_"):
            return None, []
        ids = [c for c in ids if c and not c.startswith("YOUR_")]
        return (token, ids) if ids else (None, [])

    def _zalo_params(self):
        if not self.zalo.get("enabled"):
            return None, []
        token = os.getenv("ZALO_BOT_TOKEN") or str(self.zalo.get("bot_token", "")).strip()
        env_ids = os.getenv("ZALO_CHAT_ID")
        ids = [c.strip() for c in env_ids.split(",") if c.strip()] if env_ids else \
            [str(c).strip() for c in (self.zalo.get("chat_ids") or [])]
        if not token or token.startswith("YOUR_"):
            return None, []
        ids = [c for c in ids if c and not c.startswith("YOUR_")]
        return (token, ids) if ids else (None, [])

    def _discord_url(self):
        u = os.getenv("DISCORD_WEBHOOK_URL") or str(self.discord.get("webhook_url", "")).strip()
        return u if (self.discord.get("enabled") and u.startswith("http")) else None

    def _email_ok(self):
        e = self.email
        to = [t for t in (e.get("to") or []) if t and "@" in str(t) and not str(t).startswith("YOUR_")]
        pw = str(os.getenv("EMAIL_PASSWORD") or e.get("password") or "").replace(" ", "")
        return bool(e.get("enabled") and e.get("username") and pw and to and
                    not str(e.get("username")).startswith("YOUR_")), to, pw

    def _any_other(self):
        return bool((self.ntfy.get("enabled") and self.ntfy.get("topic")) or
                    self._discord_url() or self._email_ok()[0])

    def is_configured(self):
        token, _ = self._tg_params()
        ztoken, _ = self._zalo_params()
        return bool(token) or bool(ztoken) or bool(self._any_other())

    def send(self, text, image_jpg=None):
        try:
            self.q.put_nowait((text, image_jpg))
        except queue.Full:
            log.error("Hàng đợi thông báo đầy, bỏ qua một tin")

    def send_blocking(self, text, image_jpg=None):
        """Dùng cho test_notify.py - trả về True nếu có ít nhất một kênh gửi thành công."""
        return self._deliver(text, image_jpg)

    def _worker(self):
        while True:
            text, img = self.q.get()
            try:
                self._deliver(text, img)
            except Exception as e:  # không để thread chết
                log.exception("Lỗi gửi thông báo: %s", e)

    @staticmethod
    def _retry(fn, what, tries=4):
        for i in range(1, tries + 1):
            try:
                fn()
                log.info("Đã gửi qua %s", what)
                return True
            except Exception as e:
                log.warning("Gửi %s thất bại (lần %d/%d): %s", what, i, tries, e)
                time.sleep(2 * i)
        log.error("Không gửi được qua %s sau %d lần thử", what, tries)
        return False

    def _deliver(self, text, img):
        any_ok = False
        token, chat_ids = self._tg_params()
        if token:
            for cid in chat_ids:
                def _tg(cid=cid):
                    base = f"https://api.telegram.org/bot{token}"
                    if img is not None and self.tg.get("send_photo", True):
                        r = requests.post(f"{base}/sendPhoto",
                                          data={"chat_id": cid, "caption": text[:1000]},
                                          files={"photo": ("alert.jpg", img, "image/jpeg")}, timeout=30)
                    else:
                        r = requests.post(f"{base}/sendMessage",
                                          data={"chat_id": cid, "text": text}, timeout=30)
                    if r.status_code != 200:
                        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                any_ok |= self._retry(_tg, f"Telegram({cid})")

        ztoken, zids = self._zalo_params()
        if ztoken:
            # Zalo Bot API: sendPhoto chỉ nhận URL ảnh công khai nên ở đây gửi TEXT.
            for cid in zids:
                def _zalo(cid=cid):
                    r = requests.post(f"https://bot-api.zaloplatforms.com/bot{ztoken}/sendMessage",
                                      json={"chat_id": cid, "text": text[:2000]}, timeout=30)
                    try:
                        data = r.json()
                    except ValueError:
                        data = {}
                    if r.status_code != 200 or data.get("ok") is False:
                        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                any_ok |= self._retry(_zalo, f"Zalo({cid})")

        if self.ntfy.get("enabled") and self.ntfy.get("topic"):
            url = f"{self.ntfy.get('server', 'https://ntfy.sh').rstrip('/')}/{self.ntfy['topic']}"

            def _ntfy_text():
                r = requests.post(url, data=text.encode("utf-8"), timeout=20,
                                  headers={"Title": "FIRE ALERT", "Priority": "urgent",
                                           "Tags": "fire,rotating_light"})
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")

            def _ntfy_img():  # ntfy.sh: ảnh tối đa 15MB, lưu 3 giờ
                r = requests.put(url, data=img, timeout=60,
                                 headers={"Filename": "fire.jpg", "Title": "FIRE ALERT - anh hien truong",
                                          "Priority": "high", "Tags": "fire"})
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            ok = self._retry(_ntfy_text, "ntfy")
            if img is not None:
                ok |= self._retry(_ntfy_img, "ntfy(ảnh)")
            any_ok |= ok

        durl = self._discord_url()
        if durl:
            def _discord():
                if img is not None:
                    r = requests.post(durl, data={"content": text[:1900]},
                                      files={"file": ("fire.jpg", img, "image/jpeg")}, timeout=30)
                else:
                    r = requests.post(durl, json={"content": text[:1900]}, timeout=30)
                if r.status_code not in (200, 204):
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            any_ok |= self._retry(_discord, "Discord")

        em_ok, em_to, em_pw = self._email_ok()
        if em_ok:
            def _email():
                e = self.email
                msg = EmailMessage()
                msg["Subject"] = "🔥 CẢNH BÁO CHÁY - " + text.splitlines()[1] if len(text.splitlines()) > 1 \
                    else "🔥 CẢNH BÁO CHÁY"
                msg["From"] = e["username"]
                msg["To"] = ", ".join(em_to)
                msg["X-Priority"] = "1"
                msg.set_content(text)
                if img is not None:
                    msg.add_attachment(img, maintype="image", subtype="jpeg", filename="fire.jpg")
                host, port = e.get("smtp_host", "smtp.gmail.com"), int(e.get("smtp_port", 465))
                if port == 465:
                    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as sm:
                        sm.login(e["username"], em_pw)
                        sm.send_message(msg)
                else:
                    with smtplib.SMTP(host, port, timeout=30) as sm:
                        sm.starttls(context=ssl.create_default_context())
                        sm.login(e["username"], em_pw)
                        sm.send_message(msg)
            any_ok |= self._retry(_email, "Email")

        if not token and not ztoken and not self._any_other():
            log.error("CHƯA cấu hình kênh gửi tin (Telegram/Zalo/Discord/Email/ntfy) - không thể gửi: %s", text.splitlines()[0])
        return any_ok


# ----------------------------------------------------------------------------
# Logic quyết định báo động (chống báo giả + cooldown)
# ----------------------------------------------------------------------------
class AlertLogic:
    def __init__(self, window_seconds, min_hits, cooldown_seconds):
        self.window = window_seconds
        self.min_hits = min_hits
        self.cooldown = cooldown_seconds
        self.hits = deque()
        self.last_alert = 0.0

    def update(self, detected, now=None):
        """Trả về True nếu cần gửi cảnh báo ngay lúc này."""
        now = time.time() if now is None else now
        if detected:
            self.hits.append(now)
        while self.hits and now - self.hits[0] > self.window:
            self.hits.popleft()
        if len(self.hits) >= self.min_hits and now - self.last_alert >= self.cooldown:
            self.last_alert = now
            return True
        return False

    @property
    def hit_count(self):
        return len(self.hits)


# ----------------------------------------------------------------------------
# Detector
# ----------------------------------------------------------------------------
class Detector:
    def __init__(self, cfg):
        from ultralytics import YOLO  # import trễ để khởi động nhanh / dễ test
        mpath = Path(cfg["model"]["path"])
        if not mpath.is_absolute():
            mpath = BASE_DIR / mpath
        if not mpath.exists():
            sys.exit(f"[LỖI] Không tìm thấy model: {mpath}\n"
                     f"      Hãy chép best.pt vào thư mục models/ (hoặc sửa model.path trong config.yaml)")
        self.model = YOLO(str(mpath))
        self.names = {int(k): str(v).lower() for k, v in self.model.names.items()}
        log.info("Model đã nạp: %s | classes=%s", mpath.name, self.names)

        dev = str(cfg["model"].get("device", "auto"))
        if dev == "auto":
            try:
                import torch
                dev = "0" if torch.cuda.is_available() else "cpu"
            except Exception:
                dev = "cpu"
        self.device = dev
        self.half = bool(cfg["model"].get("half", True)) and dev != "cpu"
        self.imgsz = int(cfg["model"].get("imgsz", 640))
        d = cfg["detection"]
        self.thr = {"fire": d["fire_conf"], "smoke": d["smoke_conf"], "human": d["human_conf"]}
        self.min_conf = min(self.thr.values())
        self.draw_human = d.get("draw_human", True)
        log.info("Thiết bị chạy AI: %s (half=%s)", self.device, self.half)

    def detect(self, frame):
        """Trả về list[(tên_class, conf, (x1,y1,x2,y2))] đã lọc theo ngưỡng từng class."""
        res = self.model.predict(frame, imgsz=self.imgsz, conf=self.min_conf, device=self.device,
                                 half=self.half, verbose=False)[0]
        out = []
        if res.boxes is None or len(res.boxes) == 0:
            return out
        xyxy = res.boxes.xyxy.cpu().numpy()
        conf = res.boxes.conf.cpu().numpy()
        cls = res.boxes.cls.cpu().numpy().astype(int)
        for b, c, k in zip(xyxy, conf, cls):
            name = self.names.get(int(k), str(k))
            if name not in self.thr or c < self.thr[name]:
                continue
            if name == "human" and not self.draw_human:
                continue
            out.append((name, float(c), tuple(int(v) for v in b)))
        return out


def annotate(frame, dets, cam_name, status_text, alarm):
    img = frame.copy()
    for name, conf, (x1, y1, x2, y2) in dets:
        col = COLORS.get(name, (255, 255, 0))
        cv2.rectangle(img, (x1, y1), (x2, y2), col, 3 if name != "human" else 2)
        label = f"{name.upper()} {conf:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(img, (x1, max(0, y1 - th - 8)), (x1 + tw + 6, y1), col, -1)
        cv2.putText(img, label, (x1 + 3, max(th, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    bar_col = (0, 0, 200) if alarm else (40, 40, 40)
    cv2.rectangle(img, (0, 0), (img.shape[1], 30), bar_col, -1)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(img, f"{cam_name} | {stamp} | {status_text}", (8, 21),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def encode_jpg(img, quality=85, max_width=None):
    if max_width and img.shape[1] > max_width:
        s = max_width / img.shape[1]
        img = cv2.resize(img, (max_width, int(img.shape[0] * s)))
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else None


# ----------------------------------------------------------------------------
# Web dashboard (xem trực tiếp trong LAN)
# ----------------------------------------------------------------------------
class Shared:
    def __init__(self):
        self.jpg = None
        self.status = {"state": "Đang khởi động", "camera": False, "fps": 0.0,
                       "last_alert": None, "alerts_sent": 0}
        self.lock = threading.Lock()


PAGE = """<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Giám sát cháy</title>
<style>body{margin:0;background:#111;color:#eee;font-family:system-ui,sans-serif;text-align:center}
img{max-width:100%;height:auto;display:block;margin:0 auto}
#s{padding:10px;font-size:18px}.ok{color:#4caf50}.bad{color:#ff5252;font-weight:bold}</style></head>
<body><div id="s">...</div><img src="/video_feed">
<script>
async function u(){try{const r=await fetch('/status');const j=await r.json();
const e=document.getElementById('s');
e.innerHTML=(j.camera?'<span class=ok>● Camera OK</span>':'<span class=bad>● Mất camera</span>')+
' &nbsp;|&nbsp; '+j.state+' &nbsp;|&nbsp; '+j.fps.toFixed(1)+' fps &nbsp;|&nbsp; Đã gửi cảnh báo: '+j.alerts_sent+
(j.last_alert?' (gần nhất '+j.last_alert+')':'');}catch(e){}}
setInterval(u,2000);u();
</script></body></html>"""


def start_web(shared, host, port):
    from flask import Flask, Response, jsonify
    import logging as _l
    _l.getLogger("werkzeug").setLevel(_l.WARNING)
    app = Flask(__name__)

    @app.route("/")
    def index():
        return PAGE

    @app.route("/status")
    def status():
        with shared.lock:
            return jsonify(shared.status)

    @app.route("/video_feed")
    def video_feed():
        def gen():
            last = None
            while True:
                with shared.lock:
                    jpg = shared.jpg
                if jpg is not None and jpg is not last:
                    last = jpg
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                time.sleep(0.08)
        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

    threading.Thread(target=lambda: app.run(host=host, port=port, threaded=True, use_reloader=False),
                     daemon=True).start()
    log.info("Dashboard: http://<IP-máy-tính>:%s  (chỉ dùng trong mạng LAN)", port)


# ----------------------------------------------------------------------------
# Tiện ích
# ----------------------------------------------------------------------------
def save_snapshot(jpg, keep_last):
    d = BASE_DIR / "alerts"
    d.mkdir(exist_ok=True)
    p = d / f"fire_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    p.write_bytes(jpg)
    files = sorted(d.glob("fire_*.jpg"))
    for old in files[:-keep_last] if keep_last > 0 else []:
        try:
            old.unlink()
        except OSError:
            pass
    return p


def build_message(cam_name, dets_alert, hits, window):
    lines = [f"🔥🚨 CẢNH BÁO CHÁY! 🚨🔥", f"Vị trí: {cam_name}",
             f"Thời gian: {dt.datetime.now().strftime('%H:%M:%S %d/%m/%Y')}"]
    best = {}
    for n, c, _ in dets_alert:
        best[n] = max(best.get(n, 0), c)
    for n, c in best.items():
        lines.append(f"Phát hiện {VN_LABEL.get(n, n)} (độ tin cậy {c:.0%})")
    lines.append(f"Xác nhận: {hits} lần phát hiện trong {window}s gần nhất")
    lines.append("👉 Hãy kiểm tra ngay và gọi 114 nếu cần!")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Chương trình chính
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Hệ thống phát hiện cháy bằng YOLO")
    ap.add_argument("-c", "--config", default=str(BASE_DIR / "config.yaml"))
    ap.add_argument("--source", help="ghi đè camera.source (URL / số / file video)")
    ap.add_argument("--no-web", action="store_true", help="tắt dashboard")
    ap.add_argument("--show", action="store_true", help="hiện cửa sổ xem trực tiếp trên máy tính")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")
    cfg = load_config(args.config)
    if args.source is not None:
        cfg["camera"]["source"] = args.source
    cam_name = cfg["camera"]["name"]

    notifier = Notifier(cfg)
    if not notifier.is_configured():
        log.warning("⚠ CHƯA cấu hình Telegram/Zalo/Discord/Email/ntfy trong config.yaml - hệ thống vẫn chạy nhưng KHÔNG gửi được tin!")

    detector = Detector(cfg)
    cam = CameraReader(cfg["camera"]["source"], cfg["camera"]["reconnect_delay"],
                       cfg["camera"].get("loop_video", True))
    cam.start()

    a = cfg["alert"]
    logic = AlertLogic(a["window_seconds"], a["min_hits"], a["cooldown_seconds"])
    alert_classes = {str(c).lower() for c in cfg["detection"]["alert_classes"]}

    shared = Shared()
    if cfg["web"]["enabled"] and not args.no_web:
        start_web(shared, cfg["web"]["host"], cfg["web"]["port"])

    notifier.send(f"✅ Hệ thống phát hiện cháy đã khởi động.\nCamera: {cam_name}\n"
                  f"Giờ: {dt.datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")

    interval = 1.0 / max(0.5, float(cfg["model"]["process_fps"]))
    last_seq = -1
    last_proc = 0.0
    fps_t, fps_n, fps = time.time(), 0, 0.0
    offline_notified = False
    alerts_sent = 0
    last_alert_str = None
    log.info("Hệ thống đang chạy. Nhấn Ctrl+C để dừng.")

    try:
        while True:
            now = time.time()

            # Cảnh báo mất camera
            off_s = a.get("camera_offline_alert_seconds", 0)
            if off_s and not cam.connected and now - cam.last_ok > off_s and not offline_notified:
                notifier.send(f"⚠️ {cam_name} đã MẤT KẾT NỐI hơn {off_s} giây. Hãy kiểm tra điện thoại/camera.")
                offline_notified = True
            if cam.connected:
                offline_notified = False

            frame, seq = cam.get()
            if frame is None or seq == last_seq or now - last_proc < interval:
                time.sleep(0.005)
                continue
            last_seq, last_proc = seq, now

            dets = detector.detect(frame)
            dets_alert = [d for d in dets if d[0] in alert_classes]
            fire_now = len(dets_alert) > 0
            trigger = logic.update(fire_now, now)

            fps_n += 1
            if now - fps_t >= 2:
                fps, fps_t, fps_n = fps_n / (now - fps_t), now, 0

            alarm_active = logic.hit_count >= a["min_hits"]
            if alarm_active:
                state = "!!! PHAT HIEN CHAY !!!"
            elif fire_now:
                state = f"Nghi ngo ({logic.hit_count}/{a['min_hits']})"
            else:
                state = "Binh thuong"
            vis = annotate(frame, dets, cam_name, state, alarm_active)

            if trigger:
                jpg = encode_jpg(vis, 90, 1280)
                if a.get("save_snapshots", True) and jpg:
                    p = save_snapshot(jpg, a.get("keep_last_snapshots", 200))
                    log.warning("🔥 PHÁT HIỆN CHÁY! Đã lưu ảnh: %s", p.name)
                else:
                    log.warning("🔥 PHÁT HIỆN CHÁY!")
                notifier.send(build_message(cam_name, dets_alert, logic.hit_count, a["window_seconds"]), jpg)
                alerts_sent += 1
                last_alert_str = dt.datetime.now().strftime("%H:%M:%S %d/%m")

            if cfg["web"]["enabled"] and not args.no_web:
                jpg_web = encode_jpg(vis, 75, cfg["web"].get("max_width", 960))
                with shared.lock:
                    shared.jpg = jpg_web
                    shared.status.update(state=state, camera=cam.connected, fps=fps,
                                         last_alert=last_alert_str, alerts_sent=alerts_sent)

            if args.show:
                cv2.imshow("Fire Detection (q de thoat)", vis)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        cam.stop()
        cv2.destroyAllWindows()
        log.info("Đã dừng.")


if __name__ == "__main__":
    main()
