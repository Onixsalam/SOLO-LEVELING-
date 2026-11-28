import time
import logging

import database as db
from progression import add_xp

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

logger = logging.getLogger(__name__)

TRAINING_COOLDOWN = 30 * 60
TRAINING_XP = 30


def init_training_db():
    with db.connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS training_cooldowns (
                user_id INTEGER PRIMARY KEY,
                last_training INTEGER DEFAULT 0
            )
        """)


def get_training_remaining(user_id):
    with db.connect() as conn:
        row = conn.execute("""
            SELECT last_training
            FROM training_cooldowns
            WHERE user_id = ?
        """, (user_id,)).fetchone()

    if not row:
        return 0

    remaining = (
        row["last_training"]
        + TRAINING_COOLDOWN
        - int(time.time())
    )

    return max(0, remaining)


def training_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⚔️ START TRAINING",
                callback_data="training_start"
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Refresh",
                callback_data="training"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Main Menu",
                callback_data="home"
            )
        ]
    ])


def training_text(user_id):
    remaining = get_training_remaining(user_id)

    if remaining:
        minutes = remaining // 60
        seconds = remaining % 60

        status = (
            f"⏳ Next training in: "
            f"{minutes}m {seconds}s"
        )
    else:
        status = "✅ Training is available!"

    return (
        "⚔️ HUNTER TRAINING\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "تمرین کن تا تجربه بیشتری به دست بیاوری.\n\n"
        f"🎁 Reward: {TRAINING_XP} XP\n"
        f"⏱ Cooldown: {TRAINING_COOLDOWN // 60} minutes\n\n"
        f"{status}"
    )
async def start_training(user_id):
    now = int(time.time())

    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")

        player = conn.execute("""
            SELECT user_id, is_dead
            FROM players
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not player:
            return False, "ابتدا با دستور /start ثبت‌نام کن."

        if player["is_dead"]:
            return False, "تا زمان احیای کامل نمی‌توانی تمرین کنی."

        row = conn.execute("""
            SELECT last_training
            FROM training_cooldowns
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if row:
            remaining = (
                row["last_training"]
                + TRAINING_COOLDOWN
                - now
            )

            if remaining > 0:
                minutes = remaining // 60
                seconds = remaining % 60

                return False, (
                    f"⏳ هنوز آماده تمرین نیستی.\n"
                    f"زمان باقی‌مانده: {minutes} دقیقه "
                    f"و {seconds} ثانیه"
                )

        conn.execute("""
            INSERT INTO training_cooldowns (
                user_id,
                last_training
            )
            VALUES (?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET last_training = excluded.last_training
        """, (user_id, now))

    try:
        add_xp(user_id, TRAINING_XP)

        try:
            from daily_quests import add_quest_progress
            add_quest_progress(user_id, "training", 1)
        except Exception:
            logger.exception(
                "Training quest progress failed for %s",
                user_id
            )

        return True, (
            "✅ TRAINING COMPLETE!\n\n"
            f"⭐ XP received: +{TRAINING_XP}\n"
            "⚔️ قدرتت را با تمرین بیشتر افزایش بده!"
        )

    except Exception:
        logger.exception(
            "Training XP failed for user %s",
            user_id
        )
        return False, (
            "تمرین ثبت شد، اما افزودن XP با مشکل مواجه شد. "
            "نیاز به بررسی دارد."
        )


async def training_callback(update, context):
    query = update.callback_query
    user_id = query.from_user.id

    if (
        not query.message
        or query.message.chat.type != "private"
        or query.message.chat.id != user_id
    ):
        await query.answer(
            "این منو فقط در چت خصوصی قابل استفاده است.",
            show_alert=True
        )
        return

    if not db.get_player(user_id):
        await query.answer(
            "ابتدا /start را اجرا کن.",
            show_alert=True
        )
        return

    if query.data == "training":
        await query.answer()

        await query.edit_message_text(
            training_text(user_id),
            reply_markup=training_keyboard()
        )
        return

    if query.data == "training_start":
        success, message = await start_training(user_id)

        await query.answer(
            "تمرین انجام شد!" if success else "امکان تمرین وجود ندارد.",
            show_alert=not success
        )

        await query.edit_message_text(
            f"{message}\n\n{training_text(user_id)}",
            reply_markup=training_keyboard()
        )


async def training_command(update, context):
    user_id = update.effective_user.id

    if update.effective_chat.type != "private":
        await update.effective_message.reply_text(
            "تمرین فقط در چت خصوصی بات امکان‌پذیر است."
        )
        return

    if not db.get_player(user_id):
        await update.effective_message.reply_text(
            "ابتدا /start را اجرا کن."
        )
        return

    await update.effective_message.reply_text(
        training_text(user_id),
        reply_markup=training_keyboard()
    )


def setup_training(application):
    init_training_db()

    application.add_handler(
        CommandHandler("training", training_command)
    )

    application.add_handler(
        CallbackQueryHandler(
            training_callback,
            pattern=r"^(training|training_start)$"
        )
    )