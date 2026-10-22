# apps.py
import os
import sys
import threading

from django.apps import AppConfig


class AlertAppConfig(AppConfig):
    name = 'alert_app'

    def ready(self):
        # Chạy camera + YOLO ngay khi bật server (không cần chờ ai mở trang web).
        # runserver tự reload sinh 2 tiến trình -> chỉ tiến trình con (RUN_MAIN=true) mới khởi động.
        if 'runserver' not in sys.argv:
            return
        if os.environ.get('RUN_MAIN') != 'true' and '--noreload' not in sys.argv:
            return
        from .services.camera_stream import CameraStream
        threading.Thread(target=CameraStream.get_instance, daemon=True).start()