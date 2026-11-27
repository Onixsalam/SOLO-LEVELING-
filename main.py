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


# =========================
# MAIN MENU
# =========================

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
            InlineKeyboardButton("🔥 Training", callback_data="training")
        ],
        [
            InlineKeyboardButton("✨ Awakening", callback_data="awakening"),
            InlineKeyboardButton("📜 Quests", callback_data="quests")
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================
# BATTLE MENU
# =========================

def battle_menu():

    keyboard = [
        [
            InlineKeyboardButton("🥊 Training", callback_data="training")
        ],
        [
            InlineKeyboardButton("🏆 Ranked Match", callback_data="rank")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data="home")
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_chat.type != "private":

        await update.message.reply_text(
            "برای شروع بازی، وارد چت خصوصی ربات شو و دستور /start رو بفرست."
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
        "برای شروع ماجراجویی از منوی زیر استفاده کن.",
        reply_markup=main_menu()
    )


# =========================
# HELP
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "📖 راهنمای بازی\n\n"
        "/start - شروع بازی\n"
        "/help - راهنما\n\n"
        "برای استفاده از امکانات بازی از منوی اصلی استفاده کن."
    )


# =========================
# HOME
# =========================

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


# =========================
# MENU CALLBACK
# =========================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    user = query.from_user
    action = query.data

    if query.message.chat.type != "private":
        await query.answer()
        return

    player = db.get_player(user.id)

    if not player:
        await query.answer("اول دستور /start رو بزن.", show_alert=True)
        return

    await query.answer()

    # PROFILE

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
                [InlineKeyboardButton("🔙 Back", callback_data="home")]
            ])
        )

    # STATUS

    elif action == "status":

        await query.edit_message_text(
            f"📊 HUNTER STATUS\n\n"
            f"❤️ HP: {player['hp']}\n"
            f"🔮 MP: {player['mp']}\n\n"
            f"💪 STR: {player['STR']}\n"
            f"⚡ AGI: {player['AGI']}\n"
            f"🛡 VIT: {player['VIT']}\n"
            f"🧠 INT: {player['INT']}\n"
            f"👁 SEN: {player['SEN']}\n\n"
            f"⭐ Level: {player['level']}\n"
            f"⚔ Power: {player['power']}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="home")]
            ])
        )

    # BATTLE

    elif action == "battle":

        await query.edit_message_text(
            "⚔️ BATTLE CENTER\n\n"
            "یکی از بخش‌های مبارزه رو انتخاب کن:",
            reply_markup=battle_menu()
        )

    # TRAINING

    elif action == "training":

        await query.edit_message_text(
            "🔥 TRAINING CENTER\n\n"
            "بخش تمرین در حال آماده‌سازی است.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="home")]
            ])
        )

    # INVENTORY

    elif action == "inventory":

        items = db.get_inventory(user.id)

        if not items:

            text = "🎒 INVENTORY\n\nکیف تو خالیه."

        else:

            text = "🎒 INVENTORY\n\n"

            for item in items:

                text += f"📦 {item['item_name']} × {item['quantity']}\n"

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="home")]
            ])
        )

    # SHADOWS

    elif action == "shadows":

        shadows = db.get_shadows(user.id)

        if not shadows:

            text = "👥 SHADOW ARMY\n\nهنوز هیچ سایه‌ای نداری."

        else:

            text = "👥 SHADOW ARMY\n\n"

            for shadow in shadows:

                text += f"🌑 {shadow['shadow_name']} | Rank: {shadow['shadow_rank']}\n"

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="home")]
            ])
        )

    # SHOP

    elif action == "shop":

        await query.edit_message_text(
            "🛒 SHOP\n\n"
            "فروشگاه در حال آماده‌سازی است.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="home")]
            ])
        )

    # DUNGEON

    elif action == "dungeon":

        await query.edit_message_text(
            "🏰 DUNGEON GATE\n\n"
            "سیستم دانجن در حال آماده‌سازی است.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="home")]
            ])
        )

    # RANKED MATCH

    elif action == "rank":

        await query.edit_message_text(
            "🏆 RANKED MATCH\n\n"
            "سیستم رتبه‌بندی و پیدا کردن حریف در حال آماده‌سازی است.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="home")]
            ])
        )

    # QUESTS

    elif action == "quests":

        await query.edit_message_text(
            "📜 QUEST CENTER\n\n"
            "سیستم مأموریت‌ها در حال آماده‌سازی است.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="home")]
            ])
        )


# =========================
# MAIN
# =========================

def main():

    db.init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # Awakening system
    setup_awakening(app)

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # Navigation
    app.add_handler(
        CallbackQueryHandler(home_callback, pattern="^home$")
    )

    # General menu
    app.add_handler(CallbackQueryHandler(menu_callback))

    print("SHADOW LEGACY BOT STARTED")

    app.run_polling()


if __name__ == "__main__":
    main()