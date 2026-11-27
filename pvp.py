import re

import database as db
import combat

from telegram import Update
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)


# =====================================
# INITIALIZE PVP DATABASE
# =====================================

def init_pvp_db():

    with db.connect() as conn:

        conn.execute("""
        CREATE TABLE IF NOT EXISTS pvp_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            message_id INTEGER,
            player1 INTEGER NOT NULL,
            player2 INTEGER NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)


# =====================================
# START DUEL
# =====================================

async def duel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    if message.chat.type == "private":
        await message.reply_text(
            "برای شروع PvP باید در گروه و با Reply به پیام حریف دستور /duel رو بفرستی."
        )
        return

    if not message.reply_to_message:
        await message.reply_text(
            "برای شروع مبارزه، روی پیام حریف Reply کن و /duel بفرست."
        )
        return

    attacker = message.from_user
    defender = message.reply_to_message.from_user

    if not attacker or not defender:
        return

    if attacker.is_bot or defender.is_bot:
        await message.reply_text("مبارزه با ربات امکان‌پذیر نیست.")
        return

    if attacker.id == defender.id:
        await message.reply_text("نمی‌تونی با خودت مبارزه کنی.")
        return

    player1 = db.get_player(attacker.id)
    player2 = db.get_player(defender.id)

    if not player1 or not player2:
        await message.reply_text(
            "هر دو بازیکن باید ابتدا در چت خصوصی ربات /start رو بزنن."
        )
        return

    if player1["hp"] <= 0 or player2["hp"] <= 0:
        await message.reply_text(
            "یکی از بازیکنان در وضعیت مناسبی برای مبارزه نیست."
        )
        return

    with db.connect() as conn:

        existing = conn.execute("""
        SELECT id FROM pvp_matches
        WHERE status = 'active'
        AND (
            player1 IN (?, ?)
            OR player2 IN (?, ?)
        )
        """, (
            attacker.id,
            defender.id,
            attacker.id,
            defender.id
        )).fetchone()

        if existing:
            await message.reply_text(
                "یکی از این بازیکنان در حال حاضر در یک مبارزه فعال است."
            )
            return

    battle_message = await message.reply_text(
        "⚔️ PVP BATTLE STARTED!\n\n"
        f"🥊 {attacker.first_name}\n"
        f"VS\n"
        f"🥊 {defender.first_name}\n\n"
        "برای حمله، روی همین پیام Reply کن و اسم یکی از Skillهای آزادشده‌ات رو بنویس.\n\n"
        "🛡 دفاع به‌صورت خودکار محاسبه می‌شه."
    )

    with db.connect() as conn:

        conn.execute("""
        INSERT INTO pvp_matches (
            chat_id,
            message_id,
            player1,
            player2
        )
        VALUES (?, ?, ?, ?)
        """, (
            message.chat_id,
            battle_message.message_id,
            attacker.id,
            defender.id
        ))


# =====================================
# SKILL REPLY
# =====================================

async def combat_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    if not message or not message.reply_to_message:
        return

    if message.chat.type == "private":
        return

    user = message.from_user

    if not user or user.is_bot:
        return

    skill_name = message.text.strip()

    if not skill_name:
        return

    replied_message = message.reply_to_message

    with db.connect() as conn:

        match = conn.execute("""
        SELECT *
        FROM pvp_matches
        WHERE chat_id = ?
        AND message_id = ?
        AND status = 'active'
        ORDER BY id DESC
        LIMIT 1
        """, (
            message.chat_id,
            replied_message.message_id
        )).fetchone()

    if not match:
        return

    if user.id not in (
        match["player1"],
        match["player2"]
    ):
        return

    opponent_id = (
        match["player2"]
        if user.id == match["player1"]
        else match["player1"]
    )

    result = combat.use_skill(
        user.id,
        opponent_id,
        skill_name
    )

    success, data = result

    if not success:

        await message.reply_text(
            f"❌ {data}"
        )

        return

    attacker = db.get_player(user.id)
    defender = db.get_player(opponent_id)

    if data["defeated"]:

        with db.connect() as conn:

            conn.execute("""
            UPDATE pvp_matches
            SET status = 'finished'
            WHERE id = ?
            """, (match["id"],))

        await message.reply_text(
            "🏆 PVP FINISHED!\n\n"
            f"⚔️ Skill: {data['skill']}\n"
            f"💥 Damage: {data['damage']}\n\n"
            f"👑 Winner: {attacker['name']}\n"
            f"💀 Defeated: {defender['name']}\n\n"
            "سیستم امتیازدهی و احیای PvP در مرحله بعد تکمیل می‌شه."
        )

        return

    await message.reply_text(
        "⚔️ ATTACK SUCCESSFUL!\n\n"
        f"👤 Attacker: {attacker['name']}\n"
        f"🔥 Skill: {data['skill']}\n"
        f"💥 Damage: {data['damage']}\n\n"
        f"❤️ Opponent HP: {data['defender_hp']}\n"
        f"🔮 Attacker MP: {data['attacker_mp']}"
    )


# =====================================
# SETUP
# =====================================

def setup_pvp(application):

    init_pvp_db()

    application.add_handler(
        CommandHandler("duel", duel_command)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            combat_reply
        )
    )