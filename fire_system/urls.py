from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('alert_app.urls')), # Bao gồm các đường dẫn của ứng dụng cảnh báo cháy
]

# Thêm cấu hình phục vụ file media trong khi chạy server local
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)