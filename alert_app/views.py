from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone

from .models import AlertLog
from .services.camera_stream import CameraStream


def video_feed(request):
    stream = CameraStream.get_instance()
    resp = StreamingHttpResponse(stream.frames(), content_type="multipart/x-mixed-replace; boundary=frame")
    resp["Cache-Control"] = "no-store"
    return resp


def stream_status(request):
    return JsonResponse(CameraStream.get_instance().status())


def index(request):
    today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return render(request, "alert_app/index.html", {
        "recent_alerts": AlertLog.objects.order_by("-timestamp")[:8],
        "total_alerts": AlertLog.objects.count(),
        "today_alerts": AlertLog.objects.filter(timestamp__gte=today).count(),
    })