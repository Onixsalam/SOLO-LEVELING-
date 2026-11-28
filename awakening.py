import random
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

import database as db

logger = logging.getLogger(__name__)


CLASSES = {
    "assassin": {
        "name": "Assassin",
        "description": "سرعت بالا و حملات سریع",
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
        "stats": (1, 2, 2, 4, 3),
        "powers": [
            "Shadow Monarch",
            "Abyss Commander",
            "Death Sovereign",
            "Eternal Shadow"
        ]
    }
}


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
                FOREIGN KEY(user_id) REFERENCES players(user_id)
            )
        """)


def get_awakening(user_id):
    with db.connect() as conn:
        return conn.execute(
            "SELECT * FROM awakenings WHERE user_id = ?",
            (user_id,)
        ).fetchone()


def get_player_class(user_id):
    awakening = get_awakening(user_id)

    if not awakening:
        return None

    return awakening["class_id"]


def awakening_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "🗡 Assassin",
                callback_data="awake_assassin"
            ),
            InlineKeyboardButton(
                "🥊 Fighter",
                callback_data="awake_fighter"
            )
        ],
        [
            InlineKeyboardButton(
                "🛡 Tank",
                callback_data="awake_tank"
            ),
            InlineKeyboardButton(
                "🔮 Mage",
                callback_data="awake_mage"
            )
        ],
        [
            InlineKeyboardButton(
                "🏹 Ranger",
                callback_data="awake_ranger"
            ),
            InlineKeyboardButton(
                "💚 Healer",
                callback_data="awake_healer"
            )
        ],
        [
            InlineKeyboardButton(
                "🌑 Necromancer",
                callback_data="awake_necromancer"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)
async def awakening_callback(update, context):
    query = update.callback_query
    user_id = query.from_user.id

    if query.message.chat.type != "private":
        await query.answer(
            "این بخش فقط در چت خصوصی قابل استفاده است.",
            show_alert=True
        )
        return

    player = db.get_player(user_id)

    if not player:
        await query.answer(
            "ابتدا /start را اجرا کن.",
            show_alert=True
        )
        return

    action = query.data

    if action == "awakening":
        current = get_awakening(user_id)

        if current:
            await query.answer()

            await query.edit_message_text(
                "✨ AWAKENING CARD\n\n"
                f"Class: {current['class_name']}\n"
                f"Power: {current['power_name']}\n"
                f"Rank: {current['awakening_rank']}\n"
                f"Level: {current['awakening_level']}\n\n"
                "قدرت بیداری تو قبلاً ثبت شده است."
            )
            return

        await query.answer()

        await query.edit_message_text(
            "✨ AWAKENING TEST\n\n"
            "سیستم آماده بیدار کردن قدرت توست.\n"
            "کلاس موردنظر خودت را انتخاب کن:",
            reply_markup=awakening_menu()
        )
        return

    if not action.startswith("awake_"):
        return

    class_id = action.replace("awake_", "", 1)

    if class_id not in CLASSES:
        await query.answer(
            "کلاس نامعتبر است.",
            show_alert=True
        )
        return

    if get_awakening(user_id):
        await query.answer(
            "قدرت بیداری قبلاً انتخاب شده است.",
            show_alert=True
        )
        return

    selected = CLASSES[class_id]
    power_name = random.choice(selected["powers"])

    strength, agility, vitality, intelligence, sense = (
        selected["stats"]
    )

    # تفاوت جزئی و تصادفی بین بازیکنان یک کلاس
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

    # جلوگیری از ثبت دوباره بیداری برای یک بازیکن
    try:
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")

            existing = conn.execute(
                "SELECT user_id FROM awakenings WHERE user_id = ?",
                (user_id,)
            ).fetchone()

            if existing:
                await query.answer(
                    "قدرت بیداری قبلاً انتخاب شده است.",
                    show_alert=True
                )
                return

            conn.execute("""
                INSERT INTO awakenings (
                    user_id,
                    class_id,
                    class_name,
                    power_name
                )
                VALUES (?, ?, ?, ?)
            """, (
                user_id,
                class_id,
                selected["name"],
                power_name
            ))

        db.update_player(
            user_id,
            strength=strength,
            agility=agility,
            vitality=vitality,
            intelligence=intelligence,
            sense=sense,
            power=power
        )

    except Exception:
        logger.exception("Awakening failed for user %s", user_id)

        await query.answer(
            "ثبت بیداری با مشکل مواجه شد. دوباره تلاش کن.",
            show_alert=True
        )
        return

    await query.answer("بیداری با موفقیت انجام شد!")

    await query.edit_message_text(
        "🌑 AWAKENING COMPLETE\n\n"
        f"👤 Hunter: {player['name']}\n"
        f"⚔️ Class: {selected['name']}\n"
        f"✨ Unique Power: {power_name}\n"
        "🏅 Rank: E\n\n"
        "📊 INITIAL STATS\n"
        f"STR: {strength}\n"
        f"AGI: {agility}\n"
        f"VIT: {vitality}\n"
        f"INT: {intelligence}\n"
        f"SEN: {sense}\n\n"
        f"🔥 Power: {power}\n\n"
        "قدرت تو در سیستم ثبت شد."
    )


def setup_awakening(application):
    init_awakening_db()

    application.add_handler(
        CallbackQueryHandler(
            awakening_callback,
            pattern=r"^(awakening|awake_.*)$"
        )
    )