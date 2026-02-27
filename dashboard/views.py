from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.templatetags.static import static
from django.views.decorators.csrf import csrf_exempt


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
