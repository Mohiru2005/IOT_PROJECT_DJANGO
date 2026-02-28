from django.contrib import admin
from .models import SensorReading, EmergencyEvent, SystemLockdown, Device, DeviceHealthLog


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


class DeviceHealthLogInline(admin.TabularInline):
    model = DeviceHealthLog
    extra = 0
    readonly_fields = ('status', 'signal_strength', 'health_score', 'value', 'timestamp')
    max_num = 20
    ordering = ('-timestamp',)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('icon', 'name', 'device_type', 'status', 'room', 'signal_strength',
                    'last_seen', 'total_messages', 'health_score_display')
    list_filter = ('device_type', 'status', 'room')
    search_fields = ('name', 'mqtt_topic', 'room')
    ordering = ('device_type', 'name')
    readonly_fields = ('registered_at', 'total_messages', 'error_count', 'uptime_seconds')
    inlines = [DeviceHealthLogInline]

    def health_score_display(self, obj):
        score = obj.health_score
        if score >= 80:
            return f"🟢 {score}%"
        elif score >= 50:
            return f"🟡 {score}%"
        else:
            return f"🔴 {score}%"
    health_score_display.short_description = 'Health'


@admin.register(DeviceHealthLog)
class DeviceHealthLogAdmin(admin.ModelAdmin):
    list_display = ('device', 'status', 'signal_strength', 'health_score', 'timestamp')
    list_filter = ('device', 'status')
    ordering = ('-timestamp',)
