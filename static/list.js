// Shared list state: search, filter, sort, kept in the page address.
//
// makeList({ key, search, filters, date, amount, sorts, sort, dir })
//   key      prefix for URL parameters, so two lists can share a page
//   search   item -> text that the search box matches against
//   filters  { name: item -> value }   exact-match dropdown filters
//   date     item -> 'YYYY-MM-DD'      enables the from / to range
//   amount   item -> cents             enables min / max (compared on absolute dollars)
//   sorts    { name: item -> comparable }
function makeList(cfg) {
    const pfx = cfg.key ? cfg.key + '_' : '';
    return {
        q: '', f: {}, from: '', to: '', min: '', max: '',
        sort: cfg.sort || '', dir: cfg.dir || 'asc',
        aiText: '', aiBusy: false, aiNote: '',

        read() {
            const p = new URLSearchParams(location.search);
            this.q = p.get(pfx + 'q') || '';
            this.from = p.get(pfx + 'from') || '';
            this.to = p.get(pfx + 'to') || '';
            this.min = p.get(pfx + 'min') || '';
            this.max = p.get(pfx + 'max') || '';
            if (p.get(pfx + 'sort')) this.sort = p.get(pfx + 'sort');
            if (p.get(pfx + 'dir')) this.dir = p.get(pfx + 'dir');
            const f = {};
            for (const name of Object.keys(cfg.filters || {})) f[name] = p.get(pfx + name) || '';
            this.f = f;
        },
        sync() {
            const p = new URLSearchParams(location.search);
            const put = (k, v) => { if (v) p.set(pfx + k, v); else p.delete(pfx + k); };
            put('q', this.q); put('from', this.from); put('to', this.to); put('min', this.min); put('max', this.max);
            put('sort', this.sort === (cfg.sort || '') ? '' : this.sort);
            put('dir', this.dir === (cfg.dir || 'asc') ? '' : this.dir);
            for (const name of Object.keys(cfg.filters || {})) put(name, this.f[name]);
            const qs = p.toString();
            history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '') + location.hash);
        },
        // skip: name of one dropdown filter to ignore (e.g. totals per month while a month is picked)
        apply(items, skip) {
            const q = this.q.trim().toLowerCase();
            const min = this.min === '' ? null : parseFloat(this.min) * 100;
            const max = this.max === '' ? null : parseFloat(this.max) * 100;
            let out = (items || []).filter(it => {
                if (q && !(cfg.search ? cfg.search(it) : JSON.stringify(it)).toLowerCase().includes(q)) return false;
                for (const [name, get] of Object.entries(cfg.filters || {})) {
                    if (name !== skip && this.f[name] && String(get(it) ?? '') !== this.f[name]) return false;
                }
                if (cfg.date && (this.from || this.to)) {
                    const d = cfg.date(it) || '';
                    if (this.from && d < this.from) return false;
                    if (this.to && d > this.to) return false;
                }
                if (cfg.amount && (min !== null || max !== null)) {
                    const a = Math.abs(cfg.amount(it) || 0);
                    if (min !== null && !isNaN(min) && a < min) return false;
                    if (max !== null && !isNaN(max) && a > max) return false;
                }
                return true;
            });
            const get = (cfg.sorts || {})[this.sort];
            if (get) {
                const sign = this.dir === 'desc' ? -1 : 1;
                out = out.slice().sort((a, b) => {
                    const x = get(a), y = get(b);
                    if (x == null && y == null) return 0;
                    if (x == null) return 1;
                    if (y == null) return -1;
                    return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))) * sign;
                });
            }
            return out;
        },
        options(name, items) {
            const get = (cfg.filters || {})[name];
            return [...new Set((items || []).map(get).filter(v => v != null && v !== ''))].map(String).sort();
        },
        toggleSort(name) {
            if (this.sort === name) this.dir = this.dir === 'asc' ? 'desc' : 'asc';
            else { this.sort = name; this.dir = 'asc'; }
            this.sync();
        },
        arrow(name) { return this.sort === name ? (this.dir === 'asc' ? ' ▲' : ' ▼') : ''; },
        ariaSort(name) { return this.sort === name ? (this.dir === 'asc' ? 'ascending' : 'descending') : 'none'; },
        active() {
            return (this.q ? 1 : 0) + (this.from ? 1 : 0) + (this.to ? 1 : 0) + (this.min !== '' ? 1 : 0) + (this.max !== '' ? 1 : 0)
                + Object.values(this.f).filter(Boolean).length;
        },
        clear() {
            this.q = ''; this.from = ''; this.to = ''; this.min = ''; this.max = ''; this.aiNote = '';
            for (const k of Object.keys(this.f)) this.f[k] = '';
            this.sync();
        },
        // Words -> the same controls. The result lands in the controls so it can be checked and changed.
        async askAI(items) {
            const text = this.aiText.trim();
            if (!text) return;
            this.aiBusy = true; this.aiNote = '';
            const filters = {};
            for (const name of Object.keys(cfg.filters || {})) filters[name] = this.options(name, items);
            try {
                const r = await API.post('/assistant/filter', { text, filters, sorts: Object.keys(cfg.sorts || {}), today: todayISO() });
                const f = r.filter || {};
                this.clear();
                this.q = f.q || '';
                this.from = cfg.date ? (f.date_from || '') : ''; this.to = cfg.date ? (f.date_to || '') : '';
                this.min = cfg.amount && f.min_amount != null ? String(f.min_amount) : '';
                this.max = cfg.amount && f.max_amount != null ? String(f.max_amount) : '';
                for (const [name, value] of Object.entries(f.filters || {})) if (name in this.f) this.f[name] = value;
                if (f.sort) { this.sort = f.sort; this.dir = f.dir || 'asc'; }
                this.aiNote = this.active() > 0 || f.sort
                    ? 'Filters set from "' + text + '". Check them and adjust if needed.'
                    : 'Nothing in that matched a filter on this list.';
                this.sync();
            } catch (e) { this.aiNote = e.message; }
            finally { this.aiBusy = false; }
        },
    };
}

