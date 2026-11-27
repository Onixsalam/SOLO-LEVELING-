import os

# ================= BOT =================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is missing! Set it in Railway Variables."
    )

GAME_NAME = "SOLO LEVELING: SHADOW LEGACY"


# ================= STARTER REWARDS =================

START_GOLD = 500
START_CRYSTALS = 50
START_LEVEL = 1

START_HP = 100
START_MP = 50

START_STAT = 5


# ================= DATABASE =================

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "shadow_legacy.db"
)


# ================= GAME SETTINGS =================

REVIVE_SECONDS = 300

MAX_LEVEL = 100

STAT_POINTS_PER_LEVEL = 5