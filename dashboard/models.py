from django.db import models


class SensorReading(models.Model):
    temperature = models.FloatField()
    humidity = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)

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
