# The finance app as one container. Built by deploy/deploy.sh (Cloud Build) and run on the VM
# by deploy/startup.sh, published only on the VM's loopback address for Tailscale Serve.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Fail the build, not the first page load, if the compiled stylesheet was left out.
RUN test -s static/build/tailwind.css

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001

# /data is the VM's persistent disk. Everything else in the container is read-only.
ENV FLASK_ENV=production \
    FINANCE_DB_PATH=/data/finance.db \
    IMPORT_STORAGE_DIR=/data/imports

EXPOSE 8080
# One process on purpose: the backup timer, the import worker and the queue the home
# runner reads all live in its memory. Threads serve the requests.
CMD ["waitress-serve", "--listen=0.0.0.0:8080", "--threads=8", "wsgi:app"]
