import time

from telegram import Update
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

import database as db
import combat
import pvp_lifecycle as lifecycle


# =====================================
# DATABASE
# =====================================

def init_pvp_db():

    with db.connect() as conn:

        conn.execute("""
        CREATE TABLE IF NOT EXISTS pvp_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            player1 INTEGER NOT NULL,
            player2 INTEGER NOT NULL,
            status TEXT DEFAULT 'active',
            created_at REAL
        )
        """)

        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_pvp_message
        ON pvp_matches(chat_id, message_id)
        """)


# =====================================
# PLAYER CHECK
# =====================================

def get_player(user_id):

    with db.connect() as conn:

        return conn.execute("""
        SELECT *
        FROM players
        WHERE user_id = ?
        """, (user_id,)).fetchone()


def is_player_dead(user_id):

    player = get_player(user_id)

    if not player:
        return True

    if player["is_dead"]:
        return True

    if lifecycle.get_revive_remaining(user_id) > 0:
        return True

    return False


# =====================================
# DUEL COMMAND
# =====================================

async def duel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message
    user = update.effective_user

    if message.chat.type == "private":
        await message.reply_text(
            "برای شروع مبارزه باید داخل گروه باشی."
        )
        return

    if not message.reply_to_message:
        await message.reply_text(
            "برای مبارزه باید روی پیام حریفت ریپلای کنی و /duel بزنی."
        )
        return

    opponent = message.reply_to_message.from_user

    if opponent.is_bot:
        await message.reply_text(
            "نمی‌تونی با ربات مبارزه کنی."
        )
        return

    if opponent.id == user.id:
        await message.reply_text(
            "نمی‌تونی با خودت مبارزه کنی."
        )
        return

    player1 = get_player(user.id)
    player2 = get_player(opponent.id)

    if not player1 or not player2:
        await message.reply_text(
            "هر دو بازیکن باید ابتدا با دستور /start ثبت‌نام کنند."
        )
        return

    if is_player_dead(user.id):
        await message.reply_text(
            "تو هنوز در وضعیت DEAD هستی و نمی‌تونی مبارزه کنی."
        )
        return

    if is_player_dead(opponent.id):
        await message.reply_text(
            "حریفت فعلاً قادر به مبارزه نیست."
        )
        return

    with db.connect() as conn:

        active = conn.execute("""
        SELECT id
        FROM pvp_matches
        WHERE status = 'active'
        AND (
            player1 IN (?, ?)
            OR player2 IN (?, ?)
        )
        """, (
            user.id,
            opponent.id,
            user.id,
            opponent.id
        )).fetchone()

        if active:
            await message.reply_text(
                "یکی از بازیکن‌ها در حال حاضر مبارزه فعالی داره."
            )
            return

    battle_message = await message.reply_text(
        "⚔️ PVP BATTLE STARTED!\n\n"
        f"👤 {user.first_name}\n"
        f"❤️ HP: {player1['hp']}\n\n"
        "VS\n\n"
        f"👤 {opponent.first_name}\n"
        f"❤️ HP: {player2['hp']}\n\n"
        "برای حمله، روی همین پیام ریپلای کن "
        "و اسم یکی از مهارت‌هات رو بنویس."
    )

    with db.connect() as conn:

        conn.execute("""
        INSERT INTO pvp_matches (
            chat_id,
            message_id,
            player1,
            player2,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, 'active', ?)
        """, (
            message.chat_id,
            battle_message.message_id,
            user.id,
            opponent.id,
            time.time()
        ))


# =====================================
# COMBAT REPLY
# =====================================

async def combat_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message
    user = update.effective_user

    if not message or not message.reply_to_message:
        return

    if not message.text:
        return

    with db.connect() as conn:

        match = conn.execute("""
        SELECT *
        FROM pvp_matches
        WHERE chat_id = ?
        AND message_id = ?
        AND status = 'active'
        """, (
            message.chat_id,
            message.reply_to_message.message_id
        )).fetchone()

    if not match:
        return

    attacker_id = user.id

    if attacker_id not in (
        match["player1"],
        match["player2"]
    ):
        return

    defender_id = (
        match["player2"]
        if attacker_id == match["player1"]
        else match["player1"]
    )

    if is_player_dead(attacker_id):
        await message.reply_text(
            "تو در وضعیت DEAD هستی و نمی‌تونی حمله کنی."
        )
        return

    if is_player_dead(defender_id):
        return

    skill_name = message.text.strip()

    if len(skill_name) > 60:
        return

    success, result = combat.use_skill(
        attacker_id,
        defender_id,
        skill_name
    )

    if not success:
        await message.reply_text(str(result))
        return

    damage = result["damage"]
    defender_hp = result["hp"]
    attacker_mp = result["mp"]

    attacker = get_player(attacker_id)
    defender = get_player(defender_id)

    if result["defeated"]:

        with db.connect() as conn:

            conn.execute("""
            UPDATE pvp_matches
            SET status = 'finished'
            WHERE id = ?
            AND status = 'active'
            """, (match["id"],))

        lifecycle.finish_pvp(
            winner_id=attacker_id,
            loser_id=defender_id
        )

        await message.reply_text(
            "🏆 PVP FINISHED!\n\n"
            f"👑 برنده: {attacker['name']}\n"
            f"💀 بازنده: {defender['name']}\n\n"
            f"⚔️ Damage: {damage}\n"
            "☠️ وضعیت بازنده: DEAD\n"
            "⏳ زمان احیا: ۵ دقیقه\n\n"
            "امتیاز رنک بازیکن‌ها به‌روزرسانی شد."
        )

        return

    await message.reply_text(
        "⚔️ ATTACK RESULT\n\n"
        f"👤 مهاجم: {attacker['name']}\n"
        f"🎯 هدف: {defender['name']}\n\n"
        f"💥 Damage: {damage}\n"
        f"❤️ HP باقی‌مانده: {defender_hp}\n"
        f"🔮 MP مهاجم: {attacker_mp}"
    )


# =====================================
# SETUP
# =====================================

def setup_pvp(application):

    init_pvp_db()

    lifecycle.setup_lifecycle(application)

    application.add_handler(
        CommandHandler("duel", duel_command)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            combat_reply
        )
    )