self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {};
  const title = data.title || 'New permit';
  const body  = data.body  || '';
  const opts = {
    body,
    data: data.data || {},
    icon: '/static/icon-512.png',
    badge: '/static/icon-512.png'
  };
  event.waitUntil(self.registration.showNotification(title, opts));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(clients.matchAll({ type:'window', includeUncontrolled:true }).then(list => {
    for (const c of list) {
      if ('focus' in c) { c.navigate(url); return c.focus(); }
    }
    if (clients.openWindow) return clients.openWindow(url);
  }));
});