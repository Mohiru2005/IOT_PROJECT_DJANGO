from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.templatetags.static import static
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import SensorReading, EmergencyEvent, SystemLockdown, Device, DeviceHealthLog, SchedulerConfig, ScheduleSlot, DAY_CHOICES
import json
import random
import paho.mqtt.publish as mqtt_publish
from .weather_api import get_vaddeswaram_weather
from .ai_engine import get_ai_decision
from .anomaly_detector import get_guard


def dashboard(request):
    """Main smart home dashboard view."""
    weather = get_vaddeswaram_weather()
    context = {
        'broker': 'ws://broker.hivemq.com:8000/mqtt',
        'topic_temp': 'mohith123/home/room1/temperature',
        'topic_hum': 'mohith123/home/room1/humidity',
        'topic_door': 'mohith123/home/door/light',
        'topic_bed': 'mohith123/home/bedroom/light',
        'topic_hall': 'mohith123/home/hall/light',
        'topic_lock': 'mohith123/home/door/lock',
        'weather': weather,
    }
    return render(request, 'dashboard/index.html', context)


# ══════════════════════════════════════════════
#  EMERGENCY SAFETY AGENT — API ENDPOINTS
# ══════════════════════════════════════════════

@csrf_exempt
def log_emergency(request):
    """
    POST: Log a thermal hazard event to the database.
    Expects JSON: { "temperature": float, "timestamp": str, "door_was_locked": bool }
    Also activates the SystemLockdown.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        temperature = float(data.get('temperature', 0))
        timestamp_str = data.get('timestamp', '')
        door_was_locked = bool(data.get('door_was_locked', False))

        # Parse the ISO timestamp from the client
        try:
            triggered_at = timezone.datetime.fromisoformat(timestamp_str)
            if timezone.is_naive(triggered_at):
                triggered_at = timezone.make_aware(triggered_at)
        except (ValueError, TypeError):
            triggered_at = timezone.now()

        # Log the emergency event
        event = EmergencyEvent.objects.create(
            temperature=temperature,
            triggered_at=triggered_at,
            door_was_locked=door_was_locked,
        )

        # Activate system lockdown
        lockdown = SystemLockdown.get_status()
        lockdown.is_active = True
        lockdown.activated_at = triggered_at
        lockdown.last_temperature = temperature
        lockdown.save()

        return JsonResponse({
            'status': 'logged',
            'event_id': event.id,
            'lockdown_active': True,
        })

    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
def system_reset(request):
    """
    POST: Manually reset the system after an emergency lockdown.
    Resolves all active emergency events and deactivates lockdown.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    now = timezone.now()

    # Resolve all unresolved emergency events
    EmergencyEvent.objects.filter(resolved=False).update(
        resolved=True,
        resolved_at=now,
    )

    # Deactivate system lockdown
    lockdown = SystemLockdown.get_status()
    lockdown.is_active = False
    lockdown.save()

    return JsonResponse({
        'status': 'reset_complete',
        'lockdown_active': False,
        'reset_at': now.isoformat(),
    })


def lockdown_status(request):
    """
    GET: Check the current lockdown status.
    Used by the frontend on page load to restore lockdown state.
    """
    lockdown = SystemLockdown.get_status()
    return JsonResponse({
        'is_active': lockdown.is_active,
        'activated_at': lockdown.activated_at.isoformat() if lockdown.activated_at else None,
        'last_temperature': lockdown.last_temperature,
    })


def manifest(request):
    """Serve the PWA manifest.json from a Django view so we can use dynamic URLs."""
    icon_192 = request.build_absolute_uri(static('dashboard/icons/icon-192.svg'))
    icon_512 = request.build_absolute_uri(static('dashboard/icons/icon-512.svg'))

    data = {
        "name": "NexusHome – Intelligent Home Automation",
        "short_name": "NexusHome",
        "description": "Real-time smart home dashboard. Monitor sensors and control lights & locks remotely via MQTT.",
        "start_url": "/",
        "display": "standalone",
        "orientation": "portrait",
        "theme_color": "#060912",
        "background_color": "#060912",
        "icons": [
            {
                "src": icon_192,
                "sizes": "192x192",
                "type": "image/svg+xml",
                "purpose": "any maskable"
            },
            {
                "src": icon_512,
                "sizes": "512x512",
                "type": "image/svg+xml",
                "purpose": "any maskable"
            }
        ]
    }
    return JsonResponse(data, content_type='application/manifest+json')




