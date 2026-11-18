import logging
import re
import sys
from datetime import datetime, timedelta, time as dt_time
from functools import wraps

import dateparser.search
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from config import BOT_TOKEN, ALLOWED_USER_IDS, TZ, TIMEZONE, MORNING_DIGEST_HOUR, MORNING_DIGEST_MINUTE
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
        "`/remind <date> <time> <message>` — one-time reminder\n"
        "`/remind daily <time> <message>` — repeats every day\n"
        "`/remind weekly <day> <time> <message>` — repeats every week\n"
        "`/reminders` — list all upcoming\n"
        "`/today` — today's reminders\n"
        "`/delete <id>` — remove a reminder\n"
        "`/help` — usage guide\n\n"
        "Or just type naturally: `dentist tomorrow 9am`\n\n"
        f"Your user ID: `{uid}`",
        parse_mode=ParseMode.MARKDOWN,
    )


@require_auth
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🤖 *Reminder Bot — Help*\n\n"
        "*One-time reminder:*\n"
        "`/remind <date> <time> <message>`\n\n"
        "*Recurring reminders:*\n"
        "`/remind daily 8am Take vitamins`\n"
        "`/remind weekly monday 9am Team standup`\n"
        "`/remind every friday 6pm Weekend plans`\n\n"
        "*Natural language (just type):*\n"
        "`dentist tomorrow 9am`\n"
        "`call mom daily 7pm`\n"
        "`standup every monday 10am`\n\n"
        "*Date formats:*\n"
        "• `today`, `tomorrow`, `monday` … `sunday`\n"
        "• `next friday`, `25/12`, `2025-12-25`, `dec 25`\n\n"
        "*Time formats:*\n"
        "• `9am`, `3:30pm`, `14:00`\n\n"
        "*Other commands:*\n"
        "`/reminders` — all upcoming (🔁 = recurring)\n"
        "`/today` — today only\n"
        "`/delete 5` — remove reminder #5 _(stops recurring series too)_",
        parse_mode=ParseMode.MARKDOWN,
    )


