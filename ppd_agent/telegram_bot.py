"""Telegram bot wrapping :class:`PPDAgent`.

- One :class:`PPDAgent` instance per chat (so conversation history is kept per user).
- Text messages → agent.chat → reply text + plot images.
- Multi-user whitelist via TELEGRAM_ALLOWED_USER_IDS in .env.
- Long responses are chunked to fit Telegram's 4096 char message limit.
"""
from __future__ import annotations

import logging
import textwrap
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .agent import PPDAgent
from .config import CONFIG
from .data_loader import warmup

log = logging.getLogger(__name__)

TG_TEXT_LIMIT = 4000  # leave a bit of headroom under 4096


WELCOME = (
    "Halo! Saya **PPD Assistant** — agen AI untuk steel manufacturing.\n\n"
    "**Skill saya:**\n"
    "1. Product Design lookup (steel grade, chem/mech/elongation/thickness/FT-CT standards)\n"
    "2. HRC Production Analysis (filter, statistik, histogram, scatter, heatmap, lookup coil)\n"
    "3. Deboer Property Prediction (YS/TS/CE/PCM/Tnr/Ar3/Liq dari steel grade)\n"
    "4. Compliance Check (cek apakah satu coil lulus standar tertentu)\n\n"
    "Contoh pertanyaan:\n"
    "  • _Coil ASC111 lulus standar EN 10025 S275JR nggak?_\n"
    "  • _Histogram YS untuk spec MS EN 10025-2:2011 S275JR+AR_\n"
    "  • _Cari steel grade untuk KI-A36 tebal 8mm_\n"
    "  • _Prediksi Deboer untuk grade 0A1810 tebal 8mm, FT 860, CT 590_\n\n"
    "Perintah: /reset (reset percakapan), /myid (lihat user ID kamu), /help"
)


# ---------------------------------------------------------------------------
# access control
# ---------------------------------------------------------------------------


def _is_allowed(user_id: int) -> bool:
    allowed = CONFIG.telegram_allowed_user_ids
    if not allowed:
        return False
    return user_id in allowed


def _agent_for_chat(context: ContextTypes.DEFAULT_TYPE) -> PPDAgent:
    if "agent" not in context.chat_data:
        context.chat_data["agent"] = PPDAgent()
    return context.chat_data["agent"]


# ---------------------------------------------------------------------------
# command handlers
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    if not _is_allowed(user.id):
        await update.message.reply_text(
            f"Akses ditolak.\nUser ID kamu: `{user.id}`\n\n"
            "Minta admin tambahkan ID-mu ke TELEGRAM_ALLOWED_USER_IDS di .env.",
            parse_mode="Markdown",
        )
        return
    await update.message.reply_text(WELCOME, parse_mode="Markdown")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME, parse_mode="Markdown")


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    text = (
        f"User ID kamu: `{user.id}`\n"
        f"Username: @{user.username or '(none)'}\n"
        f"Akses: {'✅ ALLOWED' if _is_allowed(user.id) else '❌ NOT ALLOWED'}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or not _is_allowed(user.id):
        return
    if "agent" in context.chat_data:
        context.chat_data["agent"].reset()
    await update.message.reply_text("Percakapan di-reset. Mulai dari awal lagi.")


# ---------------------------------------------------------------------------
# message handler
# ---------------------------------------------------------------------------


def _chunk(text: str, limit: int = TG_TEXT_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    return textwrap.wrap(
        text,
        width=limit,
        replace_whitespace=False,
        drop_whitespace=False,
        break_long_words=False,
        break_on_hyphens=False,
    )


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None or update.message.text is None:
        return
    if not _is_allowed(user.id):
        await update.message.reply_text(
            f"Akses ditolak. User ID kamu: `{user.id}` — minta admin add ke whitelist.",
            parse_mode="Markdown",
        )
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    log.info("[user=%s] %s", user.id, user_text[:200])

    # show typing while LLM thinks
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    agent = _agent_for_chat(context)
    try:
        turn = agent.chat(user_text)
    except Exception as exc:
        log.exception("agent.chat failed")
        await update.message.reply_text(f"Maaf, ada error internal: {exc}")
        return

    if turn.error and not turn.text:
        await update.message.reply_text(f"Error: {turn.error}")
        return

    # send images first (so the explanatory text comes after the visual)
    for img_path in turn.image_paths:
        try:
            with open(img_path, "rb") as fh:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=fh,
                )
        except Exception as exc:
            log.exception("send_photo failed for %s", img_path)
            await update.message.reply_text(f"(gagal kirim gambar {Path(img_path).name}: {exc})")

    # send text (chunked)
    text = turn.text or "(empty response)"
    for chunk in _chunk(text):
        await update.message.reply_text(chunk)


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------


def build_app() -> Application:
    if not CONFIG.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set. Fill .env first.")
    if not CONFIG.telegram_allowed_user_ids:
        log.warning(
            "TELEGRAM_ALLOWED_USER_IDS is empty — bot will reject ALL users. "
            "Set it in .env to allow access."
        )

    app = Application.builder().token(CONFIG.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    return app


def run() -> None:
    logging.basicConfig(
        level=getattr(logging, CONFIG.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log.info("warming up data ...")
    warmup()
    log.info("starting Telegram polling ...")
    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES)
