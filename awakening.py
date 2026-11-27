import random
import logging
import sqlite3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

import database as db


logger = logging.getLogger(__name__)


# ==================================================
# CLASSES
# ==================================================

CLASSES = {
    "assassin": {
        "name": "Assassin",
        "description": "سرعت بالا و حملات سریع",
        "emoji": "🗡",
        "stats": (2, 5, 1, 1, 2),
        "powers": [
            "Phantom Assassin",
            "Shadow Walker",
            "Silent Executioner",
            "Night Predator"
        ]
    },

    "fighter": {
        "name": "Fighter",
        "description": "قدرت فیزیکی و مبارزه نزدیک",
        "emoji": "🥊",
        "stats": (5, 2, 3, 0, 1),
        "powers": [
            "Dragon Fist",
            "Warrior Soul",
            "Titan Breaker",
            "Crimson Berserker"
        ]
    },

    "tank": {
        "name": "Tank",
        "description": "دفاع و مقاومت بالا",
        "emoji": "🛡",
        "stats": (2, 0, 6, 1, 2),
        "powers": [
            "Iron Monarch",
            "Fortress Guardian",
            "Unbreakable Wall",
            "Aegis Knight"
        ]
    },

    "mage": {
        "name": "Mage",
        "description": "قدرت جادویی و کنترل انرژی",
        "emoji": "🔮",
        "stats": (0, 1, 1, 6, 3),
        "powers": [
            "Abyssal Sorcerer",
            "Void Controller",
            "Arcane Emperor",
            "Celestial Flame"
        ]
    },

    "ranger": {
        "name": "Ranger",
        "description": "دقت و حملات از راه دور",
        "emoji": "🏹",
        "stats": (2, 4, 1, 2, 2),
        "powers": [
            "Eagle Eye",
            "Storm Archer",
            "Phantom Hunter",
            "Piercing Star"
        ]
    },

    "healer": {
        "name": "Healer",
        "description": "درمان و پشتیبانی",
        "emoji": "💚",
        "stats": (0, 1, 3, 4, 3),
        "powers": [
            "Divine Light",
            "Life Weaver",
            "Sacred Guardian",
            "Holy Resonance"
        ]
    },

    "necromancer": {
        "name": "Necromancer",
        "description": "کنترل نیروهای تاریکی و سایه‌ها",
        "emoji": "🌑",
        "stats": (1, 2, 2, 4, 3),
        "powers": [
            "Shadow Monarch",
            "Abyss Commander",
            "Death Sovereign",
            "Eternal Shadow"
        ]
    }
}


# ==================================================
# DATABASE
# ==================================================

