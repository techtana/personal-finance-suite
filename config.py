import os
from datetime import timedelta

_BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _llm_env(name: str, default: str) -> str:
    """LLM_<name>, falling back to the importer's original IMPORT_LLM_<name>."""
    return os.environ.get(f"LLM_{name}", os.environ.get(f"IMPORT_LLM_{name}", default))


class Config:
    """Base configuration."""

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-in-production")

    # Database — default to absolute path inside instance/ next to this file
    _default_db = os.path.join(_BASE_DIR, "instance", "finance.db")
    FINANCE_DB_PATH = os.environ.get("FINANCE_DB_PATH", _default_db)
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{FINANCE_DB_PATH}"

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # JSON
    JSON_SORT_KEYS = False

    # Local model, shared by every feature that uses AI (llm.py) ─────────────
    # By default the Ollama server the personal agent stack already runs, so the
    # model it keeps loaded is reused rather than a second copy started.
    #   provider "ollama": native /api/chat, JSON-schema constrained output, photos.
    #   provider "openai": any OpenAI-compatible server, e.g. the stack's LiteLLM
    #                      gateway (http://127.0.0.1:4000/v1, model local-small).
    #   provider "off":    no AI; features fall back to rules.
    # Environment: LLM_<NAME>, or the older IMPORT_LLM_<NAME>.
    LLM_PROVIDER = _llm_env("PROVIDER", "ollama")
    LLM_BASE_URL = _llm_env("BASE_URL", "http://127.0.0.1:11434")
    LLM_MODEL = _llm_env("MODEL", "qwen3.5:9b")
    LLM_VISION_MODEL = _llm_env("VISION_MODEL", "")  # empty = same as LLM_MODEL
    LLM_API_KEY = _llm_env("API_KEY", "")
    # Match the context size the agent stack loads the model with, or Ollama reloads it.
    LLM_NUM_CTX = int(_llm_env("NUM_CTX", "32768"))
    LLM_TIMEOUT = int(_llm_env("TIMEOUT", "180"))
    LLM_THINK = _llm_env("THINK", "0") == "1"
    # Financial data stays on this machine unless this is set to 1.
    LLM_ALLOW_REMOTE = _llm_env("ALLOW_REMOTE", "0") == "1"

    # More places AI work can run (ai/endpoints.py) ───────────────────────────
    # The LLM_* settings above describe one endpoint. To use several, or one that is
    # only right for batch work, list them here as JSON; this replaces LLM_*. Each entry:
    #   name, kind ("server" | "own-cloud" | "paid"), provider, base_url, model,
    #   vision_model, api_key or api_key_env, auth ("google-id-token" for a private
    #   Cloud Run service), use_for (["realtime", "batch"]), assume_up (true for a
    #   service that sleeps until called), features (paid only: ["assistant", "import"]).
    # A paid endpoint is used only for the features it lists, and only after every
    # endpoint you own.
    AI_ENDPOINTS = os.environ.get("AI_ENDPOINTS", "")
    # A computer at home with a GPU can do the work without the server ever connecting
    # to it: home_runner.py there asks this app for jobs. Tried before any other endpoint.
    AI_HOME_RUNNER = os.environ.get("AI_HOME_RUNNER", "0") == "1"
    AI_RUNNER_TOKEN = os.environ.get("AI_RUNNER_TOKEN", "")      # optional shared secret for the runner
    AI_RUNNER_TIMEOUT = int(os.environ.get("AI_RUNNER_TIMEOUT", "300"))

    # Behind Tailscale Serve (audit.py) ───────────────────────────────────────
    # Believe the Tailscale-User-Login header. Only safe when the app listens on
    # 127.0.0.1 and Tailscale Serve is the only thing that can reach it.
    TRUST_TAILSCALE_HEADERS = os.environ.get("TRUST_TAILSCALE_HEADERS", "0") == "1"
    # Optional second lock: comma-separated Tailscale logins that may use the app.
    ALLOWED_LOGINS = [x.strip().lower() for x in os.environ.get("ALLOWED_LOGINS", "").split(",") if x.strip()]

    # Backups ────────────────────────────────────────────────────────────────
    # "app": the app deletes old scheduled backups itself (it needs delete rights).
    # "bucket": the app can only add and read backups; a bucket lifecycle rule expires
    #           old ones, so nothing running on the server can erase the history.
    BACKUP_PRUNE = os.environ.get("BACKUP_PRUNE", "app")

    # File import (drop statements, receipts, pay stubs) ─────────────────────
    IMPORT_STORAGE_DIR = os.environ.get("IMPORT_STORAGE_DIR", os.path.join(_BASE_DIR, "instance", "imports"))
    IMPORT_MAX_FILE_MB = int(os.environ.get("IMPORT_MAX_FILE_MB", "20"))
    IMPORT_SYNC = False  # process uploads inside the request (tests) instead of on the worker thread
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False
    TESTING = False

    # Enforce security headers in production
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Strict"


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    LLM_PROVIDER = "off"
    IMPORT_SYNC = True
    AI_ENDPOINTS = ""
    AI_HOME_RUNNER = False
    AI_RUNNER_TOKEN = ""
    TRUST_TAILSCALE_HEADERS = False
    ALLOWED_LOGINS = []
    BACKUP_PRUNE = "app"


def get_config():
    """Get config based on FLASK_ENV."""
    env = os.environ.get("FLASK_ENV", "development")

    if env == "production":
        return ProductionConfig
    elif env == "testing":
        return TestingConfig
    else:
        return DevelopmentConfig
