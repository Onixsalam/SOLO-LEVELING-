import time
from datetime import datetime, timezone

from telegram import (
Update,
InlineKeyboardButton,
InlineKeyboardMarkup
)
from telegram.ext import (
CommandHandler,
CallbackQueryHandler,
ContextTypes
)

import database as db

DAILY_QUESTS = {
"ranked_win": {
"name": "🏆 Ranked Victory",
"description": "Win 1 Ranked Match",
"target": 1,
"exp": 150,
"gold": 300,
"crystals": 5
},
"training": {
"name": "⚔️ Training",
"description": "Complete 3 Training Sessions",
"target": 3,
"exp": 100,
"gold": 200,
"crystals": 0
},
"dungeon": {
"name": "🏰 Dungeon Hunter",
"description": "Clear 1 Dungeon",
"target": 1,
"exp": 200,
"gold": 400,
"crystals": 10
}
}

def today():
return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def init_daily_quests_db():
with db.connect() as conn:

    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_quest_progress (
            user_id INTEGER NOT NULL,
            quest_id TEXT NOT NULL,
            quest_date TEXT NOT NULL,
            progress INTEGER DEFAULT 0,
            completed INTEGER DEFAULT 0,
            claimed INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, quest_id, quest_date)
        )
    """)

def ensure_daily_quests(user_id):
current_date = today()

with db.connect() as conn:

    for quest_id in DAILY_QUESTS:

        conn.execute("""
            INSERT OR IGNORE INTO daily_quest_progress
            (user_id, quest_id, quest_date)
            VALUES (?, ?, ?)
        """, (
            user_id,
            quest_id,
            current_date
        ))

def get_daily_progress(user_id):
ensure_daily_quests(user_id)

with db.connect() as conn:
    rows = conn.execute("""
        SELECT *
        FROM daily_quest_progress
        WHERE user_id = ?
        AND quest_date = ?
    """, (
        user_id,
        today()
    )).fetchall()

return rows

def add_quest_progress(user_id, quest_id, amount=1):
if quest_id not in DAILY_QUESTS or amount <= 0:
return False

ensure_daily_quests(user_id)

quest = DAILY_QUESTS[quest_id]

with db.connect() as conn:

    row = conn.execute("""
        SELECT progress, completed
        FROM daily_quest_progress
        WHERE user_id = ?
        AND quest_id = ?
        AND quest_date = ?
    """, (
        user_id,
        quest_id,
        today()
    )).fetchone()

    if not row or row["completed"]:
        return False

    new_progress = min(
        quest["target"],
        row["progress"] + amount
    )

    completed = int(
        new_progress >= quest["target"]
    )

    conn.execute("""
        UPDATE daily_quest_progress
        SET progress = ?,
            completed = ?
        WHERE user_id = ?
        AND quest_id = ?
        AND quest_date = ?
    """, (
        new_progress,
        completed,
        user_id,
        quest_id,
        today()
    ))

return True

def claim_quest_reward(user_id, quest_id):
if quest_id not in DAILY_QUESTS:
return False, "Unknown quest."

quest = DAILY_QUESTS[quest_id]

with db.connect() as conn:

    row = conn.execute("""
        SELECT completed, claimed
        FROM daily_quest_progress
        WHERE user_id = ?
        AND quest_id = ?
        AND quest_date = ?
    """, (
        user_id,
        quest_id,
        today()
    )).fetchone()

    if not row:
        return False, "Quest not found."

    if not row["completed"]:
        return False, "Quest is not completed yet."

    if row["claimed"]:
        return False, "Reward already claimed."

    columns = {
        item["name"]
        for item in conn.execute(
            "PRAGMA table_info(players)"
        ).fetchall()
    }

    required = {"gold", "crystals"}

    if not required.issubset(columns):
        return False, "Player reward columns are missing."

    conn.execute("""
        UPDATE players
        SET gold = gold + ?,
            crystals = crystals + ?
        WHERE user_id = ?
    """, (
        quest["gold"],
        quest["crystals"],
        user_id
    ))

    conn.execute("""
        UPDATE daily_quest_progress
        SET claimed = 1
        WHERE user_id = ?
        AND quest_id = ?
        AND quest_date = ?
        AND completed = 1
        AND claimed = 0
    """, (
        user_id,
        quest_id,
        today()
    ))

# EXP is added after the reward transaction.
# This will be connected to the progression module.
try:
    from progression import add_xp
    add_xp(user_id, quest["exp"])
except Exception:
    pass

return True, (
    f"🎁 Reward claimed!\n"
    f"EXP: {quest['exp']}\n"
    f"Gold: {quest['gold']}\n"
    f"Crystals: {quest['crystals']}"
)

def quest_page(user_id):
rows = get_daily_progress(user_id)

text = (
    "📜 DAILY QUESTS\n\n"
    f"Date: {today()} UTC\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
)

for row in rows:
    quest = DAILY_QUESTS[row["quest_id"]]

    if row["claimed"]:
        status = "✅ CLAIMED"
    elif row["completed"]:
        status = "🎁 REWARD AVAILABLE"
    else:
        status = "⏳ IN PROGRESS"

    text += (
        f"{quest['name']}\n"
        f"{quest['description']}\n"
        f"Progress: {row['progress']}/{quest['target']}\n"
        f"Status: {status}\n"
        f"Reward: {quest['exp']} EXP | "
        f"{quest['gold']} Gold | "
        f"{quest['crystals']} Crystals\n\n"
    )

text += "━━━━━━━━━━━━━━━━━━\n"
text += "Complete quests and claim your rewards!"

buttons = []

for row in rows:
    quest_id = row["quest_id"]

    if row["completed"] and not row["claimed"]:
        buttons.append([
            InlineKeyboardButton(
                f"🎁 Claim {DAILY_QUESTS[quest_id]['name']}",
                callback_data=f"claim_daily_{quest_id}"
            )
        ])

buttons.append([
    InlineKeyboardButton(
        "🔄 Refresh",
        callback_data="daily_refresh"
    )
])

buttons.append([
    InlineKeyboardButton(
        "🔙 Back",
        callback_data="home"
    )
])

return text, InlineKeyboardMarkup(buttons)

async def daily_command(
update: Update,
context: ContextTypes.DEFAULT_TYPE
):
user = update.effective_user

if update.effective_chat.type != "private":
    await update.message.reply_text(
        "Use this command in the bot's private chat."
    )
    return

if not db.get_player(user.id):
    await update.message.reply_text(
        "First register using /start."
    )
    return

text, keyboard = quest_page(user.id)

await update.message.reply_text(
    text,
    reply_markup=keyboard
)

async def daily_callback(
update: Update,
context: ContextTypes.DEFAULT_TYPE
):
query = update.callback_query

if query.message.chat.type != "private":
    await query.answer(
        "Private chat only.",
        show_alert=True
    )
    return

user_id = query.from_user.id

if not db.get_player(user_id):
    await query.answer(
        "Register using /start first.",
        show_alert=True
    )
    return

data = query.data

if data.startswith("claim_daily_"):
    quest_id = data.replace("claim_daily_", "", 1)

    success, message = claim_quest_reward(
        user_id,
        quest_id
    )

    await query.answer(
        "Reward claimed!" if success else message,
        show_alert=not success
    )

else:
    await query.answer()

text, keyboard = quest_page(user_id)

await query.edit_message_text(
    text,
    reply_markup=keyboard
)

def setup_daily_quests(application):
init_daily_quests_db()

application.add_handler(
    CommandHandler("daily", daily_command)
)

application.add_handler(
    CallbackQueryHandler(
        daily_callback,
        pattern=r"^(daily_refresh|claim_daily_.*)$"
    )
)