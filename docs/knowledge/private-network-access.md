# Private network access: keeping a sign-in-free app reachable only by you

## 1. What this is and why the project needs it

The finance app has no password screen. Whoever can open its address can read and change every
balance. That is a deliberate simplification for a one-household app, but it only works if the
address is reachable by nothing except the owner's own devices. The app also has to work on a
phone, and phones only install web apps from secure (HTTPS) addresses. This page explains the
tools that solve both problems at once: a private network built with Tailscale, a small server in
Google Cloud with no public address, HTTPS certificates issued for that private name, and the web
features (manifest and service worker) that turn the site into an installed app without storing
your money data on the phone. After reading it you should be able to follow `deploy/README.md`,
`deploy/startup.sh`, `audit.py` and the comments in `pages/pwa.py` and `templates/sw.js`.

## 2. The ideas, built up from zero

### Why a no-sign-in app must stay off the internet and the LAN

Picture a filing cabinet in your house with no lock. It is safe because the front door is locked
and only family has the key. The cabinet's safety is borrowed from the door. A web app with no
sign-in works the same way: its safety is borrowed from whatever stops strangers reaching it.

Two kinds of stranger matter. On the **internet**, automated scanners try every address all day,
so a public service is found within hours, and it is then open to the world. On the **local
network** (the LAN, meaning the home Wi-Fi), other devices can reach any computer that listens
on all its network interfaces. A guest's phone, a smart TV or an infected gadget would then be
able to open the app. A café or hotel network is worse. So the app listens on `127.0.0.1`
(loopback), an address that only the same computer can use. The README tells you never to start
it with `--host 0.0.0.0`, which would listen on every interface.

The analogy has one weak spot: a network "door" has to be built from software. The rest of this
page is how.

### A VPN, and a mesh VPN

A **VPN** (virtual private network) makes your devices act as if they were on one private
network, even when they are far apart, by sending their traffic through an encrypted tunnel. The
old shape was a hub: every device connects to one central server.

A **mesh** network connects devices directly to each other, and a coordination service only
introduces them and hands out keys. **Tailscale** is a mesh VPN. Your devices (phone, laptop,
desktop, the cloud server) each run a Tailscale program and sign in to the same account. That
group of devices is your **tailnet**. Under the hood Tailscale uses **WireGuard**, a modern
encrypted tunnel protocol. Each device holds a key pair, and traffic between two devices is
encrypted so that nothing in between (café Wi-Fi, your internet provider) can read it.

A device that is not on your tailnet cannot open your server's address at all. It does not get a
"wrong password" page. It gets no answer, because the address does not exist outside the tailnet.

### Names, and who may talk to whom

**MagicDNS** gives each device a name, so you type `finance` or a full name and not a number. A
device's full name looks like `finance.<tailnet>.ts.net`. `<tailnet>` is your tailnet's own
generated name and `ts.net` is Tailscale's domain. The **device name** matters in this project:
the Windows tray app finds the server by looking for a device called `finance`
(`desktop/settings.py`, `server_from_tailscale`, which reads `tailscale status --json`).

Being on the tailnet does not by default mean being allowed to reach everything. The tailnet has
an **access policy** (a file in the Tailscale admin console) that lists who may reach what. Newer
policies write this as **grants**. A grant has a source, a destination and which ports are
allowed. Destinations are often **tags**: labels such as `tag:finance` that you put on a machine
that has no human owner, like a server. A tag has **tag owners**: who may apply it. The repo's
reference copy, `deploy/policy-reference.hujson`, has three pieces: a `group:owner` group, a
`tagOwners` line for `tag:finance`, and one grant from the owner group to `tag:finance` on
`tcp:443`. There is deliberately no rule from `tag:finance` to anything. A server that cannot
start connections into your network cannot become a way into it if it is ever broken into.

That file is a redacted reference. Tailscale holds the only live policy, and nothing syncs the
file to it. You merge the lines in by hand.

A new server joins the tailnet with an **auth key**: a one-off secret that lets a machine join
without a person clicking through a login. The deploy asks for one that is not reusable, is
pre-approved and carries `tag:finance`. The script puts it in Google Secret Manager just long
enough for the VM to read it, then deletes it. Once the VM has joined, Tailscale's state lives on
the VM and the key is no longer needed.

