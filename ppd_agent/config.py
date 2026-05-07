"""Centralised configuration loaded from ``$PPD_HOME/.env``.

Path resolution priority (highest first):

1. Explicit env vars (``PPD_DATA_DIR`` etc.) — full override.
2. ``$PPD_HOME`` — base directory; subfolders ``data/raw``, ``data/parquet``,
   ``data/plots`` and ``.env`` live inside it.
3. **Dev-mode fallback**: if a sibling ``data/`` folder exists next to the
   ``ppd_agent/`` package on disk, use it (so working from a checkout of the
   repo "just works" without setting any env var).
4. ``~/.ppd`` (the production default after ``ppd init``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
_DEV_DATA_DIR = REPO_ROOT / "data"


def _resolve_home() -> Path:
    """Resolve ``PPD_HOME`` once, with the priority described above."""
    env_home = os.getenv("PPD_HOME")
    if env_home:
        return Path(env_home).expanduser()
    if _DEV_DATA_DIR.is_dir():
        # working out of a repo checkout — keep using the repo's data folder
        return REPO_ROOT
    return Path.home() / ".ppd"


PPD_HOME: Path = _resolve_home()


# Load .env *before* the dataclass field defaults run, so values are visible
# to ``os.getenv`` calls inside the dataclass.
_DOTENV_PATH = PPD_HOME / ".env"
if _DOTENV_PATH.is_file():
    load_dotenv(_DOTENV_PATH)
else:
    # Fallback: also load a project-local .env if present (dev convenience).
    load_dotenv()


def _parse_user_ids(raw: str) -> list[int]:
    if not raw:
        return []
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


def _default_data_dir() -> Path:
    return Path(os.getenv("PPD_DATA_DIR", str(PPD_HOME / "data")))


def _default_subdir(env_var: str, leaf: str) -> Path:
    explicit = os.getenv(env_var)
    if explicit:
        return Path(explicit)
    return _default_data_dir() / leaf


@dataclass(frozen=True)
class Config:
    home: Path = field(default_factory=lambda: PPD_HOME)
    env_path: Path = field(default_factory=lambda: _DOTENV_PATH)

    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("PPD_MODEL", "anthropic/claude-sonnet-4"))
    site_url: str = field(default_factory=lambda: os.getenv("PPD_SITE_URL", ""))
    app_name: str = field(default_factory=lambda: os.getenv("PPD_APP_NAME", "PPD Assistant"))

    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_allowed_user_ids: list[int] = field(
        default_factory=lambda: _parse_user_ids(os.getenv("TELEGRAM_ALLOWED_USER_IDS", ""))
    )

    data_dir: Path = field(default_factory=_default_data_dir)
    raw_dir: Path = field(default_factory=lambda: _default_subdir("PPD_RAW_DIR", "raw"))
    parquet_dir: Path = field(default_factory=lambda: _default_subdir("PPD_PARQUET_DIR", "parquet"))
    plots_dir: Path = field(default_factory=lambda: _default_subdir("PPD_PLOTS_DIR", "plots"))

    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    def ensure_dirs(self) -> None:
        for d in (self.home, self.data_dir, self.raw_dir, self.parquet_dir, self.plots_dir):
            d.mkdir(parents=True, exist_ok=True)


CONFIG = Config()
CONFIG.ensure_dirs()
