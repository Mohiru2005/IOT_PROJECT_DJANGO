from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('manifest.json', views.manifest, name='manifest'),
    path('serviceworker.js', views.serviceworker, name='serviceworker'),
    path('offline/', views.offline, name='offline'),
]
