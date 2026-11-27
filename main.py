from awakening import setup_awakening
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
            InlineKeyboardButton("🏋️ Training", callback_data="training")
        ],
        [
            InlineKeyboardButton("🏆 Rank Match", callback_data="rank"),
            InlineKeyboardButton("🐉 World Boss", callback_data="worldboss")
        ],
        [
            InlineKeyboardButton("✨ Awakening", callback_data="awakening"),
            InlineKeyboardButton("📜 Quests", callback_data="quests")
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "برای ثبت‌نام و استفاده از منو، وارد گفت‌وگوی خصوصی ربات شو."
        )
        return

    created = db.register_player(
        user.id,
        user.username,
        user.first_name
    )

    player = db.get_player(user.id)

    if created:
        message = (
            f"🌑 به دنیای {GAME_NAME} خوش آمدی!\n\n"
            "سیستم تو را به‌عنوان یک هانتر جدید ثبت کرد.\n"
            "ماجراجویی تو از رتبه E آغاز می‌شود."
        )
    else:
        message = (
            f"🌑 خوش برگشتی، {player['name']}!\n"
            "سیستم آماده دریافت فرمان‌های توست."
        )

    await update.message.reply_text(
        message,
        reply_markup=main_menu()
    )


async def menu_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    user_id = query.from_user.id

    await query.answer()

    # جلوگیری از استفاده دیگران از منوی بازیکن
    if query.message.chat.type != "private":
        await query.answer(
            "این منو فقط در گفت‌وگوی خصوصی قابل استفاده است.",
            show_alert=True
        )
        return

    player = db.get_player(user_id)

    if not player:
        await query.edit_message_text(
            "ابتدا دستور /start را اجرا کن."
        )
        return

    action = query.data

    if action == "profile":
        text = (
            "👤 PROFILE CARD\n\n"
            f"نام: {player['name']}\n"
            f"سطح: {player['level']}\n"
            f"رتبه: {player['rank']}\n"
            f"قدرت: {player['power']}\n"
            f"پیروزی: {player['wins']}\n"
            f"شکست: {player['losses']}"
        )

    elif action == "status":
        text = (
            "📊 STATUS CARD\n\n"
            f"❤️ HP: {player['hp']}/{player['max_hp']}\n"
            f"💧 MP: {player['mp']}/{player['max_mp']}\n\n"
            f"💪 STR: {player['strength']}\n"
            f"⚡ AGI: {player['agility']}\n"
            f"🛡 VIT: {player['vitality']}\n"
            f"🧠 INT: {player['intelligence']}\n"
            f"👁 SEN: {player['sense']}\n\n"
            f"امتیاز آزاد: {player['stat_points']}"
        )

    elif action == "training":
        text = (
            "🏋️ TRAINING\n\n"
            "برای افزایش قدرت، یکی از تمرین‌ها را انتخاب کن."
        )
        keyboard = [
            [InlineKeyboardButton(
                "💪 تمرین قدرت",
                callback_data="train_strength"
            )],
            [InlineKeyboardButton(
                "⚡ تمرین سرعت",
                callback_data="train_agility"
            )],
            [InlineKeyboardButton(
                "🛡 تمرین استقامت",
                callback_data="train_vitality"
            )],
            [InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data="home"
            )]
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif action.startswith("train_"):
        stat = action.replace("train_", "")
        allowed = {
            "strength", "agility", "vitality",
            "intelligence", "sense"
        }

        if stat not in allowed:
            return

        if player["gold"] < 50:
            await query.answer(
                "برای تمرین به ۵۰ طلا نیاز داری.",
                show_alert=True
            )
            return

        db.update_player(
            user_id,
            **{
                stat: player[stat] + 1,
                "gold": player["gold"] - 50,
                "power": player["power"] + 1
            }
        )

        await query.edit_message_text(
            f"✅ تمرین انجام شد!\n"
            f"ویژگی {stat.upper()} یک واحد افزایش یافت.\n"
            "۵۰ طلا مصرف شد.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🔙 بازگشت",
                    callback_data="training"
                )
            ]])
        )
        return

    elif action == "inventory":
        items = db.get_inventory(user_id)

        if not items:
            text = "🎒 INVENTORY\n\nکیف تجهیزات تو خالی است."
        else:
            text = "🎒 INVENTORY\n\n"
            for item in items:
                text += (
                    f"• {item['item_name']} "
                    f"(×{item['quantity']})\n"
                )

    elif action == "shadows":
        shadows = db.get_shadows(user_id)

        text = "👥 SHADOW CARD\n\n"

        if not shadows:
            text += "هنوز هیچ سایه‌ای در اختیار نداری."
        else:
            for shadow in shadows:
                text += (
                    f"🌑 {shadow['shadow_name']}\n"
                    f"رتبه: {shadow['shadow_rank']}\n"
                    f"سطح: {shadow['level']}\n"
                    f"وفاداری: {shadow['loyalty']}\n\n"
                )

    elif action == "worldboss":
        boss = db.get_world_boss()

        if not boss or not boss["active"]:
            text = "🐉 در حال حاضر هیچ World Boss فعالی وجود ندارد."
        else:
            text = (
                f"🐉 WORLD BOSS\n\n"
                f"نام: {boss['boss_name']}\n"
                f"HP: {boss['hp']}/{boss['max_hp']}\n\n"
                "مبارزه گروهی از طریق پیام مخصوص باس انجام می‌شود."
            )

    else:
        sections = {
            "battle": "⚔️ سیستم Battle",
            "dungeon": "🏰 سیستم Dungeon",
            "shop": "🛒 فروشگاه",
            "rank": "🏆 سیستم Rank Match",
            "awakening": "✨ سیستم Awakening",
            "quests": "📜 مأموریت‌ها"
        }

        text = sections.get(
            action,
            "این بخش در حال آماده‌سازی است."
        )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🔙 بازگشت به منو",
                callback_data="home"
            )
        ]])
    )


async def home_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    if query.message.chat.type != "private":
        return

    if not db.get_player(query.from_user.id):
        await query.edit_message_text(
            "ابتدا /start را اجرا کن."
        )
        return

    await query.edit_message_text(
        f"🌑 {GAME_NAME}\n\nمنوی اصلی:",
        reply_markup=main_menu()
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "📖 راهنمای بازی\n\n"
        "/start - ورود به بازی\n"
        "/help - راهنما\n\n"
        "برای استفاده از امکانات بازی، از منوی خصوصی ربات استفاده کن."
    )


def main():
    db.init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(home_callback, pattern="^home$"))
    app.add_handler(CallbackQueryHandler(menu_callback))

    print(f"{GAME_NAME} is running...")

    app.run_polling()


if __name__ == "__main__":
    main()