def serviceworker(request):
    """Serve the service worker JS from root scope (/)."""
    sw_js = """
// NexusHome Service Worker v1.0
const CACHE_NAME = 'nexushome-v1';
const STATIC_ASSETS = [
    '/',
    '/static/dashboard/css/style.css',
    '/static/dashboard/css/pwa-mobile.css',
    '/static/dashboard/icons/icon-192.svg',
    '/static/dashboard/icons/icon-512.svg',
    'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap',
];

// Install – cache the app shell
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS);
        })
    );
    self.skipWaiting();
});

// Activate – clean old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
            )
        )
    );
    self.clients.claim();
});

// Fetch – network-first for API, cache-first for assets
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Don't cache MQTT WebSocket or admin
    if (url.protocol === 'ws:' || url.protocol === 'wss:' || url.pathname.startsWith('/admin')) {
        return;
    }

    // Static assets – cache first
    if (url.pathname.startsWith('/static/') || url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') {
        event.respondWith(
            caches.match(event.request).then((cached) => {
                return cached || fetch(event.request).then((response) => {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                    return response;
                });
            })
        );
        return;
    }

    // HTML pages – network first, fallback to cache
    event.respondWith(
        fetch(event.request)
            .then((response) => {
                const clone = response.clone();
                caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                return response;
            })
            .catch(() => caches.match(event.request))
    );
});
"""
    return HttpResponse(sw_js.strip(), content_type='application/javascript')


def offline(request):
    """Simple offline fallback page."""
    return render(request, 'dashboard/offline.html')


# ══════════════════════════════════════════════
#  DEVICE MONITORING — API ENDPOINTS
# ══════════════════════════════════════════════

# Mapping from known MQTT topic patterns to device info
DEVICE_TOPIC_MAP = {
    'temperature': {'name': 'Temperature Sensor', 'type': 'sensor', 'icon': '🌡️', 'room': 'Room 1'},
    'humidity': {'name': 'Humidity Sensor', 'type': 'sensor', 'icon': '💧', 'room': 'Room 1'},
    'door/light': {'name': 'Front Door Light', 'type': 'light', 'icon': '🚪', 'room': 'Entrance'},
    'bedroom/light': {'name': 'Bedroom Light', 'type': 'light', 'icon': '🛏️', 'room': 'Bedroom'},
    'hall/light': {'name': 'Hallway Light', 'type': 'light', 'icon': '🛋️', 'room': 'Hallway'},
    'door/lock': {'name': 'Front Door Lock', 'type': 'lock', 'icon': '🔒', 'room': 'Entrance'},
}


def _identify_device(topic):
    """Identify device type/name/icon/room from MQTT topic."""
    for pattern, info in DEVICE_TOPIC_MAP.items():
        if pattern in topic:
            return info
    # Fallback for unknown topics
    return {
        'name': topic.split('/')[-1].replace('_', ' ').title(),
        'type': 'other',
        'icon': '📟',
        'room': 'Unknown',
    }


