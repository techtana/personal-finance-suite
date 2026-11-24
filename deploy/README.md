# Deploying the finance server

A private server on Google Cloud that only your Tailscale devices can reach. You run every
step here yourself: the scripts create billable resources and need a Tailscale key. The first
deploy and a re-deploy over the existing VM have both been run with these scripts. Design and reasons: [docs/design/cloud-server-and-ai-endpoints.md](../docs/design/cloud-server-and-ai-endpoints.md).

**What it costs.** A small VM, a 10 GB disk with snapshots, Cloud NAT and a storage bucket,
running all month. Google's free tier covers one e2-micro VM per billing account; if the Logseq
server already uses it, this VM is billed. Check current prices before you start.

## Before you start

1. **Tailscale admin console**
   - *DNS*: MagicDNS and HTTPS Certificates are on (already true if the Logseq server works).
   - *Access controls*: merge the lines from [policy-reference.hujson](policy-reference.hujson)
     into the live policy: the `tag:finance` owner line and the one grant. Do not add any rule
     that starts from `tag:finance`. The grant's `src` must be a group your policy really
     defines; if it has no `group:owner`, use what your other rules use, e.g. `autogroup:member`.
   - *Settings → Keys*: generate an auth key: **not reusable, pre-approved, tag `tag:finance`**.
2. **Google Cloud**: a project with billing, and you signed in to `gcloud` as its owner.
3. **This repository**: a checkout of the branch to deploy, with the stylesheet built
   (`static/build/tailwind.css` is committed; `python scripts/build_css.py` rebuilds it).

## Deploy

From the repository root, in Cloud Shell or any bash with `gcloud` signed in (Git Bash on
Windows works). The script sets the project for its own run only; your default `gcloud`
project is not changed.

```bash
PROJECT_ID=your-project-id ALLOWED_LOGINS=you@example.com ./deploy/deploy.sh
```

Paste the Tailscale key once when asked and press Enter. The input is hidden, so nothing
appears; don't paste again, or the key ends up on your command line when the script finishes.
The script prints the app's address when the server is up, about 10 minutes in all on the
first run.

- `ALLOWED_LOGINS` is a comma-separated list of Tailscale logins. Leave it out on the first run
  to let in everyone the tailnet rule allows. On a re-deploy, leaving it out keeps the list the
  VM already has; set it to change the list, or `ALLOWED_LOGINS=` to remove it.
- To allow just yourself without typing your login, take it from Tailscale on this computer:
  `ALLOWED_LOGINS="$(tailscale status --json | python -c "import json,sys; s=json.load(sys.stdin); print(s['User'][str(s['Self']['UserID'])]['LoginName'])")"`
- To share the Logseq server's network and NAT in the same project, add
  `NET=logseq-net SUBNET=logseq-subnet ROUTER=logseq-router NAT=logseq-nat`.
- Run the same command again to ship a new version: it rebuilds the image, then stops and
  starts the VM so it boots on the new image. The app is offline for about two minutes; the data
  disk is not touched. No Tailscale key and no SSH are needed the second time.

## After the first deploy

1. **Open the address** on a device that is on the tailnet. Then try it from a device that is
   off the tailnet: it must not load.
2. **Move your data across.**
   - On the computer that has your data, start the app as before, open Settings → Backups,
     enter the project and the bucket the script printed, and click **Back up now**.
   - On the server's address, open Settings → Backups and click **Restore** on that backup.
3. **Check the backups.** Settings → Backups on the server should say the server cannot delete
   backups, and list a new scheduled backup within a day. Run the restore drill once:

   ```bash
   gcloud compute ssh finance --zone us-central1-a --tunnel-through-iap -- sudo docker exec finance flask --app app:create_app backups verify
   ```

4. **Install it** on each phone and computer from the app's menu (Install app).
5. **Stop using the old local copy**, so there is one place where data changes.

## AI from your home computer

The server has no model of its own. On the desktop with the GPU (Ollama running), the
simplest way is the desktop app: double-click `install-desktop.cmd`; its tray shares the PC's
AI with the server whenever it is running. Or, in a checkout of this repository:

```bash
python home_runner.py --server https://finance.<your-tailnet>.ts.net
```

Leave it running (a scheduled task at sign-in works). While it runs, the AI features appear on
every device and Settings → This device shows "Your home computer · ready". When it stops, the
assistant is hidden everywhere and dropped photos wait until it is back. Only outbound
connections are made; no tailnet rule towards your desktop is needed.

To require a shared secret as well, add `AI_RUNNER_TOKEN=<long random text>` to
`/srv/finance/secrets/extra.env` on the VM and set the same variable where the runner starts.

## AI in your own cloud (optional)

For AI when the home computer is off. **Never run; check it before relying on it.**

```bash
AI_PROJECT_ID=your-ai-project FINANCE_SA=finance-vm@your-project-id.iam.gserviceaccount.com ./deploy/ai-endpoint/deploy.sh
```

- `AI_PROJECT_ID` can be the finance project or a separate one.
- Default: the service sleeps when idle, bills per use, and is used for batch work only.
- `MIN_INSTANCES=1` keeps it running like a full-time VM: quick enough for the assistant, and
  billed every hour of the month.

The script ends by printing one `AI_ENDPOINTS=...` line. Put it in
`/srv/finance/secrets/extra.env` on the VM (admin shell below), then run `deploy/deploy.sh`
again.

A paid API is added the same way, as another entry in that list with `"kind": "paid"` and the
features you allow, for example `"features": ["import"]`. It is used only for those, and only
after every endpoint you own. Its key goes in `extra.env` as its own variable, named by
`"api_key_env"`.

## When something is wrong

| Symptom | Look at |
|---|---|
| The address doesn't load, and `tailscale status` doesn't list `finance` | Tailscale hides devices you have no rule to reach: the `tag:finance` grant is missing from the live policy, or its `src` doesn't include you |
| The address doesn't load, but `finance` is listed | Is this device connected to Tailscale? The first request can take a few seconds while the certificate is issued |
| "This Tailscale account isn't allowed" | `ALLOWED_LOGINS` doesn't include that login. Re-run the deploy with the right list, or with `ALLOWED_LOGINS=` to remove the list (break-glass: the deploy uses gcloud, not the tailnet) |
| Backups fail with a permission error | The bucket's IAM should give the VM account `objectCreator` and `objectViewer`, nothing more |
| A save is refused, asking to reload | Another device changed that entry first. Reload and repeat the change |
| AI features are missing | Settings → This device says why for each one |

Admin shell, without any public SSH:

```bash
gcloud compute ssh finance --zone us-central1-a --tunnel-through-iap
```

- App logs: `sudo docker logs finance --tail 100`
- Bootstrap log: `sudo journalctl -u google-startup-scripts -n 200`
- Restart the app on the current image: `sudo /opt/finance/update.sh`

**If Tailscale itself is down** you still have your data: the newest backup is in the bucket
(`gcloud storage ls gs://<bucket>/finance-backups/`), and it opens with the app on any
computer (Settings → Backups → Restore, signed in with `gcloud auth application-default login`).
