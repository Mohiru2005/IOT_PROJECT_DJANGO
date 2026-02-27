from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('manifest.json', views.manifest, name='manifest'),
    path('serviceworker.js', views.serviceworker, name='serviceworker'),
    path('offline/', views.offline, name='offline'),

    # ── Emergency Safety Agent API ──
    path('api/emergency/log/', views.log_emergency, name='emergency-log'),
    path('api/emergency/reset/', views.system_reset, name='emergency-reset'),
    path('api/emergency/status/', views.lockdown_status, name='emergency-status'),
]
