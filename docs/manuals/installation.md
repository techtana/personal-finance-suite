# Installation manual

For whoever sets the app up. There are three ways to run it. Pick one before you start.

| Way | What it is | Who uses it |
|---|---|---|
| **A. One computer** | `flask run` on your own computer; you open it in a browser there | Trying it out, developing |
| **B. Windows desktop app** | A Start menu entry and a tray icon. It opens your private server, or runs a copy on this PC | Everyday use on a Windows PC |
| **C. Private cloud server** | A small Google Cloud VM that only your Tailscale devices can reach. It holds the one copy of your data | Using the same data from phone, laptop and desktop |

The usual household setup is **C** for the data, **B** on the Windows PC with the GPU (it also shares that PC's AI with the server), and the installable web app on each phone.

Set them up in this order:

1. Tailscale on every device ([step C1](#c1-before-you-start)).
2. The server ([C](#c-private-cloud-server)).
3. The desktop app on the Windows PC ([B](#b-windows-desktop-app)).
4. Each phone or laptop ([Add a phone or another device](#add-a-phone-or-another-device)).

## What you need

- Python 3.9 or newer for A; Python from python.org, with the `py` launcher, for B. The server image uses Python 3.12.
- Optional, for AI features: [Ollama](https://ollama.com) on a computer with a GPU, with the model pulled (`ollama pull qwen3.5:9b`). Everything except photos and scanned PDFs works without it.
- Optional, for backups: a Google Cloud project with a private Storage bucket, and the `gcloud` command-line tool.
- For C: a Tailscale account, a Google Cloud project with billing, and Git Bash or Cloud Shell to run the deploy script.

## A. One computer

1. Get the code and open a terminal in the folder:

   ```bash
   cd personal-finance-suite
   ```

2. Create a Python environment:

   ```bash
   python -m venv .venv
   ```

3. Activate it. On Windows:

   ```bash
   .venv\Scripts\activate
   ```

   On macOS or Linux:

   ```bash
   source .venv/bin/activate
   ```

4. Install the packages:

   ```bash
   pip install -r requirements.txt
   ```

5. Optional: copy `.env.example` to `.env` and set `SECRET_KEY`. Make a key with:

   ```bash
   python -c "import secrets; print(secrets.token_hex())"
   ```

6. Start the app:

   ```bash
   flask run
   ```

7. Open http://localhost:5000. You should see **Overview** with "Three steps to a first picture".

The database `instance/finance.db` is created the first time the app starts. There is no `flask db upgrade` step: the app creates its tables and adds any missing columns by itself.

If you see `ModuleNotFoundError`, the environment isn't active. Repeat steps 3 and 4.

Keep the app on `127.0.0.1`. Never start it with `--host 0.0.0.0`: it has no sign-in, so anyone on your network could open it. To reach it from a phone, use Tailscale Serve ([below](#reach-a-one-computer-install-from-a-phone)).

### Backups for a one-computer install

1. Create a private bucket in your Google Cloud project, for example `<project-id>-finance-backups`.
2. Sign in once on this computer:

   ```bash
   gcloud auth application-default login
   ```

3. In the app, open **Settings → Backups**. Enter the **Google Cloud project** and **Bucket**, pick **Regular backup**, and click **Save**. Then click **Back up now**. A row should appear under **Restore points**.

### Reach a one-computer install from a phone

1. Install Tailscale on the computer and the phone, signed in to the same tailnet. In the Tailscale admin console, on the DNS page, turn on MagicDNS and HTTPS certificates.
2. Start the app with `flask run`.
3. Once, on the computer:

   ```bash
   tailscale serve --bg 5000
   ```

4. Check it:

   ```bash
   tailscale serve status
   ```

   You should see `https://<machine>.<tailnet>.ts.net (tailnet only)` pointing at `http://127.0.0.1:5000`.
5. On the phone, with Tailscale connected, open `https://<machine>.<tailnet>.ts.net/overview` and install it ([below](#add-a-phone-or-another-device)).

Never use `tailscale funnel` for this app: Funnel puts it on the public internet. To stop sharing:

```bash
tailscale serve --https=443 off
```

## B. Windows desktop app

1. Install Python from python.org if `py` doesn't work in a terminal:

   ```bash
   winget install --id Python.Python.3.13 --scope user
   ```

2. In the project folder, double-click `install-desktop.cmd`. It:
   - copies the app to `%LOCALAPPDATA%\Programs\PersonalFinance` and builds its own Python environment there;
   - adds **Personal Finance** to the Start menu;
   - looks on your tailnet for a device named `finance` and saves its address;
   - starts the tray.

3. You should see "Started. Look for the Personal Finance icon in the notification area." If no server was found, it says so; the tray looks again each time you open the app.

4. Optional: start the tray when you sign in. Tick **Start when I sign in** in the tray menu, or install with:

   ```bash
   py -3 desktop\install.py --autostart
   ```

The tray shows as **Finance** in Task Manager. Its settings and log are in `%LOCALAPPDATA%\PersonalFinance` (`settings.json`, `tray.log`).

| `settings.json` key | Default | Meaning |
|---|---|---|
| `mode` | `server` | `server` opens your private server; `local` runs a copy on this PC |
| `server_url` | empty | The server's address, such as `https://finance.<tailnet>.ts.net`. Found through Tailscale when empty |
| `share_ai` | `true` | Share this PC's AI with the server (server mode only) |
| `runner_name` | `home computer` | The name the server shows for this PC |

With **Run the app on this computer instead** ticked, the tray runs the app on `http://127.0.0.1:5057`. That copy has its own data in `%LOCALAPPDATA%\PersonalFinance\data`, separate from the server.

**Update:** double-click `install-desktop.cmd` again. Code is replaced; settings and data are kept.

**Remove:**

```bash
py -3 desktop\install.py --uninstall
```

This removes the app and its shortcuts. Settings and local data stay in `%LOCALAPPDATA%\PersonalFinance`; delete that folder by hand if you want them gone.

On macOS or Linux there is no installer. Run `python desktop/tray.py --open` instead.

## C. Private cloud server

The full steps, settings and costs are in [deploy/README.md](../../deploy/README.md). Follow that file; this section only gives the order and the checks.

### C1. Before you start

1. In the Tailscale admin console: MagicDNS and HTTPS certificates on.
2. Add the `tag:finance` owner line and the one grant from [deploy/policy-reference.hujson](../../deploy/policy-reference.hujson) to your live tailnet policy. The grant's `src` must be a group that exists in your policy. No rule may start from `tag:finance`.
3. Create an auth key: not reusable, pre-approved, tagged `tag:finance`. Keep it ready to paste.
4. Sign `gcloud` in as an owner of the Google Cloud project.

### C2. Deploy

From the project folder, in Git Bash or Cloud Shell:

```bash
PROJECT_ID=<project-id> ALLOWED_LOGINS=you@example.com ./deploy/deploy.sh
```

Paste the auth key once at the hidden prompt. The first run takes about 10 minutes and shows `booting`, `bootstrapping`, then `ready`. It ends with "The finance app is up and reachable ONLY from your tailnet:" and the address.

If it stops with "static/build/tailwind.css is missing", run `python scripts/build_css.py` (needs Node.js) and deploy again.

### C3. After the first deploy

1. Open the address on a tailnet device. It should load. On a device that isn't on the tailnet it must not.
2. Move your data across. On the old computer: **Settings → Backups → Back up now**. On the server: **Settings → Backups**, then **Restore** that backup.
3. On the server, **Settings → Backups** should say it can add backups but not delete them.
4. Run the restore check (it changes nothing):

   ```bash
   gcloud compute ssh finance --zone us-central1-a --tunnel-through-iap -- sudo docker exec finance flask --app app:create_app backups verify
   ```

   You should see `ok: <name> from <time> opens cleanly`.
5. Install the app on each device ([below](#add-a-phone-or-another-device)), and the desktop app on the Windows PC ([B](#b-windows-desktop-app)).
6. Stop using the old local copy.

### Share the PC's AI with the server

The desktop app (B) does this by itself while **Share this PC's AI with the server** is ticked. Without it, run this on a computer with Ollama:

```bash
python home_runner.py --server https://finance.<tailnet>.ts.net
```

On the server, **Settings → This device** should then show the home computer as ready. The home computer only makes outgoing connections; the server never connects to it.

### Update the server

Merging code changes nothing on the server. Run the deploy command again. Leave `ALLOWED_LOGINS` out to keep the current allowlist; set it to change it (`ALLOWED_LOGINS=` empties it). The script prints how many logins are allowed before it changes anything. The script updates the VM's settings and restarts it on the new image. The app is offline for about two minutes; the data disk is not touched.

## Add a phone or another device

1. Install Tailscale on the device and sign in to the same tailnet.
2. Check that your tailnet policy's grant covers that person. If the server uses `ALLOWED_LOGINS`, their login must be on the list (re-deploy with the new list to change it).
3. Open `https://finance.<tailnet>.ts.net` (or your one-computer address).
4. Install it:
   - **Android (Chrome):** menu → **Install app**, or **Install app** in the app's menu.
   - **iPhone (Safari):** Share → **Add to Home Screen**.
   - **Computer (Chrome or Edge):** **Install app** in the sidebar, or the install icon in the address bar.

The installed app keeps only its own styles, scripts, icons and offline page on the device. Your financial data is never stored there.

## Remove a device

Remove it from your tailnet in the Tailscale admin console. That alone cuts its access. If it was listed in `ALLOWED_LOGINS` and the person should lose access everywhere, re-deploy with the list updated.

## Settings reference

The app reads these environment variables (from `.env` on a one-computer install, from `/srv/finance/secrets/extra.env` on the server). Secret values never go in the repo.

| Variable | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | a development key | Signs the session. Set your own |
| `FINANCE_DB_PATH` | `instance/finance.db` | The database file |
| `IMPORT_STORAGE_DIR` | `instance/imports` | Copies of dropped files |
| `IMPORT_MAX_FILE_MB` | `20` | Largest file Import takes |
| `LLM_PROVIDER` | `ollama` | `ollama`, `openai` (any OpenAI-compatible server) or `off` |
| `LLM_BASE_URL` | `http://127.0.0.1:11434` | Model server address |
| `LLM_MODEL` | `qwen3.5:9b` | Model name |
| `LLM_VISION_MODEL` | same as `LLM_MODEL` | Model for photos |
| `LLM_API_KEY` | empty | Key for the model server, if it needs one |
| `LLM_NUM_CTX` | `32768` | Context size. Keep it equal to the agent stack's value, or Ollama reloads the model |
| `LLM_TIMEOUT` | `180` | Seconds per model call |
| `LLM_THINK` | `0` | `1` turns on the model's thinking mode |
| `LLM_ALLOW_REMOTE` | `0` | `1` allows a model server that isn't this computer. That sends your data there |
| `AI_ENDPOINTS` | empty | A JSON list of further AI endpoints (your own cloud, a paid API for named features). See [deploy/README.md](../../deploy/README.md) |
| `AI_HOME_RUNNER` | `0` | `1` lets a home computer collect AI work. The deploy sets `1` |
| `AI_RUNNER_TOKEN` | empty | Optional shared secret between server and home runner |
| `AI_RUNNER_TIMEOUT` | `300` | Seconds to wait for the home computer |
| `TRUST_TAILSCALE_HEADERS` | `0` | `1` trusts Tailscale's "who is asking" header. Only behind Tailscale Serve. The deploy sets `1` |
| `ALLOWED_LOGINS` | empty | Comma-separated Tailscale logins allowed in. Empty means anyone your tailnet lets through |
| `BACKUP_PRUNE` | `app` | `bucket`: the app only adds backups; a bucket rule removes old ones |
| `GOOGLE_CLOUD_PROJECT`, `GCS_BACKUP_BUCKET`, `GCS_BACKUP_PREFIX` | empty, empty, `finance-backups/` | Defaults for **Settings → Backups** |

The older `IMPORT_LLM_*` names still work; `LLM_*` wins when both are set.