def init_awakening_db():

    with db.connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS awakenings (
                user_id INTEGER PRIMARY KEY,
                class_id TEXT NOT NULL,
                class_name TEXT NOT NULL,
                power_name TEXT NOT NULL,
                awakening_rank TEXT DEFAULT 'E',
                awakening_level INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id)
                    REFERENCES players(user_id)
                    ON DELETE CASCADE
            )
        """)


def get_awakening(user_id):

    with db.connect() as conn:

        return conn.execute("""
            SELECT *
            FROM awakenings
            WHERE user_id = ?
        """, (user_id,)).fetchone()


# ==================================================
# KEYBOARDS
# ==================================================

def awakening_menu():

    keyboard = []

    class_ids = list(CLASSES.keys())

    for index in range(0, len(class_ids), 2):

        row = []

        for class_id in class_ids[index:index + 2]:

            selected = CLASSES[class_id]

            row.append(
                InlineKeyboardButton(
                    f"{selected['emoji']} {selected['name']}",
                    callback_data=f"awake_{class_id}"
                )
            )

        keyboard.append(row)

    keyboard.append([
        InlineKeyboardButton(
            "🔄 Refresh",
            callback_data="awakening"
        )
    ])

    return InlineKeyboardMarkup(keyboard)


# ==================================================
# AWAKENING TEXT
# ==================================================

def awakening_card(user_id):

    awakening = get_awakening(user_id)

    if not awakening:

        return (
            "✨ AWAKENING CARD\n\n"
            "وضعیت: هنوز بیداری انجام نشده است.\n\n"
            "برای دریافت قدرت اختصاصی خودت، "
            "کلاس موردنظرت را انتخاب کن."
        )

    selected = CLASSES.get(
        awakening["class_id"],
        {}
    )

    emoji = selected.get("emoji", "✨")

    return (
        "✨ AWAKENING CARD\n\n"
        f"{emoji} Class: {awakening['class_name']}\n"
        f"⚡ Power: {awakening['power_name']}\n"
        f"🏅 Rank: {awakening['awakening_rank']}\n"
        f"📈 Level: {awakening['awakening_level']}\n\n"
        "قدرت بیداری تو ثبت شده است."
    )


# ==================================================
# STAT GENERATION
# ==================================================

def generate_awakening_stats(class_id):

    selected = CLASSES[class_id]

    strength, agility, vitality, intelligence, sense = (
        selected["stats"]
    )

    strength += random.randint(0, 2)
    agility += random.randint(0, 2)
    vitality += random.randint(0, 2)
    intelligence += random.randint(0, 2)
    sense += random.randint(0, 2)

    power = (
        strength * 3
        + agility * 2
        + vitality * 2
        + intelligence * 3
        + sense * 2
    )

    return {
        "strength": strength,
        "agility": agility,
        "vitality": vitality,
        "intelligence": intelligence,
        "sense": sense,
        "power": power
    }


# ==================================================
# PLAYER AWAKENING
# ==================================================

def create_awakening(user_id, class_id):

    if class_id not in CLASSES:
        return None

    selected = CLASSES[class_id]

    power_name = random.choice(
        selected["powers"]
    )

    stats = generate_awakening_stats(class_id)

    try:

        with db.connect() as conn:

            conn.execute("BEGIN IMMEDIATE")

            existing = conn.execute("""
                SELECT user_id
                FROM awakenings
                WHERE user_id = ?
            """, (user_id,)).fetchone()

            if existing:
                return None

            player = conn.execute("""
                SELECT user_id
                FROM players
                WHERE user_id = ?
            """, (user_id,)).fetchone()

            if not player:
                return None

            conn.execute("""
                INSERT INTO awakenings (
                    user_id,
                    class_id,
                    class_name,
                    power_name,
                    awakening_rank,
                    awakening_level
                )
                VALUES (?, ?, ?, ?, 'E', 1)
            """, (
                user_id,
                class_id,
                selected["name"],
                power_name
            ))

            conn.execute("""
                UPDATE players
                SET
                    strength = ?,
                    agility = ?,
                    vitality = ?,
                    intelligence = ?,
                    sense = ?,
                    power = ?
                WHERE user_id = ?
            """, (
                stats["strength"],
                stats["agility"],
                stats["vitality"],
                stats["intelligence"],
                stats["sense"],
                stats["power"],
                user_id
            ))

        return {
            "class": selected["name"],
            "power_name": power_name,
            "stats": stats,
            "rank": "E",
            "level": 1
        }

    except sqlite3.IntegrityError:

        return None

    except Exception:

        logger.exception(
            "Failed to create awakening for user %s",
            user_id
        )

        return None
# ==================================================
# AWAKENING CALLBACK
# ==================================================

async def awakening_callback(update, context):

    query = update.callback_query

    user_id = query.from_user.id

    if not query.message:
        await query.answer()
        return

    if query.message.chat.type != "private":

        await query.answer(
            "این بخش فقط در چت خصوصی قابل استفاده است.",
            show_alert=True
        )

        return

    player = db.get_player(user_id)

    if not player:

        await query.answer(
            "ابتدا دستور /start را اجرا کن.",
            show_alert=True
        )

        return

    action = query.data

    # نمایش صفحه بیداری
    if action == "awakening":

        current = get_awakening(user_id)

        await query.answer()

        if current:

            await query.edit_message_text(
                awakening_card(user_id)
            )

            return

        await query.edit_message_text(
            "✨ AWAKENING TEST\n\n"
            "زمان بیداری تو فرا رسیده است.\n"
            "کلاس موردنظر خودت را انتخاب کن:\n\n"
            "⚠️ توجه: انتخاب کلاس دائمی است.",
            reply_markup=awakening_menu()
        )

        return

    # انتخاب کلاس
    if not action.startswith("awake_"):
        await query.answer()
        return

    class_id = action.replace("awake_", "", 1)

    if class_id not in CLASSES:

        await query.answer(
            "کلاس انتخاب‌شده معتبر نیست.",
            show_alert=True
        )

        return

    # جلوگیری از انتخاب دوباره
    if get_awakening(user_id):

        await query.answer(
            "تو قبلاً بیداری خودت را انتخاب کرده‌ای.",
            show_alert=True
        )

        await query.edit_message_text(
            awakening_card(user_id)
        )

        return

    await query.answer(
        "در حال انجام بیداری..."
    )

    result = create_awakening(
        user_id,
        class_id
    )

    if not result:

        current = get_awakening(user_id)

        if current:

            await query.edit_message_text(
                awakening_card(user_id)
            )

        else:

            await query.edit_message_text(
                "❌ انجام بیداری ناموفق بود.\n"
                "لطفاً دوباره تلاش کن.",
                reply_markup=awakening_menu()
            )

        return

    stats = result["stats"]

    await query.edit_message_text(
        "🌑 AWAKENING COMPLETE\n\n"
        f"👤 Hunter: {player['name']}\n"
        f"⚔️ Class: {result['class']}\n"
        f"✨ Unique Power: {result['power_name']}\n"
        f"🏅 Rank: {result['rank']}\n"
        f"📈 Level: {result['level']}\n\n"
        "📊 INITIAL STATS\n"
        f"STR: {stats['strength']}\n"
        f"AGI: {stats['agility']}\n"
        f"VIT: {stats['vitality']}\n"
        f"INT: {stats['intelligence']}\n"
        f"SEN: {stats['sense']}\n\n"
        f"🔥 Power: {stats['power']}\n\n"
        "قدرت بیداری تو با موفقیت ثبت شد."
    )


# ==================================================
# SETUP
# ==================================================

def setup_awakening(application):

    init_awakening_db()

    application.add_handler(
        CallbackQueryHandler(
            awakening_callback,
            pattern=r"^(awakening|awake_.*)$"
        )
    )