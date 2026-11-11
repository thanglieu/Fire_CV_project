import base64
import ipaddress
import json
import threading
import uuid
from pathlib import Path
from urllib.parse import urlparse

import cv2
import numpy as np
from django.conf import settings
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .models import AlertLog, PushSubscription
from .services.alerting import handle_fire_alert
from .services.camera_stream import CameraStream
from .services.detector import FireDetector
from .services.notifier import acknowledge_alarm, alarm_active
from .services.push import push_configured, send_push_to_all

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
_last_upload = None          # video tải lên gần nhất (để dọn khi đổi nguồn)


def video_feed(request):
    stream = CameraStream.get_instance()
    resp = StreamingHttpResponse(stream.frames(), content_type="multipart/x-mixed-replace; boundary=frame")
    resp["Cache-Control"] = "no-store"
    return resp


def stream_status(request):
    data = CameraStream.get_instance().status()
    data["alarm_active"] = alarm_active()          # còn đang nhắc lặp, chưa ai xác nhận
    return JsonResponse(data)


@require_POST
def ai_toggle(request):
    """Bật/tắt AI: enabled=1 bật, enabled=0 tắt."""
    stream = CameraStream.get_instance()
    stream.set_ai(request.POST.get("enabled") == "1")
    return JsonResponse({"ok": True, "ai_enabled": stream.ai_enabled})


@require_POST
def alarm_ack(request):
    acknowledge_alarm()
    return JsonResponse({"ok": True})


def index(request):
    today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return render(request, "alert_app/index.html", {
        "recent_alerts": AlertLog.objects.order_by("-timestamp")[:8],
        "total_alerts": AlertLog.objects.count(),
        "today_alerts": AlertLog.objects.filter(timestamp__gte=today).count(),
    })


@require_POST
def delete_alert(request, pk):
    alert = get_object_or_404(AlertLog, pk=pk)
    storage, name = alert.image_evidence.storage, alert.image_evidence.name
    alert.delete()
    if name:
        try:
            storage.delete(name)          # xóa luôn file ảnh trong media/alerts
        except OSError:
            pass
    return JsonResponse({"ok": True})


