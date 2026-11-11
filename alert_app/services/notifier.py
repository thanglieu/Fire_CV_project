# alert_app/services/notifier.py
import logging
import os
import threading
import time

import requests
from django.conf import settings
from django.core.mail import EmailMessage

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def send_fire_alert_email(image_path, confidence):
    """
    Hàm gửi email cảnh báo kèm ảnh bằng chứng (kênh "email", giữ lại để dùng khi cần)
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


def send_fire_alert_telegram(image_path, confidence):
    """Gửi cảnh báo + ảnh hiện trường về điện thoại qua Telegram bot.

    Nếu image_path rỗng thì chỉ gửi tin nhắn chữ (dùng khi test).
    Nếu có PUBLIC_BASE_URL (địa chỉ ngrok), tin nhắn kèm link mở trang giám sát.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        raise RuntimeError(
            "Thiếu cấu hình Telegram. Hãy điền TELEGRAM_BOT_TOKEN và "
            "TELEGRAM_CHAT_ID trong file .env."
        )

    text = f"🔥 CẢNH BÁO: Phát hiện lửa/khói!\nĐộ tin cậy: {confidence:.2f}"
    if settings.PUBLIC_BASE_URL:
        text += f"\nXem trực tiếp: {settings.PUBLIC_BASE_URL}/"

    try:
        if image_path:
            with open(image_path, "rb") as photo:
                resp = requests.post(
                    f"{TELEGRAM_API}/bot{token}/sendPhoto",
                    data={"chat_id": chat_id, "caption": text},
                    files={"photo": photo},
                    timeout=settings.TELEGRAM_TIMEOUT,
                )
        else:
            resp = requests.post(
                f"{TELEGRAM_API}/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": text},
                timeout=settings.TELEGRAM_TIMEOUT,
            )
    except requests.RequestException as exc:
        # Thông báo lỗi gốc của requests chứa URL có token, nên không ghi nguyên văn.
        raise RuntimeError(f"Không kết nối được Telegram ({type(exc).__name__}).") from None

    if resp.status_code != 200:
        try:
            reason = resp.json().get("description", resp.text[:200])
        except ValueError:
            reason = resp.text[:200]
        raise RuntimeError(f"Telegram từ chối (HTTP {resp.status_code}): {reason}")
    log.info("Đã gửi cảnh báo Telegram tới chat %s", chat_id)


def send_fire_alert_ntfy(image_path, confidence):
    """Gửi cảnh báo mức ưu tiên cao nhất qua ntfy: app ntfy trên Android sẽ hú chuông liên tục tới khi bạn tắt."""
    if not settings.NTFY_TOPIC:
        raise RuntimeError("Thiếu NTFY_TOPIC trong file .env.")
    payload = {
        "topic": settings.NTFY_TOPIC,
        "title": "🔥 CẢNH BÁO CHÁY",
        "message": f"Phát hiện lửa/khói (độ tin cậy {confidence:.0%}). Bấm để xem hiện trường.",
        "priority": 5,                                   # 5 = max/urgent
        "tags": ["fire", "rotating_light"],
    }
    if settings.PUBLIC_BASE_URL:
        payload["click"] = settings.PUBLIC_BASE_URL + "/?ack=1"
    headers = {"Authorization": f"Bearer {settings.NTFY_TOKEN}"} if settings.NTFY_TOKEN else {}
    try:
        resp = requests.post(settings.NTFY_SERVER, json=payload, headers=headers, timeout=settings.TELEGRAM_TIMEOUT)
    except requests.RequestException as exc:
        raise RuntimeError(f"Không kết nối được ntfy ({type(exc).__name__}).") from None
    if resp.status_code != 200:
        raise RuntimeError(f"ntfy từ chối (HTTP {resp.status_code}): {resp.text[:200]}")
    log.info("Đã gửi cảnh báo ntfy tới topic %s", settings.NTFY_TOPIC)


PUSHOVER_API = "https://api.pushover.net/1"
_pushover_receipt = ""


def _cancel_pushover():
    """Hủy đợt báo khẩn cấp còn đang lặp (khi người dùng đã xác nhận trên trang giám sát)."""
    global _pushover_receipt
    receipt, _pushover_receipt = _pushover_receipt, ""
    if not receipt or not settings.PUSHOVER_APP_TOKEN:
        return
    try:
        requests.post(f"{PUSHOVER_API}/receipts/{receipt}/cancel.json",
                      data={"token": settings.PUSHOVER_APP_TOKEN}, timeout=10)
    except requests.RequestException:
        log.warning("Không hủy được cảnh báo Pushover đang lặp.")


def send_fire_alert_pushover(image_path, confidence):
    """Pushover ưu tiên khẩn cấp (priority 2): điện thoại báo lặp lại tới khi bạn bấm Acknowledge."""
    global _pushover_receipt
    if not settings.PUSHOVER_APP_TOKEN or not settings.PUSHOVER_USER_KEY:
        raise RuntimeError("Thiếu PUSHOVER_APP_TOKEN / PUSHOVER_USER_KEY trong file .env.")
    _cancel_pushover()                                   # có đợt cũ chưa xác nhận thì thay bằng đợt mới
    data = {
        "token": settings.PUSHOVER_APP_TOKEN,
        "user": settings.PUSHOVER_USER_KEY,
        "title": "🔥 CẢNH BÁO CHÁY",
        "message": f"Phát hiện lửa/khói (độ tin cậy {confidence:.0%}).",
        "priority": 2,
        "retry": settings.PUSHOVER_RETRY_SECONDS,
        "expire": settings.PUSHOVER_EXPIRE_SECONDS,
        "sound": "siren",
    }
    if settings.PUBLIC_BASE_URL:
        data["url"] = settings.PUBLIC_BASE_URL + "/?ack=1"
        data["url_title"] = "Xem hiện trường"
    try:
        if image_path:
            with open(image_path, "rb") as photo:
                resp = requests.post(f"{PUSHOVER_API}/messages.json", data=data,
                                     files={"attachment": ("fire.jpg", photo, "image/jpeg")},
                                     timeout=settings.TELEGRAM_TIMEOUT)
        else:
            resp = requests.post(f"{PUSHOVER_API}/messages.json", data=data, timeout=settings.TELEGRAM_TIMEOUT)
    except requests.RequestException as exc:
        raise RuntimeError(f"Không kết nối được Pushover ({type(exc).__name__}).") from None
    if resp.status_code != 200:
        raise RuntimeError(f"Pushover từ chối (HTTP {resp.status_code}): {resp.text[:200]}")
    _pushover_receipt = resp.json().get("receipt", "")
    log.info("Đã gửi cảnh báo Pushover khẩn cấp")


