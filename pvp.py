import logging
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
import daily_quests


logger = logging.getLogger(__name__)


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
                match_type TEXT DEFAULT 'friendly',
                ranked_match_id INTEGER,
                created_at INTEGER NOT NULL
            )
        """)

        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(pvp_matches)"
            ).fetchall()
        }

        if "match_type" not in columns:
            conn.execute("""
                ALTER TABLE pvp_matches
                ADD COLUMN match_type TEXT DEFAULT 'friendly'
            """)

        if "ranked_match_id" not in columns:
            conn.execute("""
                ALTER TABLE pvp_matches
                ADD COLUMN ranked_match_id INTEGER
            """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_pvp_player1
            ON pvp_matches(player1, status)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_pvp_player2
            ON pvp_matches(player2, status)
        """)


# =====================================
# PLAYER
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

    return bool(
        player["is_dead"] or player["hp"] <= 0
    )


def player_has_active_match(user_id):

    with db.connect() as conn:

        row = conn.execute("""
            SELECT id
            FROM pvp_matches
            WHERE status IN ('active', 'finishing')
            AND (
                player1 = ?
                OR player2 = ?
            )
            LIMIT 1
        """, (
            user_id,
            user_id
        )).fetchone()

    return row is not None


# =====================================
# GET MATCH
# =====================================

def get_match(chat_id, message_id):

    with db.connect() as conn:

        return conn.execute("""
            SELECT *
            FROM pvp_matches
            WHERE chat_id = ?
            AND message_id = ?
            LIMIT 1
        """, (
            chat_id,
            message_id
        )).fetchone()


# =====================================
# FRIENDLY DUEL
# =====================================

async def duel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    if message.chat.type == "private":

        await message.reply_text(
            "برای مبارزه دوستانه باید داخل گروه باشی."
        )
        return

    if not message.reply_to_message:

        await message.reply_text(
            "برای مبارزه باید به پیام بازیکن موردنظر Reply کنی."
        )
        return

    opponent = message.reply_to_message.from_user

    if not opponent or opponent.is_bot:

        await message.reply_text(
            "این کاربر نمی‌تواند وارد مبارزه شود."
        )
        return

    if opponent.id == user.id:

        await message.reply_text(
            "نمی‌توانی با خودت مبارزه کنی."
        )
        return

    player1 = get_player(user.id)
    player2 = get_player(opponent.id)

    if not player1 or not player2:

        await message.reply_text(
            "هر دو بازیکن باید ابتدا ربات را در چت خصوصی Start کنند."
        )
        return

    if is_player_dead(user.id) or is_player_dead(opponent.id):

        await message.reply_text(
            "یکی از بازیکنان در وضعیت مرگ قرار دارد."
        )
        return

    if player_has_active_match(user.id):

        await message.reply_text(
            "تو در حال حاضر داخل یک مبارزه هستی."
        )
        return

    if player_has_active_match(opponent.id):

        await message.reply_text(
            "بازیکن موردنظر در حال حاضر داخل یک مبارزه است."
        )
        return

    battle_message = await message.reply_text(
        "⚔️ مبارزه دوستانه آغاز شد!\n\n"
        f"🔴 مهاجم: {user.first_name}\n"
        f"🔵 مدافع: {opponent.first_name}\n\n"
        "برای حمله، نام مهارتت را در پاسخ به همین پیام بنویس.\n"
        "دفاع به‌صورت خودکار محاسبه می‌شود."
    )

    try:

        with db.connect() as conn:

            conn.execute("BEGIN IMMEDIATE")

            active = conn.execute("""
                SELECT id
                FROM pvp_matches
                WHERE status IN ('active', 'finishing')
                AND (
                    player1 IN (?, ?)
                    OR player2 IN (?, ?)
                )
                LIMIT 1
            """, (
                user.id,
                opponent.id,
                user.id,
                opponent.id
            )).fetchone()

            if active:

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
                message.chat_id,
                battle_message.message_id,
                user.id,
                opponent.id,
                int(time.time())
            ))

    except Exception:

        logger.exception("Could not create friendly duel")

        await message.reply_text(
            "هنگام ایجاد مبارزه خطایی رخ داد."
        )


# =====================================
# FINISH FRIENDLY MATCH
# =====================================

def finish_friendly_pvp(
    winner_id,
    loser_id,
    match_id
):

    try:

        with db.connect() as conn:

            conn.execute("BEGIN IMMEDIATE")

            match = conn.execute("""
                SELECT *
                FROM pvp_matches
                WHERE id = ?
                AND status = 'active'
                AND match_type = 'friendly'
            """, (match_id,)).fetchone()

            if not match:
                return False

            if winner_id not in (
                match["player1"],
                match["player2"]
            ):
                return False

            if loser_id not in (
                match["player1"],
                match["player2"]
            ):
                return False

            if winner_id == loser_id:
                return False

            conn.execute("""
                UPDATE pvp_matches
                SET status = 'finished'
                WHERE id = ?
                AND status = 'active'
            """, (match_id,))

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

            revive_at = int(
                time.time() + lifecycle.REVIVE_SECONDS
            )

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
                revive_at
            ))

        return True

    except Exception:

        logger.exception(
            "Friendly match finish failed"
        )

        return False


# =====================================
# FINISH RANKED MATCH
# =====================================

