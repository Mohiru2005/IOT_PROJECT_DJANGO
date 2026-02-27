from django.db import models

# Create your models here.

class SensorReading(models.Model):
    temperature = models.FloatField()
    humidity = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Temp: {self.temperature}°C, Hum: {self.humidity}% at {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"

