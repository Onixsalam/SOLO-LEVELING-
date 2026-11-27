import time
import logging

import database as db


logger = logging.getLogger(__name__)


# ==================================================
# SETTINGS
# ==================================================

MAX_PROTECTION = 2

PROTECTION_DURATION = 7 * 24 * 60 * 60

BASE_WIN_POINTS = 20
BASE_LOSE_POINTS = 15

STREAK_BONUSES = {
    3: 5,
    5: 10,
    7: 15,
    10: 25
}


# ==================================================
# DATABASE
# ==================================================

def init_protection_db():

    with db.connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS rank_protection (
                user_id INTEGER PRIMARY KEY,
                protection_count INTEGER DEFAULT 0,
                last_granted REAL DEFAULT 0
            )
        """)


# ==================================================
# GET PROTECTION
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


# ==================================================
# GRANT PROTECTION
# ==================================================

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


# ==================================================
# CONSUME PROTECTION
# ==================================================

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
# POINT CALCULATIONS
# ==================================================

def calculate_streak_bonus(streak):

    streak = int(streak)

    bonus = 0

    for required, points in STREAK_BONUSES.items():

        if streak >= required:
            bonus = points

    return bonus


def calculate_win_bonus(streak):

    return calculate_streak_bonus(streak)


def calculate_win_points(streak=0):

    return (
        BASE_WIN_POINTS
        + calculate_streak_bonus(streak)
    )


def calculate_loss(user_id):

    protected = consume_protection(user_id)

    if protected:
        return 0

    return BASE_LOSE_POINTS


def calculate_loss_points(user_id):

    return calculate_loss(user_id)


# ==================================================
# PROTECTION TEXT
# ==================================================

def protection_text(user_id):

    count = get_protection(user_id)

    return (
        "🛡️ RANK PROTECTION\n\n"
        f"محافظت‌های باقی‌مانده: {count}/{MAX_PROTECTION}\n\n"
        "هر محافظت یک بار جلوی کاهش امتیاز "
        "در باخت مسابقه Ranked را می‌گیرد.\n\n"
        "حداکثر ظرفیت: 2"
    )


# ==================================================
# SETUP
# ==================================================

def setup_rank_protection():

    init_protection_db()