import logging

import database as db

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


SHADOW_COMMANDS = {
    "attack": "⚔️ ATTACK",
    "defend": "🛡 DEFEND",
    "follow": "👣 FOLLOW",
    "guard": "🔰 GUARD",
    "retreat": "🏃 RETREAT",
    "focus": "🎯 FOCUS",
    "special": "🌑 SPECIAL"
}


def init_shadows_db():
    with db.connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shadow_commands (
                user_id INTEGER PRIMARY KEY,
                command TEXT DEFAULT 'follow',
                updated_at INTEGER DEFAULT 0
            )
        """)


def get_shadows(user_id):
    with db.connect() as conn:
        return conn.execute("""
            SELECT *
            FROM shadows
            WHERE user_id = ?
            ORDER BY level DESC, loyalty DESC
        """, (user_id,)).fetchall()


def get_shadow_command(user_id):
    with db.connect() as conn:
        row = conn.execute("""
            SELECT command
            FROM shadow_commands
            WHERE user_id = ?
        """, (user_id,)).fetchone()

    return row["command"] if row else "follow"


def set_shadow_command(user_id, command):
    if command not in SHADOW_COMMANDS:
        return False

    shadows = get_shadows(user_id)

    if not shadows:
        return False

    with db.connect() as conn:
        conn.execute("""
            INSERT INTO shadow_commands (
                user_id,
                command,
                updated_at
            )
            VALUES (?, ?, strftime('%s', 'now'))
            ON CONFLICT(user_id)
            DO UPDATE SET
                command = excluded.command,
                updated_at = excluded.updated_at
        """, (
            user_id,
            command
        ))

    return True


def shadow_keyboard(user_id):
    buttons = [
        [
            InlineKeyboardButton(
                "⚔️ ATTACK",
                callback_data="shadow_cmd_attack"
            ),
            InlineKeyboardButton(
                "🛡 DEFEND",
                callback_data="shadow_cmd_defend"
            )
        ],
        [
            InlineKeyboardButton(
                "👣 FOLLOW",
                callback_data="shadow_cmd_follow"
            ),
            InlineKeyboardButton(
                "🔰 GUARD",
                callback_data="shadow_cmd_guard"
            )
        ],
        [
            InlineKeyboardButton(
                "🏃 RETREAT",
                callback_data="shadow_cmd_retreat"
            ),
            InlineKeyboardButton(
                "🎯 FOCUS",
                callback_data="shadow_cmd_focus"
            )
        ],
        [
            InlineKeyboardButton(
                "🌑 SPECIAL",
                callback_data="shadow_cmd_special"
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Refresh",
                callback_data="shadows_refresh"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Main Menu",
                callback_data="home"
            )
        ]
    ]

    return InlineKeyboardMarkup(buttons)


def shadows_text(user_id):
    shadows = get_shadows(user_id)

    if not shadows:
        return (
            "🌑 SHADOW ARMY\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "هنوز هیچ سرباز سایه‌ای نداری.\n\n"
            "با شکست دادن دشمنان و پیشرفت در بازی، "
            "می‌توانی ارتش سایه‌ای خودت را بسازی."
        )

    text = (
        "🌑 SHADOW ARMY\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    for index, shadow in enumerate(shadows, 1):
        text += (
            f"{index}. {shadow['shadow_name']}\n"
            f"   Rank: {shadow['shadow_rank']}\n"
            f"   Level: {shadow['level']}\n"
            f"   Loyalty: {shadow['loyalty']}/100\n\n"
        )

    current_command = get_shadow_command(user_id)

    text += (
        "━━━━━━━━━━━━━━━━━━\n"
        f"📜 Current Command: "
        f"{SHADOW_COMMANDS.get(current_command, 'FOLLOW')}\n\n"
        "فرمان موردنظرت را انتخاب کن."
    )

    return text
async def shadows_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user_id = update.effective_user.id

    if update.effective_chat.type != "private":
        await update.effective_message.reply_text(
            "این بخش فقط در چت خصوصی قابل استفاده است."
        )
        return

    if not db.get_player(user_id):
        await update.effective_message.reply_text(
            "ابتدا /start را اجرا کن."
        )
        return

    await update.effective_message.reply_text(
        shadows_text(user_id),
        reply_markup=shadow_keyboard(user_id)
    )


async def shadows_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    if (
        not query.message
        or query.message.chat.type != "private"
        or query.message.chat.id != query.from_user.id
    ):
        await query.answer(
            "این منو فقط در چت خصوصی قابل استفاده است.",
            show_alert=True
        )
        return

    user_id = query.from_user.id

    if not db.get_player(user_id):
        await query.answer(
            "ابتدا /start را اجرا کن.",
            show_alert=True
        )
        return

    action = query.data

    if action == "shadows_refresh":
        await query.answer("بروزرسانی شد.")

        await query.edit_message_text(
            shadows_text(user_id),
            reply_markup=shadow_keyboard(user_id)
        )
        return

    if action.startswith("shadow_cmd_"):
        command = action.replace("shadow_cmd_", "", 1)

        if command not in SHADOW_COMMANDS:
            await query.answer(
                "فرمان نامعتبر است.",
                show_alert=True
            )
            return

        if not get_shadows(user_id):
            await query.answer(
                "هنوز سرباز سایه‌ای نداری.",
                show_alert=True
            )
            return

        if not set_shadow_command(user_id, command):
            await query.answer(
                "ثبت فرمان ناموفق بود.",
                show_alert=True
            )
            return

        await query.answer(
            f"فرمان {command.upper()} ثبت شد!"
        )

        await query.edit_message_text(
            shadows_text(user_id),
            reply_markup=shadow_keyboard(user_id)
        )


async def shadow_info_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user_id = update.effective_user.id

    if update.effective_chat.type != "private":
        return

    if not db.get_player(user_id):
        await update.effective_message.reply_text(
            "ابتدا /start را اجرا کن."
        )
        return

    shadows = get_shadows(user_id)

    if not shadows:
        await update.effective_message.reply_text(
            "🌑 هنوز هیچ Shadow نداری."
        )
        return

    text = "🌑 YOUR SHADOWS\n\n"

    for shadow in shadows:
        text += (
            f"Name: {shadow['shadow_name']}\n"
            f"Rank: {shadow['shadow_rank']}\n"
            f"Level: {shadow['level']}\n"
            f"Loyalty: {shadow['loyalty']}/100\n"
            "━━━━━━━━━━━━━━\n"
        )

    await update.effective_message.reply_text(text)


def setup_shadows(application):
    init_shadows_db()

    application.add_handler(
        CommandHandler("shadows", shadows_command)
    )

    application.add_handler(
        CommandHandler("shadowinfo", shadow_info_command)
    )

    application.add_handler(
        CallbackQueryHandler(
            shadows_callback,
            pattern=r"^(shadows_refresh|shadow_cmd_(attack|defend|follow|guard|retreat|focus|special))$"
        )
    )