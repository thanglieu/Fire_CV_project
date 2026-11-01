# alert_app/services/notifier.py
import logging
import os

from django.conf import settings
from django.core.mail import EmailMessage

log = logging.getLogger(__name__)


def send_fire_alert_email(image_path, confidence):
    """
    Hàm gửi email cảnh báo kèm ảnh bằng chứng
    """
    try:
        sender_email = settings.ALERT_EMAIL_SENDER
        receiver_email = settings.ALERT_EMAIL_RECEIVER
        if not sender_email or not settings.EMAIL_HOST_PASSWORD or not receiver_email:
            raise RuntimeError(
                "Thiếu cấu hình email. Hãy điền ALERT_EMAIL_SENDER, "
                "ALERT_EMAIL_PASSWORD và ALERT_EMAIL_RECEIVER trong file .env."
            )

        message = EmailMessage(
            subject="CẢNH BÁO: Phát hiện lửa/khói",
            body=(
                "Hệ thống giám sát đã phát hiện sự cố cháy!\n"
                f"Độ tin cậy: {confidence:.2f}\n"
                "Hình ảnh hiện trường được đính kèm."
            ),
            from_email=sender_email,
            to=[receiver_email],
        )
        message.attach_file(image_path, mimetype="image/jpeg")
        if message.send(fail_silently=False) != 1:
            raise RuntimeError("SMTP không xác nhận đã gửi email cảnh báo.")
        log.info("Đã gửi email cảnh báo tới %s", receiver_email)
    except Exception:
        log.exception("Không gửi được email cảnh báo.")
        raise

    try:
        from playsound import playsound

        sound_path = os.path.join(settings.BASE_DIR, 'sounds', 'alarm.mp3')
        if os.path.exists(sound_path):
            playsound(sound_path)
    except ImportError:
        log.info("Bỏ qua âm thanh cảnh báo vì chưa cài playsound.")
    except Exception:
        log.exception("Không phát được âm thanh cảnh báo.")