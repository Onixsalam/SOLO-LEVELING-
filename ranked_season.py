import time
import logging

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes
)

import database as db
import pvp_lifecycle as lifecycle


logger = logging.getLogger(__name__)


# ==================================================
# SETTINGS
# ==================================================

SEASON_DURATION = 30 * 24 * 60 * 60

SEASON_REWARDS = {
    "Monarch": {
        "gold": 10000,
        "crystals": 500
    },
    "Master": {
        "gold": 7000,
        "crystals": 350
    },
    "Diamond": {
        "gold": 5000,
        "crystals": 250
    },
    "Platinum": {
        "gold": 3000,
        "crystals": 150
    },
    "Gold": {
        "gold": 2000,
        "crystals": 100
    },
    "Silver": {
        "gold": 1000,
        "crystals": 50
    },
    "Bronze": {
        "gold": 500,
        "crystals": 25
    }
}


RANKS = [
    ("Monarch", 6000),
    ("Master", 5000),
    ("Diamond", 4000),
    ("Platinum", 3000),
    ("Gold", 2000),
    ("Silver", 1000),
    ("Bronze", 0)
]


# ==================================================
# DATABASE
# ==================================================

def init_season_db():

    with db.connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ranked_seasons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_number INTEGER NOT NULL,
                started_at REAL NOT NULL,
                ends_at REAL NOT NULL,
                status TEXT DEFAULT 'active'
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ranked_season_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                points INTEGER DEFAULT 0,
                rank_name TEXT,
                gold_reward INTEGER DEFAULT 0,
                crystal_reward INTEGER DEFAULT 0,
                claimed INTEGER DEFAULT 0,
                UNIQUE(season_id, user_id)
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_season_status
            ON ranked_seasons(status)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_season_results
            ON ranked_season_results(season_id, points DESC)
        """)


# ==================================================
# RANK CALCULATION
# ==================================================

def get_season_rank(points):

    points = int(points)

    for name, minimum in RANKS:

        if points >= minimum:
            return name

    return "Bronze"


# ==================================================
# CURRENT SEASON
# ==================================================

def get_current_season():

    with db.connect() as conn:

        return conn.execute("""
            SELECT *
            FROM ranked_seasons
            WHERE status = 'active'
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()


