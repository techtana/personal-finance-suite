#!/bin/bash
# VM bootstrap for the private finance server.
# Runs as root on EVERY boot (GCE startup-script) and is idempotent.
#
#   Docker (hardened)  ->  the app container, published on 127.0.0.1:8080 only
#   Tailscale Serve    ->  https://<hostname>.<tailnet>.ts.net  (valid TLS, tailnet-only)
#   Data               ->  separate persistent disk mounted at /srv/finance
set -Eeuo pipefail

MD="http://metadata.google.internal/computeMetadata/v1"
md()   { curl -fsS -H 'Metadata-Flavor: Google' "$MD/$1"; }
attr() { md "instance/attributes/$1" 2>/dev/null || true; }
guest_attr() { # publish progress so deploy.sh can poll it
  curl -fsS -X PUT --data "$2" -H 'Metadata-Flavor: Google' \
    "$MD/instance/guest-attributes/finance/$1" >/dev/null 2>&1 || true
}
trap 'guest_attr status "error: line $LINENO"; echo "bootstrap failed at line $LINENO" >&2' ERR
log() { echo "[finance-bootstrap] $*"; }

PROJECT="$(md project/project-id)"
TS_HOSTNAME="$(attr ts-hostname)";       TS_HOSTNAME="${TS_HOSTNAME:-finance}"
SECRET_NAME="$(attr ts-authkey-secret)"; SECRET_NAME="${SECRET_NAME:-finance-ts-authkey}"
APP_IMAGE="$(attr app-image)"
REGISTRY_HOST="$(attr registry-host)"
BACKUP_BUCKET="$(attr backup-bucket)"
BACKUP_PREFIX="$(attr backup-prefix)";   BACKUP_PREFIX="${BACKUP_PREFIX:-finance-backups/}"
ALLOWED_LOGINS="$(attr allowed-logins | tr ';' ',')"
AI_HOME_RUNNER="$(attr ai-home-runner)"; AI_HOME_RUNNER="${AI_HOME_RUNNER:-1}"
[[ -n "$APP_IMAGE" && -n "$REGISTRY_HOST" ]]

DATA_DEV=/dev/disk/by-id/google-finance-data
DATA_MNT=/srv/finance
APP_DIR=/opt/finance
APP_UID=10001          # the user the image runs as
APT="apt-get -o DPkg::Lock::Timeout=600 -y -q"
export DEBIAN_FRONTEND=noninteractive

guest_attr status "bootstrapping"

# ---------------------------------------------------------------- swap (e2-micro has 1 GB RAM)
if [[ ! -f /swapfile ]]; then
  log "creating 1G swap"
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
swapon --show | grep -q /swapfile || swapon /swapfile

# ---------------------------------------------------------------- packages
if ! command -v docker >/dev/null || ! command -v jq >/dev/null; then
  log "installing docker + tools"
  $APT update
  $APT install ca-certificates curl gnupg jq openssl unattended-upgrades
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  # shellcheck disable=SC1091
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  $APT update
  $APT install docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi
if ! command -v tailscale >/dev/null; then
  log "installing tailscale"
  curl -fsSL https://tailscale.com/install.sh | sh
fi

# ---------------------------------------------------------------- automatic security updates + 04:00 reboot if needed
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
cat > /etc/apt/apt.conf.d/52finance-unattended <<'EOF'
Unattended-Upgrade::Origins-Pattern { "origin=*"; };
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
EOF

# ---------------------------------------------------------------- docker daemon hardening
mkdir -p /etc/docker
DAEMON_JSON='{
  "log-driver": "local",
  "log-opts": { "max-size": "10m", "max-file": "3" },
  "no-new-privileges": true,
  "live-restore": true,
  "userland-proxy": false
}'
if [[ "$(cat /etc/docker/daemon.json 2>/dev/null)" != "$DAEMON_JSON" ]]; then
  echo "$DAEMON_JSON" > /etc/docker/daemon.json
  systemctl restart docker
fi
systemctl enable --now docker >/dev/null

# ---------------------------------------------------------------- data disk
if [[ ! -e "$DATA_DEV" ]]; then
  echo "data disk $DATA_DEV not attached" >&2; false
fi
if ! blkid "$DATA_DEV" >/dev/null 2>&1; then
  log "formatting data disk"
  mkfs.ext4 -q -m 0 -L finance-data -E lazy_itable_init=0,discard "$DATA_DEV"
fi
mkdir -p "$DATA_MNT"
grep -q 'LABEL=finance-data' /etc/fstab || \
  echo "LABEL=finance-data $DATA_MNT ext4 defaults,nofail,noatime,discard 0 2" >> /etc/fstab
mountpoint -q "$DATA_MNT" || mount "$DATA_MNT"
mkdir -p "$DATA_MNT/data" "$DATA_MNT/secrets"
chown "$APP_UID:$APP_UID" "$DATA_MNT/data"
chmod 700 "$DATA_MNT/data" "$DATA_MNT/secrets"

# ---------------------------------------------------------------- tailscale join (auth key only needed on first boot)
systemctl enable --now tailscaled >/dev/null
ts_state() { tailscale status --json 2>/dev/null | jq -r '.BackendState // "Unknown"'; }
for _ in $(seq 1 30); do
  case "$(ts_state)" in NoState|Starting|Unknown) sleep 2 ;; *) break ;; esac
