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


# ---------------------------------------------------------------------------
# LLM provider presets
# ---------------------------------------------------------------------------

_PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
        "default_model": "anthropic/claude-sonnet-4",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
    },
    "anthropic-openai": {
        "base_url": "https://api.anthropic.com/v1",
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-20250514",
    },
    "google": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "env_key": "GOOGLE_API_KEY",
        "default_model": "gemini-2.0-flash",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "env_key": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "env_key": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
    },
}


def _resolve_provider() -> tuple[str, str, str]:
    """Return (base_url, api_key, default_model) from LLM_PROVIDER + env vars.

    Falls back to ``openrouter`` for backward compatibility.
    ``LLM_BASE_URL`` overrides the preset URL (for self-hosted endpoints).
    """
    provider = os.getenv("LLM_PROVIDER", "openrouter").lower().strip()
    preset = _PROVIDER_PRESETS.get(provider)

    if preset is None:
        base_url = os.getenv("LLM_BASE_URL", "")
        api_key = os.getenv("LLM_API_KEY", "")
        default_model = os.getenv("PPD_MODEL", "")
        if not base_url or not api_key:
            raise RuntimeError(
                f"LLM_PROVIDER='{provider}' is not a built-in preset "
                f"({', '.join(_PROVIDER_PRESETS)}). "
                "Set LLM_BASE_URL and LLM_API_KEY manually."
            )
        return base_url, api_key, default_model

    base_url = os.getenv("LLM_BASE_URL", preset["base_url"])
    api_key = os.getenv(preset["env_key"], os.getenv("LLM_API_KEY", ""))
    default_model = preset["default_model"]
    return base_url, api_key, default_model


@dataclass(frozen=True)
class Config:
    # LLM provider (resolved from LLM_PROVIDER env var)
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "openrouter"))
    llm_base_url: str = field(default_factory=lambda: _resolve_provider()[0])
    llm_api_key: str = field(default_factory=lambda: _resolve_provider()[1])
    model: str = field(default_factory=lambda: os.getenv("PPD_MODEL", "") or _resolve_provider()[2])

    # Backward compat
    openrouter_api_key: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_API_KEY", "")
    )

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

    # Rate limiting
    rate_limit_per_user: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_USER", "20"))
    )
    rate_limit_window_seconds: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    )

    # Context window management
    max_context_messages: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONTEXT_MESSAGES", "40"))
    )

    @property
    def effective_api_key(self) -> str:
        """Return the best available API key."""
        return self.llm_api_key or self.openrouter_api_key

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.raw_dir, self.parquet_dir, self.plots_dir):
            d.mkdir(parents=True, exist_ok=True)


CONFIG = Config()
CONFIG.ensure_dirs()
