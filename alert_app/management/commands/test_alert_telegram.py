from django.core.management.base import BaseCommand, CommandError

from alert_app.models import AlertLog
from alert_app.services.notifier import send_fire_alert_telegram


class Command(BaseCommand):
    help = "Gửi thử cảnh báo mới nhất (hoặc tin nhắn chữ nếu chưa có) qua Telegram để kiểm tra cấu hình."

    def handle(self, *args, **options):
        alert = AlertLog.objects.order_by("-timestamp").first()
        path = alert.image_evidence.path if alert else None
        conf = alert.confidence if alert else 0.99
        try:
            send_fire_alert_telegram(path, conf)
        except Exception as exc:
            raise CommandError(f"Gửi Telegram thất bại: {exc}") from exc
        self.stdout.write(self.style.SUCCESS("Đã gửi thử cảnh báo Telegram, hãy kiểm tra điện thoại."))