### Tailscale Serve and Funnel, and HTTPS

The app itself speaks plain HTTP on `127.0.0.1:8080`. **Tailscale Serve** is a feature that
publishes that local port to the tailnet as an HTTPS address, with this command in
`deploy/startup.sh`:

```
tailscale serve --bg --https=443 http://127.0.0.1:8080
```

Serve does three jobs. It accepts connections only from tailnet devices. It handles TLS (the
encryption that makes `https` work) using a certificate for the device's `*.ts.net` name. And it
passes each request on to the app, adding headers that say who is asking.

For the certificate to exist, the admin console must have MagicDNS and **HTTPS Certificates**
switched on. Tailscale gets the certificate from a public certificate authority (Let's Encrypt,
source not recorded in this repo). A browser then trusts it with no warning, even though the
address is private.

**Tailscale Funnel** is the opposite. It publishes a service to the public internet. The README
says never to use it for this app. Funnel traffic does not carry the verified identity of a
tailnet user, and the whole point is that the public cannot reach the app.

### Identity headers, and why they are trusted only here

When Serve forwards a request from a tailnet user, it adds headers such as
`Tailscale-User-Login` (the account's login) and `Tailscale-User-Name`. The app uses them to
record who made a change in the activity log (`audit.py`, `identity()`), and to enforce an optional
list, `ALLOWED_LOGINS`.

A header is only text. Any program can send `Tailscale-User-Login: someone@example.com`. So the
app believes the header only when `TRUST_TAILSCALE_HEADERS=1`, and that is set only where nothing
but Serve can reach the app. Here that holds because the container's port is published as
`127.0.0.1:8080:8080` (loopback only), the VM has no public IP, and the only firewall rule lets in
SSH from Google's proxy. Serve runs on the same VM, so it is the only caller. On a single
computer the app is started on `127.0.0.1` for the same reason.

If the setting is off, the header is ignored and the caller is recorded as `local`. The test
`test_tailscale_header_is_ignored_unless_trusted` sends a forged header and checks this. If the app
were ever put on `0.0.0.0`, behind a load balancer, or on Funnel, the header could be forged by
anyone, and the whole protection would be gone.

Two edge cases come from `audit.py`. A machine that carries a tag, not a person, arrives with no
login at all. It is recorded as `tagged-device`, and when `ALLOWED_LOGINS` is set it gets a 403.
And `ALLOWED_LOGINS` is checked only when headers are trusted. The health check path `/healthz`
is always open, so the deploy script can see that the app is up.

### Why a phone needs HTTPS to install the app

A **Progressive Web App** (PWA) is a website that a phone can install to the home screen. It
opens full screen, with its own icon, like an app. Browsers require three things:

- A **web app manifest**: a JSON file that names the app, gives its icons and says which page to
  open (`/manifest.webmanifest`, built in `pages/pwa.py`; start page `/overview`, display
  `standalone`).
- A **service worker**: a script the browser runs in the background for the site, able to answer
  requests itself (see below).
- A **secure context**: the page must come over HTTPS, or be served from `localhost`. This is
  a browser rule. Powerful features, among them service workers and install, are switched off on
  plain `http://` pages, because on an open network anyone could alter the page or the script.

`localhost` counts as secure because the traffic never leaves your computer. A phone cannot use
the computer's `localhost`, and `http://192.168.x.x` is plain HTTP, so it does not install. Hence
Tailscale Serve: it gives the private server a real HTTPS name. `static/pwa.js` repeats the check
before registering the worker: HTTPS, or `localhost`, `127.0.0.1` or `[::1]`. On iPhone, Safari has
no install prompt, so the user chooses Share, then Add to Home Screen. The app shows these steps.

### What the service worker stores here, and why never `/api/`

A **service worker** sits between the page and the network. Each request first goes through its
`fetch` handler, which can answer from a saved copy (the cache) or let the request go on to the
server. `templates/sw.js` (served from `/sw.js` by `pages/pwa.py`) makes three choices:

- **Static files** (styles, scripts, icons) are saved when the worker installs. The address of
  each includes a `?v=` version, a hash of every static file's size and date. A file under one
  version never changes, so the saved copy is always right.
- **Pages** (navigation) always go to the live server. Only if the server cannot be reached does
  the worker show `templates/offline.html`, "Can't reach your finance app", with a Try again button.
- **`/api/`** is not touched at all. The handler returns before doing anything, so the browser
  fetches it straight from the server every time.

Why the last rule matters: a cached `/api/` answer is a copy of your balances sitting on a phone
that can be lost. Keeping it out means "no financial data on the device" stays true, and nothing
shown is ever out of date. The cost is that the installed app does not work offline. It shows the
offline page. That was a conscious trade. It is also on the list of "things that would quietly
undo this" in the cloud design document.

When the app changes, a new worker waits. A Reload bar appears, and the new version takes over only
when the page asks (`skipWaiting`), so an open form is never lost. `/sw.js` and the manifest are
sent with `Cache-Control: no-cache`.

### A worked example: one phone tap, from the screen to SQLite and back

You change a savings balance on your phone and tap Save.

```
phone (Tailscale on) ──WireGuard──▶ VM "finance" (no public IP)
                                      tailscaled ─▶ tailscale serve :443  (TLS ends here, adds headers)
                                                      │ http://127.0.0.1:8080
                                                      ▼
                                                 app container  (Flask)
                                                      │
                                                 SQLite file on the data disk (/srv/finance/data)
```

1. The page was loaded over `https://finance.<tailnet>.ts.net/...`. The service worker ignores the
   save, because it is an `/api/` call and it is not a GET request.
2. The Tailscale app on the phone encrypts the request with WireGuard and sends it to the
   `finance` device. Your policy has a grant for your group to reach `tag:finance` on `tcp:443`, so
   it is allowed. Without that grant the device would not even appear in `tailscale status`.
3. Serve on the VM ends the TLS, adds `Tailscale-User-Login`, and forwards plain HTTP to
   `127.0.0.1:8080`.
4. Flask first runs `_allowed_people` in `audit.py`: with `ALLOWED_LOGINS` set, a login not on the
   list gets 403.
5. The page's request carries `X-Base-Rev`, the data revision it last read. If another device
   changed the same record since, the save is refused with 409 and a "reload" message.
6. Otherwise SQLAlchemy writes the change to SQLite. The same flush adds a row to `audit_log`: time,
   login, record and the names of the changed fields. Values are never logged.
7. The answer goes back through Serve and the tunnel. It carries `X-Data-Rev`, the new revision.

At no point does the data touch the phone's cache or leave the tailnet.

### The home runner: connections that only go out

Some AI work is done by the owner's home desktop, which has the GPU. The server could in theory
reach into the home to ask it, but that would need an open path from the cloud into the house.
Instead `home_runner.py` on the desktop makes every connection itself. It sends a long poll
("any work for me?", up to 25 seconds) to `/api/ai/runner/poll`, runs what it receives on the
local model, and posts the answer to `/api/ai/runner/result`. The desktop is a normal tailnet
member that is allowed to reach the server's port 443, so no rule towards the desktop is needed.
If the runner stops, the server notices after 45 seconds and hides the AI features. An
optional `AI_RUNNER_TOKEN` adds a shared secret (`X-Runner-Token`). The analogy is a courier who
comes to collect parcels rather than a warehouse that has a key to your front door. It breaks
down in one respect: while the runner holds a job, that job's content is on the desktop, so the
desktop must be trusted too.

### A VM with no public address

The server is a Google Compute Engine virtual machine created with `--no-address`, so it has no
public IP. Three questions follow.

How does it reach the internet for updates and to join Tailscale? Through **Cloud NAT**, a Google
service that lets machines without public addresses start outgoing connections, and answers only
those. Nothing from outside can start a connection to the VM.

How do you get a shell on it? Through **IAP** (Identity-Aware Proxy), where Google lets a signed-in
person tunnel an SSH session to the VM. The only inbound firewall rule the deploy creates allows
SSH (port 22) from Google's proxy range, `35.235.240.0/20`, and the command is
`gcloud compute ssh finance --zone us-central1-a --tunnel-through-iap`. The VM uses OS Login,
and project-wide SSH keys are blocked, so access follows Google accounts. No SSH port faces the
internet.

### Add-only backups

If the server is broken into, an attacker (or a bug) with the right to delete would erase the
backups too. So the VM's service account is given only `roles/storage.objectCreator` and
`roles/storage.objectViewer` on the backup bucket. It can add new backups and read them, but it
cannot overwrite or delete any. The app is told this with `BACKUP_PRUNE=bucket`, and a **bucket
lifecycle rule** (run by Google, not by the server) removes scheduled backups older than 30 days
(`BACKUP_KEEP_DAYS`). The bucket also has a 30-day soft delete and public access prevention. The
VM's own disk is protected separately by daily snapshots kept 14 days, on a data disk that
survives deleting the VM.

## 3. Rules of thumb and typical numbers

| Value | Number | Source |
|---|---|---|
| App port, loopback only | 127.0.0.1:8080 (single computer: 5000, or 5057 in the desktop app) | project choice, `deploy/startup.sh`, README, `desktop/settings.py` |
| Port the grant opens | tcp:443 | project choice, `deploy/policy-reference.hujson` |
| IAP SSH source range | 35.235.240.0/20 | project choice, `deploy/deploy.sh` (Google's IAP range) |
| VM size | e2-micro, 1 GB RAM, with 1 GB swap | project choice, `deploy/deploy.sh`, `deploy/startup.sh` |
| Disk snapshots | daily, kept 14 days | project choice, `deploy/deploy.sh` (`SNAPSHOT_DAYS`) |
| Scheduled backups kept | 30 days, then the bucket deletes them | project choice, `deploy/deploy.sh` (`BACKUP_KEEP_DAYS`) |
| Restore drill | weekly, Sunday 05:00 | project choice, `deploy/startup.sh` |
| First deploy, and re-deploy downtime | about 10 minutes, and about 2 minutes | `deploy/README.md` |
| Runner counted as online | 45 seconds after its last poll | project choice, `ai/relay.py` |
| Auth key for the VM | one-off, pre-approved, tagged `tag:finance` | project choice, `deploy/README.md` |

## 4. Common misconceptions and edge cases

- **"My home network is private, so the app is safe on it."** Anyone or anything on that network
  can reach it, including guests and gadgets. Loopback plus Serve is stricter.
- **"Funnel is just Serve with a longer URL."** It is public. Never use it here.
- **"The identity header proves who it is."** Only when nothing except Serve can send it.
- **"The policy file in the repo is the policy."** It is a reference; the live one is in the
  Tailscale console. If a grant's `src` names a group the live policy lacks, the device is silently
  hidden (`deploy/README.md`, "When something is wrong").
- **"Install works on any address."** `http://192.168.x.x` does not install. Safari on iPhone has
  no install prompt, so the steps are manual.
- **Machine names can leak.** HTTPS certificates are logged publicly, which can expose device and
  tailnet names (source not recorded; check Tailscale's HTTPS documentation). So this repo never
  writes the real tailnet name.

## 5. How the project uses it

| Piece | Where |
|---|---|
| Deploy script: private VPC, no public IP, Cloud NAT, IAP-only SSH, service account, add-only bucket, snapshots | `deploy/deploy.sh` |
| VM bootstrap: Docker hardening, Tailscale join, app config, `tailscale serve`, restore drill | `deploy/startup.sh` |
| What to set in Tailscale and what to do after | `deploy/README.md`, `deploy/policy-reference.hujson` |
| Identity, `ALLOWED_LOGINS`, audit log, stale-save check | `audit.py` |
| Settings | `config.py`: `TRUST_TAILSCALE_HEADERS`, `ALLOWED_LOGINS`, `BACKUP_PRUNE`, `AI_HOME_RUNNER`, `AI_RUNNER_TOKEN` |
| Manifest, service worker route, offline route, versioned static URLs | `pages/pwa.py` |
| Service worker and offline page | `templates/sw.js`, `templates/offline.html`; registration and install button in `static/pwa.js` |
| Home computer pulls work | `home_runner.py`, `ai/relay.py`, `api/ai.py` |
| Desktop app finds the server by the device name `finance` | `desktop/settings.py` |
| Single-computer setup | README, "Install it as an app": `tailscale serve --bg 5000` and the Funnel warning |

Tests: `tests/test_audit.py` (`test_tailscale_header_is_ignored_unless_trusted`,
`test_only_listed_people_get_in_and_the_health_check_stays_open`), `tests/test_pwa.py`
(`test_manifest_meets_install_requirements`,
`test_service_worker_is_served_from_the_root_and_never_cached`, `test_offline_page_stands_alone`),
`tests/test_ai_endpoints.py` (`test_runner_door_is_shut_unless_the_server_turns_it_on`,
`test_runner_token_is_checked_when_one_is_set`) and `tests/test_desktop.py`
(`test_the_server_is_found_on_the_tailnet_by_its_name`).

Simplified or left out:

- **Why a VM, not Cloud Run for the app.** SQLite needs a disk that persists, and the backup timer,
  import worker and AI queue live in one process's memory.
- **No per-person permissions and no extra check for restore or clear-all.** Tailscale vouches for
  the device, not for who holds it.

Design record: [DECISIONS.md](../design/DECISIONS.md) and
[cloud-server-and-ai-endpoints.md](../design/cloud-server-and-ai-endpoints.md), whose section
"Things that would quietly undo this" lists the changes that would break the protection:
publishing on `0.0.0.0`, adding a public IP or load balancer, turning on Funnel, a rule from
`tag:finance` to a device, giving the VM delete rights on backups, and caching `/api/`.

## 6. What we found

- **2026-11-23, decision.** One server in the cloud, reachable only through Tailscale. The earlier
  idea of a public Cloud Run service with its own key and code was rejected because of the public
  URL. The plan record says phone access over HTTPS through Tailscale Serve, "not an open network
  address", because the app has no sign-in.
- **2026-11-24, first deploy.** `deploy/deploy.sh` and `deploy/startup.sh` ran for the first time
  from Git Bash on Windows, and the app came up on the tailnet. The same day, the script fixes in
  PR #5 and #7 changed the project selection (this run only, no change to the caller's default
  `gcloud` project), turned off interactive prompts, and replaced SSH with a stop-and-start of
  the VM for updates, because SSH would create an OS Login key and needs a network path the VM
  does not offer. Each run now writes its own `deploy-id`, so a "ready" from an earlier boot is
  not taken for the new one.
- **2026-11-24, not yet verified.** The weekly restore drill is installed, but its first result
  has not been looked at. The private cloud AI endpoint has never been run.
- **No security test is recorded.** The README's check is manual: open the address from a device off
  the tailnet and confirm it does not load.

## 7. Open questions

1. Settled 2026-11-24: the re-deploy path over an existing VM was used that day, after PR #7;
   `deploy/README.md` and the design document now say so.
2. What did the first weekly restore drill report?
3. Is a per-person check (before restore or clear) worth building?
4. Should the live policy be checked against the reference file, since nothing syncs the two?

## 8. Sources and further reading

- Tailscale documentation, "Tailscale Serve": https://tailscale.com/kb/1312/serve (the page the
  README links to). Covers publishing a local port to the tailnet and the identity headers.
- Tailscale documentation on Funnel (publishing to the public internet), on access control
  grants and tags, on auth keys, on MagicDNS, and on enabling HTTPS certificates.
- Mozilla, MDN Web Docs: "Secure contexts", "Using Service Workers", and "Progressive web apps:
  installability" (manifest requirements).
- Google Cloud documentation: Cloud NAT, IAP TCP forwarding, OS Login, Cloud Storage IAM roles and
  bucket lifecycle rules.
- In this repo: `deploy/README.md`, `docs/design/cloud-server-and-ai-endpoints.md` and the
  2026-11-23 and 2026-11-24 plans in `docs/design/plans/`.

## Changes

2026-11-24: first version.
