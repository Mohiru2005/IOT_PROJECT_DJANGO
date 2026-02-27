from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.templatetags.static import static
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import EmergencyEvent, SystemLockdown
import json


def dashboard(request):
    """Main smart home dashboard view."""
    context = {
        'broker': 'ws://broker.hivemq.com:8000/mqtt',
        'topic_temp': 'mohith123/home/room1/temperature',
        'topic_hum': 'mohith123/home/room1/humidity',
        'topic_door': 'mohith123/home/door/light',
        'topic_bed': 'mohith123/home/bedroom/light',
        'topic_hall': 'mohith123/home/hall/light',
        'topic_lock': 'mohith123/home/door/lock',
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
