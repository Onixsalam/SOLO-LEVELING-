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
from config import BOT_TOKEN, GAME_NAME

from awakening import setup_awakening

from progression import (
    init_progression_db,
    unlock_available_skills,
    skills_text
)


# =====================================
# MAIN MENU
# =====================================

def main_menu():

    keyboard = [
        [
            InlineKeyboardButton("👤 Profile", callback_data="profile"),
            InlineKeyboardButton("📊 Status", callback_data="status")
        ],
        [
            InlineKeyboardButton("⚔️ Battle", callback_data="battle"),
            InlineKeyboardButton("🏰 Dungeon", callback_data="dungeon")
        ],
        [
            InlineKeyboardButton("👥 Shadows", callback_data="shadows"),
            InlineKeyboardButton("🎒 Inventory", callback_data="inventory")
        ],
        [
            InlineKeyboardButton("🛒 Shop", callback_data="shop"),
            InlineKeyboardButton("✨ Awakening", callback_data="awakening")
        ],
        [
            InlineKeyboardButton("📜 Quests", callback_data="quests")
        ],
        [
            InlineKeyboardButton("⚔️ My Skills", callback_data="show_skills")
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# =====================================
# BATTLE MENU
# =====================================

def battle_menu():

    keyboard = [
        [
            InlineKeyboardButton(
                "🔥 Training",
                callback_data="training"
            )
        ],
        [
            InlineKeyboardButton(
                "🏆 Ranked Match",
                callback_data="rank"
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


# =====================================
# START COMMAND
# =====================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_chat.type != "private":

        await update.message.reply_text(
            "برای شروع بازی وارد چت خصوصی ربات شو و /start رو بزن."
        )

        return

    user = update.effective_user

    player = db.get_player(user.id)

    if not player:

        db.register_player(
            user.id,
            user.username or "",
            user.first_name or "Hunter"
        )

    await update.message.reply_text(
        f"🌑 Welcome to {GAME_NAME}\n\n"
        "سیستم شکارچی فعال شد!\n"
        "آماده‌ای وارد دنیای سایه‌ها بشی؟",
        reply_markup=main_menu()
    )


# =====================================
# HELP COMMAND
# =====================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "📖 SHADOW LEGACY GUIDE\n\n"
        "/start - شروع بازی\n"
        "/help - راهنما\n"
        "/skills - مشاهده مهارت‌ها\n\n"
        "برای استفاده از امکانات بازی از منوی اصلی استفاده کن."
    )


# =====================================
# SKILLS COMMAND
# =====================================

async def skills_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_chat.type != "private":
        return

    user_id = update.effective_user.id

    player = db.get_player(user_id)

    if not player:

        await update.message.reply_text(
            "اول دستور /start رو بزن."
        )

        return

    unlocked = unlock_available_skills(user_id)

    text = skills_text(user_id)

    if unlocked:

        text = "🎉 مهارت‌های جدید آزاد شدند:\n\n"

        for skill in unlocked:
            text += f"⚔️ {skill}\n"

        text += "\n" + skills_text(user_id)

    await update.message.reply_text(text)


# =====================================
# HOME CALLBACK
# =====================================

async def home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    if query.message.chat.type != "private":

        await query.answer()
        return

    await query.answer()

    await query.edit_message_text(
        "🌑 SHADOW LEGACY\n\n"
        "منوی اصلی شکارچی:",
        reply_markup=main_menu()
    )


# =====================================
# GENERAL MENU CALLBACK
# =====================================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    user = query.from_user
    action = query.data

    if query.message.chat.type != "private":

        await query.answer()
        return

    player = db.get_player(user.id)

    if not player:

        await query.answer(
            "اول دستور /start رو بزن.",
            show_alert=True
        )

        return

    await query.answer()

    # =================================
    # PROFILE
    # =================================

    if action == "profile":

        await query.edit_message_text(
            f"👤 HUNTER PROFILE\n\n"
            f"Name: {player['name']}\n"
            f"Level: {player['level']}\n"
            f"Rank: {player['rank']}\n"
            f"Power: {player['power']}\n"
            f"Gold: {player['gold']}\n"
            f"Crystals: {player['crystals']}",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="home"
                    )
                ]
            ])
        )

    # =================================
    # STATUS
    # =================================

    elif action == "status":

        await query.edit_message_text(
            f"📊 HUNTER STATUS\n\n"
            f"⭐ Level: {player['level']}\n"
            f"✨ EXP: {player['xp']}\n\n"
            f"❤️ HP: {player['hp']}\n"
            f"🔮 MP: {player['mp']}\n\n"
            f"💪 STR: {player['STR']}\n"
            f"⚡ AGI: {player['AGI']}\n"
            f"🛡 VIT: {player['VIT']}\n"
            f"🧠 INT: {player['INT']}\n"
            f"👁 SEN: {player['SEN']}\n\n"
            f"📈 Stat Points: {player['stat_points']}\n"
            f"⚔ Power: {player['power']}",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="home"
                    )
                ]
            ])
        )

    # =================================
    # BATTLE
    # =================================

    elif action == "battle":

        await query.edit_message_text(
            "⚔️ BATTLE CENTER\n\n"
            "بخش موردنظرت رو انتخاب کن:",
            reply_markup=battle_menu()
        )

    # =================================
    # TRAINING
    # =================================

    elif action == "training":

        await query.edit_message_text(
            "🔥 TRAINING CENTER\n\n"
            "سیستم تمرین در مرحله بعدی فعال می‌شه.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="battle"
                    )
                ]
            ])
        )

    # =================================
    # INVENTORY
    # =================================

    elif action == "inventory":

        items = db.get_inventory(user.id)

        if not items:

            text = "🎒 INVENTORY\n\nکیف تو خالیه."

        else:

            text = "🎒 INVENTORY\n\n"

            for item in items:

                text += (
                    f"📦 {item['item_name']} "
                    f"× {item['quantity']}\n"
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

    # =================================
    # SHADOWS
    # =================================

    elif action == "shadows":

        shadows = db.get_shadows(user.id)

        if not shadows:

            text = (
                "👥 SHADOW ARMY\n\n"
                "هنوز هیچ سایه‌ای نداری."
            )

        else:

            text = "👥 SHADOW ARMY\n\n"

            for shadow in shadows:

                text += (
                    f"🌑 {shadow['shadow_name']}\n"
                    f"Rank: {shadow['shadow_rank']}\n\n"
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

    # =================================
    # SHOP
    # =================================

    elif action == "shop":

        await query.edit_message_text(
            "🛒 SHOP\n\n"
            "فروشگاه در مرحله بعدی ساخته می‌شه.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="home"
                    )
                ]
            ])
        )

    # =================================
    # DUNGEON
    # =================================

    elif action == "dungeon":

        await query.edit_message_text(
            "🏰 DUNGEON GATE\n\n"
            "سیستم دانجن در مرحله بعدی فعال می‌شه.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="home"
                    )
                ]
            ])
        )

    # =================================
    # RANKED MATCH
    # =================================

    elif action == "rank":

        await query.edit_message_text(
            "🏆 RANKED MATCH\n\n"
            "سیستم رنک مچ در مرحله بعدی ساخته می‌شه.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="battle"
                    )
                ]
            ])
        )

    # =================================
    # QUESTS
    # =================================

    elif action == "quests":

        await query.edit_message_text(
            "📜 QUEST CENTER\n\n"
            "سیستم مأموریت‌ها در مرحله بعدی ساخته می‌شه.",
            reply_markup=InlineKeyboardMarkup([
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

    elif action == "show_skills":

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


# =====================================
# MAIN
# =====================================

def main():

    # Initialize database
    db.init_db()

    # Initialize progression database
    init_progression_db()

    # Create application
    app = Application.builder().token(BOT_TOKEN).build()

    # Awakening system
    setup_awakening(app)

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("skills", skills_command))

    # Home navigation
    app.add_handler(
        CallbackQueryHandler(
            home_callback,
            pattern="^home$"
        )
    )

    # General menu handler
    app.add_handler(
        CallbackQueryHandler(menu_callback)
    )

    print("🌑 SHADOW LEGACY BOT STARTED")

    app.run_polling()


# =====================================
# RUN
# =====================================

if __name__ == "__main__":
    main()