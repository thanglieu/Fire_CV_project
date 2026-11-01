# alert_app/services/detector.py
import logging
import threading

import numpy as np
from django.conf import settings
from ultralytics import YOLO

log = logging.getLogger(__name__)


class FireDetector:
    _instance = None

    def __init__(self):
        model_path = str(settings.FIRE_MODEL_PATH)
        self.model = YOLO(model_path)
        self.names = {int(k): str(v).lower() for k, v in self.model.names.items()}
        configured_alerts = settings.FIRE_ALERT_LABELS
        self.alert_names = {n for n in self.names.values() if n in configured_alerts}
        if not self.alert_names:
            self.alert_names = set(self.names.values())
            log.warning(
                "Không class nào trong FIRE_ALERT_LABELS khớp model; "
                "mọi class đều được xem là cảnh báo: %s",
                sorted(self.alert_names),
            )

        try:
            import torch
            self.device = 0 if torch.cuda.is_available() else "cpu"
        except Exception:
            self.device = "cpu"
        self.half = self.device != "cpu"          # FP16 chỉ chạy trên GPU
        self._lock = threading.Lock()
        self.detect(
            np.zeros(
                (settings.FIRE_DETECTION_IMAGE_SIZE, settings.FIRE_DETECTION_IMAGE_SIZE, 3),
                np.uint8,
            )
        )

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def detect(self, frame):
        """Trả về list[(tên_class, độ_tin_cậy, (x1, y1, x2, y2))]. Không vẽ gì lên ảnh."""
        with self._lock:
            r = self.model.predict(
                frame,
                conf=settings.FIRE_DETECTION_CONFIDENCE,
                imgsz=settings.FIRE_DETECTION_IMAGE_SIZE,
                device=self.device,
                half=self.half,
                verbose=False,
            )[0]
        out = []
        if r.boxes is None or len(r.boxes) == 0:
            return out
        for b, c, k in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy(),
                           r.boxes.cls.cpu().numpy().astype(int)):
            out.append((self.names.get(int(k), str(k)), float(c), tuple(int(v) for v in b)))
        return out