@csrf_exempt
def device_heartbeat(request):
    """
    POST: Register or update a device heartbeat.
    Called by the frontend whenever an MQTT message is received.
    Expects JSON: { "topic": str, "value": str }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        topic = data.get('topic', '')
        value = data.get('value', '')

        if not topic:
            return JsonResponse({'error': 'topic is required'}, status=400)

        now = timezone.now()
        info = _identify_device(topic)

        device, created = Device.objects.get_or_create(
            mqtt_topic=topic,
            defaults={
                'name': info['name'],
                'device_type': info['type'],
                'icon': info['icon'],
                'room': info['room'],
                'status': 'online',
                'last_seen': now,
                'last_value': str(value)[:100],
                'signal_strength': random.randint(75, 98),
                'total_messages': 1,
            }
        )

        if not created:
            # Update existing device
            device.status = 'online'
            device.last_seen = now
            device.last_value = str(value)[:100]
            device.total_messages += 1
            # Simulate slight signal variation
            device.signal_strength = max(50, min(100,
                device.signal_strength + random.randint(-3, 3)
            ))
            device.save()

        # Log health snapshot (throttled: max once per 30 seconds per device)
        recent_log = DeviceHealthLog.objects.filter(
            device=device
        ).first()

        should_log = (
            not recent_log or
            (now - recent_log.timestamp).total_seconds() >= 30
        )

        if should_log:
            DeviceHealthLog.objects.create(
                device=device,
                status=device.status,
                signal_strength=device.signal_strength,
                health_score=device.health_score,
                value=str(value)[:100],
            )

        # ── Also store a SensorReading if this is a temp or humidity topic ──
        try:
            float_val = float(value)
            is_temp = 'temperature' in topic
            is_hum = 'humidity' in topic

            if is_temp or is_hum:
                weather = get_vaddeswaram_weather()
                out_t_str = weather.get("temp", "0°C").replace('°C', '')
                try:
                    out_t = float(out_t_str)
                except ValueError:
                    last_reading = SensorReading.objects.exclude(outdoor_temp__isnull=True).order_by('-timestamp').first()
                    out_t = last_reading.outdoor_temp if last_reading else 0.0

                if is_temp:
                    indoor_t = float_val
                    # Find latest humidity from DB to pair with
                    last_hum_device = Device.objects.filter(mqtt_topic__contains='humidity').first()
                    indoor_h = float(last_hum_device.last_value) if last_hum_device and last_hum_device.last_value else 0.0

                    # ══ NEXUSGUARD — Data Integrity Check ══
                    # Validate sensor data BEFORE allowing Climate AI inference
                    guard = get_guard()
                    data_valid = guard.is_data_valid(indoor_t, indoor_h)
                    reading_status = 'OK'

                    if not data_valid:
                        # ── ANOMALY DETECTED: Block the AI command ──
                        decision = "ANOMALY"
                        reading_status = 'ANOMALY'
                        print(f"[NexusGuard] BLOCKED: temp={indoor_t}C, hum={indoor_h}% - Anomaly. No MQTT command sent.")
                        # Publish anomaly notification (informational only, no hardware command)
                        try:
                            mqtt_publish.single("mohith123/home/climate/command", "ANOMALY", hostname="broker.hivemq.com", port=1883)
                        except Exception:
                            pass
                    else:
                        # ── Data is VALID — proceed with normal pipeline ──

                        # ── Scheduler Check ──
                        # If scheduler is ON and status is AWAY → skip ML, force STANDBY
                        # But ALWAYS let fire alarm (>40°C) through
                        scheduler_cfg = SchedulerConfig.get_config()
                        is_away = False
                        if scheduler_cfg.is_enabled:
                            current_presence = ScheduleSlot.get_current_status()
                            if current_presence == 'AWAY':
                                is_away = True

                        if is_away and indoor_t <= 40.0:
                            # User is AWAY and no fire → force STANDBY, turn off devices
                            decision = "AWAY_STANDBY"
                            reading_status = 'AWAY_STANDBY'
                            try:
                                mqtt_publish.single("mohith123/home/door/light", "OFF", hostname="broker.hivemq.com", port=1883)
                                mqtt_publish.single("mohith123/home/bedroom/light", "OFF", hostname="broker.hivemq.com", port=1883)
                                mqtt_publish.single("mohith123/home/hall/light", "OFF", hostname="broker.hivemq.com", port=1883)
                                mqtt_publish.single("mohith123/home/door/lock", "LOCK", hostname="broker.hivemq.com", port=1883)
                                mqtt_publish.single("mohith123/home/climate/command", decision, hostname="broker.hivemq.com", port=1883)
                            except Exception as e:
                                print(f"Failed to publish AWAY commands: {e}")
                        else:
                            # Normal ML path (HOME or fire override)
                            # 2. ML Inference
                            decision = get_ai_decision(indoor_t, out_t, indoor_h)

                            # 3. Hardware Safety Override (fire alarm always active)
                            if indoor_t > 40.0:
                                decision = "SYSTEM_LOCKDOWN"

                            # 5. Publish to MQTT
                            try:
                                mqtt_publish.single("mohith123/home/climate/command", decision, hostname="broker.hivemq.com", port=1883)
                            except Exception as e:
                                print(f"Failed to publish ML decision to MQTT: {e}")

                    # 4. Save to Database (always save regardless of anomaly/scheduler)
                    SensorReading.objects.create(
                        temperature=indoor_t, 
                        humidity=indoor_h,
                        outdoor_temp=out_t,
                        outdoor_humidity=0.0,
                        ai_decision=decision,
                        status=reading_status,
                    )

                elif is_hum:
                    last_temp_device = Device.objects.filter(mqtt_topic__contains='temperature').first()
                    last_temp = float(last_temp_device.last_value) if last_temp_device and last_temp_device.last_value else 0.0
                    SensorReading.objects.create(
                        temperature=last_temp, 
                        humidity=float_val,
                        outdoor_temp=out_t,
                        outdoor_humidity=0.0
                    )
        except (ValueError, TypeError) as e:
            print(f"Skipping sensor reading storage due to error: {repr(e)}")

        return JsonResponse({
            'status': 'ok',
            'device_id': device.id,
            'created': created,
            'health_score': device.health_score,
        })

    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'error': str(e)}, status=400)


def device_list(request):
    """
    GET: Return all registered devices with their current status and health.
    """
    # Auto-mark offline: any device not seen in 60s
    stale_cutoff = timezone.now() - timezone.timedelta(seconds=60)
    Device.objects.filter(
        last_seen__lt=stale_cutoff, status='online'
    ).update(status='offline')

    devices = Device.objects.all()
    result = []
    for d in devices:
        result.append({
            'id': d.id,
            'name': d.name,
            'device_type': d.device_type,
            'mqtt_topic': d.mqtt_topic,
            'status': d.status,
            'last_seen': d.last_seen.isoformat() if d.last_seen else None,
            'last_value': d.last_value,
            'signal_strength': d.signal_strength,
            'health_score': d.health_score,
            'total_messages': d.total_messages,
            'error_count': d.error_count,
            'firmware_version': d.firmware_version,
            'icon': d.icon,
            'room': d.room,
            'registered_at': d.registered_at.isoformat(),
            'uptime_seconds': d.uptime_seconds,
        })

    return JsonResponse({'devices': result})


def device_health_history(request, device_id):
    """
    GET: Return health log history for a specific device.
    Optional query param: ?limit=N (default 50)
    """
    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return JsonResponse({'error': 'Device not found'}, status=404)

    limit = int(request.GET.get('limit', 50))
    logs = DeviceHealthLog.objects.filter(device=device)[:limit]

    history = []
    for log in logs:
        history.append({
            'timestamp': log.timestamp.isoformat(),
            'status': log.status,
            'signal_strength': log.signal_strength,
            'health_score': log.health_score,
            'value': log.value,
        })

    return JsonResponse({
        'device_id': device.id,
        'device_name': device.name,
        'history': history,
    })


# ══════════════════════════════════════════════
#  ANALYTICS — API ENDPOINT
# ══════════════════════════════════════════════

def analytics_data(request):
    """
    GET: Return the last 720 SensorReading rows (1-hour at 5s intervals)
    for initial chart population.
    """
    readings = SensorReading.objects.order_by('-timestamp')[:720]
    # Reverse so oldest is first (chronological order for chart)
    readings = list(reversed(readings))

    data = []
    
    # Pre-calculate a sensible default for fallback
    last_valid_out = 0.0
    for r in readings:
        if r.outdoor_temp is not None and r.outdoor_temp != 0.0:
            last_valid_out = r.outdoor_temp
            break

    for r in readings:
        # Keep track of last valid outdoor temp to prevent graph drops
        if r.outdoor_temp is not None and r.outdoor_temp != 0.0:
            last_valid_out = r.outdoor_temp
            
        data.append({
            'temperature': r.temperature,
            'outdoor_temp': last_valid_out,
            'humidity': r.humidity,
            'timestamp': r.timestamp.strftime('%H:%M:%S'),
        })

    return JsonResponse({'readings': data, 'count': len(data)})

# ══════════════════════════════════════════════
#  NEXUSGUARD — ANOMALY STATUS API
# ══════════════════════════════════════════════

def anomaly_status(request):
    """
    GET: Return recent anomaly information for the dashboard.
    Checks the last 5 minutes of readings for any anomalies.
    """
    cutoff = timezone.now() - timezone.timedelta(minutes=5)
    recent_anomalies = SensorReading.objects.filter(
        status='ANOMALY',
        timestamp__gte=cutoff,
    ).order_by('-timestamp')[:10]

    anomaly_list = []
    for a in recent_anomalies:
        anomaly_list.append({
            'temperature': a.temperature,
            'humidity': a.humidity,
            'timestamp': a.timestamp.strftime('%H:%M:%S'),
            'ai_decision': a.ai_decision,
        })

    # Count total anomalies in the current session (last 60 min)
    session_cutoff = timezone.now() - timezone.timedelta(minutes=60)
    total_anomalies = SensorReading.objects.filter(
        status='ANOMALY',
        timestamp__gte=session_cutoff,
    ).count()

    return JsonResponse({
        'has_active_anomaly': len(anomaly_list) > 0,
        'recent_anomalies': anomaly_list,
        'total_session_anomalies': total_anomalies,
    })


# ══════════════════════════════════════════════
#  SCHEDULER — API ENDPOINTS
# ══════════════════════════════════════════════

def scheduler_data(request):
    """
    GET: Return scheduler config (enabled/disabled) + all schedule slots.
    """
    config = SchedulerConfig.get_config()
    slots = ScheduleSlot.objects.all()
    current_status = ScheduleSlot.get_current_status() if config.is_enabled else 'HOME'

    day_names = dict(DAY_CHOICES)
    slot_list = []
    for s in slots:
        slot_list.append({
            'id': s.id,
            'day_of_week': s.day_of_week,
            'day_name': day_names.get(s.day_of_week, '?'),
            'start_time': s.start_time.strftime('%H:%M'),
            'end_time': s.end_time.strftime('%H:%M'),
            'status': s.status,
            'label': s.label,
        })

    return JsonResponse({
        'is_enabled': config.is_enabled,
        'current_status': current_status,
        'slots': slot_list,
    })


@csrf_exempt
def scheduler_toggle(request):
    """
    POST: Toggle the scheduler on/off.
    Optionally accepts JSON: { "enabled": true/false }
    If no body, it just toggles the current state.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    config = SchedulerConfig.get_config()

    try:
        data = json.loads(request.body)
        config.is_enabled = bool(data.get('enabled', not config.is_enabled))
    except (json.JSONDecodeError, ValueError):
        config.is_enabled = not config.is_enabled

    config.save()

    return JsonResponse({
        'is_enabled': config.is_enabled,
        'current_status': ScheduleSlot.get_current_status() if config.is_enabled else 'HOME',
    })


