import json
from django.test import TestCase
from django.urls import reverse
from dashboard.models import SensorReading, Device


class AIIntegrityTest(TestCase):
    def setUp(self):
        # Reset the singleton guard between tests
        import dashboard.anomaly_detector as ad
        ad._guard_instance = None

        # Seed 10 recent "normal" readings around 25°C / 50% humidity.
        # NexusGuard compares incoming data against the average of these.
        for i in range(10):
            SensorReading.objects.create(
                temperature=25.0 + (i * 0.2),    # 25.0 → 26.8 (gradual)
                humidity=50.0 + (i * 0.3),        # 50.0 → 52.7 (gradual)
                outdoor_temp=30.0,
                status='OK',
                ai_decision='STANDBY'
            )

        # Create a humidity Device so the heartbeat view can pair humidity with temperature.
        Device.objects.create(
            mqtt_topic='mohith123/home/room1/humidity',
            name='Humidity Sensor',
            device_type='sensor',
            icon='💧',
            room='Room 1',
            status='online',
            last_value='50.0',
            signal_strength=90,
            total_messages=1,
        )

    def test_a_normal_reading(self):
        """Test A: A reading within ±10 of recent avg should be accepted."""
        print("\n--- Test A: Normal Reading (within ±10) ---")

        # Recent avg temp ≈ 25.9°C. Sending 26°C → Δ0.1 → should be OK.
        payload = {
            "topic": "mohith123/home/room1/temperature",
            "value": "26.0"
        }

        response = self.client.post(
            reverse('device-heartbeat'),
            data=json.dumps(payload),
            content_type='application/json'
        )

        if response.status_code != 200:
            print(f"ERROR: status={response.status_code}, body={response.content}")
        self.assertEqual(response.status_code, 200)

        latest = SensorReading.objects.order_by('-id').first()
        self.assertEqual(latest.temperature, 26.0)
        self.assertEqual(latest.status, 'OK')

        print(f"✅ Test A Passed: 26.0°C accepted (status={latest.status})")

    def test_b_glitch_reading(self):
        """Test B: A reading that jumps >10 from recent avg should be BLOCKED."""
        print("\n--- Test B: Glitch Reading (jump > ±10) ---")

        # Recent avg temp ≈ 25.9°C. Sending 98°C → Δ72.1 → should be ANOMALY.
        payload = {
            "topic": "mohith123/home/room1/temperature",
            "value": "98.0"
        }

        response = self.client.post(
            reverse('device-heartbeat'),
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)

        latest = SensorReading.objects.order_by('-id').first()
        self.assertEqual(latest.temperature, 98.0)
        self.assertEqual(latest.status, 'ANOMALY')
        self.assertEqual(latest.ai_decision, 'ANOMALY')

        print(f"✅ Test B Passed: 98.0°C BLOCKED (status={latest.status})")

    def test_c_gradual_change(self):
        """Test C: A reading that's +9 from avg should be accepted (within threshold)."""
        print("\n--- Test C: Gradual Change (within ±10) ---")

        # Recent avg temp ≈ 25.9°C. Sending 34°C → Δ8.1 → still within ±10 → OK.
        payload = {
            "topic": "mohith123/home/room1/temperature",
            "value": "34.0"
        }

        response = self.client.post(
            reverse('device-heartbeat'),
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)

        latest = SensorReading.objects.order_by('-id').first()
        self.assertEqual(latest.temperature, 34.0)
        self.assertEqual(latest.status, 'OK')

        print(f"✅ Test C Passed: 34.0°C accepted — gradual change is fine (status={latest.status})")
