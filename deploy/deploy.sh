#!/usr/bin/env bash
# Deploy the finance app as a private, Tailscale-only server on Google Cloud.
# Same shape as logseq-sync-gcp: a small VM with no public IP, Tailscale Serve as the only
# way in, a separate data disk with daily snapshots. On top of that: the app's own
# database backups go to a bucket the server can add to but not delete from.
#
# Run it yourself, from a machine with an authenticated gcloud (Cloud Shell works), in a
# checkout of this repository:
#
#   PROJECT_ID=my-project ALLOWED_LOGINS=you@example.com ./deploy/deploy.sh
#
# Safe to re-run: existing resources are left as they are, the image is rebuilt and the
# VM picks it up. Read deploy/README.md first; it lists what to set up in Tailscale.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${PROJECT_ID:?Set PROJECT_ID, e.g. PROJECT_ID=my-project ./deploy/deploy.sh}"
REGION="${REGION:-us-central1}"
ZONE="${ZONE:-${REGION}-a}"
NAME="${NAME:-finance}"                    # VM name AND Tailscale hostname
MACHINE_TYPE="${MACHINE_TYPE:-e2-micro}"   # 1 GB RAM is enough for one household
DISK_TYPE="${DISK_TYPE:-pd-standard}"
DATA_DISK_GB="${DATA_DISK_GB:-10}"
IMAGE_FAMILY="${IMAGE_FAMILY:-debian-12}"
SNAPSHOT_DAYS="${SNAPSHOT_DAYS:-14}"
BACKUP_BUCKET="${BACKUP_BUCKET:-${PROJECT_ID}-finance-backups}"
BACKUP_PREFIX="${BACKUP_PREFIX:-finance-backups/}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"  # scheduled backups older than this are removed by the bucket
ALLOWED_LOGINS="${ALLOWED_LOGINS:-}"        # comma-separated Tailscale logins; empty = anyone the tailnet lets in
AI_HOME_RUNNER="${AI_HOME_RUNNER:-1}"       # let a home computer collect AI work (home_runner.py)

# To share an existing private network and its Cloud NAT in the same project instead of paying
# for a second NAT, set all four, e.g. NET=logseq-net SUBNET=logseq-subnet ROUTER=logseq-router NAT=logseq-nat.
NET="${NET:-finance-net}"; SUBNET="${SUBNET:-finance-subnet}"; SUBNET_RANGE="${SUBNET_RANGE:-10.81.0.0/24}"
ROUTER="${ROUTER:-finance-router}"; NAT="${NAT:-finance-nat}"
SA_NAME=finance-vm; SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SECRET=finance-ts-authkey
DATA_DISK="${NAME}-data"; POLICY=finance-daily-snapshots
REPO=finance; IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/app:latest"

