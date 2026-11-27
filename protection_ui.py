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
import pvp_lifecycle as lifecycle


logger = logging.getLogger(__name__)


# ==================================================
# SETTINGS
# ==================================================

MAX_PROTECTION = lifecycle.MAX_PROTECTION


# ==================================================
# KEYBOARD
# ==================================================

def protection_keyboard(user_id):

    keyboard = [
        [
            InlineKeyboardButton(
                "🔄 Refresh",
                callback_data=f"protection_refresh_{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Back",
                callback_data=f"protection_back_{user_id}"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# ==================================================
# PROTECTION PAGE
# ==================================================

def protection_page(user_id):

    count = lifecycle.get_protection(user_id)

    count = max(
        0,
        min(MAX_PROTECTION, int(count))
    )

    available = "🛡️" * count
    empty = "▫️" * (MAX_PROTECTION - count)

    return (
        "🛡️ RANK PROTECTION\n\n"
        f"محافظت‌های ذخیره‌شده: {count}/{MAX_PROTECTION}\n\n"
        f"{available}{empty}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📌 نحوه عملکرد:\n\n"
        "اگر در مسابقه Ranked شکست بخوری، "
        "یک محافظت مصرف می‌شود و امتیاز رنکت کم نمی‌شود.\n\n"
        "هر بازیکن حداکثر دو محافظت می‌تواند داشته باشد.\n\n"
        "⚠️ محافظت فقط برای باخت Ranked است؛ "
        "در دوئل دوستانه استفاده نمی‌شود."
    )


# ==================================================
# SHOW PAGE
# ==================================================

async def show_protection(query, user_id):

    await query.edit_message_text(
        protection_page(user_id),
        reply_markup=protection_keyboard(user_id)
    )


# ==================================================
# COMMAND
# ==================================================

async def protection_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_chat.type != "private":

        await update.effective_message.reply_text(
            "این دستور را در چت خصوصی بات اجرا کن."
        )

        return

    user_id = update.effective_user.id

    if not db.get_player(user_id):

        await update.effective_message.reply_text(
            "ابتدا دستور /start را اجرا کن."
        )

        return

    await update.effective_message.reply_text(
        protection_page(user_id),
        reply_markup=protection_keyboard(user_id)
    )
# ==================================================
# CALLBACK
# ==================================================

async def protection_callback(update, context):

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

    parts = query.data.split("_")

    if len(parts) != 3 and len(parts) != 4:
        await query.answer(
            "درخواست نامعتبر است.",
            show_alert=True
        )
        return

    try:
        owner_id = int(parts[-1])
    except ValueError:
        await query.answer(
            "شناسه بازیکن نامعتبر است.",
            show_alert=True
        )
        return

    user_id = query.from_user.id

    # جلوگیری از استفاده دیگران از صفحه بازیکن
    if owner_id != user_id:

        await query.answer(
            "این صفحه متعلق به بازیکن دیگری است.",
            show_alert=True
        )

        return

    if not db.get_player(user_id):

        await query.answer(
            "ابتدا دستور /start را اجرا کن.",
            show_alert=True
        )

        return

    action = parts[1]

    if action == "refresh":

        await query.answer(
            "اطلاعات به‌روزرسانی شد."
        )

        await show_protection(
            query,
            user_id
        )

        return

    if action == "back":

        await query.answer()

        await query.edit_message_text(
            "برای بازگشت به منوی اصلی دستور /start را اجرا کن."
        )

        return

    await query.answer()


# ==================================================
# SETUP
# ==================================================

def setup_protection_ui(application):

    lifecycle.init_lifecycle_db()

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