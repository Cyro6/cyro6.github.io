---
permalink: "/sw.js"
layout: null
sitemap: false
---

const VERSION = '{{ site.time | date: '%Y%m%d%H%M%S' }}';
const STATIC_CACHE  = `dtf-static::${VERSION}`;
const CDN_CACHE     = 'dtf-cdn::v1';
const DATA_CACHE    = 'dtf-data::v1';

// CDN assets — versioned URLs, cache-first forever
const CDN_PRECACHE = [
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js',
];

// Same-origin data files — pre-cached at install, refreshed at runtime
const DATA_PRECACHE = [
  '/assets/data/streams.json',
  '/assets/data/stream_posts.json',
];

// Same-origin app pages — Jekyll-generated list
const STATIC_PRECACHE = [
  {%- for post in site.posts limit: 10 -%}
    "{{ post.url | relative_url }}",
  {%- endfor -%}
  {%- for page in site.pages -%}
    {%- unless page.url contains 'sw.js' or page.url contains '404.html' -%}
      "{{ page.url | relative_url }}",
    {%- endunless -%}
  {%- endfor -%}
  "{{ site.logo | relative_url }}",
  "/assets/scripts/fetch.js"
];

// ── Install ──────────────────────────────────────────────────────────────────

self.addEventListener('install', event => {
  event.waitUntil(
    Promise.all([
      caches.open(CDN_CACHE).then(c => c.addAll(CDN_PRECACHE)),
      caches.open(DATA_CACHE).then(c => c.addAll(DATA_PRECACHE)),
      caches.open(STATIC_CACHE).then(c => c.addAll(STATIC_PRECACHE)),
    ]).then(() => {
      console.log(`[SW] installed ${STATIC_CACHE}`);
      return self.skipWaiting();
    })
  );
});

// ── Activate ─────────────────────────────────────────────────────────────────

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k.startsWith('dtf-static::') && k !== STATIC_CACHE)
          .map(k => {
            console.log(`[SW] removing old cache: ${k}`);
            return caches.delete(k);
          })
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch ─────────────────────────────────────────────────────────────────────

self.addEventListener('fetch', event => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Open-Meteo weather API — network only, offline JSON fallback
  if (url.hostname === 'api.open-meteo.com') {
    event.respondWith(
      fetch(request).catch(() =>
        new Response(JSON.stringify({ offline: true, error: 'Network unavailable' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    );
    return;
  }

  // CDN assets (unpkg, jsdelivr) — cache-first
  if (url.hostname === 'unpkg.com' || url.hostname === 'cdn.jsdelivr.net') {
    event.respondWith(
      caches.open(CDN_CACHE).then(async cache => {
        const cached = await cache.match(request);
        if (cached) return cached;
        const fresh = await fetch(request);
        if (fresh.ok) cache.put(request, fresh.clone());
        return fresh;
      })
    );
    return;
  }

  // Same-origin data files — stale-while-revalidate
  if (url.origin === location.origin && url.pathname.startsWith('/assets/data/')) {
    event.respondWith(
      caches.open(DATA_CACHE).then(async cache => {
        const cached = await cache.match(request);

        const refresh = () => fetch(request).then(fresh => {
          if (fresh.ok) cache.put(request, fresh.clone());
          return fresh;
        });

        if (cached) {
          event.waitUntil(refresh().catch(() => {}));
          return cached;
        }
        return refresh().catch(() => new Response('Offline', { status: 503 }));
      })
    );
    return;
  }

  // Other cross-origin requests — pass through
  if (url.origin !== location.origin) return;

  // Same-origin pages & assets — network-first, static cache fallback
  event.respondWith(
    fetch(request)
      .then(response => {
        const clone = response.clone();
        caches.open(STATIC_CACHE).then(c => c.put(request, clone));
        return response;
      })
      .catch(async () => {
        const cached = await caches.match(request);
        return cached || caches.match('/offline/');
      })
  );
});
