import logging

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

import config
import database as db

from progression import (
    init_progression_db,
    unlock_available_skills,
    get_progression_info,
    get_player_skills,
)

from combat import init_combat_db

from awakening import setup_awakening
from stats_ui import setup_stats
from protection_ui import setup_protection_ui
from daily_quests import setup_daily_quests
from training import setup_training
from pvp import setup_pvp
from ranked import setup_ranked
from ranked_season import setup_ranked_season
from dungeon import setup_dungeon
from shadows import setup_shadows
from world_boss import setup_world_boss


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# MAIN MENU
# =========================================================

def main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton(
                "👤 Profile",
                callback_data="menu_profile"
            ),
            InlineKeyboardButton(
                "📊 Status",
                callback_data="menu_status"
            ),
        ],
        [
            InlineKeyboardButton(
                "⚔️ Battle",
                callback_data="menu_battle"
            ),
            InlineKeyboardButton(
                "🏰 Dungeon",
                callback_data="menu_dungeon"
            ),
        ],
        [
            InlineKeyboardButton(
                "🌑 Shadows",
                callback_data="menu_shadows"
            ),
            InlineKeyboardButton(
                "🎒 Inventory",
                callback_data="menu_inventory"
            ),
        ],
        [
            InlineKeyboardButton(
                "🛒 Shop",
                callback_data="menu_shop"
            ),
            InlineKeyboardButton(
                "✨ Awakening",
                callback_data="menu_awakening"
            ),
        ],
        [
            InlineKeyboardButton(
                "📈 Upgrade Stats",
                callback_data="menu_upgrade"
            ),
            InlineKeyboardButton(
                "📜 My Skills",
                callback_data="menu_skills"
            ),
        ],
        [
            InlineKeyboardButton(
                "🎯 Daily Quests",
                callback_data="menu_daily"
            ),
            InlineKeyboardButton(
                "🛡 Rank Protection",
                callback_data="menu_protection"
            ),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


def back_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⬅️ Main Menu",
                callback_data="menu_home"
            )
        ]
    ])


def battle_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🏋️ Training",
                callback_data="training"
            )
        ],
        [
            InlineKeyboardButton(
                "🏆 Ranked Match",
                callback_data="ranked_info"
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Main Menu",
                callback_data="menu_home"
            )
        ],
    ])


# =========================================================
# PLAYER REGISTRATION
# =========================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "برای ساخت شخصیت و استفاده از منو، "
            "ربات را در گفتگوی خصوصی باز کن و /start بزن."
        )
        return

    player = db.get_player(user.id)

    if not player:
        db.register_player(
            user_id=user.id,
            username=user.username or "",
            name=user.first_name or "Hunter"
        )

        unlock_available_skills(user.id)

        await update.message.reply_text(
            "🌑 به دنیای SOLO LEVELING: SHADOW LEGACY خوش آمدی!\n\n"
            "شخصیتت ساخته شد.\n"
            "برای شروع مسیر شکارچی‌ها از منوی زیر استفاده کن."
        )

    else:
        unlock_available_skills(user.id)

        await update.message.reply_text(
            "🌑 دوباره به دنیای Shadow Legacy برگشتی!"
        )

    await update.message.reply_text(
        "⚔️ MAIN MENU",
        reply_markup=main_menu_keyboard()
    )


# =========================================================
# PROFILE
# =========================================================

