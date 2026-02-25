"""Configuration management for the blog pipeline."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config.yaml"
DATA_DIR = ROOT_DIR / "data"
SITE_DIR = ROOT_DIR / "site"


def _load_dotenv() -> None:
    """Load .env file into os.environ if it exists."""
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def load_config() -> dict:
    """Load and return the global config, with env-var overrides."""
    _load_dotenv()

    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)

    # Allow environment variable overrides
    if tag := os.getenv("AMAZON_TAG_JA"):
        cfg["affiliate"]["amazon_associate_tag_ja"] = tag
    if tag := os.getenv("AMAZON_TAG_EN"):
        cfg["affiliate"]["amazon_associate_tag_en"] = tag
    if api_key := os.getenv("GEMINI_API_KEY"):
        cfg["gemini"]["api_key"] = api_key
    if rakuten_key := os.getenv("RAKUTEN_ACCESS_KEY"):
        cfg["affiliate"]["rakuten_access_key"] = rakuten_key
    # Legacy env var name fallback
    if not cfg["affiliate"].get("rakuten_access_key") and (legacy := os.getenv("RAKUTEN_APP_ID")):
        cfg["affiliate"]["rakuten_access_key"] = legacy

    return cfg


def get_data_path(filename: str) -> Path:
    """Return a path inside the data/ directory."""
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / filename


def get_content_dir(lang: str) -> Path:
    """Return the Hugo content directory for a given language."""
    path = SITE_DIR / "content" / lang
    path.mkdir(parents=True, exist_ok=True)
    return path
