import time
import logging

from telegram.ext import ContextTypes

import database as db

logger = logging.getLogger(name)

=====================================

SETTINGS

=====================================

BASE_WIN_POINTS = 20
BASE_LOSE_POINTS = 15

Compatibility with pvp.py

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

=====================================

DATABASE

=====================================

def init_lifecycle_db():

with db.connect() as conn:

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pvp_rankings (
            user_id INTEGER PRIMARY KEY,
            points INTEGER DEFAULT 0,
            win_streak INTEGER DEFAULT 0,
            best_streak INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pvp_revives (
            user_id INTEGER PRIMARY KEY,
            revive_at INTEGER NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS rank_protection (
            user_id INTEGER PRIMARY KEY,
            protection_count INTEGER DEFAULT 0,
            last_granted INTEGER DEFAULT 0
        )
    """)

=====================================

RANK

=====================================

def get_rank(points):

ranks = [
    (6000, "Monarch"),
    (5000, "Master"),
    (4000, "Diamond"),
    (3000, "Platinum"),
    (2000, "Gold"),
    (1000, "Silver"),
    (0, "Bronze")
]

for minimum, name in ranks:

    if points >= minimum:
        return name

return "Bronze"

def get_ranking(user_id):

with db.connect() as conn:

    conn.execute("""
        INSERT OR IGNORE INTO pvp_rankings (user_id)
        VALUES (?)
    """, (user_id,))

    return conn.execute("""
        SELECT *
        FROM pvp_rankings
        WHERE user_id = ?
    """, (user_id,)).fetchone()

def get_rank_profile(user_id):

row = get_ranking(user_id)

if not row:
    return None

return {
    "points": row["points"],
    "rank": get_rank(row["points"]),
    "win_streak": row["win_streak"],
    "best_streak": row["best_streak"]
}

=====================================

PROTECTION

=====================================

def get_protection(user_id):

with db.connect() as conn:

    row = conn.execute("""
        SELECT protection_count
        FROM rank_protection
        WHERE user_id = ?
    """, (user_id,)).fetchone()

return row["protection_count"] if row else 0

def grant_protection(user_id, amount=1):

if amount <= 0:
    return False

with db.connect() as conn:

    conn.execute("""
        INSERT OR IGNORE INTO rank_protection
        (user_id, protection_count)
        VALUES (?, 0)
    """, (user_id,))

    conn.execute("""
        UPDATE rank_protection
        SET protection_count =
            MIN(protection_count + ?, ?),
            last_granted = ?
        WHERE user_id = ?
    """, (
        amount,
        MAX_PROTECTION,
        int(time.time()),
        user_id
    ))

return True

def consume_protection_in_transaction(conn, user_id):

row = conn.execute("""
    SELECT protection_count
    FROM rank_protection
    WHERE user_id = ?
""", (user_id,)).fetchone()

if not row or row["protection_count"] <= 0:
    return False

result = conn.execute("""
    UPDATE rank_protection
    SET protection_count = protection_count - 1
    WHERE user_id = ?
    AND protection_count > 0
""", (user_id,))

return result.rowcount == 1

=====================================

STREAK BONUS

=====================================

def get_streak_bonus(streak):

bonus = 0

for required_streak, points in STREAK_BONUSES.items():

    if streak >= required_streak:
        bonus = points

return bonus

=====================================

FINISH RANKED MATCH

=====================================

def finish_pvp(winner_id, loser_id):

if winner_id == loser_id:
    return None

now = int(time.time())

with db.connect() as conn:

    # Ensure ranking records exist

    conn.execute("""
        INSERT OR IGNORE INTO pvp_rankings (user_id)
        VALUES (?), (?)
    """, (winner_id, loser_id))

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

    if not winner or not loser:
        return None

    # Calculate winner streak

    new_streak = winner["win_streak"] + 1

    bonus = get_streak_bonus(new_streak)

    winner_points = BASE_WIN_POINTS + bonus

    # Check loser protection

    protected = consume_protection_in_transaction(
        conn,
        loser_id
    )

    loser_points = (
        0 if protected else BASE_LOSE_POINTS
    )

    # Update winner

    conn.execute("""
        UPDATE pvp_rankings
        SET points = MAX(0, points + ?),
            win_streak = ?,
            best_streak = MAX(best_streak, ?)
        WHERE user_id = ?
    """, (
        winner_points,
        new_streak,
        new_streak,
        winner_id
    ))

    # Update loser

    conn.execute("""
        UPDATE pvp_rankings
        SET points = MAX(0, points - ?),
            win_streak = 0
        WHERE user_id = ?
    """, (
        loser_points,
        loser_id
    ))

    # Update player records

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

    # Schedule revival

    conn.execute("""
        INSERT INTO pvp_revives (user_id, revive_at)
        VALUES (?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET revive_at = excluded.revive_at
    """, (
        loser_id,
        now + REVIVE_SECONDS
    ))

    return {
        "winner_points": winner_points,
        "streak_bonus": bonus,
        "loser_points": loser_points,
        "protected": protected,
        "winner_streak": new_streak
    }

=====================================

REVIVAL

=====================================

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
    row["revive_at"] - int(time.time())
)

def revive_player(user_id):

with db.connect() as conn:

    row = conn.execute("""
        SELECT revive_at
        FROM pvp_revives
        WHERE user_id = ?
    """, (user_id,)).fetchone()

    if not row:
        return False

    if row["revive_at"] > int(time.time()):
        return False

    conn.execute("""
        UPDATE players
        SET hp = 100,
            mp = 100,
            is_dead = 0
        WHERE user_id = ?
    """, (user_id,))

    conn.execute("""
        DELETE FROM pvp_revives
        WHERE user_id = ?
    """, (user_id,))

return True

=====================================

AUTO REVIVE

=====================================

async def auto_revive_job(
context: ContextTypes.DEFAULT_TYPE
):

now = int(time.time())

with db.connect() as conn:

    expired = conn.execute("""
        SELECT user_id
        FROM pvp_revives
        WHERE revive_at <= ?
    """, (now,)).fetchall()

for row in expired:

    user_id = row["user_id"]

    if revive_player(user_id):

        try:

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "✨ REVIVAL COMPLETE\n\n"
                    "Your recovery is complete.\n"
                    "HP: 100/100\n"
                    "MP: 100/100\n\n"
                    "You can enter battles again."
                )
            )

        except Exception:

            logger.exception(
                "Could not send revival message to user %s",
                user_id
            )

=====================================

SETUP

=====================================

def setup_lifecycle(application):

init_lifecycle_db()

if application.job_queue:

    application.job_queue.run_repeating(
        auto_revive_job,
        interval=10,
        first=10
    )