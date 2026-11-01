from django.core.management.base import BaseCommand, CommandError

from alert_app.models import AlertLog
from alert_app.services.notifier import send_fire_alert_email


class Command(BaseCommand):
    help = "Send the latest saved fire alert to verify the Gmail SMTP configuration."

    def handle(self, *args, **options):
        alert = AlertLog.objects.order_by("-timestamp").first()
        if alert is None:
            raise CommandError(
                "No saved alert image found. Trigger a fire alert before testing email."
            )

        try:
            send_fire_alert_email(alert.image_evidence.path, alert.confidence)
        except Exception as exc:
            raise CommandError(f"Email test failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("Test alert email sent successfully."))
