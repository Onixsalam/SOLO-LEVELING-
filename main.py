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


# =====================================
# DATABASE MIGRATION
# =====================================

def ensure_player_columns():

    with db.connect() as conn:

        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(players)"
            ).fetchall()
        }

        required = {
            "is_dead": "INTEGER DEFAULT 0",
            "wins": "INTEGER DEFAULT 0",
            "losses": "INTEGER DEFAULT 0",
            "deaths": "INTEGER DEFAULT 0"
        }

        for column, definition in required.items():

            if column not in columns:

                conn.execute(
                    f"ALTER TABLE players ADD COLUMN "
                    f"{column} {definition}"
                )


# =====================================
# KEYBOARDS
# =====================================

def main_menu():

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
                callback_data="show_skills"
            )
        ],

        [
            InlineKeyboardButton(
                "📋 Quests",
                callback_data="quests"
            )
        ]

    ]

    return InlineKeyboardMarkup(keyboard)


def battle_menu():

    keyboard = [

        [
            InlineKeyboardButton(
                "🥊 Training",
                callback_data="training"
            )
        ],

        [
            InlineKeyboardButton(
                "🏆 Ranked Match",
                callback_data="ranked"
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


def back_button():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="home"
            )
        ]
    ])


# =====================================
# PLAYER DATA
# =====================================

