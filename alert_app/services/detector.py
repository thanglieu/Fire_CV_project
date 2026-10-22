# alert_app/services/detector.py
import os
import threading

import numpy as np
from django.conf import settings
from ultralytics import YOLO


class FireDetector:
    _instance = None
    CONF = 0.5
    IMGSZ = 480                       # nhỏ hơn 640 => nhanh hơn ~1.7 lần; tăng lại 640 nếu bỏ sót lửa nhỏ
    ALERT_LABELS = {"fire", "smoke"}  # chỉ các class này mới gây báo động

    def __init__(self):
        model_path = os.path.join(settings.BASE_DIR, "model_ai", "best.pt")
        self.model = YOLO(model_path)
        self.names = {int(k): str(v).lower() for k, v in self.model.names.items()}
        # Nếu model đặt tên class khác (vd "Fire", "flame") thì không bỏ lỡ báo động: coi mọi class là báo động
        self.alert_names = {n for n in self.names.values() if n in self.ALERT_LABELS} or set(self.names.values())

        try:
            import torch
            self.device = 0 if torch.cuda.is_available() else "cpu"
        except Exception:
            self.device = "cpu"
        self.half = self.device != "cpu"          # FP16 chỉ chạy trên GPU
        self._lock = threading.Lock()
        self.detect(np.zeros((self.IMGSZ, self.IMGSZ, 3), np.uint8))   # chạy thử 1 lần cho "nóng máy"

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def detect(self, frame):
        """Trả về list[(tên_class, độ_tin_cậy, (x1, y1, x2, y2))]. Không vẽ gì lên ảnh."""
        with self._lock:
            r = self.model.predict(frame, conf=self.CONF, imgsz=self.IMGSZ, device=self.device,
                                   half=self.half, verbose=False)[0]
        out = []
        if r.boxes is None or len(r.boxes) == 0:
            return out
        for b, c, k in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy(),
                           r.boxes.cls.cpu().numpy().astype(int)):
            out.append((self.names.get(int(k), str(k)), float(c), tuple(int(v) for v in b)))
        return out