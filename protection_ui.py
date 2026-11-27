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
import rank_protection


def protection_keyboard(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔄 Refresh",
                callback_data=f"protection_refresh_{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data=f"protection_back_{user_id}"
            )
        ]
    ])


def protection_page(user_id):
    count = rank_protection.get_protection(user_id)

    return (
        "🛡️ RANK PROTECTION\n\n"
        f"Available Protection: {count}/"
        f"{rank_protection.MAX_PROTECTION}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "HOW IT WORKS\n\n"
        "• Prevents losing Rank Points after a ranked defeat.\n"
        "• One protection is consumed per protected defeat.\n"
        "• Maximum stored protection: 2\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "WIN STREAK BONUS\n\n"
        "3 Wins: +5 RP\n"
        "5 Wins: +10 RP\n"
        "7 Wins: +15 RP\n"
        "10 Wins: +25 RP\n\n"
        "Protection is only used in Ranked Matches."
    )


async def protection_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    if update.effective_chat.type != "private":
        await update.effective_message.reply_text(
            "این دستور فقط در چت خصوصی بات قابل استفاده است."
        )
        return

    if not db.get_player(user.id):
        await update.effective_message.reply_text(
            "ابتدا با /start ثبت نام کن."
        )
        return

    await update.effective_message.reply_text(
        protection_page(user.id),
        reply_markup=protection_keyboard(user.id)
    )
async def protection_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    user_id = query.from_user.id

    if query.message.chat.type != "private":
        await query.answer(
            "این منو فقط در چت خصوصی قابل استفاده است.",
            show_alert=True
        )
        return

    try:
        owner_id = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        await query.answer(
            "درخواست نامعتبر است.",
            show_alert=True
        )
        return

    if owner_id != user_id:
        await query.answer(
            "این منو متعلق به تو نیست.",
            show_alert=True
        )
        return

    if not db.get_player(user_id):
        await query.answer(
            "ابتدا با /start ثبت نام کن.",
            show_alert=True
        )
        return

    action = query.data.replace(
        f"_{owner_id}", ""
    )

    if action == "protection_back":
        await query.answer()
        await query.edit_message_text(
            "برای بازگشت به منوی اصلی از دستور /start استفاده کن."
        )
        return

    if action != "protection_refresh":
        await query.answer(
            "درخواست نامعتبر است.",
            show_alert=True
        )
        return

    await query.answer("اطلاعات به‌روزرسانی شد.")

    await query.edit_message_text(
        protection_page(user_id),
        reply_markup=protection_keyboard(user_id)
    )


def setup_protection_ui(application):
    rank_protection.init_protection_db()

    application.add_handler(
        CommandHandler(
            "protection",
            protection_command
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            protection_callback,
            pattern=r"^protection_(refresh|back)_\d+$"
        )
    )