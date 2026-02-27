from django.contrib import admin
from .models import SensorReading, EmergencyEvent, SystemLockdown


@admin.register(SensorReading)
class SensorReadingAdmin(admin.ModelAdmin):
    list_display = ('temperature', 'humidity', 'timestamp')
    list_filter = ('timestamp',)
    ordering = ('-timestamp',)


@admin.register(EmergencyEvent)
class EmergencyEventAdmin(admin.ModelAdmin):
    list_display = ('temperature', 'triggered_at', 'door_was_locked', 'resolved', 'resolved_at')
    list_filter = ('resolved', 'triggered_at')
    ordering = ('-triggered_at',)
    readonly_fields = ('temperature', 'triggered_at', 'door_was_locked')


@admin.register(SystemLockdown)
class SystemLockdownAdmin(admin.ModelAdmin):
    list_display = ('is_active', 'activated_at', 'last_temperature')