async def show_profile(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user_id = update.effective_user.id
    player = db.get_player(user_id)

    if not player:
        await update.effective_message.reply_text(
            "❌ ابتدا /start را اجرا کن."
        )
        return

    level = player["level"]
    power = player["power"]
    gold = player["gold"]
    crystals = player["crystals"]

    text = (
        "👤 PLAYER PROFILE\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: {user_id}\n"
        f"👤 Name: {update.effective_user.first_name}\n"
        f"⭐ Level: {level}\n"
        f"⚡ Power: {power}\n\n"
        f"🪙 Gold: {gold}\n"
        f"💎 Crystals: {crystals}\n"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=back_keyboard()
        )
    else:
        await update.effective_message.reply_text(
            text,
            reply_markup=back_keyboard()
        )


# =========================================================
# STATUS
# =========================================================

async def show_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user_id = update.effective_user.id
    player = db.get_player(user_id)

    if not player:
        await update.effective_message.reply_text(
            "❌ ابتدا /start را اجرا کن."
        )
        return

    text = (
        "📊 PLAYER STATUS\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"⭐ Level: {player['level']}\n"
        f"⚡ Power: {player['power']}\n\n"
        f"❤️ HP: {player['hp']}/{player['max_hp']}\n"
        f"🔵 MP: {player['mp']}/{player['max_mp']}\n\n"
        f"💪 STR: {player['STR']}\n"
        f"⚡ AGI: {player['AGI']}\n"
        f"🛡 VIT: {player['VIT']}\n"
        f"🧠 INT: {player['INT']}\n"
        f"👁 SEN: {player['SEN']}\n\n"
        f"📈 Stat Points: {player['stat_points']}\n"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=back_keyboard()
        )
    else:
        await update.effective_message.reply_text(
            text,
            reply_markup=back_keyboard()
        )


# =========================================================
# SKILLS
# =========================================================

async def show_skills(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user_id = update.effective_user.id

    skills = get_player_skills(user_id)

    if not skills:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "📜 هنوز مهارتی آزاد نکرده‌ای.",
                reply_markup=back_keyboard()
            )
        else:
            await update.effective_message.reply_text(
                "📜 هنوز مهارتی آزاد نکرده‌ای.",
                reply_markup=back_keyboard()
            )
        return

    text = "📜 YOUR SKILLS\n━━━━━━━━━━━━━━━━━━\n\n"

    for skill in skills:
        text += (
            f"⚔️ {skill['skill_name']}\n"
            f"🔹 Type: {skill['skill_type']}\n"
            f"💥 Damage: {skill['damage']}\n"
            f"🔵 MP Cost: {skill['mp_cost']}\n"
            f"⏳ Cooldown: {skill['cooldown']}s\n\n"
        )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=back_keyboard()
        )
    else:
        await update.effective_message.reply_text(
            text,
            reply_markup=back_keyboard()
        )


# =========================================================
# MENU CALLBACK
# =========================================================

async def menu_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    if not query.message or query.message.chat.type != "private":
        await query.answer()
        return

    if query.from_user.id != query.message.chat.id:
        await query.answer(
            "این منو متعلق به شخص دیگری است.",
            show_alert=True
        )
        return

    await query.answer()
    action = query.data

    if action == "menu_home":
        await query.edit_message_text(
            "⚔️ MAIN MENU",
            reply_markup=main_menu_keyboard()
        )
        return

    if action == "menu_profile":
        await show_profile(update, context)
        return

    if action == "menu_status":
        await show_status(update, context)
        return

    if action == "menu_skills":
        await show_skills(update, context)
        return

    if action == "menu_battle":
        await query.edit_message_text(
            "⚔️ BATTLE MENU\n\n"
            "مسیر مبارزه‌ات را انتخاب کن:",
            reply_markup=battle_keyboard()
        )
        return

    if action == "menu_dungeon":
        await query.edit_message_text(
            "🏰 DUNGEON\n\n"
            "برای مشاهده دروازه‌های فعال از دستور زیر استفاده کن:\n"
            "/gates\n\n"
            "برای ورود به دروازه:\n"
            "/dungeon",
            reply_markup=back_keyboard()
        )
        return

    if action == "menu_shadows":
        await query.edit_message_text(
            "🌑 SHADOW ARMY\n\n"
            "برای مشاهده ارتش سایه‌ها دستور زیر را بزن:\n"
            "/shadows",
            reply_markup=back_keyboard()
        )
        return

    if action == "menu_inventory":
        await query.edit_message_text(
            "🎒 INVENTORY\n\n"
            "سیستم نمایش و مدیریت آیتم‌ها هنوز به منوی اصلی متصل نشده است.",
            reply_markup=back_keyboard()
        )
        return

    if action == "menu_shop":
        await query.edit_message_text(
            "🛒 SHOP\n\n"
            "فروشگاه هنوز به منوی اصلی متصل نشده است.",
            reply_markup=back_keyboard()
        )
        return

    if action == "menu_awakening":
        await query.edit_message_text(
            "✨ برای مشاهده سیستم بیداری از دستور زیر استفاده کن:\n"
            "/awakening",
            reply_markup=back_keyboard()
        )
        return

    if action == "menu_upgrade":
        await query.edit_message_text(
            "📈 برای ارتقای ویژگی‌ها از دستور زیر استفاده کن:\n"
            "/stats",
            reply_markup=back_keyboard()
        )
        return

    if action == "menu_daily":
        await query.edit_message_text(
            "🎯 برای مشاهده مأموریت‌های روزانه:\n"
            "/daily",
            reply_markup=back_keyboard()
        )
        return

    if action == "menu_protection":
        await query.edit_message_text(
            "🛡 برای مشاهده Rank Protection:\n"
            "/protection",
            reply_markup=back_keyboard()
        )
        return


