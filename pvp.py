import time
import logging

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
import daily_quests


logger = logging.getLogger(__name__)


# ==========================================
# DATABASE
# ==========================================

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
                match_type TEXT DEFAULT 'friendly',
                ranked_match_id INTEGER,
                created_at REAL NOT NULL
            )
        """)

        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(pvp_matches)"
            ).fetchall()
        }

        additions = {
            "match_type": "TEXT DEFAULT 'friendly'",
            "ranked_match_id": "INTEGER"
        }

        for column, definition in additions.items():

            if column not in columns:

                conn.execute(
                    f"ALTER TABLE pvp_matches "
                    f"ADD COLUMN {column} {definition}"
                )

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_pvp_message
            ON pvp_matches(chat_id, message_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_pvp_status
            ON pvp_matches(status)
        """)


# ==========================================
# PLAYER
# ==========================================

def get_player(user_id):

    return db.get_player(user_id)


def is_player_dead(user_id):

    player = get_player(user_id)

    if not player:
        return True

    if player["is_dead"] or player["hp"] <= 0:
        return True

    return lifecycle.get_revive_remaining(user_id) > 0


def player_has_active_match(user_id):

    with db.connect() as conn:

        row = conn.execute("""
            SELECT id
            FROM pvp_matches
            WHERE (player1 = ? OR player2 = ?)
            AND status = 'active'
            LIMIT 1
        """, (
            user_id,
            user_id
        )).fetchone()

    return row is not None


# ==========================================
# DUEL COMMAND
# ==========================================

async def duel_command(update, context):

    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if chat.type == "private":

        await message.reply_text(
            "برای دوئل دوستانه، به پیام بازیکن موردنظر "
            "در یک گروه ریپلای کن و دستور /duel را بفرست."
        )

        return

    if not message.reply_to_message:

        await message.reply_text(
            "برای شروع دوئل باید به پیام حریف ریپلای کنی."
        )

        return

    target = message.reply_to_message.from_user

    if not target or target.is_bot:

        await message.reply_text(
            "این کاربر نمی‌تواند وارد دوئل شود."
        )

        return

    if target.id == user.id:

        await message.reply_text(
            "نمی‌توانی با خودت مبارزه کنی."
        )

        return

    player1 = get_player(user.id)
    player2 = get_player(target.id)

    if not player1 or not player2:

        await message.reply_text(
            "هر دو بازیکن باید ابتدا در بات ثبت‌نام کنند."
        )

        return

    if is_player_dead(user.id) or is_player_dead(target.id):

        await message.reply_text(
            "یکی از بازیکنان در حال احیاست و نمی‌تواند مبارزه کند."
        )

        return

    if player_has_active_match(user.id):

        await message.reply_text(
            "تو در حال حاضر داخل یک مسابقه هستی."
        )

        return

    if player_has_active_match(target.id):

        await message.reply_text(
            "حریف در حال حاضر داخل یک مسابقه است."
        )

        return

    battle_message = await message.reply_text(
        "⚔️ FRIENDLY DUEL\n\n"
        f"👤 {player1['name']}\n"
        f"❤️ {player1['hp']}/{player1['max_hp']}\n\n"
        "VS\n\n"
        f"👤 {player2['name']}\n"
        f"❤️ {player2['hp']}/{player2['max_hp']}\n\n"
        "برای حمله، به همین پیام ریپلای کن "
        "و نام مهارتت را بنویس.\n"
        "دفاع به‌صورت خودکار محاسبه می‌شود."
    )

    try:

        with db.connect() as conn:

            conn.execute("BEGIN IMMEDIATE")

            active = conn.execute("""
                SELECT id
                FROM pvp_matches
                WHERE (
                    player1 IN (?, ?)
                    OR player2 IN (?, ?)
                )
                AND status = 'active'
                LIMIT 1
            """, (
                user.id,
                target.id,
                user.id,
                target.id
            )).fetchone()

            if active:

                await battle_message.edit_text(
                    "این دوئل لغو شد؛ یکی از بازیکنان وارد مسابقه دیگری شده است."
                )

                return

            conn.execute("""
                INSERT INTO pvp_matches (
                    chat_id,
                    message_id,
                    player1,
                    player2,
                    status,
                    match_type,
                    created_at
                )
                VALUES (?, ?, ?, ?, 'active', 'friendly', ?)
            """, (
                chat.id,
                battle_message.message_id,
                user.id,
                target.id,
                time.time()
            ))

    except Exception:

        logger.exception("Could not create friendly duel.")

        await battle_message.edit_text(
            "خطا در ساخت دوئل. لطفاً دوباره تلاش کن."
        )


# ==========================================
# MATCH LOOKUP
# ==========================================

def get_match(chat_id, message_id):

    with db.connect() as conn:

        return conn.execute("""
            SELECT *
            FROM pvp_matches
            WHERE chat_id = ?
            AND message_id = ?
            AND status = 'active'
            LIMIT 1
        """, (
            chat_id,
            message_id
        )).fetchone()


# ==========================================
# FINISH FRIENDLY MATCH
# ==========================================

