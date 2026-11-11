# alert_app/services/detector.py
import logging
import threading

import numpy as np
from django.conf import settings
from ultralytics import YOLO

log = logging.getLogger(__name__)


class _YoloModel:
    """Bọc 1 model YOLO: chỉ giữ các class cần dùng, có thể đổi tên class đầu ra."""

    def __init__(self, path, labels, conf, imgsz, device, half, rename=None):
        self.model = YOLO(str(path))
        self.names = {int(k): str(v).lower() for k, v in self.model.names.items()}
        self.class_ids = sorted(i for i, n in self.names.items() if n in labels)
        if not self.class_ids:
            self.class_ids = sorted(self.names)
            log.warning(
                "Model %s không có class nào khớp %s; dùng tất cả class: %s",
                path, sorted(labels), sorted(self.names.values()),
            )
        self.conf, self.imgsz = conf, imgsz
        self.device, self.half = device, half
        self.rename = rename or {}
        self._lock = threading.Lock()

    @property
    def used_names(self):
        return {self.names[i] for i in self.class_ids}

    def detect(self, frame):
        with self._lock:
            r = self.model.predict(
                frame,
                conf=self.conf,
                imgsz=self.imgsz,
                classes=self.class_ids,          # bỏ qua các class không dùng
                device=self.device,
                half=self.half,
                verbose=False,
            )[0]
        out = []
        if r.boxes is None or len(r.boxes) == 0:
            return out
        for b, c, k in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy(),
                           r.boxes.cls.cpu().numpy().astype(int)):
            name = self.names.get(int(k), str(k))
            name = self.rename.get(name, name)
            out.append((name, float(c), tuple(int(v) for v in b)))
        return out


class FireDetector:
    """Model 1: lửa + khói (FIRE_MODEL_PATH). Model 2: người (PERSON_MODEL_PATH)."""
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        try:
            import torch
            device = 0 if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"
        half = device != "cpu"                    # FP16 chỉ chạy trên GPU

        self.fire_model = _YoloModel(
            settings.FIRE_MODEL_PATH, settings.FIRE_ALERT_LABELS,
            settings.FIRE_DETECTION_CONFIDENCE, settings.FIRE_DETECTION_IMAGE_SIZE,
            device, half,
        )
        self.alert_names = self.fire_model.used_names   # chỉ lửa/khói mới gây báo động

        self.person_model = None
        if settings.PERSON_MODEL_PATH:
            self.person_model = _YoloModel(
                settings.PERSON_MODEL_PATH, settings.PERSON_LABELS,
                settings.PERSON_DETECTION_CONFIDENCE, settings.PERSON_DETECTION_IMAGE_SIZE,
                device, half,
                rename={label: "human" for label in settings.PERSON_LABELS},  # để khớp màu/legend
            )

        size = settings.FIRE_DETECTION_IMAGE_SIZE
        self.detect(np.zeros((size, size, 3), np.uint8))   # chạy thử để nạp model

    @classmethod
    def get_instance(cls):
        with cls._lock:                       # luồng AI và request tải ảnh có thể gọi cùng lúc
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def detect(self, frame):
        """Trả về list[(tên_class, độ_tin_cậy, (x1, y1, x2, y2))]. Không vẽ gì lên ảnh."""
        out = self.fire_model.detect(frame)
        if self.person_model is not None:
            out += self.person_model.detect(frame)
        return out