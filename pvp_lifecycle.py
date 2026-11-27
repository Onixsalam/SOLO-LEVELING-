import time
import logging

from telegram.ext import ContextTypes

import database as db


logger = logging.getLogger(__name__)


# =====================================
# SETTINGS
# =====================================

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


# =====================================
# DATABASE
# =====================================

def init_lifecycle_db():

    with db.connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS pvp_rankings (
                user_id INTEGER PRIMARY KEY,
                points INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0,
                FOREIGN KEY(user_id)
                    REFERENCES players(user_id)
                    ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS pvp_revives (
                user_id INTEGER PRIMARY KEY,
                revive_at INTEGER NOT NULL,
                FOREIGN KEY(user_id)
                    REFERENCES players(user_id)
                    ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS rank_protection (
                user_id INTEGER PRIMARY KEY,
                protection_count INTEGER DEFAULT 0,
                FOREIGN KEY(user_id)
                    REFERENCES players(user_id)
                    ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS lifecycle_processed_matches (
                match_id INTEGER PRIMARY KEY,
                processed_at INTEGER NOT NULL
            )
        """)


# =====================================
# RANKING
# =====================================

def get_ranking(user_id):

    with db.connect() as conn:

        row = conn.execute("""
            SELECT *
            FROM pvp_rankings
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if row:
            return row

        player = conn.execute("""
            SELECT user_id
            FROM players
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not player:
            return None

        conn.execute("""
            INSERT OR IGNORE INTO pvp_rankings (
                user_id,
                points,
                wins,
                losses,
                streak,
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

    ranks = [
        (6000, "Monarch"),
        (5000, "Master"),
        (4000, "Diamond"),
        (3000, "Platinum"),
        (2000, "Gold"),
        (1000, "Silver"),
        (0, "Bronze")
    ]

    for required, name in ranks:

        if points >= required:
            return name

    return "Bronze"


def get_rank_text(user_id):

    ranking = get_ranking(user_id)

    if not ranking:
        return "بازیکن پیدا نشد."

    points = ranking["points"]

    return (
        f"رتبه: {get_rank_name(points)}\n"
        f"امتیاز: {points}\n"
        f"برد: {ranking['wins']}\n"
        f"باخت: {ranking['losses']}\n"
        f"استریک: {ranking['streak']}"
    )


# =====================================
# RANK PROTECTION
# =====================================

def get_protection(user_id):

    with db.connect() as conn:

        row = conn.execute("""
            SELECT protection_count
            FROM rank_protection
            WHERE user_id = ?
        """, (user_id,)).fetchone()

    if not row:
        return 0

    return int(row["protection_count"] or 0)


def grant_protection(user_id, amount=1):

    amount = max(0, int(amount))

    if amount == 0:
        return get_protection(user_id)

    with db.connect() as conn:

        conn.execute("""
            INSERT OR IGNORE INTO rank_protection (
                user_id,
                protection_count
            )
            VALUES (?, 0)
        """, (user_id,))

        conn.execute("""
            UPDATE rank_protection
            SET protection_count = MIN(
                protection_count + ?,
                ?
            )
            WHERE user_id = ?
        """, (
            amount,
            MAX_PROTECTION,
            user_id
        ))

        row = conn.execute("""
            SELECT protection_count
            FROM rank_protection
            WHERE user_id = ?
        """, (user_id,)).fetchone()

    return int(row["protection_count"] or 0)


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

        conn.execute("""
            UPDATE rank_protection
            SET protection_count = protection_count - 1
            WHERE user_id = ?
            AND protection_count > 0
        """, (user_id,))

    return True


# =====================================
# STREAK BONUS
# =====================================

def get_streak_bonus(streak):

    bonus = 0

    for required, points in STREAK_BONUSES.items():

        if streak >= required:
            bonus = points

    return bonus


# =====================================
# REVIVE
# =====================================

def schedule_revive(user_id):

    revive_at = int(
        time.time() + REVIVE_SECONDS
    )

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
            revive_at
        ))

    return revive_at


def get_revive_remaining(user_id):

    with db.connect() as conn:

        row = conn.execute("""
            SELECT revive_at
            FROM pvp_revives
            WHERE user_id = ?
        """, (user_id,)).fetchone()

    if not row:
        return 0

    return max(
        0,
        int(row["revive_at"] - time.time())
    )


def revive_player(user_id):

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        revive = conn.execute("""
            SELECT revive_at
            FROM pvp_revives
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not revive:
            return False

        if revive["revive_at"] > time.time():
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
            SET hp = max_hp,
                mp = max_mp,
                is_dead = 0
            WHERE user_id = ?
        """, (user_id,))

        conn.execute("""
            DELETE FROM pvp_revives
            WHERE user_id = ?
        """, (user_id,))

    return True


# =====================================
# FINISH RANKED MATCH
# =====================================

def finish_pvp(
    winner_id,
    loser_id,
    match_id=None
):

    if winner_id == loser_id:
        return False

    if match_id is None:
        return False

    try:

        with db.connect() as conn:

            conn.execute("BEGIN IMMEDIATE")

            # جلوگیری از ثبت دوباره نتیجه
            existing = conn.execute("""
                SELECT match_id
                FROM lifecycle_processed_matches
                WHERE match_id = ?
            """, (match_id,)).fetchone()

            if existing:
                return False

            # بررسی بازیکنان
            winner = conn.execute("""
                SELECT user_id
                FROM players
                WHERE user_id = ?
            """, (winner_id,)).fetchone()

            loser = conn.execute("""
                SELECT user_id
                FROM players
                WHERE user_id = ?
            """, (loser_id,)).fetchone()

            if not winner or not loser:
                return False

            # بررسی مسابقه Ranked
            ranked_match = conn.execute("""
                SELECT *
                FROM ranked_matches
                WHERE id = ?
            """, (match_id,)).fetchone()

            if not ranked_match:
                return False

            if ranked_match["status"] not in (
                "active",
                "finishing"
            ):
                return False

            if winner_id not in (
                ranked_match["player1"],
                ranked_match["player2"]
            ):
                return False

            if loser_id not in (
                ranked_match["player1"],
                ranked_match["player2"]
            ):
                return False

            # ثبت نهایی مسابقه
            conn.execute("""
                INSERT INTO lifecycle_processed_matches (
                    match_id,
                    processed_at
                )
                VALUES (?, ?)
            """, (
                match_id,
                int(time.time())
            ))

            # ساخت رتبه در صورت نبودن
            for player_id in (
                winner_id,
                loser_id
            ):

                conn.execute("""
                    INSERT OR IGNORE INTO pvp_rankings (
                        user_id,
                        points,
                        wins,
                        losses,
                        streak,
                        best_streak
                    )
                    VALUES (?, 0, 0, 0, 0, 0)
                """, (player_id,))

            winner_rank = conn.execute("""
                SELECT *
                FROM pvp_rankings
                WHERE user_id = ?
            """, (winner_id,)).fetchone()

            loser_rank = conn.execute("""
                SELECT *
                FROM pvp_rankings
                WHERE user_id = ?
            """, (loser_id,)).fetchone()

            # محاسبه استریک و پاداش
            new_streak = winner_rank["streak"] + 1

            bonus = get_streak_bonus(
                new_streak
            )

            winner_points = (
                BASE_WIN_POINTS + bonus
            )

            # محافظ رتبه
            protection_row = conn.execute("""
                SELECT protection_count
                FROM rank_protection
                WHERE user_id = ?
            """, (loser_id,)).fetchone()

            protected = bool(
                protection_row
                and protection_row["protection_count"] > 0
            )

            if protected:

                conn.execute("""
                    UPDATE rank_protection
                    SET protection_count = protection_count - 1
                    WHERE user_id = ?
                    AND protection_count > 0
                """, (loser_id,))

                loser_points = 0

            else:

                loser_points = min(
                    BASE_LOSE_POINTS,
                    loser_rank["points"]
                )

            # به‌روزرسانی برنده
            conn.execute("""
                UPDATE pvp_rankings
                SET points = points + ?,
                    wins = wins + 1,
                    streak = ?,
                    best_streak = MAX(
                        best_streak,
                        ?
                    )
                WHERE user_id = ?
            """, (
                winner_points,
                new_streak,
                new_streak,
                winner_id
            ))

            # به‌روزرسانی بازنده
            conn.execute("""
                UPDATE pvp_rankings
                SET points = MAX(
                        0,
                        points - ?
                    ),
                    losses = losses + 1,
                    streak = 0
                WHERE user_id = ?
            """, (
                loser_points,
                loser_id
            ))

            # آمار بازیکنان
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

            # زمان احیا
            revive_at = int(
                time.time() + REVIVE_SECONDS
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

            winner_total = conn.execute("""
                SELECT points
                FROM pvp_rankings
                WHERE user_id = ?
            """, (winner_id,)).fetchone()["points"]

            loser_total = conn.execute("""
                SELECT points
                FROM pvp_rankings
                WHERE user_id = ?
            """, (loser_id,)).fetchone()["points"]

            return {
                "winner_points": winner_points,
                "loser_points": loser_points,
                "streak_bonus": bonus,
                "protected": protected,
                "winner_total": winner_total,
                "loser_total": loser_total
            }

    except Exception:

        logger.exception(
            "Ranked result processing failed"
        )

        return False
# =====================================
# AUTOMATIC REVIVE
# =====================================

async def auto_revive_job(
    context: ContextTypes.DEFAULT_TYPE
):

    now = int(time.time())

    try:

        with db.connect() as conn:

            expired = conn.execute("""
                SELECT user_id
                FROM pvp_revives
                WHERE revive_at <= ?
            """, (now,)).fetchall()

        for row in expired:

            user_id = row["user_id"]

            revived = revive_player(user_id)

            if not revived:
                continue

            try:

                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "✨ احیای شخصیت انجام شد!\n\n"
                        "❤️ HP به حداکثر رسید.\n"
                        "💙 MP به حداکثر رسید.\n\n"
                        "اکنون می‌توانی دوباره وارد مبارزه شوی."
                    )
                )

            except Exception:

                logger.warning(
                    "Could not notify revived player %s",
                    user_id
                )

    except Exception:

        logger.exception(
            "Automatic revive job failed"
        )


# =====================================
# SETUP
# =====================================

def setup_lifecycle(application):

    init_lifecycle_db()

    if application.job_queue:

        existing = application.job_queue.get_jobs_by_name(
            "pvp_auto_revive"
        )

        if not existing:

            application.job_queue.run_repeating(
                auto_revive_job,
                interval=10,
                first=5,
                name="pvp_auto_revive"
            )

    logger.info(
        "PvP lifecycle loaded successfully"
    )