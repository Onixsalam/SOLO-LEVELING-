import logging
import random
from datetime import datetime, timezone

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update
)
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

import database as db


logger = logging.getLogger(__name__)


# ==================================================
# SETTINGS
# ==================================================

QUESTS_PER_DAY = 3

DAILY_QUESTS = [
    {
        "id": "training",
        "name": "تمرین روزانه",
        "description": "یک بار تمرین انجام بده.",
        "target": 1,
        "gold": 100,
        "crystals": 5
    },
    {
        "id": "dungeon",
        "name": "شکار سیاه‌چال",
        "description": "یک سیاه‌چال را کامل کن.",
        "target": 1,
        "gold": 200,
        "crystals": 10
    },
    {
        "id": "monster",
        "name": "شکار هیولا",
        "description": "یک هیولا را شکست بده.",
        "target": 1,
        "gold": 150,
        "crystals": 5
    },
    {
        "id": "pvp",
        "name": "مبارز روزانه",
        "description": "یک مسابقه PvP را کامل کن.",
        "target": 1,
        "gold": 200,
        "crystals": 10
    },
    {
        "id": "boss",
        "name": "شکارچی باس",
        "description": "به یک باس آسیب وارد کن.",
        "target": 1,
        "gold": 250,
        "crystals": 15
    }
]


# ==================================================
# DATABASE
# ==================================================

def init_daily_quests_db():

    with db.connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_quest_progress (
                user_id INTEGER NOT NULL,
                quest_date TEXT NOT NULL,
                quest_id TEXT NOT NULL,
                progress INTEGER DEFAULT 0,
                completed INTEGER DEFAULT 0,
                claimed INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, quest_date, quest_id)
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_daily_quest_user_date
            ON daily_quest_progress(user_id, quest_date)
        """)


# ==================================================
# DATE
# ==================================================

def today_date():

    return datetime.now(
        timezone.utc
    ).date().isoformat()


# ==================================================
# DAILY QUEST GENERATION
# ==================================================

def generate_daily_quests(user_id):

    today = today_date()

    with db.connect() as conn:

        existing = conn.execute("""
            SELECT quest_id
            FROM daily_quest_progress
            WHERE user_id = ?
            AND quest_date = ?
        """, (user_id, today)).fetchall()

        if existing:
            return

        selected = random.sample(
            DAILY_QUESTS,
            min(QUESTS_PER_DAY, len(DAILY_QUESTS))
        )

        for quest in selected:

            conn.execute("""
                INSERT OR IGNORE INTO daily_quest_progress
                (
                    user_id,
                    quest_date,
                    quest_id,
                    progress,
                    completed,
                    claimed
                )
                VALUES (?, ?, ?, 0, 0, 0)
            """, (
                user_id,
                today,
                quest["id"]
            ))


# ==================================================
# GET QUEST DATA
# ==================================================

def get_daily_quests(user_id):

    generate_daily_quests(user_id)

    today = today_date()

    with db.connect() as conn:

        rows = conn.execute("""
            SELECT quest_id, progress, completed, claimed
            FROM daily_quest_progress
            WHERE user_id = ?
            AND quest_date = ?
        """, (user_id, today)).fetchall()

    result = []

    for row in rows:

        quest = next(
            (
                item for item in DAILY_QUESTS
                if item["id"] == row["quest_id"]
            ),
            None
        )

        if not quest:
            continue

        item = dict(quest)

        item["progress"] = row["progress"]
        item["completed"] = bool(row["completed"])
        item["claimed"] = bool(row["claimed"])

        result.append(item)

    return result


# ==================================================
# ADD QUEST PROGRESS
# ==================================================

def add_quest_progress(user_id, quest_id, amount=1):

    if amount <= 0:
        return False

    today = today_date()

    quest = next(
        (
            item for item in DAILY_QUESTS
            if item["id"] == quest_id
        ),
        None
    )

    if not quest:
        return False

    generate_daily_quests(user_id)

    with db.connect() as conn:

        row = conn.execute("""
            SELECT progress, completed
            FROM daily_quest_progress
            WHERE user_id = ?
            AND quest_date = ?
            AND quest_id = ?
        """, (
            user_id,
            today,
            quest_id
        )).fetchone()

        if not row:
            return False

        if row["completed"]:
            return True

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
            AND quest_date = ?
            AND quest_id = ?
        """, (
            new_progress,
            completed,
            user_id,
            today,
            quest_id
        ))

    return bool(completed)
# ==================================================
# CLAIM REWARD
# ==================================================