@require_auth
async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    msg = update.effective_message

    if not args:
        await msg.reply_text(
            "❌ Usage: `/remind <date> <time> <message>`\n\n"
            "_Example:_ `/remind tomorrow 3pm Dentist`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    recurrence = None
    remind_at = None
    msg_start = 2
    first = args[0].lower()

    if first == "daily":
        # /remind daily 8am Take vitamins
        if len(args) < 3:
            await msg.reply_text(
                "❌ Usage: `/remind daily <time> <message>`\n"
                "_Example:_ `/remind daily 8am Take vitamins`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        remind_at = parse_reminder_datetime("today", args[1], TZ)
        # If today's time has already passed, start tomorrow
        if remind_at and remind_at <= datetime.now(TZ).replace(tzinfo=None):
            remind_at = parse_reminder_datetime("tomorrow", args[1], TZ)
        msg_start = 2
        recurrence = "daily"

    elif first in ("weekly", "every") and len(args) >= 4:
        # /remind weekly monday 9am Standup
        # /remind every friday 6pm Weekend plans
        remind_at = parse_reminder_datetime(args[1], args[2], TZ)
        msg_start = 3
        recurrence = "weekly"

    else:
        # Normal one-time reminder
        if len(args) < 3:
            await msg.reply_text(
                "❌ Usage: `/remind <date> <time> <message>`\n\n"
                "_Example:_ `/remind tomorrow 3pm Dentist`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        remind_at = parse_reminder_datetime(args[0], args[1], TZ)
        msg_start = 2
        if remind_at is None and len(args) >= 4:
            remind_at = parse_reminder_datetime(f"{args[0]} {args[1]}", args[2], TZ)
            msg_start = 3

    if remind_at is None:
        await msg.reply_text(
            "❌ Could not parse date/time. Try:\n"
            "`/remind tomorrow 9am Dentist`\n"
            "`/remind daily 8am Vitamins`\n"
            "`/remind weekly monday 9am Standup`",
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
        recurrence=recurrence,
    )

    if recurrence == "daily":
        friendly = f"Every day at {remind_at.strftime('%I:%M %p')}"
        note = f"_To stop this series: /delete {rid}_"
        icon = "🔁"
    elif recurrence == "weekly":
        friendly = f"Every {remind_at.strftime('%A')} at {remind_at.strftime('%I:%M %p')}"
        note = f"_To stop this series: /delete {rid}_"
        icon = "🔁"
    else:
        friendly = remind_at.strftime("%A, %b %d at %I:%M %p")
        note = ""
        icon = "✅"

    await msg.reply_text(
        f"{icon} *Reminder set!*\n📅 {friendly}\n📝 {reminder_text}\n🔖 ID: `{rid}`"
        + (f"\n\n{note}" if note else ""),
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
        recur = " 🔁" if r.get("recurrence") else ""
        lines.append(f"🔖 `#{r['id']}` {dt.strftime('%a %b %d, %I:%M %p')} — {r['message']}{recur}")
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
        recur = " 🔁" if r.get("recurrence") else ""
        lines.append(f"⏰ {dt.strftime('%I:%M %p')} — {r['message']}{recur} _(#{r['id']})_")
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
            icon = "🔁" if r.get("recurrence") else "⏰"
            await context.bot.send_message(
                chat_id=r["chat_id"],
                text=f"{icon} *Reminder!*\n\n{r['message']}",
                parse_mode=ParseMode.MARKDOWN,
            )
            mark_sent(r["id"])
            log.info(f"Sent reminder #{r['id']} to chat {r['chat_id']}")

            # Auto-schedule next occurrence for recurring reminders
            recurrence = r.get("recurrence")
            if recurrence == "daily":
                next_dt = datetime.fromisoformat(r["remind_at"]) + timedelta(days=1)
                add_reminder(r["user_id"], r["chat_id"], r["message"], next_dt, "daily")
                log.info(f"Rescheduled daily reminder for {next_dt.date()}")
            elif recurrence == "weekly":
                next_dt = datetime.fromisoformat(r["remind_at"]) + timedelta(weeks=1)
                add_reminder(r["user_id"], r["chat_id"], r["message"], next_dt, "weekly")
                log.info(f"Rescheduled weekly reminder for {next_dt.date()}")

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
            recur = " 🔁" if r.get("recurrence") else ""
            lines.append(f"⏰ {dt.strftime('%I:%M %p')} — {r['message']}{recur}")
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            log.error(f"Could not send digest to {chat_id}: {e}")


# ── Natural language handler ──────────────────────────────────────────────────

_FILLER = re.compile(
    r"^(remind me (about|to|of)?|reminder (for|about)?|set (a )?reminder (for|about)?)\s*",
    re.IGNORECASE,
)
_WEEKDAY_PATTERN = r"monday|tuesday|wednesday|thursday|friday|saturday|sunday"


@require_auth
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.effective_message.text.strip()
    msg = update.effective_message

    # Detect recurrence keywords before passing to date parser
    recurrence = None
    parse_text = text

    if re.search(r"\b(every day|daily)\b", text, re.IGNORECASE):
        recurrence = "daily"
        parse_text = re.sub(r"\b(every day|daily)\b", "", text, flags=re.IGNORECASE).strip()
    elif re.search(rf"\bevery\s+({_WEEKDAY_PATTERN}|week)\b", text, re.IGNORECASE):
        recurrence = "weekly"
        parse_text = re.sub(r"\bevery\b", "", text, flags=re.IGNORECASE).strip()

    results = dateparser.search.search_dates(
        parse_text,
        languages=["en"],
        settings={
            "PREFER_DATES_FROM": "future",
            "TIMEZONE": TIMEZONE,
            "TO_TIMEZONE": TIMEZONE,
            "RETURN_AS_TIMEZONE_AWARE": False,
        },
    )

    if not results:
        await msg.reply_text(
            "⚠️ I couldn't find a date or time in your message.\n\n"
            "Try: `dentist tomorrow 9am` or `/remind tomorrow 9am Dentist`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    date_str_found, remind_at = results[0]
    now = datetime.now(TZ).replace(tzinfo=None)

    # For daily recurrence, if parsed time is past, shift to tomorrow
    if recurrence == "daily" and remind_at <= now:
        remind_at += timedelta(days=1)

    if remind_at <= now:
        await msg.reply_text("❌ That time seems to be in the past. Can you be more specific?")
        return

    reminder_text = parse_text.replace(date_str_found, "").strip()
    reminder_text = re.sub(r"\s{2,}", " ", reminder_text)
    reminder_text = _FILLER.sub("", reminder_text).strip()
    if not reminder_text:
        reminder_text = "Reminder"

    chat = update.effective_chat
    register_chat(chat.id, chat.title or update.effective_user.first_name)

    rid = add_reminder(
        user_id=update.effective_user.id,
        chat_id=chat.id,
        message=reminder_text,
        remind_at=remind_at,
        recurrence=recurrence,
    )

    if recurrence == "daily":
        friendly = f"Every day at {remind_at.strftime('%I:%M %p')}"
        note = f"_To stop: /delete {rid}_"
        icon = "🔁"
    elif recurrence == "weekly":
        friendly = f"Every {remind_at.strftime('%A')} at {remind_at.strftime('%I:%M %p')}"
        note = f"_To stop: /delete {rid}_"
        icon = "🔁"
    else:
        friendly = remind_at.strftime("%A, %b %d at %I:%M %p")
        note = f"_Wrong time? /delete {rid} and try again._"
        icon = "✅"

    await msg.reply_text(
        f"{icon} *Got it!*\n📅 {friendly}\n📝 {reminder_text}\n🔖 ID: `{rid}`\n\n{note}",
        parse_mode=ParseMode.MARKDOWN,
    )


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

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

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
