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


# ==================================================
# DATABASE
# ==================================================

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

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pvp_players
            ON pvp_matches(player1, player2, status)
        """)


# ==================================================
# PLAYER
# ==================================================

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

    if player["is_dead"] or player["hp"] <= 0:
        return True

    if lifecycle.get_revive_remaining(user_id) > 0:
        return True

    return False


# ==================================================
# ACTIVE MATCH CHECK
# ==================================================

def player_has_active_match(user_id):

    with db.connect() as conn:

        row = conn.execute("""
            SELECT id
            FROM pvp_matches
            WHERE status = 'active'
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


# ==================================================
# CREATE FRIENDLY DUEL
# ==================================================

async def duel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    if message.chat.type not in ("group", "supergroup"):

        await message.reply_text(
            "برای شروع مبارزه باید داخل گروه باشی."
        )

        return

    if not message.reply_to_message:

        await message.reply_text(
            "روی پیام حریفت ریپلای کن و /duel بزن."
        )

        return

    opponent = message.reply_to_message.from_user

    if (
        not opponent
        or opponent.is_bot
        or opponent.id == user.id
    ):

        await message.reply_text(
            "این حریف قابل انتخاب نیست."
        )

        return

    player1 = get_player(user.id)
    player2 = get_player(opponent.id)

    if not player1 or not player2:

        await message.reply_text(
            "هر دو بازیکن باید ابتدا با /start ثبت‌نام کنند."
        )

        return

    if is_player_dead(user.id) or is_player_dead(opponent.id):

        await message.reply_text(
            "یکی از بازیکن‌ها فعلاً قادر به مبارزه نیست."
        )

        return

    if (
        player_has_active_match(user.id)
        or player_has_active_match(opponent.id)
    ):

        await message.reply_text(
            "یکی از بازیکن‌ها در حال حاضر مبارزه فعالی داره."
        )

        return

    battle_message = await message.reply_text(
        "⚔️ FRIENDLY PVP STARTED!\n\n"
        f"👤 {player1['name']}\n"
        f"❤️ HP: {player1['hp']}/{player1['max_hp']}\n\n"
        "VS\n\n"
        f"👤 {player2['name']}\n"
        f"❤️ HP: {player2['hp']}/{player2['max_hp']}\n\n"
        "برای حمله روی همین پیام ریپلای کن "
        "و اسم یکی از مهارت‌هات رو بنویس."
    )

    try:

        with db.connect() as conn:

            conn.execute("BEGIN IMMEDIATE")

            active = conn.execute("""
                SELECT id
                FROM pvp_matches
                WHERE status = 'active'
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

                raise ValueError(
                    "یکی از بازیکن‌ها وارد مبارزه دیگری شده."
                )

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

    except ValueError as error:

        try:
            await battle_message.edit_text(
                "❌ مبارزه ساخته نشد.\n"
                f"{error}"
            )
        except Exception:
            pass

    except Exception:

        logger.exception(
            "Failed to create friendly PVP."
        )

        try:
            await battle_message.edit_text(
                "ساخت مبارزه با خطا مواجه شد. دوباره تلاش کن."
            )
        except Exception:
            pass


# ==================================================
# FINISH FRIENDLY MATCH
# ==================================================

def finish_friendly_pvp(
    winner_id,
    loser_id,
    match_id
):

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        updated = conn.execute("""
            UPDATE pvp_matches
            SET status = 'finished'
            WHERE id = ?
              AND status = 'active'
        """, (match_id,))

        if updated.rowcount != 1:
            return False

        conn.execute("""
            UPDATE players
            SET wins = wins + 1
            WHERE user_id = ?
        """, (winner_id,))

        conn.execute("""
            UPDATE players
            SET
                losses = losses + 1,
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


# ==================================================
# FINISH RANKED MATCH
# ==================================================

def finish_ranked_match(match_id):

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        updated = conn.execute("""
            UPDATE ranked_matches
            SET status = 'finished'
            WHERE id = ?
              AND status = 'active'
        """, (match_id,))

    return updated.rowcount == 1
# ==================================================
# COMBAT REPLY
# ==================================================

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

    if not message.text or user.is_bot:
        return

    if message.chat.type not in ("group", "supergroup"):
        return

    # ==============================================
    # FIND MATCH
    # ==============================================

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

    # فقط دو شرکت‌کننده اجازه حمله دارند
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
            "☠️ تو در وضعیت DEAD هستی و نمی‌تونی حمله کنی."
        )

        return

    if is_player_dead(defender_id):
        return

    skill_name = message.text.strip()

    if not skill_name or len(skill_name) > 60:
        return

    # ==============================================
    # USE SKILL
    # ==============================================

    success, result = combat.use_skill(
        attacker_id,
        defender_id,
        skill_name
    )

    if not success:

        await message.reply_text(str(result))
        return

    damage = result["damage"]
    defender_hp = result["defender_hp"]
    attacker_mp = result["attacker_mp"]

    attacker = get_player(attacker_id)
    defender = get_player(defender_id)

    if not attacker or not defender:
        return

    # ==============================================
    # MATCH FINISHED
    # ==============================================

    if result["defeated"]:

        with db.connect() as conn:

            ranked_match = conn.execute("""
                SELECT id
                FROM ranked_matches
                WHERE battle_message_id = ?
                  AND battle_chat_id = ?
                  AND status = 'active'
            """, (
                match["message_id"],
                match["chat_id"]
            )).fetchone()

        # ==========================================
        # RANKED MATCH
        # ==========================================

        if ranked_match:

            ranked_id = ranked_match["id"]

            ranking_result = lifecycle.finish_pvp(
                winner_id=attacker_id,
                loser_id=defender_id,
                match_id=ranked_id
            )

            if not ranking_result:

                logger.warning(
                    "Ranked result was already processed or failed. "
                    "Match ID: %s",
                    ranked_id
                )

                return

            with db.connect() as conn:

                conn.execute("BEGIN IMMEDIATE")

                conn.execute("""
                    UPDATE ranked_matches
                    SET status = 'finished'
                    WHERE id = ?
                      AND status = 'active'
                """, (ranked_id,))

                conn.execute("""
                    UPDATE pvp_matches
                    SET status = 'finished'
                    WHERE id = ?
                      AND status = 'active'
                """, (match["id"],))

            # Daily quest
            try:

                daily_quests.add_quest_progress(
                    attacker_id,
                    "ranked_win",
                    1
                )

            except Exception:

                logger.exception(
                    "Failed to update ranked daily quest."
                )

            winner_points = ranking_result.get(
                "winner_points",
                lifecycle.WIN_POINTS
            )

            loser_points = ranking_result.get(
                "loser_points",
                lifecycle.LOSE_POINTS
            )

            streak_bonus = ranking_result.get(
                "streak_bonus",
                0
            )

            protected = ranking_result.get(
                "protected",
                False
            )

            points_text = (
                "🏆 RANKED MATCH\n\n"
                f"📈 Winner: +{winner_points} RP\n"
                f"📉 Loser: -{loser_points} RP\n"
                f"🔥 Streak Bonus: +{streak_bonus} RP\n"
            )

            if protected:

                points_text += (
                    "🛡️ Rank Protection فعال شد؛ "
                    "از کاهش امتیاز جلوگیری کرد.\n"
                )

        # ==========================================
        # FRIENDLY MATCH
        # ==========================================

        else:

            friendly_finished = finish_friendly_pvp(
                winner_id=attacker_id,
                loser_id=defender_id,
                match_id=match["id"]
            )

            if not friendly_finished:
                return

            points_text = (
                "🤝 FRIENDLY MATCH\n"
                "امتیاز رنک تغییری نکرد."
            )

        # ==========================================
        # FINAL RESULT
        # ==========================================

        await message.reply_text(
            "🏆 MATCH FINISHED!\n\n"
            f"👑 Winner: {attacker['name']}\n"
            f"💀 Loser: {defender['name']}\n\n"
            f"💥 Final Damage: {damage}\n"
            "☠️ Loser Status: DEAD\n"
            "⏳ Revival: 5 Minutes\n\n"
            f"{points_text}"
        )

        return

    # ==============================================
    # ATTACK RESULT
    # ==============================================

    await message.reply_text(
        "⚔️ ATTACK RESULT\n\n"
        f"👤 Attacker: {attacker['name']}\n"
        f"🎯 Target: {defender['name']}\n\n"
        f"🌀 Skill: {result['skill']}\n"
        f"💥 Damage: {damage}\n"
        f"❤️ Remaining HP: {defender_hp}\n"
        f"🔮 Attacker MP: {attacker_mp}"
    )


# ==================================================
# SETUP
# ==================================================

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