# =========================================================
# RANKED INFO
# =========================================================

async def ranked_info_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    if not query.message or query.message.chat.type != "private":
        await query.answer()
        return

    if query.from_user.id != query.message.chat.id:
        await query.answer(
            "این منو متعلق به شخص دیگری است.",
            show_alert=True
        )
        return

    await query.answer()
    await query.edit_message_text(
        "🏆 RANKED MATCH\n\n"
        "برای ورود به صف مسابقه:\n"
        "/ranked\n\n"
        "برای مشاهده رتبه:\n"
        "/rank\n\n"
        "برای لغو جستجو:\n"
        "/rankcancel",
        reply_markup=back_keyboard()
    )
# =========================================================
# HELP
# =========================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    text = (
        "📖 SHADOW LEGACY HELP\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🔹 /start - شروع بازی\n"
        "🔹 /stats - وضعیت و ارتقای ویژگی‌ها\n"
        "🔹 /daily - مأموریت‌های روزانه\n"
        "🔹 /training - تمرین\n"
        "🔹 /awakening - بیداری\n"
        "🔹 /protection - محافظت رتبه\n\n"
        "⚔️ BATTLE\n"
        "🔹 /duel - شروع دوئل دوستانه با Reply\n"
        "🔹 /ranked - ورود به مسابقه رتبه‌ای\n"
        "🔹 /rank - مشاهده رتبه\n"
        "🔹 /rankcancel - لغو جستجوی مسابقه\n\n"
        "🏰 DUNGEON\n"
        "🔹 /gates - مشاهده دروازه‌ها\n"
        "🔹 /dungeon - ورود به دروازه\n\n"
        "🌑 SHADOWS\n"
        "🔹 /shadows - مشاهده ارتش سایه‌ها\n"
        "🔹 /shadowinfo - اطلاعات سایه‌ها\n\n"
        "👑 WORLD BOSS\n"
        "🔹 /worldboss - وضعیت باس جهانی\n"
        "🔹 /wbattack - حمله به باس\n"
    )

    await update.message.reply_text(text)


# =========================================================
# PRIVATE MENU PROTECTION
# =========================================================

async def reject_group_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "⚠️ منوی اصلی بازی فقط در گفتگوی خصوصی قابل استفاده است."
        )


# =========================================================
# APPLICATION SETUP
# =========================================================

def setup_application(application: Application):

    # Database
    db.init_db()

    # Core systems
    init_progression_db()
    init_combat_db()

    # Awakening and progression-related systems
    setup_awakening(application)
    setup_stats(application)

    # Player systems
    setup_training(application)
    setup_daily_quests(application)
    setup_protection_ui(application)

    # Combat systems
    setup_pvp(application)
    setup_ranked(application)
    setup_ranked_season(application)

    # World systems
    setup_dungeon(application)
    setup_shadows(application)
    setup_world_boss(application)

    # Main commands
    application.add_handler(
        CommandHandler("start", start_command)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    # Main menu callbacks
    application.add_handler(
        CallbackQueryHandler(
            menu_callback,
            pattern=r"^menu_"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            ranked_info_callback,
            pattern=r"^ranked_info$"
        )
    )


# =========================================================
# MAIN
# =========================================================

def main():
    if not config.BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN در متغیرهای Railway تنظیم نشده است."
        )

    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .build()
    )

    setup_application(application)

    logger.info(
        "SOLO LEVELING: SHADOW LEGACY started."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()