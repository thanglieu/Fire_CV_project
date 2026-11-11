# alert_app/services/push.py
"""Gửi Web Push tới các thiết bị đã đăng ký (điện thoại đã bật thông báo từ trang giám sát)."""
import json
import logging

from django.conf import settings
from django.templatetags.static import static
from pywebpush import WebPushException, webpush

log = logging.getLogger(__name__)


def push_configured():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def send_push_to_all(title, body, url="/", tag="fire-alert", ttl=None, topic=None):
    """Gửi tới mọi thiết bị đã đăng ký. Trả về (số_gửi_thành_công, tổng_số_thiết_bị)."""
    from ..models import PushSubscription

    if not push_configured():
        raise RuntimeError(
            "Thiếu khóa VAPID. Chạy `python manage.py generate_vapid_keys` rồi điền "
            "VAPID_PUBLIC_KEY và VAPID_PRIVATE_KEY vào file .env."
        )

    payload = json.dumps(
        {"title": title, "body": body, "url": url, "tag": tag, "icon": static("alert_app/icon-192.png")},
        ensure_ascii=False,
    )
    subs = list(PushSubscription.objects.all())
    sent = 0
    for sub in subs:
        try:
            webpush(
                subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},   # pywebpush sửa dict này nên tạo mới mỗi lần
                ttl=settings.WEBPUSH_TTL if ttl is None else ttl,
                headers={"Urgency": "high", **({"Topic": topic} if topic else {})},   # Urgency: đánh thức máy; Topic: tin mới thay tin cũ chưa nhận
                timeout=10,
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):                             # thiết bị đã hủy đăng ký/gỡ app
                sub.delete()
                log.info("Đã xóa thiết bị hết hạn #%s (HTTP %s)", sub.pk, status)
            else:
                log.warning("Push tới thiết bị #%s lỗi (HTTP %s): %s", sub.pk, status, type(exc).__name__)
        except Exception:
            log.exception("Push tới thiết bị #%s lỗi.", sub.pk)
    return sent, len(subs)
