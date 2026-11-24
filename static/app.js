// Personal Finance Suite - shared front-end helpers

// ── Formatting ───────────────────────────────────────────────────────────────
const _money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
const _moneyWhole = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

function formatCurrency(cents, currencyCode = 'USD') {
    if (currencyCode !== 'USD') return new Intl.NumberFormat('en-US', { style: 'currency', currency: currencyCode }).format(cents / 100);
    return _money.format(cents / 100);
}
// Headline figures (tiles, chart labels): whole dollars read faster than cents.
function fmtWhole(cents) { return _moneyWhole.format(Math.round((cents || 0) / 100)); }

function formatDate(dateObj) {
    if (typeof dateObj === 'string') return dateObj;
    return dateObj.toISOString().split('T')[0];
}

function parseDate(isoString) {
    return new Date(isoString + 'T00:00:00Z');
}

// ── API ──────────────────────────────────────────────────────────────────────
// Every call either returns parsed JSON or throws an Error whose message can be shown as is.
async function _request(method, endpoint, data) {
    let response;
    try {
        response = await fetch(`/api${endpoint}`, {
            method,
            headers: data === undefined ? {} : { 'Content-Type': 'application/json' },
            body: data === undefined ? undefined : JSON.stringify(data),
        });
    } catch (e) {
        throw new Error("Can't reach the app. Check that it is running and that this device is connected.");
    }
    if (!response.ok) {
        let message = `The app answered with error ${response.status}.`;
        try { const body = await response.json(); if (body && body.error) message = body.error; } catch (e) { /* not JSON */ }
        throw new Error(message);
    }
    if (response.status === 204) return true;
    return response.json();
}

const API = {
    get: (endpoint) => _request('GET', endpoint),
    post: (endpoint, data) => _request('POST', endpoint, data ?? {}),
    patch: (endpoint, data) => _request('PATCH', endpoint, data ?? {}),
    delete: (endpoint) => _request('DELETE', endpoint),
};

// ── Toasts ───────────────────────────────────────────────────────────────────
// showAlert(message, type, { action: { label, run }, duration })
// Bottom of the screen on phones (above the tab bar), top right on wide screens.
// Errors are announced assertively; everything else politely.
const TOAST_ICONS = {
    success: '<path d="M20 6 9 17l-5-5"/>',
    error: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
    warning: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
};

function _toastRegion(kind) {
    const id = kind === 'error' ? 'toasts-alert' : 'toasts';
    let region = document.getElementById(id);
    if (!region) {
        region = document.createElement('div');
        region.id = id;
        region.className = 'toasts';
        region.setAttribute('role', kind === 'error' ? 'alert' : 'status');
        region.setAttribute('aria-live', kind === 'error' ? 'assertive' : 'polite');
        document.body.appendChild(region);
    }
    return region;
}

function showAlert(message, type = 'info', opts = {}) {
    const kind = TOAST_ICONS[type] ? type : 'info';
    const toast = document.createElement('div');
    toast.className = `toast toast-${kind}`;
    const icon = `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${TOAST_ICONS[kind]}</svg>`;
    const text = document.createElement('span');
    text.className = 'toast-text';
    text.textContent = message;
    toast.innerHTML = icon;
    toast.appendChild(text);
    if (opts.action) {
        const btn = document.createElement('button');
        btn.type = 'button'; btn.className = 'toast-action'; btn.textContent = opts.action.label;
        btn.addEventListener('click', () => { opts.action.run(); dismiss(); });
        toast.appendChild(btn);
    }
    const close = document.createElement('button');
    close.type = 'button'; close.className = 'toast-close'; close.setAttribute('aria-label', 'Dismiss');
    close.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>';
    close.addEventListener('click', () => dismiss());
    toast.appendChild(close);
    _toastRegion(kind).appendChild(toast);

    let timer = null;
    const ms = opts.duration ?? (kind === 'error' || kind === 'warning' ? 9000 : 5000);
    const start = () => { timer = setTimeout(dismiss, ms); };
    const stop = () => clearTimeout(timer);
    toast.addEventListener('mouseenter', stop);
    toast.addEventListener('mouseleave', start);
    toast.addEventListener('focusin', stop);
    function dismiss() {
        stop();
        toast.classList.add('toast-leave');
        setTimeout(() => toast.remove(), 180);
    }
    start();
    return dismiss;
}

// Kept for older callers: a simple confirm dialog.
function showModal(title, content, onConfirm) {
    if (confirm(title + '\n\n' + content)) onConfirm();
}

// ── Charts ───────────────────────────────────────────────────────────────────
// One look for every chart. Colors are the validated categorical slots (blue, orange,
// aqua) in fixed order; ink and grid stay neutral so text never wears a series color.
const CHART = {
    series: ['#2a78d6', '#eb6834', '#1baf7a'],
    ink: '#0f172a', muted: '#64748b', grid: 'rgba(15, 23, 42, .06)', surface: '#ffffff', neutral: '#94a3b8',
};

function chartMoneyTick(v) { return fmtShort(v); }
function chartTooltipMoney(ctx) { return ' ' + ctx.dataset.label + ': ' + formatCurrency(Math.round(ctx.raw * 100)); }

// Vertical guide line under the pointer on line charts.
const crosshairPlugin = {
    id: 'crosshair',
    afterDatasetsDraw(chart) {
        const active = chart.tooltip && chart.tooltip.getActiveElements ? chart.tooltip.getActiveElements() : [];
        if (!active.length || chart.config.type !== 'line') return;
        const x = active[0].element.x, { top, bottom } = chart.chartArea, ctx = chart.ctx;
        ctx.save();
        ctx.strokeStyle = 'rgba(15, 23, 42, .25)'; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
        ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke();
        ctx.restore();
    },
};

document.addEventListener('DOMContentLoaded', () => {
    if (!window.Chart) return;
    const d = Chart.defaults;
    d.font.family = getComputedStyle(document.body).fontFamily;
    d.font.size = 12;
    d.color = CHART.muted;
    d.borderColor = CHART.grid;
    d.maintainAspectRatio = false;          // every chart sits in a .chart-box that sets its height
    d.interaction.mode = 'index';
    d.interaction.intersect = false;
    d.plugins.legend.position = 'bottom';
    d.plugins.legend.labels.boxWidth = 10;
    d.plugins.legend.labels.boxHeight = 10;
    d.plugins.legend.labels.usePointStyle = true;
    d.plugins.legend.labels.padding = 14;
    d.plugins.tooltip.backgroundColor = CHART.ink;
    d.plugins.tooltip.padding = 10;
    d.plugins.tooltip.cornerRadius = 8;
    d.plugins.tooltip.boxPadding = 4;
    d.elements.line.borderWidth = 2;
    d.elements.line.tension = 0.25;
    d.elements.point.radius = 0;
    d.elements.point.hoverRadius = 5;
    d.elements.point.hitRadius = 12;
    d.elements.bar.borderRadius = 4;
    Chart.register(crosshairPlugin);
});

window.formatCurrency = formatCurrency;
window.fmtWhole = fmtWhole;
window.formatDate = formatDate;
window.parseDate = parseDate;
window.API = API;
window.showModal = showModal;
window.showAlert = showAlert;
window.CHART = CHART;
window.chartMoneyTick = chartMoneyTick;
window.chartTooltipMoney = chartTooltipMoney;
