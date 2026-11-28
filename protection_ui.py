import logging

import database as db
import rank_protection

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


def protection_keyboard(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔄 بروزرسانی",
                callback_data=f"protection_refresh_{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data=f"protection_back_{user_id}"
            )
        ]
    ])


def protection_page(user_id):
    count = rank_protection.get_protection(user_id)

    return (
        "🛡️ RANK PROTECTION\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"محافظ‌های باقی‌مانده: {count}/"
        f"{rank_protection.MAX_PROTECTION}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "نحوه عملکرد:\n\n"
        "• هنگام باخت در Ranked Match، از کم شدن امتیاز رنک جلوگیری می‌کند.\n"
        "• هر باخت محافظت‌شده، یک محافظ مصرف می‌کند.\n"
        "• حداکثر دو محافظ می‌توانی ذخیره کنی.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "پاداش بردهای متوالی:\n\n"
        "3 برد: +5 RP\n"
        "5 برد: +10 RP\n"
        "7 برد: +15 RP\n"
        "10 برد: +25 RP\n\n"
        "🛡️ محافظت فقط در Ranked Match استفاده می‌شود."
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
            "ابتدا با دستور /start ثبت‌نام کن."
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

    if (
        query.message.chat.type != "private"
        or query.message.chat.id != user_id
    ):
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
            "این منو متعلق به شما نیست.",
            show_alert=True
        )
        return

    if not db.get_player(user_id):
        await query.answer(
            "ابتدا با دستور /start ثبت‌نام کن.",
            show_alert=True
        )
        return

    action = query.data.rsplit("_", 1)[0]

    if action == "protection_back":
        await query.answer()
        await query.edit_message_text(
            "برای بازگشت به منوی اصلی دستور /start را اجرا کن."
        )
        return

    if action == "protection_refresh":
        await query.answer("اطلاعات بروزرسانی شد.")

        await query.edit_message_text(
            protection_page(user_id),
            reply_markup=protection_keyboard(user_id)
        )
        return

    await query.answer(
        "درخواست نامعتبر است.",
        show_alert=True
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