def claim_quest_reward(user_id, quest_id):

    today = today_date()

    quest = next(
        (
            item for item in DAILY_QUESTS
            if item["id"] == quest_id
        ),
        None
    )

    if not quest:
        return False, "مأموریت پیدا نشد."

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        row = conn.execute("""
            SELECT completed, claimed
            FROM daily_quest_progress
            WHERE user_id = ?
            AND quest_date = ?
            AND quest_id = ?
        """, (
            user_id,
            today,
            quest_id
        )).fetchone()

        if not row:
            return False, "مأموریت امروز پیدا نشد."

        if not row["completed"]:
            return False, "این مأموریت هنوز کامل نشده است."

        if row["claimed"]:
            return False, "جایزه این مأموریت قبلاً دریافت شده است."

        conn.execute("""
            UPDATE daily_quest_progress
            SET claimed = 1
            WHERE user_id = ?
            AND quest_date = ?
            AND quest_id = ?
        """, (
            user_id,
            today,
            quest_id
        ))

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

    return True, (
        f"🎁 جایزه دریافت شد!\n"
        f"🪙 طلا: {quest['gold']}\n"
        f"💎 کریستال: {quest['crystals']}"
    )


# ==================================================
# QUEST PAGE
# ==================================================

def quest_text(user_id):

    quests = get_daily_quests(user_id)

    lines = [
        "📜 DAILY QUESTS",
        "",
        "مأموریت‌های روزانه تو:",
        ""
    ]

    for index, quest in enumerate(quests, start=1):

        if quest["claimed"]:
            status = "✅ جایزه دریافت شده"

        elif quest["completed"]:
            status = "🎁 آماده دریافت جایزه"

        else:
            status = (
                f"⏳ پیشرفت: "
                f"{quest['progress']}/{quest['target']}"
            )

        lines.extend([
            f"{index}. {quest['name']}",
            quest["description"],
            status,
            f"🪙 {quest['gold']} طلا | "
            f"💎 {quest['crystals']} کریستال",
            ""
        ])

    return "\n".join(lines)


# ==================================================
# KEYBOARD
# ==================================================

def quest_keyboard(user_id):

    quests = get_daily_quests(user_id)

    keyboard = []

    for quest in quests:

        if quest["completed"] and not quest["claimed"]:

            keyboard.append([
                InlineKeyboardButton(
                    f"🎁 دریافت: {quest['name']}",
                    callback_data=(
                        f"quest_claim_{quest['id']}"
                    )
                )
            ])

    keyboard.append([
        InlineKeyboardButton(
            "🔄 Refresh",
            callback_data=f"daily_refresh_{user_id}"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "🏠 Back",
            callback_data="home"
        )
    ])

    return InlineKeyboardMarkup(keyboard)


# ==================================================
# COMMAND
# ==================================================

async def daily_command(update, context):

    if update.effective_chat.type != "private":

        await update.effective_message.reply_text(
            "مأموریت‌های روزانه فقط در چت خصوصی قابل مشاهده هستند."
        )

        return

    user_id = update.effective_user.id

    if not db.get_player(user_id):

        await update.effective_message.reply_text(
            "ابتدا دستور /start را اجرا کن."
        )

        return

    await update.effective_message.reply_text(
        quest_text(user_id),
        reply_markup=quest_keyboard(user_id)
    )


# ==================================================
# CALLBACK
# ==================================================

async def daily_callback(update, context):

    query = update.callback_query

    if not query.message:
        await query.answer()
        return

    if query.message.chat.type != "private":

        await query.answer(
            "این بخش فقط در چت خصوصی قابل استفاده است.",
            show_alert=True
        )

        return

    user_id = query.from_user.id
    data = query.data

    if data == f"daily_refresh_{user_id}":

        await query.answer("به‌روزرسانی شد.")

        await query.edit_message_text(
            quest_text(user_id),
            reply_markup=quest_keyboard(user_id)
        )

        return

    if data.startswith("quest_claim_"):

        quest_id = data.replace(
            "quest_claim_",
            "",
            1
        )

        success, message = claim_quest_reward(
            user_id,
            quest_id
        )

        await query.answer(
            message,
            show_alert=True
        )

        await query.edit_message_text(
            quest_text(user_id),
            reply_markup=quest_keyboard(user_id)
        )

        return

    await query.answer()


# ==================================================
# SETUP
# ==================================================

def setup_daily_quests(application):

    init_daily_quests_db()

    application.add_handler(
        CommandHandler(
            "daily",
            daily_command
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            daily_callback,
            pattern=r"^(daily_refresh_\d+|quest_claim_[a-z_]+)$"
        )
    )