say()    { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
exists() { "$@" >/dev/null 2>&1; }

[[ -s static/build/tailwind.css ]] || {
  echo "static/build/tailwind.css is missing. Run: python scripts/build_css.py" >&2; exit 1; }

gcloud config set project "$PROJECT_ID" >/dev/null
VM_EXISTS=0; exists gcloud compute instances describe "$NAME" --zone "$ZONE" && VM_EXISTS=1

if [[ "$VM_EXISTS" == 0 ]]; then
  if [[ -z "${TS_AUTHKEY:-}" ]]; then
    echo "Paste a Tailscale auth key (one-off, pre-approved, tagged tag:finance):"
    read -rs TS_AUTHKEY; echo
  fi
  TS_AUTHKEY="${TS_AUTHKEY//$'\r'/}"; TS_AUTHKEY="${TS_AUTHKEY// /}"   # strip CR/spaces from Windows pastes
  [[ "$TS_AUTHKEY" == tskey-* ]] || { echo "That doesn't look like a Tailscale auth key." >&2; exit 1; }
fi

say "Enabling APIs"
gcloud services enable compute.googleapis.com secretmanager.googleapis.com iap.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com storage.googleapis.com

say "Network: private VPC, no public IP, egress via Cloud NAT"
exists gcloud compute networks describe "$NET" || \
  gcloud compute networks create "$NET" --subnet-mode=custom
exists gcloud compute networks subnets describe "$SUBNET" --region "$REGION" || \
  gcloud compute networks subnets create "$SUBNET" --network "$NET" --region "$REGION" \
    --range "$SUBNET_RANGE" --enable-private-ip-google-access
# New VPCs deny all ingress by default. The ONLY inbound rule: SSH from Google's IAP proxy.
exists gcloud compute firewall-rules describe "${NET}-allow-iap-ssh-${NAME}" || \
  gcloud compute firewall-rules create "${NET}-allow-iap-ssh-${NAME}" --network "$NET" \
    --direction INGRESS --action ALLOW --rules tcp:22 \
    --source-ranges 35.235.240.0/20 --target-tags "$NAME"
exists gcloud compute routers describe "$ROUTER" --region "$REGION" ||   gcloud compute routers create "$ROUTER" --network "$NET" --region "$REGION"
exists gcloud compute routers nats describe "$NAT" --router "$ROUTER" --region "$REGION" ||   gcloud compute routers nats create "$NAT" --router "$ROUTER" --region "$REGION"     --auto-allocate-nat-external-ips --nat-all-subnet-ip-ranges

say "Least-privilege service account"
exists gcloud iam service-accounts describe "$SA_EMAIL" || {
  gcloud iam service-accounts create "$SA_NAME" --display-name "Finance app VM"
  sleep 10   # IAM propagation
}
for role in roles/logging.logWriter roles/monitoring.metricWriter; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$SA_EMAIL" \
    --role "$role" --condition=None >/dev/null
done

say "Backup bucket: private, the server can add and read but never delete"
exists gcloud storage buckets describe "gs://$BACKUP_BUCKET" || \
  gcloud storage buckets create "gs://$BACKUP_BUCKET" --location "$REGION" \
    --uniform-bucket-level-access --public-access-prevention --soft-delete-duration=30d
LIFECYCLE="$(mktemp)"
cat > "$LIFECYCLE" <<EOF
{"rule": [{"action": {"type": "Delete"},
           "condition": {"age": ${BACKUP_KEEP_DAYS}, "matchesPrefix": ["${BACKUP_PREFIX}"], "matchesSuffix": ["_scheduled.db"]}}]}
EOF
gcloud storage buckets update "gs://$BACKUP_BUCKET" --lifecycle-file "$LIFECYCLE" >/dev/null
rm -f "$LIFECYCLE"
# objectCreator can add new objects but not overwrite or delete; objectViewer can list and read.
for role in roles/storage.objectCreator roles/storage.objectViewer; do
  gcloud storage buckets add-iam-policy-binding "gs://$BACKUP_BUCKET" \
    --member "serviceAccount:$SA_EMAIL" --role "$role" >/dev/null
done

say "Building the app image"
exists gcloud artifacts repositories describe "$REPO" --location "$REGION" || \
  gcloud artifacts repositories create "$REPO" --repository-format docker --location "$REGION" \
    --description "Finance app images"
gcloud artifacts repositories add-iam-policy-binding "$REPO" --location "$REGION" \
  --member "serviceAccount:$SA_EMAIL" --role roles/artifactregistry.reader >/dev/null
gcloud builds submit --tag "$IMAGE" .

say "Data disk + daily snapshots (kept ${SNAPSHOT_DAYS} days)"
exists gcloud compute disks describe "$DATA_DISK" --zone "$ZONE" || \
  gcloud compute disks create "$DATA_DISK" --zone "$ZONE" --size "${DATA_DISK_GB}GB" --type "$DISK_TYPE"
exists gcloud compute resource-policies describe "$POLICY" --region "$REGION" || \
  gcloud compute resource-policies create snapshot-schedule "$POLICY" --region "$REGION" \
    --daily-schedule --start-time 09:00 --max-retention-days "$SNAPSHOT_DAYS" \
    --on-source-disk-delete keep-auto-snapshots
gcloud compute disks add-resource-policies "$DATA_DISK" --zone "$ZONE" \
  --resource-policies "$POLICY" >/dev/null 2>&1 || true

METADATA="ts-hostname=${NAME},ts-authkey-secret=${SECRET},app-image=${IMAGE},registry-host=${REGION}-docker.pkg.dev"
METADATA+=",backup-bucket=${BACKUP_BUCKET},backup-prefix=${BACKUP_PREFIX},ai-home-runner=${AI_HOME_RUNNER}"
# Logins contain commas between them; metadata values are comma-separated, so store them with ';'.
METADATA+=",allowed-logins=${ALLOWED_LOGINS//,/;}"

if [[ "$VM_EXISTS" == 0 ]]; then
  say "Storing the Tailscale auth key in Secret Manager (deleted after the VM joins)"
  if exists gcloud secrets describe "$SECRET"; then
    printf %s "$TS_AUTHKEY" | gcloud secrets versions add "$SECRET" --data-file=- >/dev/null
  else
    printf %s "$TS_AUTHKEY" | gcloud secrets create "$SECRET" --replication-policy automatic --data-file=- >/dev/null
  fi
  unset TS_AUTHKEY
  gcloud secrets add-iam-policy-binding "$SECRET" --member "serviceAccount:$SA_EMAIL" \
    --role roles/secretmanager.secretAccessor >/dev/null

  say "VM: Shielded, OS Login, no external IP"
  gcloud compute instances create "$NAME" --zone "$ZONE" \
    --machine-type "$MACHINE_TYPE" \
    --subnet "$SUBNET" --no-address \
    --image-family "$IMAGE_FAMILY" --image-project debian-cloud \
    --boot-disk-size 10GB --boot-disk-type "$DISK_TYPE" \
    --disk "name=${DATA_DISK},device-name=finance-data,mode=rw,boot=no,auto-delete=no" \
    --service-account "$SA_EMAIL" --scopes cloud-platform \
    --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring \
    --tags "$NAME" \
    --metadata "enable-oslogin=TRUE,block-project-ssh-keys=TRUE,enable-guest-attributes=TRUE,serial-port-enable=FALSE,${METADATA}" \
    --metadata-from-file startup-script=deploy/startup.sh \
    --deletion-protection
else
  say "VM exists: updating its settings and restarting the app on the new image"
  gcloud compute instances add-metadata "$NAME" --zone "$ZONE" \
    --metadata-from-file startup-script=deploy/startup.sh --metadata "$METADATA"
  gcloud compute ssh "$NAME" --zone "$ZONE" --tunnel-through-iap \
    --command 'sudo google_metadata_script_runner startup' || true
fi

say "Waiting for the server to come up (first boot takes 3-6 minutes)"
status=""
for _ in $(seq 1 90); do
  status="$(gcloud compute instances get-guest-attributes "$NAME" --zone "$ZONE" \
    --query-path finance/status --format 'value(value)' 2>/dev/null | tr -d '\r' || true)"
  printf '\r  status: %-40s' "${status:-booting}"
  [[ "$status" == ready || "$status" == error* ]] && break
  sleep 10
done
echo
if [[ "$status" != ready ]]; then
  echo "Bootstrap did not finish (status: ${status:-unknown}). Inspect logs with:" >&2
  echo "  gcloud compute ssh $NAME --zone $ZONE --tunnel-through-iap -- sudo journalctl -u google-startup-scripts -n 200" >&2
  exit 1
fi
URL="$(gcloud compute instances get-guest-attributes "$NAME" --zone "$ZONE" \
  --query-path finance/url --format 'value(value)' | tr -d '\r')"

if exists gcloud secrets describe "$SECRET"; then
  say "Removing the auth key from Secret Manager (Tailscale's state now lives on the VM)"
  gcloud secrets delete "$SECRET" --quiet
fi

cat <<EOF

  The finance app is up and reachable ONLY from your tailnet:

      $URL

  Backups:       gs://$BACKUP_BUCKET/$BACKUP_PREFIX  (daily; the server cannot delete them)
  Disk snapshots: daily, kept $SNAPSHOT_DAYS days
  Service account (give it run.invoker on a private AI service): $SA_EMAIL

  Admin shell (via IAP, no public SSH):
      gcloud compute ssh $NAME --zone $ZONE --tunnel-through-iap
  Restore drill, any time:
      gcloud compute ssh $NAME --zone $ZONE --tunnel-through-iap -- sudo docker exec finance flask --app app:create_app backups verify

  Next: deploy/README.md, "After the first deploy".
EOF
