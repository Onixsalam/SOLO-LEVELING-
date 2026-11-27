import time
import random
import logging

import database as db


logger = logging.getLogger(__name__)


# =====================================
# COMBAT DATABASE
# =====================================

def init_combat_db():

    with db.connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS combat_cooldowns (
                user_id INTEGER NOT NULL,
                skill_name TEXT NOT NULL,
                last_used REAL NOT NULL,
                PRIMARY KEY (user_id, skill_name),
                FOREIGN KEY (user_id)
                    REFERENCES players(user_id)
                    ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS combat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attacker_id INTEGER NOT NULL,
                defender_id INTEGER NOT NULL,
                skill_name TEXT NOT NULL,
                damage INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_combat_attacker
            ON combat_history(attacker_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_combat_defender
            ON combat_history(defender_id)
        """)


# =====================================
# RESULT HELPERS
# =====================================

def success_result(**kwargs):

    result = {
        "success": True,
        "message": "حمله با موفقیت انجام شد."
    }

    result.update(kwargs)

    return result


def error_result(message):

    return {
        "success": False,
        "message": message,
        "damage": 0
    }


# =====================================
# GET SKILL
# =====================================

def get_skill(user_id, skill_name):

    if not skill_name:
        return None

    with db.connect() as conn:

        return conn.execute("""
            SELECT *
            FROM player_skills
            WHERE user_id = ?
            AND LOWER(skill_name) = LOWER(?)
            LIMIT 1
        """, (
            user_id,
            skill_name.strip()
        )).fetchone()


# =====================================
# COOLDOWN
# =====================================

def check_cooldown(user_id, skill_name, cooldown):

    with db.connect() as conn:

        row = conn.execute("""
            SELECT last_used
            FROM combat_cooldowns
            WHERE user_id = ?
            AND LOWER(skill_name) = LOWER(?)
        """, (
            user_id,
            skill_name
        )).fetchone()

    if not row:
        return True, 0

    remaining = cooldown - (
        time.time() - row["last_used"]
    )

    if remaining > 0:
        return False, int(remaining) + 1

    return True, 0


def set_cooldown(user_id, skill_name):

    with db.connect() as conn:

        conn.execute("""
            INSERT INTO combat_cooldowns (
                user_id,
                skill_name,
                last_used
            )
            VALUES (?, ?, ?)

            ON CONFLICT(user_id, skill_name)
            DO UPDATE SET
                last_used = excluded.last_used
        """, (
            user_id,
            skill_name,
            time.time()
        ))


# =====================================
# PLAYER STATS
# =====================================

def get_stat(player, upper_name, lower_name):

    value = player[upper_name]

    if value is None:
        value = player[lower_name]

    return max(0, int(value or 0))


# =====================================
# DEFENSE
# =====================================

def calculate_defense(player):

    vitality = get_stat(
        player,
        "VIT",
        "vitality"
    )

    agility = get_stat(
        player,
        "AGI",
        "agility"
    )

    sense = get_stat(
        player,
        "SEN",
        "sense"
    )

    defense = (
        vitality * 2
        + agility
        + sense
    )

    return max(0, defense)


# =====================================
# DAMAGE
# =====================================

def calculate_damage(attacker, defender, skill):

    base_damage = max(
        0,
        int(skill["damage"] or 0)
    )

    strength = get_stat(
        attacker,
        "STR",
        "strength"
    )

    intelligence = get_stat(
        attacker,
        "INT",
        "intelligence"
    )

    agility = get_stat(
        attacker,
        "AGI",
        "agility"
    )

    attack_power = (
        strength * 2
        + intelligence * 2
        + agility
    )

    defense = calculate_defense(defender)

    raw_damage = base_damage + (
        attack_power * 0.5
    )

    final_damage = raw_damage - (
        defense * 0.25
    )

    final_damage *= random.uniform(
        0.90,
        1.10
    )

    return max(
        1,
        int(final_damage)
    )


# =====================================
# USE SKILL
# =====================================

def use_skill(
    attacker_id,
    defender_id,
    skill_name
):

    if attacker_id == defender_id:

        return error_result(
            "نمی‌توانی به خودت حمله کنی."
        )

    if not skill_name or len(skill_name) > 60:

        return error_result(
            "نام مهارت معتبر نیست."
        )

    skill_name = skill_name.strip()

    if not skill_name:

        return error_result(
            "نام مهارت معتبر نیست."
        )

    try:

        with db.connect() as conn:

            conn.execute("BEGIN IMMEDIATE")

            attacker = conn.execute("""
                SELECT *
                FROM players
                WHERE user_id = ?
            """, (attacker_id,)).fetchone()

            defender = conn.execute("""
                SELECT *
                FROM players
                WHERE user_id = ?
            """, (defender_id,)).fetchone()

            if not attacker or not defender:

                return error_result(
                    "یکی از بازیکنان پیدا نشد."
                )

            if attacker["is_dead"] or attacker["hp"] <= 0:

                return error_result(
                    "شخصیت مهاجم در وضعیت مرگ قرار دارد."
                )

            if defender["is_dead"] or defender["hp"] <= 0:

                return error_result(
                    "این بازیکن توان ادامه مبارزه را ندارد."
                )

            # فقط مهارت متعلق به مهاجم قابل استفاده است.
            skill = conn.execute("""
                SELECT *
                FROM player_skills
                WHERE user_id = ?
                AND LOWER(skill_name) = LOWER(?)
                LIMIT 1
            """, (
                attacker_id,
                skill_name
            )).fetchone()

            if not skill:

                return error_result(
                    "این مهارت را آزاد نکرده‌ای."
                )

            skill_type = (
                skill["skill_type"] or ""
            ).lower()

            if skill_type not in (
                "attack",
                "special"
            ):

                return error_result(
                    "این مهارت برای حمله نیست."
                )

            mp_cost = max(
                0,
                int(skill["mp_cost"] or 0)
            )

            cooldown = max(
                0,
                int(skill["cooldown"] or 0)
            )

            if attacker["mp"] < mp_cost:

                return error_result(
                    "MP کافی نداری."
                )

            # بررسی زمان استفاده قبلی
            cooldown_row = conn.execute("""
                SELECT last_used
                FROM combat_cooldowns
                WHERE user_id = ?
                AND LOWER(skill_name) = LOWER(?)
            """, (
                attacker_id,
                skill["skill_name"]
            )).fetchone()

            now = time.time()

            if cooldown_row:

                remaining = cooldown - (
                    now - cooldown_row["last_used"]
                )

                if remaining > 0:

                    return error_result(
                        f"این مهارت تا "
                        f"{int(remaining) + 1} ثانیه دیگر "
                        f"آماده نمی‌شود."
                    )

            # محاسبه آسیب
            damage = calculate_damage(
                attacker,
                defender,
                skill
            )

            new_hp = max(
                0,
                defender["hp"] - damage
            )

            new_mp = max(
                0,
                attacker["mp"] - mp_cost
            )

            # ثبت کاهش مانا
            conn.execute("""
                UPDATE players
                SET mp = ?
                WHERE user_id = ?
            """, (
                new_mp,
                attacker_id
            ))

            # ثبت کاهش سلامتی
            conn.execute("""
                UPDATE players
                SET hp = ?
                WHERE user_id = ?
            """, (
                new_hp,
                defender_id
            ))

            # ثبت زمان استفاده مهارت
            conn.execute("""
                INSERT INTO combat_cooldowns (
                    user_id,
                    skill_name,
                    last_used
                )
                VALUES (?, ?, ?)

                ON CONFLICT(user_id, skill_name)
                DO UPDATE SET
                    last_used = excluded.last_used
            """, (
                attacker_id,
                skill["skill_name"],
                now
            ))

            # ثبت تاریخچه
            conn.execute("""
                INSERT INTO combat_history (
                    attacker_id,
                    defender_id,
                    skill_name,
                    damage,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                attacker_id,
                defender_id,
                skill["skill_name"],
                damage,
                int(now)
            ))
            # نتیجه نهایی
            defeated = new_hp <= 0

            return success_result(
                attacker_id=attacker_id,
                defender_id=defender_id,
                skill=skill["skill_name"],
                damage=damage,
                hp=new_hp,
                defender_hp=new_hp,
                mp=new_mp,
                attacker_mp=new_mp,
                defeated=defeated
            )

    except Exception:

        logger.exception(
            "Combat error: attacker=%s defender=%s",
            attacker_id,
            defender_id
        )

        return error_result(
            "هنگام اجرای مبارزه خطایی رخ داد."
        )


# =====================================
# COMBAT HISTORY
# =====================================

def get_combat_history(user_id, limit=10):

    limit = max(
        1,
        min(int(limit), 100)
    )

    with db.connect() as conn:

        return conn.execute("""
            SELECT *
            FROM combat_history
            WHERE attacker_id = ?
            OR defender_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (
            user_id,
            user_id,
            limit
        )).fetchall()


# =====================================
# RESTORE PLAYER
# =====================================

def restore_player(user_id):

    with db.connect() as conn:

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

    return True