import time

import database as db


# =====================================
# RANK SETTINGS
# =====================================

WIN_POINTS = 20
LOSE_POINTS = 15

REVIVE_SECONDS = 300

RANKS = [
    (0, "Bronze"),
    (1000, "Silver"),
    (2000, "Gold"),
    (3000, "Platinum"),
    (4000, "Diamond"),
    (5000, "Master"),
    (6000, "Monarch")
]


# =====================================
# DATABASE
# =====================================

def init_lifecycle_db():

    with db.connect() as conn:

        conn.execute("""
        CREATE TABLE IF NOT EXISTS pvp_rankings (
            user_id INTEGER PRIMARY KEY,
            points INTEGER DEFAULT 0,
            win_streak INTEGER DEFAULT 0,
            best_streak INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES players(user_id)
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS pvp_revives (
            user_id INTEGER PRIMARY KEY,
            revive_at REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES players(user_id)
        )
        """)


# =====================================
# GET RANK
# =====================================

def get_rank(points):

    current_rank = "Bronze"

    for required, name in RANKS:

        if points >= required:
            current_rank = name

    return current_rank


# =====================================
# GET PLAYER RANK
# =====================================

def get_ranking(user_id):

    with db.connect() as conn:

        conn.execute("""
        INSERT OR IGNORE INTO pvp_rankings (user_id)
        VALUES (?)
        """, (user_id,))

        row = conn.execute("""
        SELECT *
        FROM pvp_rankings
        WHERE user_id = ?
        """, (user_id,)).fetchone()

    return row


# =====================================
# FINISH PVP
# =====================================

def finish_pvp(winner_id, loser_id):

    if winner_id == loser_id:
        return False

    current_time = time.time()

    with db.connect() as conn:

        winner = conn.execute("""
        SELECT * FROM players WHERE user_id = ?
        """, (winner_id,)).fetchone()

        loser = conn.execute("""
        SELECT * FROM players WHERE user_id = ?
        """, (loser_id,)).fetchone()

        if not winner or not loser:
            return False

        conn.execute("""
        INSERT OR IGNORE INTO pvp_rankings (user_id)
        VALUES (?), (?)
        """, (winner_id, loser_id))

        winner_rank = conn.execute("""
        SELECT * FROM pvp_rankings WHERE user_id = ?
        """, (winner_id,)).fetchone()

        loser_rank = conn.execute("""
        SELECT * FROM pvp_rankings WHERE user_id = ?
        """, (loser_id,)).fetchone()

        new_streak = winner_rank["win_streak"] + 1

        conn.execute("""
        UPDATE pvp_rankings
        SET points = points + ?,
            win_streak = ?,
            best_streak = MAX(best_streak, ?)
        WHERE user_id = ?
        """, (
            WIN_POINTS,
            new_streak,
            new_streak,
            winner_id
        ))

        conn.execute("""
        UPDATE pvp_rankings
        SET points = MAX(0, points - ?),
            win_streak = 0
        WHERE user_id = ?
        """, (LOSE_POINTS, loser_id))

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
        INSERT INTO pvp_revives (user_id, revive_at)
        VALUES (?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET revive_at = excluded.revive_at
        """, (
            loser_id,
            current_time + REVIVE_SECONDS
        ))

        return True


# =====================================
# REVIVE PLAYER
# =====================================

def revive_player(user_id):

    with db.connect() as conn:

        revive = conn.execute("""
        SELECT revive_at
        FROM pvp_revives
        WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not revive:
            return False

        if time.time() < revive["revive_at"]:
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


# =====================================
# CHECK REVIVE
# =====================================

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


# =====================================
# AUTO REVIVE
# =====================================

async def auto_revive_job(context):

    current_time = time.time()

    with db.connect() as conn:

        expired = conn.execute("""
        SELECT user_id
        FROM pvp_revives
        WHERE revive_at <= ?
        """, (current_time,)).fetchall()

    for row in expired:

        user_id = row["user_id"]

        if revive_player(user_id):

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "✨ REVIVAL COMPLETE!\n\n"
                        "زمان احیای تو به پایان رسید.\n"
                        "❤️ HP: 100%\n"
                        "🔮 MP: 100%\n\n"
                        "دوباره آماده مبارزه هستی!"
                    )
                )

            except Exception:
                pass


# =====================================
# RANK PROFILE
# =====================================

def get_rank_profile(user_id):

    ranking = get_ranking(user_id)

    points = ranking["points"]

    return {
        "points": points,
        "rank": get_rank(points),
        "win_streak": ranking["win_streak"],
        "best_streak": ranking["best_streak"]
    }


# =====================================
# SETUP
# =====================================

def setup_lifecycle(application):

    init_lifecycle_db()

    application.job_queue.run_repeating(
        auto_revive_job,
        interval=10,
        first=10,
        name="pvp_auto_revive"
    )