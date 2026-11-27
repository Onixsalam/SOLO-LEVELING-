import os

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is missing! Set it in Railway Variables."
    )

GAME_NAME = "SOLO LEVELING: SHADOW LEGACY"

START_GOLD = 500
START_CRYSTALS = 50
START_LEVEL = 1

DATABASE_NAME = "shadow_legacy.db"