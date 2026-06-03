/**
 * NexusAgent PWA — Service Worker
 * 缓存静态资源，支持离线访问
 */

const CACHE_NAME = 'nexusagent-v1';
const STATIC_ASSETS = [
  '/desktop/index.html',
  '/desktop/app.js',
  '/desktop/style.css',
  '/desktop/manifest.json',
];

// 安装: 预缓存核心静态资源
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    }).catch(() => {
      // 部分资源可能不存在，忽略错误
    })
  );
  self.skipWaiting();
});

// 激活: 清理旧缓存
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

// 拦截请求: 缓存优先策略
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // 只缓存 GET 请求的同源静态资源
  if (request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;

  // API 请求不走缓存
  if (url.pathname.startsWith('/api/')) return;
  if (url.pathname.startsWith('/ws')) return;

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (!response || response.status !== 200 || response.type !== 'basic') {
          return response;
        }
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => {
          cache.put(request, clone);
        });
        return response;
      }).catch(() => {
        // 离线且缓存未命中
        return new Response('Offline', { status: 503 });
      });
    })
  );
});
