# alert_app/middleware.py
import base64
import hmac

from django.conf import settings
from django.http import HttpResponse


PUBLIC_PATHS = {"/sw.js", "/manifest.webmanifest"}   # không chứa dữ liệu nhạy cảm; trình duyệt tải không kèm mật khẩu


class DashboardBasicAuthMiddleware:
    """Yêu cầu tài khoản/mật khẩu (HTTP Basic) khi truy cập qua ngrok.

    - Chỉ bật khi DASHBOARD_USER và DASHBOARD_PASSWORD đều được đặt trong .env.
    - Ngoại lệ không cần mật khẩu: /sw.js, /manifest.webmanifest và /static/ (icon, file tĩnh).
    - Truy cập trực tiếp từ chính máy chạy server (127.0.0.1, không qua ngrok) thì không hỏi.
      Yêu cầu qua ngrok luôn có header X-Forwarded-For nên vẫn bị hỏi mật khẩu.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(settings, "DASHBOARD_USER", "")
        password = getattr(settings, "DASHBOARD_PASSWORD", "")
        if (user and password and not self._is_public(request) and not self._is_local(request)
                and not self._ok(request, user, password)):
            resp = HttpResponse("Cần đăng nhập.", status=401, content_type="text/plain; charset=utf-8")
            resp["WWW-Authenticate"] = 'Basic realm="Fire CV", charset="UTF-8"'
            return resp
        return self.get_response(request)

    @staticmethod
    def _is_public(request):
        static_prefix = "/" + settings.STATIC_URL.lstrip("/")
        return request.path in PUBLIC_PATHS or request.path.startswith(static_prefix)

    @staticmethod
    def _is_local(request):
        return (
            request.META.get("REMOTE_ADDR") in ("127.0.0.1", "::1")
            and "HTTP_X_FORWARDED_FOR" not in request.META
        )

    @staticmethod
    def _ok(request, user, password):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header.lower().startswith("basic "):
            return False
        try:
            got_user, _, got_pass = base64.b64decode(header[6:]).decode("utf-8").partition(":")
        except (ValueError, UnicodeDecodeError):
            return False
        # so sánh thời gian không đổi để tránh dò mật khẩu
        return hmac.compare_digest(got_user.encode(), user.encode()) & hmac.compare_digest(
            got_pass.encode(), password.encode()
        )
