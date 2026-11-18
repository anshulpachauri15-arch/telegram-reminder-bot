import os
import pytz
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

ALLOWED_USER_IDS: list[int] = [
    int(x.strip())
    for x in os.getenv("ALLOWED_USER_IDS", "").split(",")
    if x.strip().isdigit()
]

TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")
TZ = pytz.timezone(TIMEZONE)

MORNING_DIGEST_HOUR: int = int(os.getenv("MORNING_DIGEST_HOUR", "8"))
MORNING_DIGEST_MINUTE: int = int(os.getenv("MORNING_DIGEST_MINUTE", "0"))

DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/reminders.db")
