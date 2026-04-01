from django.db import models
from django.utils import timezone


class SensorReading(models.Model):
    temperature = models.FloatField()
    humidity = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        """Save and auto-purge readings older than 60 minutes."""
        super().save(*args, **kwargs)
        cutoff = timezone.now() - timezone.timedelta(minutes=60)
        SensorReading.objects.filter(timestamp__lt=cutoff).delete()

    def __str__(self):
        return f"Temp: {self.temperature}°C, Hum: {self.humidity}% at {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"


class EmergencyEvent(models.Model):
    """Logs every time the Safe Shutdown & Evacuation sequence is triggered."""
    temperature = models.FloatField(help_text="Temperature (°C) that triggered the event")
    triggered_at = models.DateTimeField(help_text="Exact timestamp when threshold was breached")
    door_was_locked = models.BooleanField(
        default=False,
        help_text="Whether the door was locked at the time of the event"
    )
    resolved = models.BooleanField(
        default=False,
        help_text="Has this event been resolved via System Reset?"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-triggered_at']
        verbose_name = "Emergency Event"
        verbose_name_plural = "Emergency Events"

    def __str__(self):
        status = "⚠️ ACTIVE" if not self.resolved else "✅ Resolved"
        return f"{status} | {self.temperature}°C at {self.triggered_at.strftime('%Y-%m-%d %H:%M:%S')}"


class SystemLockdown(models.Model):
    """
    Singleton-style model to track whether the system is in emergency lockdown.
    Only one row should exist. When is_active=True, all lights must stay OFF
    and door must remain UNLOCKED until a manual reset.
    """
    is_active = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True)
    last_temperature = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "System Lockdown Status"
        verbose_name_plural = "System Lockdown Status"

    def __str__(self):
        if self.is_active:
            return f"🔴 LOCKDOWN ACTIVE since {self.activated_at}"
        return "🟢 System Normal"

    @classmethod
    def get_status(cls):
        """Get or create the singleton lockdown status row."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Device(models.Model):
    """
    Represents a physical IoT device connected via MQTT.
    Automatically registered when the system first sees its topic.
    """
    DEVICE_TYPES = [
        ('sensor', 'Sensor'),
        ('light', 'Light'),
        ('lock', 'Lock'),
        ('relay', 'Relay'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('degraded', 'Degraded'),
    ]

    name = models.CharField(max_length=100)
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPES, default='other')
    mqtt_topic = models.CharField(max_length=200, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offline')
    last_seen = models.DateTimeField(null=True, blank=True)
    last_value = models.CharField(max_length=100, blank=True, default='')
    signal_strength = models.IntegerField(
        default=0,
        help_text="Simulated signal quality 0-100%"
    )
    uptime_seconds = models.IntegerField(default=0, help_text="Cumulative uptime in seconds")
    total_messages = models.IntegerField(default=0, help_text="Total MQTT messages received")
    error_count = models.IntegerField(default=0, help_text="Number of errors/timeouts detected")
    firmware_version = models.CharField(max_length=20, blank=True, default='1.0.0')
    registered_at = models.DateTimeField(auto_now_add=True)
    icon = models.CharField(max_length=10, default='📟')
    room = models.CharField(max_length=50, blank=True, default='')

    class Meta:
        ordering = ['device_type', 'name']
        verbose_name = 'IoT Device'
        verbose_name_plural = 'IoT Devices'

    def __str__(self):
        return f"{self.icon} {self.name} ({self.get_status_display()})"

    @property
    def is_online(self):
        """Device is online if we heard from it in the last 60 seconds."""
        if not self.last_seen:
            return False
        from django.utils import timezone as tz
        return (tz.now() - self.last_seen).total_seconds() < 60

    @property
    def health_score(self):
        """Calculate a 0-100 health score based on signal, errors, and uptime."""
        score = self.signal_strength
        if self.total_messages > 0:
            error_rate = self.error_count / self.total_messages
            score -= int(error_rate * 50)
        if not self.is_online:
            score -= 30
        return max(0, min(100, score))


class DeviceHealthLog(models.Model):
    """
    Periodic snapshot of a device's health metrics.
    Stored at intervals to build a health timeline.
    """
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='health_logs')
    status = models.CharField(max_length=20, default='online')
    signal_strength = models.IntegerField(default=0)
    health_score = models.IntegerField(default=100)
    value = models.CharField(max_length=100, blank=True, default='')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Device Health Log'
        verbose_name_plural = 'Device Health Logs'
        # Keep the table manageable — index for fast lookups
        indexes = [
            models.Index(fields=['device', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.device.name} | {self.status} | {self.health_score}% at {self.timestamp.strftime('%H:%M:%S')}"
