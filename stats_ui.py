import database as db

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes
)

from progression import upgrade_stat


# =====================================
# STAT MENU
# =====================================

def stats_keyboard():

    keyboard = [
        [
            InlineKeyboardButton("💪 STR +1", callback_data="stat_up_STR"),
            InlineKeyboardButton("⚡ AGI +1", callback_data="stat_up_AGI")
        ],
        [
            InlineKeyboardButton("🛡 VIT +1", callback_data="stat_up_VIT"),
            InlineKeyboardButton("🧠 INT +1", callback_data="stat_up_INT")
        ],
        [
            InlineKeyboardButton("👁 SEN +1", callback_data="stat_up_SEN")
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="stats_menu")
        ],
        [
            InlineKeyboardButton("🔙 Main Menu", callback_data="home")
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# =====================================
# STAT TEXT
# =====================================

def get_stats_text(user_id):

    player = db.get_player(user_id)

    if not player:
        return "بازیکن پیدا نشد."

    return (
        "📊 HUNTER STAT UPGRADE\n\n"
        f"⭐ Level: {player['level']}\n"
        f"📈 Available Points: {player['stat_points']}\n\n"
        f"💪 STR: {player['STR']}\n"
        f"⚡ AGI: {player['AGI']}\n"
        f"🛡 VIT: {player['VIT']}\n"
        f"🧠 INT: {player['INT']}\n"
        f"👁 SEN: {player['SEN']}\n\n"
        f"⚔ Power: {player['power']}\n\n"
        "برای افزایش هر ویژگی، دکمه مربوط به آن را بزن."
    )


# =====================================
# CALLBACK
# =====================================

async def stats_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if query.message.chat.type != "private":
        await query.answer()
        return

    user_id = query.from_user.id
    action = query.data

    player = db.get_player(user_id)

    if not player:
        await query.answer(
            "اول دستور /start رو بزن.",
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

        stat = action.replace("stat_up_", "")

        success, message = upgrade_stat(
            user_id,
            stat,
            1
        )

        await query.answer(
            message,
            show_alert=not success
        )

        if success:

            await query.edit_message_text(
                "✅ STAT UPGRADED!\n\n"
                f"{message}\n\n"
                + get_stats_text(user_id),
                reply_markup=stats_keyboard()
            )


# =====================================
# SETUP
# =====================================

def setup_stats(application):

    application.add_handler(
        CallbackQueryHandler(
            stats_callback,
            pattern=r"^(stats_menu|stat_up_.*)$"
        )
    )