done
if [[ "$(ts_state)" != "Running" ]]; then
  log "joining tailnet"
  TOKEN="$(md instance/service-accounts/default/token | jq -r .access_token)"
  TS_AUTHKEY="$(curl -fsS -H "Authorization: Bearer $TOKEN" \
    "https://secretmanager.googleapis.com/v1/projects/$PROJECT/secrets/$SECRET_NAME/versions/latest:access" \
    | jq -r .payload.data | base64 -d)"
  tailscale up --auth-key="$TS_AUTHKEY" --hostname="$TS_HOSTNAME" --accept-dns=false
  unset TS_AUTHKEY TOKEN
fi
TS_FQDN="$(tailscale status --json | jq -r '.Self.DNSName' | sed 's/\.$//')"
[[ -n "$TS_FQDN" && "$TS_FQDN" != "null" ]]
APP_URL="https://$TS_FQDN"
log "tailnet name: $TS_FQDN"

# ---------------------------------------------------------------- app config
mkdir -p "$APP_DIR"; chmod 700 "$APP_DIR"
if [[ ! -s "$DATA_MNT/secrets/secret_key" ]]; then
  ( umask 077; openssl rand -hex 32 > "$DATA_MNT/secrets/secret_key" )
fi
# Yours to edit: extra settings such as AI_ENDPOINTS=... (see deploy/README.md). Kept across deploys.
[[ -f "$DATA_MNT/secrets/extra.env" ]] || ( umask 077; : > "$DATA_MNT/secrets/extra.env" )
( umask 077; cat > "$APP_DIR/.env" <<EOF
FLASK_ENV=production
SECRET_KEY=$(cat "$DATA_MNT/secrets/secret_key")
FINANCE_DB_PATH=/data/finance.db
IMPORT_STORAGE_DIR=/data/imports
# Only Tailscale Serve can reach the app (it is published on loopback), so its identity headers are believed.
TRUST_TAILSCALE_HEADERS=1
ALLOWED_LOGINS=$ALLOWED_LOGINS
GOOGLE_CLOUD_PROJECT=$PROJECT
GCS_BACKUP_BUCKET=$BACKUP_BUCKET
GCS_BACKUP_PREFIX=$BACKUP_PREFIX
# The bucket expires old backups; this server has no right to delete any.
BACKUP_PRUNE=bucket
# No model runs on this small VM. AI work goes to the home runner or to endpoints in extra.env.
LLM_PROVIDER=off
AI_HOME_RUNNER=$AI_HOME_RUNNER
EOF
cat "$DATA_MNT/secrets/extra.env" >> "$APP_DIR/.env"
)

cat > "$APP_DIR/docker-compose.yml" <<EOF
services:
  app:
    image: $APP_IMAGE
    container_name: finance
    env_file: .env
    ports:
      - "127.0.0.1:8080:8080"     # loopback only; Tailscale Serve is the only way in
    volumes:
      - $DATA_MNT/data:/data
    read_only: true
    tmpfs:
      - /tmp
    cap_drop: [ALL]
    security_opt:
      - no-new-privileges:true
    mem_limit: 640m
    pids_limit: 256
    restart: unless-stopped
EOF

# Pull with the VM's own identity (a short-lived token), then (re)start.
cat > "$APP_DIR/update.sh" <<EOF
#!/bin/bash
set -euo pipefail
TOKEN="\$(curl -fsS -H 'Metadata-Flavor: Google' "$MD/instance/service-accounts/default/token" | jq -r .access_token)"
echo "\$TOKEN" | docker login -u oauth2accesstoken --password-stdin "https://$REGISTRY_HOST" >/dev/null
docker compose -f "$APP_DIR/docker-compose.yml" up -d --pull always --remove-orphans
docker logout "https://$REGISTRY_HOST" >/dev/null
docker image prune -f >/dev/null
EOF
chmod 700 "$APP_DIR/update.sh"

log "starting the app"
"$APP_DIR/update.sh"

# ---------------------------------------------------------------- weekly restore drill (Sun 05:00)
# Downloads the newest backup into a scratch file and checks that it opens. Changes nothing.
cat > /etc/systemd/system/finance-restore-drill.service <<'EOF'
[Unit]
Description=Check that the newest finance backup restores
After=docker.service
[Service]
Type=oneshot
ExecStart=/usr/bin/docker exec finance flask --app app:create_app backups verify
EOF
cat > /etc/systemd/system/finance-restore-drill.timer <<'EOF'
[Unit]
Description=Weekly finance restore drill
[Timer]
OnCalendar=Sun *-*-* 05:00:00
Persistent=true
RandomizedDelaySec=15m
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now finance-restore-drill.timer >/dev/null

# ---------------------------------------------------------------- health + HTTPS via Tailscale Serve
for _ in $(seq 1 45); do
  curl -fsS http://127.0.0.1:8080/healthz 2>/dev/null | grep -q '"ok"' && break
  sleep 2
done
curl -fsS http://127.0.0.1:8080/healthz | grep -q '"ok"'

# Requires MagicDNS + "HTTPS Certificates" enabled in the Tailscale admin console (DNS page).
# (timeout: if HTTPS isn't enabled, tailscale waits for you to enable it in a browser)
timeout 120 tailscale serve --bg --https=443 http://127.0.0.1:8080

guest_attr url "$APP_URL"
guest_attr status "ready"
log "ready at $APP_URL"
