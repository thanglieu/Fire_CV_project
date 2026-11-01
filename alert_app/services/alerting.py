# alert_app/services/alerting.py
"""Xử lý khi có báo động: lưu ảnh, ghi DB, gửi email (chạy ở luồng riêng để không làm khựng video)."""
import logging
import threading
import time
import uuid
from pathlib import Path

import cv2
from django.conf import settings

log = logging.getLogger(__name__)


def handle_fire_alert(annotated_frame, max_conf):
    from ..models import AlertLog

    filename = f"fire_{int(time.time())}_{uuid.uuid4().hex[:8]}.jpg"
    media_root = Path(settings.MEDIA_ROOT)
    alerts_dir = media_root / "alerts"
    alerts_dir.mkdir(parents=True, exist_ok=True)
    image_path = alerts_dir / filename
    if not cv2.imwrite(str(image_path), annotated_frame):
        raise OSError(f"Không ghi được ảnh cảnh báo: {image_path}")

    try:
        AlertLog.objects.create(
            image_evidence=str(image_path.relative_to(media_root)),
            confidence=max_conf,
            status="Cảnh báo: Phát hiện lửa/khói!",
        )
    except Exception:
        image_path.unlink(missing_ok=True)
        raise

    log.warning("PHÁT HIỆN CHÁY (%.2f) - đã lưu %s", max_conf, filename)

    from .notifier import send_fire_alert_email

    threading.Thread(
        target=send_fire_alert_email,
        args=(str(image_path), max_conf),
        daemon=True,
    ).start()