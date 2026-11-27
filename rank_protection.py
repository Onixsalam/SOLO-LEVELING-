import time
import database as db


# ================= SETTINGS =================

PROTECTION_DURATION = 7 * 24 * 60 * 60
MAX_PROTECTION = 2

BASE_LOSS_POINTS = 15
BASE_WIN_POINTS = 20

STREAK_BONUSES = {
    3: 5,
    5: 10,
    7: 15,
    10: 25
}


# ================= DATABASE =================

def init_protection_db():
    with db.connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rank_protection (
                user_id INTEGER PRIMARY KEY,
                protection_count INTEGER DEFAULT 0,
                last_granted INTEGER DEFAULT 0
            )
        """)


# ================= PROTECTION =================

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
            SET protection_count = MIN(
                protection_count + ?,
                ?
            ),
            last_granted = ?
            WHERE user_id = ?
        """, (
            amount,
            MAX_PROTECTION,
            int(time.time()),
            user_id
        ))

    return True


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

        cursor = conn.execute("""
            UPDATE rank_protection
            SET protection_count = protection_count - 1
            WHERE user_id = ?
            AND protection_count > 0
        """, (user_id,))

        return cursor.rowcount == 1
# ================= RANK POINTS =================

def calculate_loss(user_id):
    """
    Returns:
        (points_to_remove, protected)
    """

    if consume_protection(user_id):
        return 0, True

    return BASE_LOSS_POINTS, False


def calculate_win_bonus(win_streak):
    bonus = 0

    for streak, points in STREAK_BONUSES.items():
        if win_streak >= streak:
            bonus = points

    return bonus


def calculate_win_points(win_streak):
    bonus = calculate_win_bonus(win_streak)

    return BASE_WIN_POINTS + bonus


# ================= PLAYER INFO =================

def protection_text(user_id):
    count = get_protection(user_id)

    return (
        "🛡️ RANK PROTECTION\n\n"
        f"Available protections: {count}/{MAX_PROTECTION}\n\n"
        "A protection charge prevents one ranked loss "
        "from removing your Rank Points.\n\n"
        "Protection is consumed only when you lose a ranked match."
    )