def get_player(user_id):

    with db.connect() as conn:

        return conn.execute(
            """
            SELECT *
            FROM players
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()


# =====================================
# START COMMAND
# =====================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user
    message = update.effective_message

    if message.chat.type != "private":

        await message.reply_text(
            "برای استفاده از منوی بازی وارد چت خصوصی بات شو."
        )

        return

    player = get_player(user.id)

    if not player:

        db.register_player(
            user.id,
            user.username,
            user.first_name
        )

    await message.reply_text(
        f"🌑 WELCOME TO {GAME_NAME}\n\n"
        "به دنیای شکارچیان خوش اومدی!\n"
        "ماجراجویی تو از اینجا شروع می‌شه.",
        reply_markup=main_menu()
    )


# =====================================
# HELP COMMAND
# =====================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.effective_message.reply_text(
        "📖 SHADOW LEGACY HELP\n\n"
        "/start - شروع بازی\n"
        "/help - راهنما\n"
        "/skills - مشاهده مهارت‌ها\n"
        "/duel - شروع مبارزه با ریپلای\n\n"
        "برای مبارزه در گروه، روی پیام حریفت "
        "ریپلای کن و /duel بفرست."
    )


# =====================================
# SKILLS COMMAND
# =====================================

async def skills_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user
    message = update.effective_message

    if message.chat.type != "private":
        await message.reply_text(
            "مهارت‌ها رو در چت خصوصی بات مشاهده کن."
        )
        return

    if not get_player(user.id):
        await message.reply_text(
            "ابتدا با دستور /start ثبت‌نام کن."
        )
        return

    unlock_available_skills(user.id)

    await message.reply_text(
        skills_text(user.id)
    )


# =====================================
# HOME CALLBACK
# =====================================

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

    player = get_player(query.from_user.id)

    if not player:
        await query.answer(
            "ابتدا ثبت‌نام کن.",
            show_alert=True
        )
        return

    await query.answer()

    await query.edit_message_text(
        f"🌑 {GAME_NAME}\n\n"
        "منوی اصلی بازی:",
        reply_markup=main_menu()
    )


# =====================================
# MENU CALLBACK
# =====================================

async def menu_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    if query.message.chat.type != "private":

        await query.answer(
            "این منو فقط در چت خصوصی قابل استفاده است.",
            show_alert=True
        )

        return

    player = get_player(user_id)

    if not player:

        await query.answer(
            "ابتدا با دستور /start ثبت‌نام کن.",
            show_alert=True
        )

        return

    await query.answer()

    # =================================
    # PROFILE
    # =================================

    if data == "profile":

        player = get_player(user_id)

        text = (
            "👤 HUNTER PROFILE\n\n"
            f"Name: {player['name']}\n"
            f"Level: {player['level']}\n"
            f"HP: {player['hp']}\n"
            f"MP: {player['mp']}\n"
            f"Gold: {player['gold']}\n"
            f"Crystals: {player['crystals']}\n"
            f"Power: {player['power']}\n"
        )

        await query.edit_message_text(
            text,
            reply_markup=back_button()
        )

    # =================================
    # BATTLE
    # =================================

    elif data == "battle":

        await query.edit_message_text(
            "⚔️ BATTLE CENTER\n\n"
            "نوع مبارزه خودت رو انتخاب کن:",
            reply_markup=battle_menu()
        )

    # =================================
    # TRAINING
    # =================================

    elif data == "training":

        await query.edit_message_text(
            "🥊 TRAINING CENTER\n\n"
            "بخش تمرینی در مرحله بعدی به سیستم مبارزه "
            "و مهارت‌ها متصل می‌شه.",
            reply_markup=back_button()
        )

    # =================================
    # RANKED MATCH
    # =================================

    elif data == "ranked":

        await query.edit_message_text(
            "🏆 RANKED MATCH\n\n"
            "سیستم پیدا کردن حریف و مسابقات رتبه‌بندی "
            "در مرحله بعدی پیاده‌سازی می‌شه.",
            reply_markup=back_button()
        )

    # =================================
    # DUNGEON
    # =================================

    elif data == "dungeon":

        await query.edit_message_text(
            "🏰 DUNGEON GATE\n\n"
            "دروازه‌ها و دانجن‌ها در این بخش قرار می‌گیرن.\n\n"
            "سیستم ورود، مبارزه، جایزه و باس‌ها "
            "در مراحل بعدی اضافه می‌شه.",
            reply_markup=back_button()
        )

    # =================================
    # SHADOWS
    # =================================

    elif data == "shadows":

        with db.connect() as conn:

            shadows = conn.execute(
                """
                SELECT *
                FROM shadows
                WHERE user_id = ?
                """,
                (user_id,)
            ).fetchall()

        if not shadows:

            text = (
                "👥 SHADOW ARMY\n\n"
                "هنوز هیچ شادویی نداری."
            )

        else:

            text = "👥 YOUR SHADOW ARMY\n\n"

            for shadow in shadows:

                text += (
                    f"⚔️ {shadow['shadow_name']}\n"
                    f"Rank: {shadow['shadow_rank']}\n\n"
                )

        await query.edit_message_text(
            text,
            reply_markup=back_button()
        )

    # =================================
    # INVENTORY
    # =================================

    elif data == "inventory":

        with db.connect() as conn:

            items = conn.execute(
                """
                SELECT *
                FROM inventory
                WHERE user_id = ?
                """,
                (user_id,)
            ).fetchall()

        if not items:

            text = (
                "🎒 INVENTORY\n\n"
                "کیف تو خالیه."
            )

        else:

            text = "🎒 YOUR INVENTORY\n\n"

            for item in items:

                text += (
                    f"📦 {item['item_name']}\n"
                    f"Amount: {item['quantity']}\n\n"
                )

        await query.edit_message_text(
            text,
            reply_markup=back_button()
        )

    # =================================
    # SHOP
    # =================================

    elif data == "shop":

        await query.edit_message_text(
            "🛒 SHADOW SHOP\n\n"
            "بخش فروشگاه در مرحله بعدی ساخته می‌شه.",
            reply_markup=back_button()
        )

    # =================================
    # AWAKENING
    # =================================

    elif data == "awakening":

        await query.edit_message_text(
            "✨ AWAKENING SYSTEM\n\n"
            "برای مشاهده و انجام بیداری، "
            "از دکمه زیر استفاده کن.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✨ Open Awakening",
                        callback_data="awakening"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="home"
                    )
                ]
            ])
        )

    # =================================
    # SKILLS
    # =================================

    elif data == "show_skills":

        unlock_available_skills(user_id)

        await query.edit_message_text(
            skills_text(user_id),
            reply_markup=back_button()
        )

    # =================================
    # QUESTS
    # =================================

    elif data == "quests":

        await query.edit_message_text(
            "📋 QUEST CENTER\n\n"
            "Daily Quests\n"
            "Main Quests\n"
            "Hidden Quests\n"
            "Achievements\n"
            "Special Quests\n\n"
            "سیستم مأموریت‌ها در مرحله بعدی ساخته می‌شه.",
            reply_markup=back_button()
        )


# =====================================
# MAIN
# =====================================

def main():

    print("Initializing Shadow Legacy...")

    # DATABASE
    db.init_db()

    # DATABASE MIGRATION
    ensure_player_columns()

    # GAME SYSTEMS
    init_progression_db()

    combat.init_combat_db()

    # TELEGRAM APPLICATION
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # AWAKENING
    setup_awakening(app)

    # STATS
    setup_stats(app)

    # PVP + REVIVAL
    setup_pvp(app)

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

    # HOME BUTTON
    app.add_handler(
        CallbackQueryHandler(
            home_callback,
            pattern="^home$"
        )
    )

    # OTHER MENU BUTTONS
    app.add_handler(
        CallbackQueryHandler(menu_callback)
    )

    print("SHADOW LEGACY IS RUNNING!")

    app.run_polling()


# =====================================
# RUN
# =====================================

if __name__ == "__main__":
    main()