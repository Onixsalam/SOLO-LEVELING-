import time
import logging

from telegram.ext import ContextTypes

import database as db


logger = logging.getLogger(__name__)


# ==================================================
# SETTINGS
# ==================================================

BASE_WIN_POINTS = 20
BASE_LOSE_POINTS = 15

WIN_POINTS = BASE_WIN_POINTS
LOSE_POINTS = BASE_LOSE_POINTS

REVIVE_SECONDS = 300

MAX_PROTECTION = 2

STREAK_BONUSES = {
    3: 5,
    5: 10,
    7: 15,
    10: 25
}


# ==================================================
# DATABASE
# ==================================================

def init_lifecycle_db():

    with db.connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS pvp_rankings (
                user_id INTEGER PRIMARY KEY,
                points INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                win_streak INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS pvp_revives (
                user_id INTEGER PRIMARY KEY,
                revive_at REAL NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS rank_protection (
                user_id INTEGER PRIMARY KEY,
                protection_count INTEGER DEFAULT 0,
                last_granted REAL DEFAULT 0
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS lifecycle_processed_matches (
                match_id INTEGER PRIMARY KEY,
                processed_at REAL NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_revive_time
            ON pvp_revives(revive_at)
        """)


# ==================================================
# PLAYER RANKING
# ==================================================

def get_ranking(user_id):

    with db.connect() as conn:

        row = conn.execute("""
            SELECT *
            FROM pvp_rankings
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if row:
            return row

        conn.execute("""
            INSERT OR IGNORE INTO pvp_rankings (
                user_id,
                points,
                wins,
                losses,
                win_streak,
                best_streak
            )
            VALUES (?, 0, 0, 0, 0, 0)
        """, (user_id,))

        return conn.execute("""
            SELECT *
            FROM pvp_rankings
            WHERE user_id = ?
        """, (user_id,)).fetchone()


def get_rank_name(points):

    points = int(points)

    if points >= 6000:
        return "👑 Monarch"

    if points >= 5000:
        return "Master"

    if points >= 4000:
        return "Diamond"

    if points >= 3000:
        return "Platinum"

    if points >= 2000:
        return "Gold"

    if points >= 1000:
        return "Silver"

    return "Bronze"


def get_rank_text(user_id):

    ranking = get_ranking(user_id)

    if not ranking:
        return "اطلاعات رنک پیدا نشد."

    return (
        "🏆 RANK PROFILE\n\n"
        f"🎖 Rank: {get_rank_name(ranking['points'])}\n"
        f"📊 Points: {ranking['points']}\n"
        f"⚔️ Wins: {ranking['wins']}\n"
        f"💀 Losses: {ranking['losses']}\n"
        f"🔥 Win Streak: {ranking['win_streak']}\n"
        f"🏅 Best Streak: {ranking['best_streak']}"
    )


# ==================================================
# RANK PROTECTION
# ==================================================

def get_protection(user_id):

    with db.connect() as conn:

        row = conn.execute("""
            SELECT protection_count
            FROM rank_protection
            WHERE user_id = ?
        """, (user_id,)).fetchone()

    if not row:
        return 0

    return max(0, int(row["protection_count"]))


def grant_protection(user_id, amount=1):

    amount = max(0, int(amount))

    if amount == 0:
        return get_protection(user_id)

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        conn.execute("""
            INSERT OR IGNORE INTO rank_protection (
                user_id,
                protection_count,
                last_granted
            )
            VALUES (?, 0, 0)
        """, (user_id,))

        conn.execute("""
            UPDATE rank_protection
            SET
                protection_count = MIN(
                    ?,
                    protection_count + ?
                ),
                last_granted = ?
            WHERE user_id = ?
        """, (
            MAX_PROTECTION,
            amount,
            time.time(),
            user_id
        ))

        row = conn.execute("""
            SELECT protection_count
            FROM rank_protection
            WHERE user_id = ?
        """, (user_id,)).fetchone()

    return int(row["protection_count"])


def consume_protection(user_id):

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        row = conn.execute("""
            SELECT protection_count
            FROM rank_protection
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not row or row["protection_count"] <= 0:
            return False

        updated = conn.execute("""
            UPDATE rank_protection
            SET protection_count = protection_count - 1
            WHERE user_id = ?
              AND protection_count > 0
        """, (user_id,))

        return updated.rowcount == 1


# ==================================================
# REVIVAL
# ==================================================

def get_revive_remaining(user_id):

    with db.connect() as conn:

        row = conn.execute("""
            SELECT revive_at
            FROM pvp_revives
            WHERE user_id = ?
        """, (user_id,)).fetchone()

    if not row:
        return 0

    remaining = int(row["revive_at"] - time.time())

    return max(0, remaining)


def schedule_revive(user_id):

    with db.connect() as conn:

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
            user_id,
            time.time() + REVIVE_SECONDS
        ))


def revive_player(user_id):

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        row = conn.execute("""
            SELECT revive_at
            FROM pvp_revives
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not row:
            return False

        if row["revive_at"] > time.time():
            return False

        player = conn.execute("""
            SELECT max_hp, max_mp
            FROM players
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not player:
            return False

        conn.execute("""
            UPDATE players
            SET
                hp = max_hp,
                mp = max_mp,
                is_dead = 0
            WHERE user_id = ?
        """, (user_id,))

        conn.execute("""
            DELETE FROM pvp_revives
            WHERE user_id = ?
        """, (user_id,))

    return True


# ==================================================
# STREAK BONUS
# ==================================================

def calculate_streak_bonus(streak):

    streak = int(streak)

    bonus = 0

    for required_streak, points in STREAK_BONUSES.items():

        if streak >= required_streak:
            bonus = points

    return bonus
# ==================================================
# FINISH RANKED PVP
# ==================================================

def finish_pvp(
    winner_id,
    loser_id,
    match_id=None
):

    now = time.time()

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        # ==========================================
        # PREVENT DUPLICATE RESULTS
        # ==========================================

        if match_id is not None:

            try:

                conn.execute("""
                    INSERT INTO lifecycle_processed_matches (
                        match_id,
                        processed_at
                    )
                    VALUES (?, ?)
                """, (
                    match_id,
                    now
                ))

            except Exception:

                logger.warning(
                    "Match %s was already processed.",
                    match_id
                )

                return False

        # ==========================================
        # ENSURE RANKING ROWS
        # ==========================================

        for user_id in (winner_id, loser_id):

            conn.execute("""
                INSERT OR IGNORE INTO pvp_rankings (
                    user_id,
                    points,
                    wins,
                    losses,
                    win_streak,
                    best_streak
                )
                VALUES (?, 0, 0, 0, 0, 0)
            """, (user_id,))

        winner = conn.execute("""
            SELECT *
            FROM pvp_rankings
            WHERE user_id = ?
        """, (winner_id,)).fetchone()

        loser = conn.execute("""
            SELECT *
            FROM pvp_rankings
            WHERE user_id = ?
        """, (loser_id,)).fetchone()

        # ==========================================
        # WINNER
        # ==========================================

        new_streak = winner["win_streak"] + 1

        streak_bonus = calculate_streak_bonus(
            new_streak
        )

        winner_points = (
            BASE_WIN_POINTS + streak_bonus
        )

        conn.execute("""
            UPDATE pvp_rankings
            SET
                points = points + ?,
                wins = wins + 1,
                win_streak = ?,
                best_streak = MAX(best_streak, ?)
            WHERE user_id = ?
        """, (
            winner_points,
            new_streak,
            new_streak,
            winner_id
        ))

        # ==========================================
        # LOSER PROTECTION
        # ==========================================

        conn.execute("""
            INSERT OR IGNORE INTO rank_protection (
                user_id,
                protection_count,
                last_granted
            )
            VALUES (?, 0, 0)
        """, (loser_id,))

        protection = conn.execute("""
            SELECT protection_count
            FROM rank_protection
            WHERE user_id = ?
        """, (loser_id,)).fetchone()

        protected = False
        loser_points = 0

        if protection and protection["protection_count"] > 0:

            updated = conn.execute("""
                UPDATE rank_protection
                SET protection_count = protection_count - 1
                WHERE user_id = ?
                  AND protection_count > 0
            """, (loser_id,))

            protected = updated.rowcount == 1

        if not protected:

            loser_points = BASE_LOSE_POINTS

            conn.execute("""
                UPDATE pvp_rankings
                SET
                    points = MAX(0, points - ?),
                    losses = losses + 1,
                    win_streak = 0
                WHERE user_id = ?
            """, (
                loser_points,
                loser_id
            ))

        else:

            conn.execute("""
                UPDATE pvp_rankings
                SET
                    losses = losses + 1,
                    win_streak = 0
                WHERE user_id = ?
            """, (loser_id,))

        # ==========================================
        # PLAYER STATISTICS
        # ==========================================

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

        # ==========================================
        # REVIVAL TIMER
        # ==========================================

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
            now + REVIVE_SECONDS
        ))

        # ==========================================
        # RESULT
        # ==========================================

        winner_new = conn.execute("""
            SELECT points
            FROM pvp_rankings
            WHERE user_id = ?
        """, (winner_id,)).fetchone()

        loser_new = conn.execute("""
            SELECT points
            FROM pvp_rankings
            WHERE user_id = ?
        """, (loser_id,)).fetchone()

    return {
        "winner_points": winner_points,
        "loser_points": loser_points,
        "streak_bonus": streak_bonus,
        "protected": protected,
        "winner_total": winner_new["points"],
        "loser_total": loser_new["points"]
    }


# ==================================================
# AUTO REVIVAL JOB
# ==================================================

async def auto_revive_job(
    context: ContextTypes.DEFAULT_TYPE
):

    now = time.time()

    with db.connect() as conn:

        expired = conn.execute("""
            SELECT user_id
            FROM pvp_revives
            WHERE revive_at <= ?
        """, (now,)).fetchall()

    for row in expired:

        user_id = row["user_id"]

        try:

            success = revive_player(user_id)

            if success:

                try:

                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            "✨ REVIVAL COMPLETE!\n\n"
                            "❤️ HP restored.\n"
                            "🔮 MP restored.\n\n"
                            "تو دوباره می‌تونی وارد مبارزه بشی."
                        )
                    )

                except Exception:

                    logger.info(
                        "Could not notify revived player %s",
                        user_id
                    )

        except Exception:

            logger.exception(
                "Auto revival failed for user %s",
                user_id
            )


# ==================================================
# SETUP
# ==================================================

def setup_lifecycle(application):

    init_lifecycle_db()

    if application.job_queue:

        application.job_queue.run_repeating(
            auto_revive_job,
            interval=10,
            first=10,
            name="pvp_auto_revive"
        )

    else:

        logger.warning(
            "JobQueue is unavailable. Auto revival is disabled."
        )