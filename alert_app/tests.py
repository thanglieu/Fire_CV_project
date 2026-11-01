import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from django.core import mail
from django.test import TestCase, override_settings

from .models import AlertLog
from .services.alerting import handle_fire_alert
from .services.notifier import send_fire_alert_email


class AlertEmailTests(TestCase):
    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        EMAIL_HOST_PASSWORD='test-app-password',
        ALERT_EMAIL_SENDER='sender@example.com',
        ALERT_EMAIL_RECEIVER='receiver@example.com',
    )
    def test_sends_email_with_evidence_attachment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / 'fire.jpg'
            image_path.write_bytes(b'test image')

            send_fire_alert_email(str(image_path), 0.91)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['receiver@example.com'])
        self.assertEqual(len(mail.outbox[0].attachments), 1)

    @override_settings(
        EMAIL_HOST_PASSWORD='',
        ALERT_EMAIL_SENDER='',
        ALERT_EMAIL_RECEIVER='',
    )
    def test_missing_email_configuration_raises_an_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / 'fire.jpg'
            image_path.write_bytes(b'test image')

            with self.assertRaisesRegex(RuntimeError, 'Thiếu cấu hình email'):
                send_fire_alert_email(str(image_path), 0.91)


class AlertPersistenceTests(TestCase):
    def test_fire_alert_saves_image_and_database_record(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                with patch('alert_app.services.alerting.threading.Thread') as thread:
                    handle_fire_alert(np.zeros((20, 20, 3), dtype=np.uint8), 0.91)

                alert = AlertLog.objects.get()
                self.assertEqual(alert.confidence, 0.91)
                self.assertTrue(Path(alert.image_evidence.path).is_file())
                thread.assert_called_once()