def _droidcam_url(text):
    """'192.168.1.5' | '192.168.1.5:4747' | 'http://192.168.1.5:4747/video' -> URL đầy đủ.
    Chỉ nhận địa chỉ trong mạng LAN để server không bị lợi dụng gọi ra Internet."""
    text = (text or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text
    p = urlparse(text)
    host = (p.hostname or "").lower()
    try:
        ip = ipaddress.ip_address(host)
        ok = ip.is_private or ip.is_loopback
    except ValueError:
        ok = host == "localhost" or host.endswith(".local")
    if not host or not ok:
        raise ValueError("Chỉ nhận địa chỉ trong mạng LAN, ví dụ 192.168.1.5 hoặc 192.168.1.5:4747")
    path = p.path if p.path not in ("", "/") else "/video"
    return f"http://{'[' + host + ']' if ':' in host else host}:{p.port or 4747}{path}"


def _unlink(path):
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:                       # Windows: file còn đang được OpenCV mở
        pass


@require_POST
def set_source(request):
    """Đổi nguồn của luồng trực tiếp: mode=camera (DroidCam) hoặc mode=video (kèm file)."""
    global _last_upload
    mode = request.POST.get("mode")
    stream = CameraStream.get_instance()
    new_upload = None

    if mode == "camera":
        try:
            url = _droidcam_url(request.POST.get("ip"))
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        stream.set_source(url or stream.camera_url or settings.DROIDCAM_URL, "camera")
    elif mode == "video":
        f = request.FILES.get("file")
        if f is None:
            return JsonResponse({"ok": False, "error": "Chưa chọn file video"}, status=400)
        ext = Path(f.name).suffix.lower()
        if ext not in VIDEO_EXTS:
            return JsonResponse({"ok": False, "error": "Định dạng video không hỗ trợ"}, status=400)
        folder = Path(settings.MEDIA_ROOT) / "uploads"
        folder.mkdir(parents=True, exist_ok=True)
        new_upload = folder / f"video_{uuid.uuid4().hex[:8]}{ext}"
        with open(new_upload, "wb") as out:
            for chunk in f.chunks():
                out.write(chunk)
        stream.set_source(str(new_upload), "video")
    else:
        return JsonResponse({"ok": False, "error": "Chế độ không hợp lệ"}, status=400)

    if _last_upload and _last_upload != new_upload:       # dọn video cũ sau vài giây
        threading.Timer(3.0, _unlink, args=[_last_upload]).start()
    _last_upload = new_upload
    return JsonResponse({"ok": True, "mode": stream.kind})


@require_POST
def analyze_image(request):
    """Nhận 1 ảnh, chạy 2 model, trả về ảnh đã vẽ khung (base64). Có lửa/khói thì lưu cảnh báo."""
    f = request.FILES.get("file")
    if f is None:
        return JsonResponse({"ok": False, "error": "Chưa chọn ảnh"}, status=400)
    img = cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return JsonResponse({"ok": False, "error": "Không đọc được ảnh"}, status=400)
    if img.shape[1] > 1600:                               # ảnh quá lớn thì thu nhỏ cho nhẹ
        scale = 1600 / img.shape[1]
        img = cv2.resize(img, (1600, int(img.shape[0] * scale)), interpolation=cv2.INTER_AREA)

    detector = FireDetector.get_instance()
    dets = detector.detect(img)
    annotated = CameraStream._draw(img.copy(), dets)
    alarm = [d for d in dets if d[0] in detector.alert_names]
    if alarm:
        handle_fire_alert(annotated, max(d[1] for d in alarm))    # lưu ảnh + DB + gửi email

    ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return JsonResponse({
        "ok": True,
        "image": "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode(),
        "detected": sorted({d[0] for d in dets}),
        "fire": bool(alarm),
    })


# ===================== PWA + Web Push =====================
PWA_DIR = Path(__file__).resolve().parent / "pwa"


def service_worker(request):
    """Phục vụ sw.js ở thư mục gốc (/sw.js) để service worker có phạm vi toàn site."""
    resp = HttpResponse((PWA_DIR / "sw.js").read_text(encoding="utf-8"),
                        content_type="application/javascript; charset=utf-8")
    resp["Cache-Control"] = "no-cache"
    return resp


def manifest(request):
    icons = [{"src": static("alert_app/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
             {"src": static("alert_app/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"}]
    return JsonResponse({
        "name": "FireGuard – Giám sát cháy",
        "short_name": "FireGuard",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#0b0f17",
        "theme_color": "#0b0f17",
        "lang": "vi",
        "icons": icons,
    }, content_type="application/manifest+json")


@ensure_csrf_cookie
def push_public_key(request):
    return JsonResponse({"key": settings.VAPID_PUBLIC_KEY, "configured": push_configured()})


def _valid_push_endpoint(url):
    """Chỉ nhận địa chỉ https của dịch vụ push; chặn localhost/IP nội bộ để server không bị lợi dụng gọi vào mạng LAN."""
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if p.scheme != "https" or not host or host == "localhost" or host.endswith(".local"):
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        return True


@require_POST
def push_subscribe(request):
    try:
        data = json.loads(request.body)
        endpoint, p256dh, auth = data["endpoint"], data["keys"]["p256dh"], data["keys"]["auth"]
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"ok": False, "error": "Dữ liệu đăng ký không hợp lệ"}, status=400)
    if not all(isinstance(v, str) and v for v in (endpoint, p256dh, auth)) or not _valid_push_endpoint(endpoint):
        return JsonResponse({"ok": False, "error": "Địa chỉ đăng ký không hợp lệ"}, status=400)
    PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={"p256dh": p256dh, "auth": auth, "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300]},
    )
    return JsonResponse({"ok": True, "devices": PushSubscription.objects.count()})


@require_POST
def push_unsubscribe(request):
    try:
        endpoint = json.loads(request.body)["endpoint"]
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"ok": False, "error": "Dữ liệu không hợp lệ"}, status=400)
    PushSubscription.objects.filter(endpoint=endpoint).delete()
    return JsonResponse({"ok": True})


@require_POST
def push_test(request):
    try:
        sent, total = send_push_to_all("🔔 Thử thông báo", "Nếu thấy dòng này, điện thoại đã nhận được thông báo.",
                                       url="/", tag="push-test")
    except RuntimeError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return JsonResponse({"ok": sent > 0, "sent": sent, "total": total})