def finish_ranked_match(
    winner_id,
    loser_id,
    pvp_match
):

    ranked_id = pvp_match["ranked_match_id"]

    if not ranked_id:
        return False

    try:

        with db.connect() as conn:

            conn.execute("BEGIN IMMEDIATE")

            current = conn.execute("""
                SELECT *
                FROM pvp_matches
                WHERE id = ?
                AND status = 'active'
                AND match_type = 'ranked'
            """, (
                pvp_match["id"],
            )).fetchone()

            if not current:
                return False

            conn.execute("""
                UPDATE pvp_matches
                SET status = 'finishing'
                WHERE id = ?
                AND status = 'active'
            """, (
                pvp_match["id"],
            ))

        result = lifecycle.finish_pvp(
            winner_id,
            loser_id,
            match_id=ranked_id
        )

        if not result:
            with db.connect() as conn:
                conn.execute("""
                    UPDATE pvp_matches
                    SET status = 'active'
                    WHERE id = ?
                    AND status = 'finishing'
                """, (
                    pvp_match["id"],
                ))

            return False

        with db.connect() as conn:

            conn.execute("BEGIN IMMEDIATE")

            conn.execute("""
                UPDATE pvp_matches
                SET status = 'finished'
                WHERE id = ?
                AND status = 'finishing'
            """, (
                pvp_match["id"],
            ))

            conn.execute("""
                UPDATE ranked_matches
                SET status = 'finished'
                WHERE id = ?
                AND status = 'active'
            """, (
                ranked_id,
            ))

        return result

    except Exception:

        logger.exception(
            "Ranked match finish failed"
        )

        return False
# =====================================
# COMBAT REPLY
# =====================================

async def combat_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    if not message.reply_to_message:
        return

    if message.chat.type == "private":
        return

    if not message.text:
        return

    skill_name = message.text.strip()

    if not skill_name or len(skill_name) > 60:
        return

    pvp_match = get_match(
        message.chat_id,
        message.reply_to_message.message_id
    )

    if not pvp_match:
        return

    if pvp_match["status"] != "active":
        return

    attacker_id = user.id

    if attacker_id not in (
        pvp_match["player1"],
        pvp_match["player2"]
    ):
        return

    if attacker_id == pvp_match["player1"]:
        defender_id = pvp_match["player2"]
    else:
        defender_id = pvp_match["player1"]

    if is_player_dead(attacker_id):

        await message.reply_text(
            "شخصیت تو در وضعیت مرگ قرار دارد."
        )
        return

    if is_player_dead(defender_id):

        await message.reply_text(
            "حریف دیگر توان ادامه مبارزه را ندارد."
        )
        return

    result = combat.use_skill(
        attacker_id,
        defender_id,
        skill_name
    )

    if not result["success"]:

        await message.reply_text(
            result["message"]
        )
        return

    damage = result["damage"]
    defender_hp = result["defender_hp"]
    attacker_mp = result["attacker_mp"]

    attacker = get_player(attacker_id)
    defender = get_player(defender_id)

    attacker_name = (
        attacker["name"]
        if attacker
        else str(attacker_id)
    )

    defender_name = (
        defender["name"]
        if defender
        else str(defender_id)
    )

    text = (
        "⚔️ نتیجه حمله\n\n"
        f"🔴 مهاجم: {attacker_name}\n"
        f"🔵 مدافع: {defender_name}\n\n"
        f"💥 مهارت: {result['skill']}\n"
        f"❤️ آسیب واردشده: {damage}\n"
        f"💙 مانای باقی‌مانده مهاجم: {attacker_mp}\n"
        f"❤️ سلامتی باقی‌مانده مدافع: {defender_hp}"
    )

    await message.reply_text(text)

    if not result["defeated"]:
        return

    if pvp_match["match_type"] == "ranked":

        finish_result = finish_ranked_match(
            attacker_id,
            defender_id,
            pvp_match
        )

        if not finish_result:

            await message.reply_text(
                "⚠️ مبارزه تمام شد، اما ثبت نتیجه Ranked "
                "با خطا مواجه شد. نتیجه باید بررسی شود."
            )
            return

        winner_points = finish_result.get(
            "winner_points",
            0
        )

        loser_points = finish_result.get(
            "loser_points",
            0
        )

        bonus = finish_result.get(
            "streak_bonus",
            0
        )

        protected = finish_result.get(
            "protected",
            False
        )

        final_text = (
            "🏆 پایان مبارزه Ranked!\n\n"
            f"🥇 برنده: {attacker_name}\n"
            f"💀 بازنده: {defender_name}\n\n"
            f"📈 امتیاز دریافتی: +{winner_points}\n"
            f"📉 امتیاز ازدست‌رفته حریف: -{loser_points}\n"
        )

        if bonus:
            final_text += (
                f"🔥 پاداش استریک: +{bonus}\n"
            )

        if protected:
            final_text += (
                "🛡️ محافظ رتبه از کاهش امتیاز حریف جلوگیری کرد.\n"
            )

        await message.reply_text(final_text)

    else:

        finished = finish_friendly_pvp(
            attacker_id,
            defender_id,
            pvp_match["id"]
        )

        if not finished:

            await message.reply_text(
                "ثبت نتیجه مبارزه دوستانه با خطا مواجه شد."
            )
            return

        await message.reply_text(
            "🏆 مبارزه دوستانه تمام شد!\n\n"
            f"🥇 برنده: {attacker_name}\n"
            f"💀 بازنده: {defender_name}\n\n"
            "بازیکن بازنده پس از ۵ دقیقه احیا می‌شود."
        )

    # ثبت مأموریت PvP
    try:

        daily_quests.add_quest_progress(
            attacker_id,
            "pvp",
            1
        )

        daily_quests.add_quest_progress(
            defender_id,
            "pvp",
            1
        )

    except Exception:

        logger.exception(
            "Could not update PvP daily quests"
        )


# =====================================
# SETUP
# =====================================

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
            filters.TEXT & ~filters.COMMAND,
            combat_reply
        )
    )

    logger.info("PvP system loaded successfully")