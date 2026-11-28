import logging

import database as db
from progression import upgrade_stat

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes
)

logger = logging.getLogger(__name__)


STATS = {
    "STR": "💪 قدرت",
    "AGI": "⚡ چابکی",
    "VIT": "🛡 مقاومت",
    "INT": "🧠 هوش",
    "SEN": "👁 حس"
}


def stats_keyboard():
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
                "🛡 VIT +1",
                callback_data="stat_up_VIT"
            ),
            InlineKeyboardButton(
                "🧠 INT +1",
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
                "🔄 بروزرسانی",
                callback_data="stats_menu"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 منوی اصلی",
                callback_data="home"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


def get_stats_text(user_id):
    player = db.get_player(user_id)

    if not player:
        return "❌ بازیکن پیدا نشد."

    return (
        "📊 HUNTER STATUS\n"
        "━━━━━━━━━━━━━━\n\n"
        f"⭐ Level: {player['level']}\n"
        f"✨ Stat Points: {player['stat_points']}\n\n"
        f"💪 STR: {player['STR']}\n"
        f"⚡ AGI: {player['AGI']}\n"
        f"🛡 VIT: {player['VIT']}\n"
        f"🧠 INT: {player['INT']}\n"
        f"👁 SEN: {player['SEN']}\n\n"
        f"⚔ Power: {player['power']}\n"
        "━━━━━━━━━━━━━━\n"
        "برای ارتقای ویژگی‌ها از دکمه‌ها استفاده کن."
    )
async def stats_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    user_id = query.from_user.id

    # فقط صاحب چت خصوصی اجازه استفاده دارد.
    if (
        query.message.chat.type != "private"
        or query.message.chat.id != user_id
    ):
        await query.answer(
            "این منو متعلق به شما نیست.",
            show_alert=True
        )
        return

    action = query.data
    player = db.get_player(user_id)

    if not player:
        await query.answer(
            "ابتدا دستور /start را اجرا کن.",
            show_alert=True
        )
        return

    if action == "stats_menu":
        await query.answer()

        await query.edit_message_text(
            get_stats_text(user_id),
            reply_markup=stats_keyboard()
        )
        return

    if action.startswith("stat_up_"):
        stat = action.replace("stat_up_", "", 1)

        if stat not in STATS:
            await query.answer(
                "ویژگی نامعتبر است.",
                show_alert=True
            )
            return

        try:
            success, message = upgrade_stat(
                user_id,
                stat,
                1
            )

        except Exception:
            logger.exception(
                "Stat upgrade failed for user %s",
                user_id
            )

            await query.answer(
                "ارتقای ویژگی با مشکل مواجه شد.",
                show_alert=True
            )
            return

        await query.answer(
            message,
            show_alert=not success
        )

        if success:
            await query.edit_message_text(
                "✅ STAT UPGRADED!\n\n"
                f"{message}\n\n"
                f"{get_stats_text(user_id)}",
                reply_markup=stats_keyboard()
            )


def setup_stats(application):
    application.add_handler(
        CallbackQueryHandler(
            stats_callback,
            pattern=r"^(stats_menu|stat_up_.*)$"
        )
    )