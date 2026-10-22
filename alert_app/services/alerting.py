# alert_app/services/alerting.py
"""Xử lý khi có báo động: lưu ảnh, ghi DB, gửi email (chạy ở luồng riêng để không làm khựng video)."""
import logging
import os
import threading
import time

import cv2
from django.conf import settings

log = logging.getLogger(__name__)


def handle_fire_alert(annotated_frame, max_conf):
    from ..models import AlertLog
    from .notifier import send_fire_alert_email

    filename = f"fire_{int(time.time())}.jpg"
    alerts_dir = os.path.join(settings.MEDIA_ROOT, "alerts")
    os.makedirs(alerts_dir, exist_ok=True)
    image_path = os.path.join(alerts_dir, filename)
    cv2.imwrite(image_path, annotated_frame)

    AlertLog.objects.create(image_evidence=f"alerts/{filename}", confidence=max_conf,
                            status="Cảnh báo: Phát hiện lửa/khói!")
    log.warning("PHÁT HIỆN CHÁY (%.2f) - đã lưu %s", max_conf, filename)

    threading.Thread(target=send_fire_alert_email, args=(image_path, max_conf), daemon=True).start()