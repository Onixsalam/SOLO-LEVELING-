import time
import logging

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
import progression
import daily_quests


logger = logging.getLogger(__name__)


# ==========================================
# SETTINGS
# ==========================================

TRAINING_COOLDOWN = 1800  # 30 minutes

TRAINING_REWARDS = {
    "strength": {
        "name": "💪 تمرین قدرت",
        "xp": 30,
        "description": "تمرکز روی قدرت بدنی"
    },
    "agility": {
        "name": "⚡ تمرین سرعت",
        "xp": 30,
        "description": "تمرکز روی سرعت و چابکی"
    },
    "vitality": {
        "name": "❤️ تمرین استقامت",
        "xp": 30,
        "description": "تمرکز روی استقامت"
    },
    "intelligence": {
        "name": "🧠 تمرین ذهن",
        "xp": 30,
        "description": "تمرکز روی هوش و کنترل مانا"
    },
    "sense": {
        "name": "👁️ تمرین حواس",
        "xp": 30,
        "description": "تمرکز روی درک محیط"
    }
}


# ==========================================
# DATABASE
# ==========================================

def init_training_db():

    with db.connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS training_sessions (
                user_id INTEGER PRIMARY KEY,
                last_training REAL NOT NULL DEFAULT 0
            )
        """)


# ==========================================
# COOLDOWN
# ==========================================

def get_training_remaining(user_id):

    with db.connect() as conn:

        row = conn.execute("""
            SELECT last_training
            FROM training_sessions
            WHERE user_id = ?
        """, (user_id,)).fetchone()

    if not row:
        return 0

    remaining = TRAINING_COOLDOWN - (
        time.time() - row["last_training"]
    )

    return max(0, int(remaining) + 1)


def format_time(seconds):

    minutes, seconds = divmod(seconds, 60)

    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours} ساعت و {minutes} دقیقه"

    return f"{minutes} دقیقه و {seconds} ثانیه"


# ==========================================
# TRAINING KEYBOARD
# ==========================================

def training_keyboard():

    keyboard = []

    for key, item in TRAINING_REWARDS.items():

        keyboard.append([
            InlineKeyboardButton(
                item["name"],
                callback_data=f"training_{key}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "🔄 Refresh",
            callback_data="training_refresh"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "🏠 Back",
            callback_data="home"
        )
    ])

    return InlineKeyboardMarkup(keyboard)


# ==========================================
# TRAINING PAGE
# ==========================================

def training_text(user_id):

    remaining = get_training_remaining(user_id)

    lines = [
        "🏋️ TRAINING CENTER",
        "",
        "برای تقویت شکارچی خود یک نوع تمرین انتخاب کن.",
        "",
        "🎁 پاداش هر تمرین: 30 XP",
        "⏳ زمان انتظار: 30 دقیقه",
        "",
        "━━━━━━━━━━━━━━━━"
    ]

    if remaining > 0:

        lines.extend([
            "",
            "🔒 تمرین فعلاً در دسترس نیست.",
            f"⏱️ زمان باقی‌مانده: {format_time(remaining)}"
        ])

    else:

        lines.extend([
            "",
            "🟢 آماده تمرین هستی!"
        ])

    return "\n".join(lines)
# ==========================================
# PERFORM TRAINING
# ==========================================

def perform_training(user_id, training_type):

    if training_type not in TRAINING_REWARDS:
        return False, "نوع تمرین معتبر نیست."

    if not db.get_player(user_id):
        return False, "بازیکن پیدا نشد."

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        row = conn.execute("""
            SELECT last_training
            FROM training_sessions
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        now = time.time()

        if row:

            remaining = TRAINING_COOLDOWN - (
                now - row["last_training"]
            )

            if remaining > 0:

                return False, (
                    "هنوز زمان تمرین بعدی نرسیده.\n"
                    f"⏱️ زمان باقی‌مانده: "
                    f"{format_time(int(remaining) + 1)}"
                )

        conn.execute("""
            INSERT INTO training_sessions (
                user_id,
                last_training
            )
            VALUES (?, ?)

            ON CONFLICT(user_id)
            DO UPDATE SET
                last_training = excluded.last_training
        """, (
            user_id,
            now
        ))

    reward = TRAINING_REWARDS[training_type]

    # دریافت XP
    progression.add_xp(
        user_id,
        reward["xp"]
    )

    # پیشرفت مأموریت روزانه
    daily_quests.add_quest_progress(
        user_id,
        "training",
        1
    )

    return True, (
        f"✅ تمرین با موفقیت انجام شد!\n\n"
        f"{reward['name']}\n"
        f"📈 XP دریافت‌شده: {reward['xp']}\n\n"
        f"⏳ تمرین بعدی: 30 دقیقه دیگر"
    )


# ==========================================
# TRAINING COMMAND
# ==========================================

async def training_command(update, context):

    if update.effective_chat.type != "private":

        await update.effective_message.reply_text(
            "تمرین فقط در چت خصوصی بات قابل استفاده است."
        )

        return

    user_id = update.effective_user.id

    if not db.get_player(user_id):

        await update.effective_message.reply_text(
            "ابتدا دستور /start را اجرا کن."
        )

        return

    await update.effective_message.reply_text(
        training_text(user_id),
        reply_markup=training_keyboard()
    )


# ==========================================
# TRAINING CALLBACK
# ==========================================

async def training_callback(update, context):

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

    if not db.get_player(user_id):

        await query.answer(
            "ابتدا دستور /start را اجرا کن.",
            show_alert=True
        )

        return

    if data == "training_refresh":

        await query.answer("به‌روزرسانی شد.")

        await query.edit_message_text(
            training_text(user_id),
            reply_markup=training_keyboard()
        )

        return

    if data.startswith("training_"):

        training_type = data.replace(
            "training_",
            "",
            1
        )

        if training_type not in TRAINING_REWARDS:
            await query.answer(
                "نوع تمرین نامعتبر است.",
                show_alert=True
            )
            return

        success, message = perform_training(
            user_id,
            training_type
        )

        await query.answer(
            message,
            show_alert=True
        )

        await query.edit_message_text(
            training_text(user_id),
            reply_markup=training_keyboard()
        )

        return

    await query.answer()


# ==========================================
# SETUP
# ==========================================

def setup_training(application):

    init_training_db()

    application.add_handler(
        CommandHandler(
            "training",
            training_command
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            training_callback,
            pattern=r"^training_(strength|agility|vitality|intelligence|sense|refresh)$"
        )
    )