def create_season():

    now = time.time()

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        existing = conn.execute("""
            SELECT *
            FROM ranked_seasons
            WHERE status = 'active'
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

        if existing:
            return existing

        previous = conn.execute("""
            SELECT MAX(season_number) AS number
            FROM ranked_seasons
        """).fetchone()

        season_number = (
            (previous["number"] or 0) + 1
        )

        cursor = conn.execute("""
            INSERT INTO ranked_seasons (
                season_number,
                started_at,
                ends_at,
                status
            )
            VALUES (?, ?, ?, 'active')
        """, (
            season_number,
            now,
            now + SEASON_DURATION
        ))

        season_id = cursor.lastrowid

        return conn.execute("""
            SELECT *
            FROM ranked_seasons
            WHERE id = ?
        """, (season_id,)).fetchone()


# ==================================================
# SEASON REWARDS
# ==================================================

def get_reward(rank_name):

    return SEASON_REWARDS.get(
        rank_name,
        SEASON_REWARDS["Bronze"]
    )


# ==================================================
# FINISH SEASON
# ==================================================

def finish_season():

    now = time.time()

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        season = conn.execute("""
            SELECT *
            FROM ranked_seasons
            WHERE status = 'active'
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

        if not season:
            return False

        if season["ends_at"] > now:
            return False

        players = conn.execute("""
            SELECT user_id, points
            FROM pvp_rankings
            ORDER BY points DESC
        """).fetchall()

        for player in players:

            user_id = player["user_id"]
            points = int(player["points"])

            rank_name = get_season_rank(points)
            reward = get_reward(rank_name)

            gold = reward["gold"]
            crystals = reward["crystals"]

            cursor = conn.execute("""
                INSERT OR IGNORE INTO ranked_season_results (
                    season_id,
                    user_id,
                    points,
                    rank_name,
                    gold_reward,
                    crystal_reward,
                    claimed
                )
                VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (
                season["id"],
                user_id,
                points,
                rank_name,
                gold,
                crystals
            ))

            if cursor.rowcount != 1:
                continue

            player_exists = conn.execute("""
                SELECT user_id
                FROM players
                WHERE user_id = ?
            """, (user_id,)).fetchone()

            if not player_exists:
                continue

            conn.execute("""
                UPDATE players
                SET
                    gold = gold + ?,
                    crystals = crystals + ?
                WHERE user_id = ?
            """, (
                gold,
                crystals,
                user_id
            ))

        conn.execute("""
            UPDATE ranked_seasons
            SET status = 'finished'
            WHERE id = ?
              AND status = 'active'
        """, (season["id"],))

    return True
# ==================================================
# SEASON PROFILE
# ==================================================

def get_season_text():

    season = get_current_season()

    if not season:

        return (
            "🏆 RANKED SEASON\n\n"
            "فصلی فعال وجود ندارد."
        )

    remaining = max(
        0,
        int(season["ends_at"] - time.time())
    )

    days = remaining // 86400
    hours = (remaining % 86400) // 3600

    return (
        "🏆 RANKED SEASON\n\n"
        f"🌍 Season: {season['season_number']}\n"
        f"📅 Remaining: {days} روز و {hours} ساعت\n"
        f"📊 Status: {season['status']}"
    )


# ==================================================
# SEASON TOP
# ==================================================

def get_season_top(limit=10):

    season = get_current_season()

    if not season:
        return []

    with db.connect() as conn:

        return conn.execute("""
            SELECT
                r.user_id,
                r.points,
                p.name
            FROM pvp_rankings r
            LEFT JOIN players p
                ON p.user_id = r.user_id
            ORDER BY r.points DESC
            LIMIT ?
        """, (limit,)).fetchall()


# ==================================================
# SEASON COMMAND
# ==================================================

async def season_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    finished = finish_season()

    season = get_current_season()

    if not season:
        season = create_season()

    text = get_season_text()

    if finished:
        text += (
            "\n\n🎉 فصل قبلی به پایان رسید "
            "و فصل جدید شروع شد."
        )

    await update.effective_message.reply_text(text)


# ==================================================
# SEASON TOP COMMAND
# ==================================================

async def season_top_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    rows = get_season_top(10)

    if not rows:

        await update.effective_message.reply_text(
            "هنوز بازیکنی در جدول رنک ثبت نشده."
        )

        return

    lines = ["🏆 RANK LEADERBOARD\n"]

    for index, row in enumerate(rows, start=1):

        name = row["name"] or str(row["user_id"])

        rank_name = get_season_rank(
            row["points"]
        )

        lines.append(
            f"{index}. {name}\n"
            f"   🎖 {rank_name} | "
            f"⭐ {row['points']} RP"
        )

    await update.effective_message.reply_text(
        "\n\n".join(lines)
    )


# ==================================================
# SEASON AUTO CHECK
# ==================================================

async def season_check_job(
    context: ContextTypes.DEFAULT_TYPE
):

    try:

        finished = finish_season()

        if finished or not get_current_season():

            create_season()

    except Exception:

        logger.exception(
            "Season check failed."
        )


# ==================================================
# SETUP
# ==================================================

def setup_ranked_season(application):

    init_season_db()

    if not get_current_season():
        create_season()

    application.add_handler(
        CommandHandler(
            "season",
            season_command
        )
    )

    application.add_handler(
        CommandHandler(
            "top",
            season_top_command
        )
    )

    if application.job_queue:

        application.job_queue.run_repeating(
            season_check_job,
            interval=3600,
            first=60,
            name="ranked_season_check"
        )

    else:

        logger.warning(
            "JobQueue unavailable. Automatic season checks are disabled."
        )