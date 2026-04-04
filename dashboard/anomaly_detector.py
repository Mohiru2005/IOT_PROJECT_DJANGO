"""
NexusGuard - Anomaly Detection Service for NexusHome
=====================================================
Detects sudden sensor glitches by comparing incoming readings
against the recent average. Only flags data when the jump
exceeds +/-10 units (temperature in C or humidity in %).

Gradual changes are perfectly fine - this only catches
hardware glitches and noise spikes.
"""


# How many recent readings to average for the baseline
RECENT_WINDOW = 10

# Maximum allowed sudden jump from the recent average
# +/-10 is OK, anything beyond that is flagged
TEMP_JUMP_THRESHOLD = 10.0
HUMIDITY_JUMP_THRESHOLD = 10.0


class NexusGuard:
    """
    Data Integrity Layer for NexusHome.
    Validates sensor readings by checking for sudden jumps
    compared to the recent average. If temp or humidity changes
    by more than +/-10 from the last few readings -> ANOMALY.
    """

    def is_data_valid(self, temp, humidity):
        """
        Validate a sensor reading by comparing it to recent history.

        Returns:
            True  - change is within +/-10 of recent average (proceed to Climate AI)
            False - sudden spike/drop detected (BLOCK the command)
        """
        from dashboard.models import SensorReading

        # Grab the last N OK readings to build a recent baseline
        recent = list(
            SensorReading.objects.filter(status='OK')
            .order_by('-timestamp')
            .values_list('temperature', 'humidity')[:RECENT_WINDOW]
        )

        # Cold start: no history yet, so accept everything
        if len(recent) == 0:
            print(f"[NexusGuard] No history yet - accepting: temp={temp}C, humidity={humidity}%")
            return True

        # Calculate the recent average
        avg_temp = sum(r[0] for r in recent) / len(recent)
        avg_hum = sum(r[1] for r in recent) / len(recent)

        temp_diff = abs(temp - avg_temp)
        hum_diff = abs(humidity - avg_hum)

        # Check for sudden jumps
        if temp_diff > TEMP_JUMP_THRESHOLD:
            print(
                f"[NexusGuard] ANOMALY - Sudden temp jump: "
                f"{temp}C vs recent avg {avg_temp:.1f}C (diff={temp_diff:.1f}C > +/-{TEMP_JUMP_THRESHOLD})"
            )
            return False

        if hum_diff > HUMIDITY_JUMP_THRESHOLD:
            print(
                f"[NexusGuard] ANOMALY - Sudden humidity jump: "
                f"{humidity}% vs recent avg {avg_hum:.1f}% (diff={hum_diff:.1f}% > +/-{HUMIDITY_JUMP_THRESHOLD})"
            )
            return False

        print(
            f"[NexusGuard] OK: temp={temp}C (diff={temp_diff:.1f}), "
            f"humidity={humidity}% (diff={hum_diff:.1f})"
        )
        return True


# Module-level singleton for reuse across requests
_guard_instance = None


def get_guard():
    """Get or create the singleton NexusGuard instance."""
    global _guard_instance
    if _guard_instance is None:
        _guard_instance = NexusGuard()
    return _guard_instance
