import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()]

DB_PATH = Path(os.environ.get("DB_PATH", str(BASE_DIR / "data" / "bot.db")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

PLANS = {
    "1d":  {"label": "1 Day",  "days": 1,  "stars": int(os.environ.get("PLAN_1D_STARS",  "250"))},
    "3d": {"label": "3 Days", "days": 3, "stars": int(os.environ.get("PLAN_3D_STARS", "450"))},
    "7d": {"label": "7 Days", "days": 7, "stars": int(os.environ.get("PLAN_7D_STARS", "600"))},
    "15d":  {"label": "15 Days",  "days": 15,  "stars": int(os.environ.get("PLAN_15D_STARS",  "900"))},
    "30d": {"label": "30 Days", "days": 30, "stars": int(os.environ.get("PLAN_30D_STARS", "1200"))},
}

EXPIRY_CHECK_INTERVAL = int(os.environ.get("EXPIRY_CHECK_INTERVAL", "600"))