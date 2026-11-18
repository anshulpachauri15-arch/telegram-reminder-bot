import logging
import sys
from datetime import datetime, time as dt_time
from functools import wraps

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from config import BOT_TOKEN, ALLOWED_USER_IDS, TZ, MORNING_DIGEST_HOUR, MORNING_DIGEST_MINUTE
from database import (
    init_db, register_chat, add_reminder,
    get_upcoming_reminders, get_todays_reminders,
    get_due_reminders, mark_sent, delete_reminder,
    get_all_registered_chats,
)
from date_parser import parse_reminder_datetime

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


# ── Auth ──────────────────────────────────────────────────────────────────────

def _allowed(user_id: int) -> bool:
    return not ALLOWED_USER_IDS or user_id in ALLOWED_USER_IDS


def require_auth(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_message:
            return
        uid = update.effective_user.id
        if not _allowed(uid):
            await update.effective_message.reply_text(
                f"⛔ *Not authorized.*\n\nYour Telegram user ID is `{uid}`.\n"
                "Ask the bot owner to add it to `ALLOWED_USER_IDS`.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        return await func(update, context)
    return wrapper


# ── Commands ──────────────────────────────────────────────────────────────────

@require_auth
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    register_chat(chat.id, chat.title or update.effective_user.first_name)
    uid = update.effective_user.id
    await update.effective_message.reply_text(
        "👋 *Hi! I'm your personal reminder bot!*\n\n"
        "I'll ping you at the exact time and send a morning digest every day.\n\n"
        "📋 *Commands:*\n"
        "`/remind <date> <time> <message>` — set a reminder\n"
        "`/reminders` — list all upcoming\n"
        "`/today` — today's reminders\n"
        "`/delete <id>` — remove a reminder\n"
        "`/help` — usage guide\n\n"
        "📅 *Date:* `today`, `tomorrow`, `monday`, `25/12`, `next friday`\n"
        "⏰ *Time:* `9am`, `3:30pm`, `14:00`\n\n"
        "_Example:_ `/remind tomorrow 9am Dentist appointment`\n\n"
        f"Your user ID: `{uid}`",
        parse_mode=ParseMode.MARKDOWN,
    )


@require_auth
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🤖 *Reminder Bot — Help*\n\n"
        "*Set a reminder:*\n"
        "`/remind <date> <time> <message>`\n\n"
        "*Date formats:*\n"
        "• `today`, `tomorrow`\n"
        "• `monday` … `sunday` _(next occurrence)_\n"
        "• `next monday`, `next friday`\n"
        "• `25/12`, `25/12/2025`, `2025-12-25`\n"
        "• `dec 25`, `25 dec`\n\n"
        "*Time formats:*\n"
        "• `9am`, `3pm`, `3:30pm`, `10:15am`\n"
        "• `09:00`, `15:30`\n\n"
        "*Examples:*\n"
        "`/remind tomorrow 9am Dentist`\n"
        "`/remind 25/12 6pm Christmas dinner`\n"
        "`/remind next friday 10:30am Project review`\n"
        "`/remind monday 8am Take medication`\n\n"
        "*Other commands:*\n"
        "`/reminders` — all upcoming\n"
        "`/today` — today only\n"
        "`/delete 5` — remove reminder #5",
        parse_mode=ParseMode.MARKDOWN,
    )


@require_auth
async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    msg = update.effective_message

    if len(args) < 3:
        await msg.reply_text(
            "❌ Usage: `/remind <date> <time> <message>`\n\n"
            "_Example:_ `/remind tomorrow 3pm Dentist appointment`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Try single-word date first, then two-word (e.g. "next monday")
    remind_at = parse_reminder_datetime(args[0], args[1], TZ)
    msg_start = 2
    if remind_at is None and len(args) >= 4:
        remind_at = parse_reminder_datetime(f"{args[0]} {args[1]}", args[2], TZ)
        msg_start = 3

    if remind_at is None:
        await msg.reply_text(
            "❌ Could not parse date/time. Try:\n"
            "`/remind tomorrow 9am Dentist`\n"
            "`/remind 25/12 3pm Party`\n"
            "`/remind next monday 10am Meeting`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if remind_at <= datetime.now(TZ).replace(tzinfo=None):
        await msg.reply_text("❌ That time is in the past! Please choose a future date/time.")
        return

    chat = update.effective_chat
    register_chat(chat.id, chat.title or update.effective_user.first_name)

    reminder_text = " ".join(args[msg_start:])
    rid = add_reminder(
        user_id=update.effective_user.id,
        chat_id=chat.id,
        message=reminder_text,
        remind_at=remind_at,
    )

    friendly = remind_at.strftime("%A, %b %d at %I:%M %p")
    await msg.reply_text(
        f"✅ *Reminder set!*\n📅 {friendly}\n📝 {reminder_text}\n🔖 ID: `{rid}`",
        parse_mode=ParseMode.MARKDOWN,
    )


@require_auth
async def cmd_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = get_upcoming_reminders(update.effective_chat.id)
    if not items:
        await update.effective_message.reply_text("📭 No upcoming reminders!")
        return
    lines = ["📋 *Upcoming Reminders:*\n"]
    for r in items:
        dt = datetime.fromisoformat(r["remind_at"])
        lines.append(f"🔖 `#{r['id']}` {dt.strftime('%a %b %d, %I:%M %p')} — {r['message']}")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


@require_auth
async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = get_todays_reminders(update.effective_chat.id)
    label = datetime.now(TZ).strftime("%A, %B %d")
    if not items:
        await update.effective_message.reply_text(f"🎉 No reminders for today ({label})!")
        return
    lines = [f"📅 *Today — {label}:*\n"]
    for r in items:
        dt = datetime.fromisoformat(r["remind_at"])
        lines.append(f"⏰ {dt.strftime('%I:%M %p')} — {r['message']} _(#{r['id']})_")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


@require_auth
async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    msg = update.effective_message
    if not args or not args[0].isdigit():
        await msg.reply_text(
            "❌ Usage: `/delete <id>`\n_Example:_ `/delete 5`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    rid = int(args[0])
    if delete_reminder(rid, update.effective_chat.id):
        await msg.reply_text(f"🗑️ Reminder #{rid} deleted.")
    else:
        await msg.reply_text(
            f"❌ Reminder `#{rid}` not found, already sent, or not in this chat.",
            parse_mode=ParseMode.MARKDOWN,
        )


# ── Background jobs ───────────────────────────────────────────────────────────

async def job_check_due(context: ContextTypes.DEFAULT_TYPE):
    for r in get_due_reminders():
        try:
            await context.bot.send_message(
                chat_id=r["chat_id"],
                text=f"⏰ *Reminder!*\n\n{r['message']}",
                parse_mode=ParseMode.MARKDOWN,
            )
            mark_sent(r["id"])
            log.info(f"Sent reminder #{r['id']} to chat {r['chat_id']}")
        except Exception as e:
            log.error(f"Could not send reminder #{r['id']}: {e}")


async def job_morning_digest(context: ContextTypes.DEFAULT_TYPE):
    label = datetime.now(TZ).strftime("%A, %B %d")
    for chat_id in get_all_registered_chats():
        items = get_todays_reminders(chat_id)
        if not items:
            continue
        lines = [f"🌅 *Good morning! Reminders for {label}:*\n"]
        for r in items:
            dt = datetime.fromisoformat(r["remind_at"])
            lines.append(f"⏰ {dt.strftime('%I:%M %p')} — {r['message']}")
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            log.error(f"Could not send digest to {chat_id}: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        sys.exit("BOT_TOKEN is not set. Copy .env.example to .env and configure it.")

    init_db()
    log.info("Database initialised")

    app = Application.builder().token(BOT_TOKEN).build()

    for cmd, handler in [
        ("start",     cmd_start),
        ("help",      cmd_help),
        ("remind",    cmd_remind),
        ("reminders", cmd_reminders),
        ("list",      cmd_reminders),
        ("today",     cmd_today),
        ("delete",    cmd_delete),
    ]:
        app.add_handler(CommandHandler(cmd, handler))

    jq = app.job_queue
    jq.run_repeating(job_check_due, interval=60, first=5)
    jq.run_daily(
        job_morning_digest,
        time=dt_time(MORNING_DIGEST_HOUR, MORNING_DIGEST_MINUTE, tzinfo=TZ),
    )

    log.info(
        f"Bot running | TZ={TZ} | digest at {MORNING_DIGEST_HOUR:02d}:{MORNING_DIGEST_MINUTE:02d} | "
        f"allowed users: {ALLOWED_USER_IDS or 'everyone (bootstrap mode)'}"
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