def send_fire_alert_webpush(image_path, confidence):
    """Đẩy thông báo tới các điện thoại đã bật thông báo từ trang giám sát (Web Push)."""
    from .push import send_push_to_all

    sent, total = send_push_to_all(
        "🔥 CẢNH BÁO CHÁY",
        f"Phát hiện lửa/khói (độ tin cậy {confidence:.0%}). Bấm để xem hiện trường.",
        url="/?ack=1",                 # bấm vào thông báo = đã xem -> trang tự xác nhận
        tag="fire-alert",
    )
    if total == 0:
        log.warning("Chưa có thiết bị nào đăng ký nhận thông báo (mở trang giám sát và bấm Bật thông báo).")
    elif sent == 0:
        raise RuntimeError(f"Không gửi được Web Push tới thiết bị nào (0/{total}).")
    else:
        log.info("Đã gửi Web Push tới %d/%d thiết bị", sent, total)


# ---- Nhắc lặp cho tới khi người dùng xác nhận đã xem ----
_alarm_lock = threading.Lock()
_alarm_ack = threading.Event()
_alarm_active = False


def alarm_active():
    return _alarm_active


def acknowledge_alarm():
    """Người dùng đã xem cảnh báo -> dừng gửi lặp."""
    global _alarm_active
    _alarm_active = False
    _alarm_ack.set()
    threading.Thread(target=_cancel_pushover, daemon=True).start()     # dừng luôn chuông Pushover (nếu có)


def _alarm_loop():
    """Gửi lại Web Push mỗi ALARM_REPEAT_SECONDS giây tới khi được xác nhận hoặc hết ALARM_MAX_MINUTES."""
    global _alarm_active
    from .push import send_push_to_all

    deadline = time.time() + settings.ALARM_MAX_MINUTES * 60
    count = 1
    while not _alarm_ack.wait(settings.ALARM_REPEAT_SECONDS):      # wait() trả True khi đã xác nhận
        if time.time() >= deadline:
            log.warning("Hết %s phút mà chưa ai xác nhận, ngừng nhắc lặp.", settings.ALARM_MAX_MINUTES)
            break
        count += 1
        try:
            send_push_to_all(
                "🔥 CẢNH BÁO CHÁY – CHƯA XEM",
                f"Nhắc lần {count}: bấm vào đây để xem hiện trường và tắt chuông.",
                url="/?ack=1", tag="fire-alert",
                ttl=60, topic="fire-alert",       # máy mất mạng thì chỉ nhận tin mới nhất, không dồn hàng chục tin
            )
        except Exception:
            log.exception("Nhắc lặp Web Push lỗi.")
    _alarm_active = False


def start_alarm_loop():
    global _alarm_active
    with _alarm_lock:
        if _alarm_active:
            return                                  # đang nhắc rồi, không mở thêm luồng
        _alarm_active = True
        _alarm_ack.clear()
    threading.Thread(target=_alarm_loop, daemon=True).start()


def _play_alarm_sound():
    try:
        from playsound import playsound

        sound_path = os.path.join(settings.BASE_DIR, 'sounds', 'alarm.mp3')
        if os.path.exists(sound_path):
            playsound(sound_path)
    except ImportError:
        log.info("Bỏ qua âm thanh cảnh báo vì chưa cài playsound.")
    except Exception:
        log.exception("Không phát được âm thanh cảnh báo.")


def send_fire_alert(image_path, confidence):
    """Gửi cảnh báo qua các kênh trong ALERT_CHANNELS (webpush, telegram, email), rồi phát còi.

    Lỗi của một kênh không chặn kênh còn lại.
    """
    channels = settings.ALERT_CHANNELS
    if not channels:
        log.warning("ALERT_CHANNELS đang rỗng, không có kênh nào để gửi cảnh báo.")

    if "telegram" in channels:
        try:
            send_fire_alert_telegram(image_path, confidence)
        except Exception:
            log.exception("Không gửi được cảnh báo Telegram.")
    if "pushover" in channels:
        try:
            send_fire_alert_pushover(image_path, confidence)
        except Exception:
            log.exception("Không gửi được cảnh báo Pushover.")
    if "ntfy" in channels:
        try:
            send_fire_alert_ntfy(image_path, confidence)
        except Exception:
            log.exception("Không gửi được cảnh báo ntfy.")
    if "webpush" in channels:
        try:
            send_fire_alert_webpush(image_path, confidence)
        except Exception:
            log.exception("Không gửi được cảnh báo Web Push.")
        start_alarm_loop()
    if "email" in channels:
        try:
            send_fire_alert_email(image_path, confidence)
        except Exception:
            pass                       # send_fire_alert_email đã ghi log lỗi
    _play_alarm_sound()