function fmtSigned(cents) { return (cents >= 0 ? '+' : '−') + formatCurrency(Math.abs(cents)); }
function fmtShort(v) {
    const a = Math.abs(v);
    return (v < 0 ? '−' : '') + '$' + (a >= 1e6 ? (a / 1e6).toFixed(1) + 'M' : a >= 1e3 ? (a / 1e3).toFixed(0) + 'K' : a.toFixed(0));
}
function localISO(d) { return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); }
function todayISO() { return localISO(new Date()); }
function addMonthsISO(n) { const d = new Date(); d.setMonth(d.getMonth() + n); return localISO(d); }
// Slugs become labels ("retirement_401k" -> "Retirement 401k"); anything already written by a person is left alone.
const LABELS = { rsu: 'RSU', espp: 'ESPP', etf: 'ETF', reit: 'REIT', heloc: 'HELOC', retirement_401k: '401(k)', retirement_ira: 'IRA' };
function titleCase(s) {
    s = String(s || '');
    if (LABELS[s]) return LABELS[s];
    return /^[a-z0-9_ -]+$/.test(s) ? s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : s;
}

// App-wide state: is the AI assistant usable, and how many things need attention.
document.addEventListener('alpine:init', () => {
    Alpine.store('ui', { menu: false });
    Alpine.store('app', {
        ai: { enabled: false, ok: false, model: '', error: '', loaded: false },
        // What the server can do right now (see /api/capabilities) plus who is signed in.
        caps: { loaded: false, features: [], endpoints: [], identity: {}, home_runner: {} },
        attention: 0,
        feature(id) { return this.caps.features.find(f => f.id === id) || { available: false, waiting: false, shown: false }; },
        load() {
            this.refreshAI();
            this.refreshAttention();
            // The home computer comes and goes, so look again when the app returns to the front, and now and then.
            document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') this.refreshAI(); });
            setInterval(() => { if (document.visibilityState === 'visible') this.refreshAI(); }, 60000);
        },
        refreshAI() {
            const status = API.get('/assistant/status').then(s => { this.ai = { ...s, loaded: true }; }).catch(() => { this.ai.loaded = true; });
            const caps = API.get('/capabilities').then(c => { this.caps = { ...c, loaded: true }; }).catch(() => { this.caps.loaded = true; });
            return Promise.all([status, caps]);
        },
        refreshAttention() {
            API.get('/insights').then(r => { this.attention = (r.counts || {}).attention || 0; }).catch(() => {});
        },
    });
    Alpine.store('app').load();
});

window.makeList = makeList;
window.fmtSigned = fmtSigned;
window.fmtShort = fmtShort;
window.todayISO = todayISO;
window.addMonthsISO = addMonthsISO;
window.titleCase = titleCase;
