#!/usr/bin/env bash
# Optional: your own AI endpoint in the cloud, for when the home computer is off.
# A Cloud Run service with a GPU running Ollama. Nobody can call it anonymously; only the
# finance server's service account may (Google checks the identity token the app sends).
#
# NOT YET RUN: written from Google's documentation, never deployed. Check the flags against
# `gcloud run deploy --help` and expect to need a GPU quota in the region before it works.
#
#   AI_PROJECT_ID=my-ai-project FINANCE_SA=finance-vm@my-project.iam.gserviceaccount.com ./deploy/ai-endpoint/deploy.sh
#
# AI_PROJECT_ID can be the finance project or a separate one. A separate project keeps the
# GPU budget and the model images away from the project that holds your data, and other apps
# of yours can share it.
#
# Two ways to run it:
#   MIN_INSTANCES=0 (default)  Sleeps when idle and bills per second of use. Waking takes from
#                              tens of seconds to minutes, so use it for batch work only.
#   MIN_INSTANCES=1            Always on, like a full-time VM: fast enough for the assistant,
#                              and it bills every hour of the month whether used or not.
set -euo pipefail
cd "$(dirname "$0")"

: "${AI_PROJECT_ID:?Set AI_PROJECT_ID (the finance project, or a separate one for AI)}"
: "${FINANCE_SA:?Set FINANCE_SA to the finance VM service account (deploy.sh prints it)}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-finance-ai}"
MODEL="${MODEL:-qwen3.5:9b}"
GPU_TYPE="${GPU_TYPE:-nvidia-l4}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"
REPO=ai; IMAGE="${REGION}-docker.pkg.dev/${AI_PROJECT_ID}/${REPO}/ollama-${MODEL//[:.]/-}:latest"

say()    { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
exists() { "$@" >/dev/null 2>&1; }

# For this run only: the default project of whoever runs the script is left alone.
# Never stop to ask (a hidden "enable this API?" question would hang the script).
export CLOUDSDK_CORE_DISABLE_PROMPTS=1
export CLOUDSDK_CORE_PROJECT="$AI_PROJECT_ID"

say "Enabling APIs"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

say "Building the model image (the model is downloaded once, here)"
exists gcloud artifacts repositories describe "$REPO" --location "$REGION" || \
  gcloud artifacts repositories create "$REPO" --repository-format docker --location "$REGION" \
    --description "Private model servers"
BUILD_CONFIG="$(mktemp)"
cat > "$BUILD_CONFIG" <<EOF
steps:
  - name: gcr.io/cloud-builders/docker
    args: [build, --build-arg, "MODEL=${MODEL}", -t, "${IMAGE}", .]
images: ["${IMAGE}"]
options: {machineType: E2_HIGHCPU_8, diskSizeGb: 100}
timeout: 3600s
EOF
gcloud builds submit --config "$BUILD_CONFIG" .
rm -f "$BUILD_CONFIG"

say "Deploying $SERVICE (GPU, private, min instances: $MIN_INSTANCES)"
gcloud run deploy "$SERVICE" --image "$IMAGE" --region "$REGION" \
  --gpu 1 --gpu-type "$GPU_TYPE" --no-gpu-zonal-redundancy \
  --cpu 4 --memory 16Gi --no-cpu-throttling \
  --concurrency 1 --min-instances "$MIN_INSTANCES" --max-instances 1 \
  --timeout 900 --port 8080 \
  --no-allow-unauthenticated

say "Letting only the finance server call it"
gcloud run services add-iam-policy-binding "$SERVICE" --region "$REGION" \
  --member "serviceAccount:$FINANCE_SA" --role roles/run.invoker >/dev/null

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')"
if [[ "$MIN_INSTANCES" == 0 ]]; then USE='["batch"]'; UP=true; else USE='["realtime","batch"]'; UP=false; fi

cat <<EOF

  Private AI endpoint: $URL

  Add this ONE line to /srv/finance/secrets/extra.env on the finance VM, then re-run
  deploy/deploy.sh (or restart the app) so it takes effect:

  AI_ENDPOINTS=[{"name":"$SERVICE","kind":"own-cloud","provider":"ollama","base_url":"$URL","model":"$MODEL","auth":"google-id-token","use_for":$USE,"assume_up":$UP,"timeout":600}]

  Settings → This device in the app then lists it under "Where AI work runs".
EOF
