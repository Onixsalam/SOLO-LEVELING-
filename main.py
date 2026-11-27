import logging

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

import database as db
import combat

from config import BOT_TOKEN, GAME_NAME

from awakening import setup_awakening

from progression import (
    init_progression_db,
    unlock_available_skills,
    skills_text
)

from stats_ui import setup_stats
from pvp import setup_pvp
from ranked import setup_ranked
from ranked_season import setup_ranked_season
from protection_ui import setup_protection_ui
from daily_quests import setup_daily_quests


# ==================================================
# LOGGING
# ==================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# ==================================================
# MAIN MENU
# ==================================================

def main_menu(user_id):

    keyboard = [

        [
            InlineKeyboardButton(
                "👤 Profile",
                callback_data="profile"
            ),

            InlineKeyboardButton(
                "📊 Status",
                callback_data="stats_menu"
            )
        ],

        [
            InlineKeyboardButton(
                "⚔️ Battle",
                callback_data="battle"
            ),

            InlineKeyboardButton(
                "🏰 Dungeon",
                callback_data="dungeon"
            )
        ],

        [
            InlineKeyboardButton(
                "👥 Shadows",
                callback_data="shadows"
            ),

            InlineKeyboardButton(
                "🎒 Inventory",
                callback_data="inventory"
            )
        ],

        [
            InlineKeyboardButton(
                "🛒 Shop",
                callback_data="shop"
            ),

            InlineKeyboardButton(
                "✨ Awakening",
                callback_data="awakening"
            )
        ],

        [
            InlineKeyboardButton(
                "📈 Upgrade Stats",
                callback_data="stats_menu"
            ),

            InlineKeyboardButton(
                "📜 My Skills",
                callback_data="skills_menu"
            )
        ],

        [
            InlineKeyboardButton(
                "📋 Daily Quests",
                callback_data=f"daily_refresh_{user_id}"
            )
        ],

        [
            InlineKeyboardButton(
                "🛡️ Rank Protection",
                callback_data=f"protection_refresh_{user_id}"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# ==================================================
# BATTLE MENU
# ==================================================

def battle_menu():

    keyboard = [

        [
            InlineKeyboardButton(
                "🎯 Training",
                callback_data="training"
            )
        ],

        [
            InlineKeyboardButton(
                "🏆 Ranked Match",
                callback_data="ranked_search"
            )
        ],

        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="home"
            )
        ]

    ]

    return InlineKeyboardMarkup(keyboard)


# ==================================================
# BACK BUTTON
# ==================================================

def back_button(callback="home"):

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data=callback
            )
        ]
    ])


# ==================================================
# START COMMAND
# ==================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private":

        await update.message.reply_text(
            "برای استفاده از منوی بازی، وارد چت خصوصی بات شو."
        )

        return

    player = db.get_player(user.id)

    if not player:

        db.register_player(
            user.id,
            user.username,
            user.first_name
        )

    unlock_available_skills(user.id)

    await update.message.reply_text(

        f"⚔️ Welcome to {GAME_NAME}\n\n"
        f"Player: {user.first_name}\n"
        "Your journey as a Hunter begins now.",

        reply_markup=main_menu(user.id)
    )


# ==================================================
# HELP COMMAND
# ==================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = (

        "📖 GAME COMMANDS\n\n"

        "/start - Open game menu\n"
        "/help - Show commands\n"
        "/skills - Show your skills\n"
        "/rank - Show ranked profile\n"
        "/season - Show current season\n"
        "/top - Show top 10 players\n"
        "/daily - Daily quests\n"
        "/protection - Rank protection\n"
        "/duel - Challenge a player by replying to their message\n\n"

        "⚔️ PvP attacks are performed by replying to the battle "
        "message with the name of an unlocked skill."

    )

    await update.message.reply_text(text)


# ==================================================
# SKILLS COMMAND
# ==================================================

async def skills_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    player = db.get_player(user.id)

    if not player:

        await update.message.reply_text(
            "ابتدا با دستور /start وارد بازی شو."
        )

        return

    unlock_available_skills(user.id)

    await update.message.reply_text(
        skills_text(user.id)
    )


# ==================================================
# HOME CALLBACK
# ==================================================

