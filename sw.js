// Service Worker for New Permits Mobile App
const CACHE_NAME = 'new-permits-v2';
const urlsToCache = [
  '/',
  '/static/manifest.webmanifest',
  '/static/icon-512.png',
  '/static/apple-touch-icon.png',
  '/static/apple-touch-icon-120x120.png'
];

// Install event
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

// Fetch event
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Return cached version or fetch from network
        return response || fetch(event.request);
      })
  );
});

// Activate event
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});

// Push notification event
self.addEventListener('push', event => {
  console.log('Push event received:', event);
  
  let data = {};
  
  if (event.data) {
    try {
      data = event.data.json();
      console.log('Push data:', data);
    } catch (e) {
      console.log('Error parsing push data:', e);
      data = { body: event.data.text() };
    }
  }
  
  const options = {
    body: data.body || 'New permit found in your selected county!',
    icon: data.icon || '/static/icon-512.png',
    badge: data.badge || '/static/apple-touch-icon.png',
    vibrate: [200, 100, 200],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: 1,
      url: data.url || '/'
    },
    // iOS Safari doesn't support actions, so we'll keep it simple
    tag: 'new-permits',
    requireInteraction: false,
    silent: false
  };

  console.log('Showing notification with options:', options);

  event.waitUntil(
    self.registration.showNotification(data.title || 'New Permits Alert', options)
    .then(() => {
      console.log('Notification shown successfully');
    })
    .catch(error => {
      console.error('Error showing notification:', error);
    })
  );
});

// Notification click event
self.addEventListener('notificationclick', event => {
  console.log('Notification clicked:', event);
  event.notification.close();

  event.waitUntil(
    clients.openWindow(event.notification.data.url || '/')
  );
});

// Background sync for periodic updates
self.addEventListener('sync', event => {
  if (event.tag === 'background-sync') {
    event.waitUntil(doBackgroundSync());
  }
});

async function doBackgroundSync() {
  try {
    const response = await fetch('/api/check-new-permits');
    const data = await response.json();
    
    if (data.newPermits && data.newPermits.length > 0) {
      // Send notification for new permits
      self.registration.showNotification('New Permits Found!', {
        body: `${data.newPermits.length} new permit(s) found in your selected counties`,
        icon: '/static/icon-512.png',
        badge: '/static/apple-touch-icon.png',
        vibrate: [200, 100, 200],
        tag: 'new-permits'
      });
    }
  } catch (error) {
    console.error('Background sync failed:', error);
  }
}