def finish_friendly_pvp(match, winner_id, loser_id):

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        current = conn.execute("""
            SELECT status
            FROM pvp_matches
            WHERE id = ?
        """, (match["id"],)).fetchone()

        if not current or current["status"] != "active":
            return False

        conn.execute("""
            UPDATE pvp_matches
            SET status = 'finished'
            WHERE id = ?
            AND status = 'active'
        """, (match["id"],))

        if match["match_type"] == "ranked":
            return False

        conn.execute("""
            UPDATE players
            SET wins = wins + 1
            WHERE user_id = ?
        """, (winner_id,))

        conn.execute("""
            UPDATE players
            SET losses = losses + 1,
                deaths = deaths + 1,
                hp = 0,
                is_dead = 1
            WHERE user_id = ?
        """, (loser_id,))

        conn.execute("""
            INSERT INTO pvp_revives (
                user_id,
                revive_at
            )
            VALUES (?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET
                revive_at = excluded.revive_at
        """, (
            loser_id,
            time.time() + lifecycle.REVIVE_SECONDS
        ))

    return True


# ==========================================
# RANKED MATCH FINISH
# ==========================================

def finish_ranked_match(match, winner_id, loser_id):

    ranked_id = match["ranked_match_id"]

    if not ranked_id:
        logger.error(
            "Ranked PvP match %s has no ranked_match_id.",
            match["id"]
        )
        return False

    # ثبت نتیجه و امتیاز فقط یک بار
    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        current = conn.execute("""
            SELECT status
            FROM pvp_matches
            WHERE id = ?
        """, (match["id"],)).fetchone()

        ranked = conn.execute("""
            SELECT status
            FROM ranked_matches
            WHERE id = ?
        """, (ranked_id,)).fetchone()

        if (
            not current
            or current["status"] != "active"
            or not ranked
            or ranked["status"] != "active"
        ):
            return False

        conn.execute("""
            UPDATE pvp_matches
            SET status = 'finished'
            WHERE id = ?
            AND status = 'active'
        """, (match["id"],))

        conn.execute("""
            UPDATE ranked_matches
            SET status = 'finished'
            WHERE id = ?
            AND status = 'active'
        """, (ranked_id,))

    result = lifecycle.finish_pvp(
        winner_id,
        loser_id,
        match_id=ranked_id
    )

    return result or False
# ==========================================
# COMBAT REPLY
# ==========================================

async def combat_reply(update, context):

    message = update.effective_message
    user = update.effective_user

    if not message or not message.reply_to_message:
        return

    if not user or user.is_bot:
        return

    match = get_match(
        message.chat_id,
        message.reply_to_message.message_id
    )

    if not match:
        return

    if user.id not in (
        match["player1"],
        match["player2"]
    ):
        return

    if is_player_dead(user.id):
        await message.reply_text(
            "شخصیتت در حال احیاست."
        )
        return

    defender_id = (
        match["player2"]
        if user.id == match["player1"]
        else match["player1"]
    )

    if is_player_dead(defender_id):
        return

    skill_name = message.text.strip()

    if not skill_name or len(skill_name) > 80:
        return

    result = combat.use_skill(
        user.id,
        defender_id,
        skill_name
    )

    if not result["success"]:

        await message.reply_text(
            result["message"]
        )

        return

    attacker = get_player(user.id)
    defender = get_player(defender_id)

    if not attacker or not defender:
        return

    await message.reply_text(
        "⚔️ ATTACK RESULT\n\n"
        f"👤 مهاجم: {attacker['name']}\n"
        f"✨ مهارت: {skill_name}\n"
        f"💥 آسیب واردشده: {result['damage']}\n"
        f"🔷 مانای باقی‌مانده: {result['attacker_mp']}\n\n"
        f"👤 مدافع: {defender['name']}\n"
        f"❤️ HP باقی‌مانده: {result['defender_hp']}"
    )

    # بازیکن هنوز زنده است
    if result["defender_hp"] > 0:
        return

    winner_id = user.id
    loser_id = defender_id

    # بررسی مجدد مسابقه برای جلوگیری از ثبت نتیجه تکراری
    current_match = get_match(
        match["chat_id"],
        match["message_id"]
    )

    if not current_match:
        return

    if current_match["match_type"] == "ranked":

        result_data = finish_ranked_match(
            current_match,
            winner_id,
            loser_id
        )

        if not result_data:
            return

        await message.reply_text(
            "🏆 RANKED MATCH FINISHED!\n\n"
            f"🥇 برنده: {attacker['name']}\n"
            f"💀 بازنده: {defender['name']}\n\n"
            f"⭐ امتیاز برنده: +{result_data['winner_points']}\n"
            f"📉 امتیاز بازنده: {result_data['loser_points']}\n"
            f"🏅 امتیاز فعلی برنده: {result_data['winner_total']}\n"
            f"🏅 امتیاز فعلی بازنده: {result_data['loser_total']}"
        )

    else:

        finished = finish_friendly_pvp(
            current_match,
            winner_id,
            loser_id
        )

        if not finished:
            return

        await message.reply_text(
            "⚔️ FRIENDLY DUEL FINISHED!\n\n"
            f"🥇 برنده: {attacker['name']}\n"
            f"💀 بازنده: {defender['name']}\n\n"
            "این دوئل امتیاز Ranked را تغییر نمی‌دهد.\n"
            "بازیکن بازنده پس از ۵ دقیقه احیا می‌شود."
        )

    # پیشرفت مأموریت PvP
    try:

        daily_quests.add_quest_progress(
            winner_id,
            "pvp",
            1
        )

        daily_quests.add_quest_progress(
            loser_id,
            "pvp",
            1
        )

    except Exception:

        logger.exception(
            "Could not update daily PvP quests."
        )


# ==========================================
# SETUP
# ==========================================

def setup_pvp(application):

    init_pvp_db()

    lifecycle.setup_lifecycle(application)

    application.add_handler(
        CommandHandler(
            "duel",
            duel_command
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND
            & filters.REPLY,
            combat_reply
        )
    )