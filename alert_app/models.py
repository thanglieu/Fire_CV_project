from django.db import models

class AlertLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian phát hiện")
    image_evidence = models.ImageField(upload_to='alerts/', verbose_name="Ảnh bằng chứng")
    confidence = models.FloatField(verbose_name="Độ tin cậy")
    status = models.CharField(max_length=50, default="Phát hiện lửa/khói", verbose_name="Trạng thái")

    def __str__(self):
        return f"Cảnh báo lúc {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - Độ tin cậy: {self.confidence:.2f}"

    class Meta:
        verbose_name = "Lịch sử cảnh báo"
        verbose_name_plural = "Danh sách lịch sử cảnh báo"


class PushSubscription(models.Model):
    """Một thiết bị (trình duyệt/PWA) đã đăng ký nhận Web Push."""
    endpoint = models.TextField(unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    user_agent = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Thiết bị #{self.pk} ({self.user_agent[:40]})"
