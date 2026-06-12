/*
 * FiForesight service worker — Web Push (Feature 9 — Alerts & Notifications).
 *
 * Receives encrypted push messages sent by the backend (pywebpush) and shows a
 * notification. Clicking it focuses an existing tab or opens the alerts page.
 * Kept intentionally minimal — no offline caching, only push handling.
 */
self.addEventListener('push', (event) => {
  let data = { title: 'FiForesight', body: 'You have a new alert.', url: '/alerts' };
  try {
    if (event.data) data = { ...data, ...event.data.json() };
  } catch (_e) {
    if (event.data) data.body = event.data.text();
  }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/favicon.ico',
      data: { url: data.url || '/alerts' },
      tag: 'fiforesight-alert',
      renotify: true,
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || '/alerts';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientsArr) => {
      for (const client of clientsArr) {
        if ('focus' in client) {
          client.focus();
          if ('navigate' in client) client.navigate(targetUrl).catch(() => {});
          return;
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(targetUrl);
    })
  );
});
