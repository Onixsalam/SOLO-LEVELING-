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
from training import setup_training


# ==========================================
# LOGGING
# ==========================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# ==========================================
# DATABASE MIGRATION
# ==========================================

def ensure_player_columns():

    required_columns = {
        "is_dead": "INTEGER DEFAULT 0",
        "wins": "INTEGER DEFAULT 0",
        "losses": "INTEGER DEFAULT 0",
        "deaths": "INTEGER DEFAULT 0"
    }

    with db.connect() as conn:

        existing = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(players)"
            ).fetchall()
        }

        for column, definition in required_columns.items():

            if column not in existing:

                conn.execute(
                    f"ALTER TABLE players ADD COLUMN "
                    f"{column} {definition}"
                )


# ==========================================
# MAIN MENU
# ==========================================

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


# ==========================================
# BATTLE MENU
# ==========================================

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


# ==========================================
# START
# ==========================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private":

        await update.effective_message.reply_text(
            "برای استفاده از منوی بازی وارد چت خصوصی بات شو."
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

    await update.effective_message.reply_text(

        f"⚔️ Welcome to {GAME_NAME}\n\n"
        f"Player: {user.first_name}\n"
        "Your journey as a Hunter begins now.",

        reply_markup=main_menu(user.id)
    )


# ==========================================
# HELP
# ==========================================

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
        "/top - Show top players\n"
        "/daily - Daily quests\n"
        "/training - Training center\n"
        "/protection - Rank protection\n"
        "/duel - Challenge a player by replying to their message\n\n"
        "⚔️ PvP attacks are performed by replying to "
        "the battle message with the name of an unlocked skill."
    )

    await update.effective_message.reply_text(text)


# ==========================================
# SKILLS COMMAND
# ==========================================

async def skills_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    player = db.get_player(user.id)

    if not player:

        await update.effective_message.reply_text(
            "ابتدا با دستور /start ثبت‌نام کن."
        )

        return

    unlock_available_skills(user.id)

    await update.effective_message.reply_text(
        skills_text(user.id)
    )


# ==========================================
# HOME CALLBACK
# ==========================================

async def home_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query.message or query.message.chat.type != "private":

        await query.answer(
            "این منو فقط در چت خصوصی قابل استفاده است.",
            show_alert=True
        )

        return

    user_id = query.from_user.id

    if not db.get_player(user_id):

        await query.answer(
            "ابتدا با /start ثبت‌نام کن.",
            show_alert=True
        )

        return

    await query.answer()

    await query.edit_message_text(

        "⚔️ SOLO LEVELING: SHADOW LEGACY\n\n"
        "Choose your next action:",

        reply_markup=main_menu(user_id)
    )


# ==========================================
# GENERAL MENU CALLBACK
# ==========================================

async def menu_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query.message or query.message.chat.type != "private":

        await query.answer(
            "این منو فقط در چت خصوصی قابل استفاده است.",
            show_alert=True
        )

        return

    user = query.from_user
    data = query.data

    player = db.get_player(user.id)

    if not player:

        await query.answer(
            "ابتدا با /start ثبت‌نام کن.",
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
        )

        await query.edit_message_text(

            text,

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="home"
                    )
                ]
            ])
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

        from training import training_text, training_keyboard

        await query.edit_message_text(
            training_text(user.id),
            reply_markup=training_keyboard()
        )

    # DUNGEON

    elif data == "dungeon":

        await query.edit_message_text(

            "🏰 DUNGEON GATE\n\n"
            "Dungeon system is being developed.",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="home"
                    )
                ]
            ])
        )
    # SHADOWS

    elif data == "shadows":

        await query.edit_message_text(

            "👥 SHADOW ARMY\n\n"
            "Your shadow army will appear here.",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="home"
                    )
                ]
            ])
        )

    # INVENTORY

    elif data == "inventory":

        await query.edit_message_text(

            "🎒 INVENTORY\n\n"
            "Your equipment and items will appear here.",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="home"
                    )
                ]
            ])
        )

    # SHOP

    elif data == "shop":

        await query.edit_message_text(

            "🛒 SHOP\n\n"
            "Shop system is being developed.",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="home"
                    )
                ]
            ])
        )

    # SKILLS

    elif data == "skills_menu":

        unlock_available_skills(user.id)

        await query.edit_message_text(

            skills_text(user.id),

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="home"
                    )
                ]
            ])
        )

    # AWAKENING

    elif data == "awakening":

        from awakening import awakening_menu

        await query.edit_message_text(
            awakening_menu(user.id)
        )

    else:

        await query.edit_message_text(

            "این گزینه هنوز آماده نشده است.",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="home"
                    )
                ]
            ])
        )


# ==========================================
# ERROR HANDLER
# ==========================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "An error occurred:",
        exc_info=context.error
    )


# ==========================================
# MAIN
# ==========================================

def main():

    logger.info(
        "Starting %s...",
        GAME_NAME
    )

    # DATABASE

    db.init_db()

    ensure_player_columns()

    # GAME SYSTEMS

    init_progression_db()

    combat.init_combat_db()

    # TELEGRAM APPLICATION

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # SPECIALIZED SYSTEMS

    setup_awakening(application)

    setup_stats(application)

    setup_pvp(application)

    setup_ranked(application)

    setup_ranked_season(application)

    setup_protection_ui(application)

    setup_daily_quests(application)

    setup_training(application)

    # COMMANDS

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        CommandHandler("skills", skills_command)
    )

    # HOME CALLBACK

    application.add_handler(
        CallbackQueryHandler(
            home_callback,
            pattern=r"^home$"
        )
    )

    # GENERAL MENU CALLBACK
    # باید بعد از هندلرهای اختصاصی ثبت شود.

    application.add_handler(
        CallbackQueryHandler(
            menu_callback
        )
    )

    # ERROR HANDLER

    application.add_error_handler(
        error_handler
    )

    logger.info("Bot is running.")

    application.run_polling()


# ==========================================
# RUN
# ==========================================

if __name__ == "__main__":
    main()