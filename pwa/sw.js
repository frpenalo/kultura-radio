var CACHE = "kultura-v11";
var SHELL = ["/", "/app.js", "/manifest.webmanifest", "/icons/icon-192.png", "/icons/icon-512.png"];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(SHELL); }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (e) {
  var url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  // Never cache the live stream or the API — always go to network.
  if (url.pathname.indexOf("/api/") === 0 || url.pathname.indexOf("/stream") === 0) return;
  // Shell VIVO (documento + app.js + manifest): RED PRIMERO, cache solo como
  // respaldo offline. Antes era cache-first y los oyentes quedaban corriendo
  // app.js viejo por días (el deploy solo llegaba al segundo load, si llegaba).
  var live = url.pathname === "/" || url.pathname === "/index.html" || url.pathname === "/app.js" || url.pathname === "/manifest.webmanifest";
  if (live) {
    e.respondWith(
      fetch(e.request).then(function (res) {
        if (res && res.status === 200 && url.origin === location.origin) {
          var copy = res.clone();
          caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
        }
        return res;
      }).catch(function () { return caches.match(e.request); })
    );
    return;
  }
  // Assets estáticos (íconos): cache-first, refresh en background.
  e.respondWith(
    caches.match(e.request).then(function (hit) {
      var net = fetch(e.request).then(function (res) {
        if (res && res.status === 200 && url.origin === location.origin) {
          var copy = res.clone();
          caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
        }
        return res;
      }).catch(function () { return hit; });
      return hit || net;
    })
  );
});
