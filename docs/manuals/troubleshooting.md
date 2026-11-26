# Troubleshooting

Find what you see in the left column. Server-specific problems are also covered in [deploy/README.md](../../deploy/README.md).

## Health checks

| Check | How | Normal |
|---|---|---|
| Is the app up? | Open `<address>/healthz` | `{"ok": true}` |
| Is the app up (on the server)? | `curl http://127.0.0.1:8080/healthz` in an admin shell | `{"ok": true}` |
| Which features work here? | **Settings → This device** | Each feature says it works, or why not |
| Is the import AI reachable? | `flask --app app:create_app imports status` | `ready` |
| Do backups restore? | `flask --app app:create_app backups verify` | `ok: <name> ... opens cleanly` |
| Is the server on my tailnet? | `tailscale status` | Lists `finance` |
| Is Serve set up (one computer)? | `tailscale serve status` | `https://<machine>.<tailnet>.ts.net (tailnet only)` |
| Server logs | `sudo docker logs finance --tail 100` in an admin shell | No tracebacks |
| Server boot log | `sudo journalctl -u google-startup-scripts -n 200` | Ends with the app ready |
| Desktop tray log | `%LOCALAPPDATA%\PersonalFinance\tray.log`, or **Open the log** in the tray | "tray started", then what it is doing |

Open an admin shell on the server with:

```bash
gcloud compute ssh finance --zone us-central1-a --tunnel-through-iap
```

## Opening the app

| What you see | Likely cause | Fix |
|---|---|---|
| "Can't reach your finance app" (with **Try again**) | This device can't reach the computer or server running the app | Check that Tailscale is connected on this device, and that the app is running there |
| "Can't reach the app. Check that it is running and that this device is connected." | Same, while using a page | Same |
| 502 error on a `ts.net` address | Tailscale Serve is up, but the app behind it isn't running | Start `flask run` (one computer), or check the server logs |
| The address doesn't load; `tailscale status` doesn't list `finance` | Your tailnet policy doesn't let you reach the server | Fix the grant in the live tailnet policy; see [deploy/README.md](../../deploy/README.md) |
| The address doesn't load; `finance` is listed | This device isn't connected, or the first HTTPS request is waiting for its certificate | Connect Tailscale and wait a few seconds |
| "This Tailscale account isn't allowed to open this app." | Your login isn't in `ALLOWED_LOGINS` | Re-deploy with the right list |
| The phone won't offer to install the app | The address isn't HTTPS | Use the `https://...ts.net` address, not an IP address |
| "A new version is ready." | A newer version is running | Click **Reload** |
| A change merged into the code doesn't show on the server | The server only gets new code when you deploy | Run `deploy/deploy.sh` again |

## Saving and data

| What you see | Likely cause | Fix |
|---|---|---|
| "... was changed by ... after this page loaded it. Reload to see the latest version, then make your change again." | Another device saved the same thing first | Reload, then make your change again |
| `database is locked` | Two processes use the same database file | Stop the extra one and restart the app. Run only one app process per database |
| `ModuleNotFoundError` | The Python environment isn't active | Activate `.venv` and run `pip install -r requirements.txt` |
| The guide you followed says `flask db upgrade` and it fails | There is no migrations folder | Skip it. The app creates the database when it starts |

## Backups

| What you see | Likely cause | Fix |
|---|---|---|
| "No Google Cloud Storage bucket is set. Add one under Settings → Backups." | No bucket configured | Enter the project and bucket in **Settings → Backups** |
| "Could not sign in to Google Cloud ..." | No Google credentials on this computer | Run `gcloud auth application-default login` |
| "The google-cloud-storage package is not installed." | Missing package | `pip install -r requirements.txt` |
| "Could not list backups in gs://...", "Upload to ... failed", "Download of ... failed" | Bucket name, permission or network | Check the bucket name and that this account may read and write it |
| "Last scheduled backup failed: ..." | The last scheduled run hit one of the errors above | Fix the cause, then click **Back up now** |
| "This server can add backups but not delete them." | Expected on the server (`BACKUP_PRUNE=bucket`) | Nothing to fix. A bucket rule removes old scheduled backups |
| "The restore point is damaged" / "is not a readable database" / "is not a Personal Finance Suite database" | The chosen file is broken or isn't a backup of this app | Pick another restore point |
| "Nothing was deleted because the cloud backup failed: ..." | **Clear All Data** stopped because its safety backup failed | Fix backups first |
| "No backups found in gs://..." (from `backups verify`) | Empty bucket or wrong folder | Make a backup first, or check the folder name |