@csrf_exempt
def scheduler_add_slot(request):
    """
    POST: Create a new schedule slot.
    Expects JSON: { "day_of_week": int, "start_time": "HH:MM", "end_time": "HH:MM", "status": "HOME"|"AWAY", "label": str }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        day = int(data.get('day_of_week', 0))
        start = data.get('start_time', '00:00')
        end = data.get('end_time', '23:59')
        status = data.get('status', 'AWAY')
        label = data.get('label', '')

        if day < 0 or day > 6:
            return JsonResponse({'error': 'day_of_week must be 0-6'}, status=400)
        if status not in ('HOME', 'AWAY'):
            return JsonResponse({'error': 'status must be HOME or AWAY'}, status=400)

        from datetime import time as dt_time
        sh, sm = map(int, start.split(':'))
        eh, em = map(int, end.split(':'))
        start_time = dt_time(sh, sm)
        end_time = dt_time(eh, em)

        if start_time >= end_time:
            return JsonResponse({'error': 'start_time must be before end_time'}, status=400)

        slot = ScheduleSlot.objects.create(
            day_of_week=day,
            start_time=start_time,
            end_time=end_time,
            status=status,
            label=label[:60],
        )

        day_names = dict(DAY_CHOICES)
        return JsonResponse({
            'status': 'created',
            'slot': {
                'id': slot.id,
                'day_of_week': slot.day_of_week,
                'day_name': day_names.get(slot.day_of_week, '?'),
                'start_time': slot.start_time.strftime('%H:%M'),
                'end_time': slot.end_time.strftime('%H:%M'),
                'status': slot.status,
                'label': slot.label,
            }
        })

    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
def scheduler_delete_slot(request, slot_id):
    """
    DELETE: Remove a schedule slot by ID.
    """
    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE required'}, status=405)

    try:
        slot = ScheduleSlot.objects.get(pk=slot_id)
        slot.delete()
        return JsonResponse({'status': 'deleted', 'id': slot_id})
    except ScheduleSlot.DoesNotExist:
        return JsonResponse({'error': 'Slot not found'}, status=404)