async def home_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if query.message.chat.type != "private":

        await query.answer(
            "این منو فقط در چت خصوصی قابل استفاده است.",
            show_alert=True
        )

        return

    user_id = query.from_user.id

    if not db.get_player(user_id):

        await query.answer(
            "ابتدا با /start ثبت نام کن.",
            show_alert=True
        )

        return

    await query.answer()

    await query.edit_message_text(

        "⚔️ SOLO LEVELING: SHADOW LEGACY\n\n"
        "Choose your next action:",

        reply_markup=main_menu(user_id)
    )


# ==================================================
# MENU CALLBACK
# ==================================================

async def menu_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    user = query.from_user
    data = query.data

    if query.message.chat.type != "private":

        await query.answer(
            "این منو فقط در چت خصوصی قابل استفاده است.",
            show_alert=True
        )

        return

    player = db.get_player(user.id)

    if not player:

        await query.answer(
            "ابتدا با /start ثبت نام کن.",
            show_alert=True
        )

        return

    await query.answer()

    # PROFILE
    if data == "profile":

        text = (

            "👤 PLAYER PROFILE\n\n"

            f"Name: {player['name']}\n"
            f"Level: {player['level']}\n"
            f"Rank: {player['rank']}\n"
            f"Power: {player['power']}\n"
            f"Gold: {player['gold']}\n"
            f"Crystals: {player['crystals']}\n"

        )

        await query.edit_message_text(
            text,
            reply_markup=back_button()
        )

    # BATTLE
    elif data == "battle":

        await query.edit_message_text(

            "⚔️ BATTLE CENTER\n\n"
            "Choose your battle mode:",

            reply_markup=battle_menu()
        )

    # TRAINING
    elif data == "training":

        await query.edit_message_text(

            "🎯 TRAINING\n\n"
            "Training system will be connected in the next development stage.",

            reply_markup=back_button("battle")
        )

    # DUNGEON
    elif data == "dungeon":

        await query.edit_message_text(

            "🏰 DUNGEON GATE\n\n"
            "Dungeon system is being developed.",

            reply_markup=back_button()
        )

    # SHADOWS
    elif data == "shadows":

        await query.edit_message_text(

            "👥 SHADOW ARMY\n\n"
            "Your shadow army will appear here.",

            reply_markup=back_button()
        )

    # INVENTORY
    elif data == "inventory":

        await query.edit_message_text(

            "🎒 INVENTORY\n\n"
            "Your equipment and items will appear here.",

            reply_markup=back_button()
        )

    # SHOP
    elif data == "shop":

        await query.edit_message_text(

            "🛒 SHOP\n\n"
            "The shop system will be connected in a future stage.",

            reply_markup=back_button()
        )

    # SKILLS
    elif data == "skills_menu":

        unlock_available_skills(user.id)

        await query.edit_message_text(

            skills_text(user.id),

            reply_markup=back_button()
        )

    # UNKNOWN
    else:

        await query.edit_message_text(

            "این گزینه هنوز آماده نشده است.",

            reply_markup=back_button()
        )
# ==================================================
# ERROR HANDLER
# ==================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "An error occurred:",
        exc_info=context.error
    )


# ==================================================
# MAIN
# ==================================================

def main():

    logger.info(
        "Starting %s...",
        GAME_NAME
    )

    # DATABASE
    db.init_db()

    # GAME SYSTEMS
    init_progression_db()

    combat.init_combat_db()

    # TELEGRAM APPLICATION
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # SPECIALIZED SYSTEMS
    setup_awakening(app)

    setup_stats(app)

    setup_pvp(app)

    setup_ranked(app)

    setup_ranked_season(app)

    setup_protection_ui(app)

    setup_daily_quests(app)

    # COMMANDS
    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    app.add_handler(
        CommandHandler("skills", skills_command)
    )

    # HOME CALLBACK
    app.add_handler(
        CallbackQueryHandler(
            home_callback,
            pattern=r"^home$"
        )
    )

    # GENERAL MENU CALLBACK
    app.add_handler(
        CallbackQueryHandler(menu_callback)
    )

    # ERROR HANDLER
    app.add_error_handler(error_handler)

    logger.info("Bot is running.")

    app.run_polling()


# ==================================================
# RUN
# ==================================================

if __name__ == "__main__":
    main()