If Tailscale is down and you must restore, list the bucket with `gcloud storage ls gs://<bucket>/finance-backups/`, then restore from **Settings → Backups** on any computer that has run `gcloud auth application-default login`.

## Import and AI

| What you see | Likely cause | Fix |
|---|---|---|
| AI buttons are missing | No model is reachable from this device | **Settings → This device** says why |
| "The local AI is turned off (LLM_PROVIDER=off)." | AI is off on this install | Set `LLM_PROVIDER`, or connect the home computer |
| "LLM_BASE_URL points at ..., not this computer." | The model address isn't local, and remote use is off | Use a local address, or set `LLM_ALLOW_REMOTE=1` on purpose (your data then goes there) |
| "Model ... isn't available on ..." | The model isn't downloaded | `ollama pull qwen3.5:9b` (or your `LLM_MODEL`) |
| "Can't reach the local AI at ..." | Ollama isn't running | Start Ollama |
| "Waiting for the home computer" on an import | The server's AI is the home computer, and it is off | Turn on the PC with the desktop app, or run `home_runner.py`. The file is read when it connects |
| "The home computer isn't connected right now." | Same | Same |
| "The home computer didn't answer in time." | The model is slow or busy | Try again; raise `AI_RUNNER_TIMEOUT` if it keeps happening |
| "AI_ENDPOINTS isn't valid JSON: ..." | A typo in the `AI_ENDPOINTS` setting | Fix the JSON in `extra.env` and re-deploy |
| "... files aren't supported." | HEIC photo or old `.xls` file | Save as JPEG, `.xlsx` or `.csv` |
| "The file is over 20 MB." | File too large | Split it, or raise `IMPORT_MAX_FILE_MB` |
| Money in and out are swapped | The bank uses the other sign convention | Click **Flip signs** |
| Columns are wrong | The table layout wasn't recognised | Fix the mapping and click **Re-read with these columns** |
| A stock-plan document "couldn't be read" | Only RSU grant notices are read so far | Add the grant by hand in **Plan** |

## Desktop app

| What you see | Likely cause | Fix |
|---|---|---|
| "Python from python.org is needed" | No `py` launcher | `winget install --id Python.Python.3.13 --scope user`, then run `install-desktop.cmd` again |
| "Installing failed; see the messages above." | pip, Python or the shortcut step failed | Read the messages in the window |
| "No server found. Connect Tailscale, or choose "Run the app on this computer instead"." | Tailscale is off, or no device named `finance` is on the tailnet | Connect Tailscale, or set `server_url` in `settings.json` |
| "Can't reach the finance server. Check that Tailscale is connected." | The server didn't answer `/healthz` | Connect Tailscale; check the server |
| Starting it again does nothing new | The tray is already running | It opens the running app; look for the icon in the notification area |
| "AI runner not started: ..." in `tray.log` | The local model is off or blocked | See the AI rows above |

## Deploy

| What you see | Likely cause | Fix |
|---|---|---|
| "Set PROJECT_ID, e.g. PROJECT_ID=my-project ./deploy/deploy.sh" | `PROJECT_ID` not given | Add it to the command |
| "static/build/tailwind.css is missing." | The compiled stylesheet isn't in this checkout | `python scripts/build_css.py` (needs Node.js) |
| "That doesn't look like a Tailscale auth key." | The pasted text doesn't start with `tskey-` | Paste the key again, once |
| "Bootstrap did not finish (status: ...)" | The VM's startup script failed or took too long | Read the boot log; `error: line N` names the failing line of `deploy/startup.sh` |
| The deploy waits a long time at `tailscale serve` | HTTPS certificates are off in the tailnet | Turn them on in the Tailscale admin console's DNS page |
