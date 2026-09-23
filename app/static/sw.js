self.addEventListener("install", e => self.skipWaiting());

self.addEventListener("push", e => {
  e.waitUntil(
    self.registration.showNotification("עדכון תחזית", {
      body: e.data ? e.data.text() : "יש עדכון חדש"
    })
  );
});
