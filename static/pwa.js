// Installable app: service worker registration, the install button and the update bar.
// Loaded in <head> so the browser's install event is caught however early it fires.
(function () {
    'use strict';
    let deferredPrompt = null;
    let waitingWorker = null;
    let updating = false;

    const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent)
        || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const isStandalone = () => window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
    const initial = { canInstall: false, isIOS, standalone: isStandalone(), updateReady: false, offline: !navigator.onLine, iosHelp: false };

    function set(key, value) {
        initial[key] = value;
        if (window.Alpine && Alpine.store('pwa')) Alpine.store('pwa')[key] = value;
    }

    window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); deferredPrompt = e; set('canInstall', true); });
    window.addEventListener('appinstalled', () => {
        deferredPrompt = null; set('canInstall', false);
        if (window.showAlert) showAlert('Installed. Open Finance from your home screen or app list.', 'success');
    });
    window.addEventListener('online', () => set('offline', false));
    window.addEventListener('offline', () => set('offline', true));
    window.matchMedia('(display-mode: standalone)').addEventListener('change', () => set('standalone', isStandalone()));

    document.addEventListener('alpine:init', () => {
        Alpine.store('pwa', {
            ...initial,
            // Shown only when the browser offers installing, or on iOS where it is a manual step.
            get showInstall() { return !this.standalone && (this.canInstall || this.isIOS); },
            async install() {
                if (deferredPrompt) {
                    deferredPrompt.prompt();
                    await deferredPrompt.userChoice.catch(() => null);
                    deferredPrompt = null;
                    this.canInstall = false;
                } else if (this.isIOS) {
                    this.iosHelp = true;
                }
            },
            applyUpdate() {
                if (!waitingWorker) { location.reload(); return; }
                updating = true;
                waitingWorker.postMessage('skipWaiting');
            },
        });
    });

    // Service workers need a secure origin: https, or localhost while developing.
    const secure = location.protocol === 'https:' || ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
    if (!('serviceWorker' in navigator) || !secure) return;

    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js', { scope: '/' }).then((reg) => {
            const offerUpdate = (worker) => { waitingWorker = worker; set('updateReady', true); };
            if (reg.waiting && navigator.serviceWorker.controller) offerUpdate(reg.waiting);
            reg.addEventListener('updatefound', () => {
                const worker = reg.installing;
                if (!worker) return;
                worker.addEventListener('statechange', () => {
                    if (worker.state === 'installed' && navigator.serviceWorker.controller) offerUpdate(worker);
                });
            });
            // Look for a new version when the app comes back to the foreground.
            document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') reg.update().catch(() => {}); });
        }).catch((err) => console.warn('Offline support is unavailable:', err));

        navigator.serviceWorker.addEventListener('controllerchange', () => { if (updating) location.reload(); });
    });
})();
