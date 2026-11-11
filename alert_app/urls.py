# urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('video_feed/', views.video_feed, name='video_feed'),
    path('status/', views.stream_status, name='stream_status'),
    path('alerts/<int:pk>/delete/', views.delete_alert, name='delete_alert'),
    path('source/', views.set_source, name='set_source'),
    path('analyze_image/', views.analyze_image, name='analyze_image'),
    path('sw.js', views.service_worker, name='service_worker'),
    path('manifest.webmanifest', views.manifest, name='manifest'),
    path('push/public_key/', views.push_public_key, name='push_public_key'),
    path('push/subscribe/', views.push_subscribe, name='push_subscribe'),
    path('push/unsubscribe/', views.push_unsubscribe, name='push_unsubscribe'),
    path('push/test/', views.push_test, name='push_test'),
    path('alarm/ack/', views.alarm_ack, name='alarm_ack'),
    path('ai/', views.ai_toggle, name='ai_toggle'),
]