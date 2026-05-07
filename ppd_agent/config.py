"""Centralised configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent


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


@dataclass(frozen=True)
class Config:
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("PPD_MODEL", "anthropic/claude-sonnet-4"))
    site_url: str = field(default_factory=lambda: os.getenv("PPD_SITE_URL", ""))
    app_name: str = field(default_factory=lambda: os.getenv("PPD_APP_NAME", "PPD Assistant"))

    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_allowed_user_ids: list[int] = field(
        default_factory=lambda: _parse_user_ids(os.getenv("TELEGRAM_ALLOWED_USER_IDS", ""))
    )

    data_dir: Path = field(default_factory=lambda: Path(os.getenv("PPD_DATA_DIR", str(REPO_ROOT / "data"))))
    raw_dir: Path = field(default_factory=lambda: Path(os.getenv("PPD_RAW_DIR", str(REPO_ROOT / "data" / "raw"))))
    parquet_dir: Path = field(default_factory=lambda: Path(os.getenv("PPD_PARQUET_DIR", str(REPO_ROOT / "data" / "parquet"))))
    plots_dir: Path = field(default_factory=lambda: Path(os.getenv("PPD_PLOTS_DIR", str(REPO_ROOT / "data" / "plots"))))

    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.raw_dir, self.parquet_dir, self.plots_dir):
            d.mkdir(parents=True, exist_ok=True)


CONFIG = Config()
CONFIG.ensure_dirs()
