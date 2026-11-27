import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import CallbackQueryHandler

import database as db
import progression


logger = logging.getLogger(__name__)


# ==================================================
# KEYBOARD
# ==================================================

def stats_keyboard(user_id):

    keyboard = [
        [
            InlineKeyboardButton(
                "💪 STR +1",
                callback_data="stat_up_STR"
            ),
            InlineKeyboardButton(
                "⚡ AGI +1",
                callback_data="stat_up_AGI"
            )
        ],
        [
            InlineKeyboardButton(
                "❤️ VIT +1",
                callback_data="stat_up_VIT"
            ),
            InlineKeyboardButton(
                "🔮 INT +1",
                callback_data="stat_up_INT"
            )
        ],
        [
            InlineKeyboardButton(
                "👁 SEN +1",
                callback_data="stat_up_SEN"
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Refresh",
                callback_data="stats_menu"
            ),
            InlineKeyboardButton(
                "🏠 Back",
                callback_data="home"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# ==================================================
# STAT DISPLAY
# ==================================================

def get_stats_text(user_id):

    player = db.get_player(user_id)

    if not player:
        return "❌ بازیکن پیدا نشد."

    info = progression.get_progression_info(user_id)

    if not info:
        return "❌ اطلاعات ویژگی‌ها در دسترس نیست."

    return (
        "📊 STATUS UPGRADE\n\n"
        f"⭐ Level: {info['level']}\n"
        f"🔥 Power: {info['power']}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📌 YOUR ATTRIBUTES\n\n"
        f"💪 STR: {info['STR']}\n"
        f"⚡ AGI: {info['AGI']}\n"
        f"❤️ VIT: {info['VIT']}\n"
        f"🔮 INT: {info['INT']}\n"
        f"👁 SEN: {info['SEN']}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🎯 Available Points: {info['stat_points']}\n\n"
        "برای افزایش هر ویژگی، دکمه مربوطه را انتخاب کن."
    )


# ==================================================
# SHOW STATS
# ==================================================

async def show_stats(query, user_id):

    await query.edit_message_text(
        get_stats_text(user_id),
        reply_markup=stats_keyboard(user_id)
    )
# ==================================================
# CALLBACK
# ==================================================

async def stats_callback(update, context):

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

    if not db.get_player(user_id):

        await query.answer(
            "ابتدا دستور /start را اجرا کن.",
            show_alert=True
        )

        return

    action = query.data

    # نمایش صفحه ویژگی‌ها
    if action == "stats_menu":

        await query.answer()

        await show_stats(
            query,
            user_id
        )

        return

    # ارتقای ویژگی
    if action.startswith("stat_up_"):

        stat = action.replace(
            "stat_up_",
            "",
            1
        ).upper()

        if stat not in progression.VALID_STATS:

            await query.answer(
                "ویژگی نامعتبر است.",
                show_alert=True
            )

            return

        success, message = progression.upgrade_stat(
            user_id,
            stat,
            1
        )

        await query.answer(
            message,
            show_alert=not success
        )

        await show_stats(
            query,
            user_id
        )

        return

    await query.answer()


# ==================================================
# SETUP
# ==================================================

def setup_stats(application):

    application.add_handler(
        CallbackQueryHandler(
            stats_callback,
            pattern=r"^(stats_menu|stat_up_(STR|AGI|VIT|INT|SEN))$"
        )
    )