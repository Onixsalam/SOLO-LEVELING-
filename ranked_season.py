import time
from telegram import Update
from telegram.ext import (
CommandHandler,
ContextTypes
)

import database as db

SEASON_DURATION = 30 * 24 * 60 * 60

REWARDS = {
"Bronze": (500, 25),
"Silver": (1000, 50),
"Gold": (2000, 100),
"Platinum": (3500, 175),
"Diamond": (5000, 250),
"Master": (7500, 400),
"Monarch": (12000, 700),
}

RANKS = [
(6000, "Monarch"),
(5000, "Master"),
(4000, "Diamond"),
(3000, "Platinum"),
(2000, "Gold"),
(1000, "Silver"),
(0, "Bronze"),
]

def get_rank(points):
for minimum, rank in RANKS:
if points >= minimum:
return rank
return "Bronze"

def init_season_db():
with db.connect() as conn:
conn.execute("""
CREATE TABLE IF NOT EXISTS ranked_seasons (
id INTEGER PRIMARY KEY AUTOINCREMENT,
start_at INTEGER NOT NULL,
end_at INTEGER NOT NULL,
status TEXT DEFAULT 'active'
)
""")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS ranked_season_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            points INTEGER NOT NULL,
            rank TEXT NOT NULL,
            reward_gold INTEGER DEFAULT 0,
            reward_crystals INTEGER DEFAULT 0,
            UNIQUE(season_id, user_id)
        )
    """)

def get_current_season():
now = int(time.time())

with db.connect() as conn:
    season = conn.execute("""
        SELECT *
        FROM ranked_seasons
        WHERE status = 'active'
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    if season and season["end_at"] > now:
        return season

    return None

def create_season():
now = int(time.time())

with db.connect() as conn:
    conn.execute("""
        UPDATE ranked_seasons
        SET status = 'finished'
        WHERE status = 'active'
    """)

    cursor = conn.execute("""
        INSERT INTO ranked_seasons
        (start_at, end_at, status)
        VALUES (?, ?, 'active')
    """, (now, now + SEASON_DURATION))

    return cursor.lastrowid

def finish_season():
season = get_current_season()

if not season:
    return

now = int(time.time())

if season["end_at"] > now:
    return

with db.connect() as conn:
    players = conn.execute("""
        SELECT user_id, points
        FROM pvp_rankings
        ORDER BY points DESC
    """).fetchall()

    for player in players:
        user_id = player["user_id"]
        points = player["points"]
        rank = get_rank(points)

        gold, crystals = REWARDS[rank]

        conn.execute("""
            INSERT OR IGNORE INTO ranked_season_results
            (season_id, user_id, points, rank,
             reward_gold, reward_crystals)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            season["id"],
            user_id,
            points,
            rank,
            gold,
            crystals
        ))

        result = conn.execute("""
            SELECT changes()
        """).fetchone()[0]

        if result:
            columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(players)"
                ).fetchall()
            }

            if "gold" in columns:
                conn.execute("""
                    UPDATE players
                    SET gold = gold + ?
                    WHERE user_id = ?
                """, (gold, user_id))

            if "crystals" in columns:
                conn.execute("""
                    UPDATE players
                    SET crystals = crystals + ?
                    WHERE user_id = ?
                """, (crystals, user_id))

    conn.execute("""
        UPDATE ranked_seasons
        SET status = 'finished'
        WHERE id = ?
    """, (season["id"],))

create_season()

async def season_command(
update: Update,
context: ContextTypes.DEFAULT_TYPE
):
season = get_current_season()

if not season:
    create_season()
    season = get_current_season()

remaining = max(0, season["end_at"] - int(time.time()))

days = remaining // 86400
hours = (remaining % 86400) // 3600

await update.message.reply_text(
    "🏆 RANKED SEASON\n\n"
    f"Season: #{season['id']}\n"
    f"Days remaining: {days}\n"
    f"Hours remaining: {hours}\n\n"
    "Season duration: 30 days\n"
    "Rewards are given when the season ends."
)

async def season_top_command(
update: Update,
context: ContextTypes.DEFAULT_TYPE
):
with db.connect() as conn:
players = conn.execute("""
SELECT r.user_id, r.points, p.name
FROM pvp_rankings r
LEFT JOIN players p
ON p.user_id = r.user_id
ORDER BY r.points DESC
LIMIT 10
""").fetchall()

if not players:
    await update.message.reply_text(
        "There are no ranked players yet."
    )
    return

text = "🏆 RANKED TOP 10\n\n"

for index, player in enumerate(players, 1):
    name = player["name"] or str(player["user_id"])
    rank = get_rank(player["points"])

    text += (
        f"{index}. {name}\n"
        f"   {rank} | {player['points']} RP\n\n"
    )

await update.message.reply_text(text)

async def season_check_job(context):
finish_season()

def setup_ranked_season(application):
init_season_db()

if not get_current_season():
    create_season()

application.add_handler(
    CommandHandler("season", season_command)
)

application.add_handler(
    CommandHandler("top", season_top_command)
)

application.job_queue.run_repeating(
    season_check_job,
    interval=3600,
    first=60
)