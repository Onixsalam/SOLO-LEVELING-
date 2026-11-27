import time
import random

import database as db


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
            PRIMARY KEY(user_id, skill_name),
            FOREIGN KEY(user_id) REFERENCES players(user_id)
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS combat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attacker_id INTEGER NOT NULL,
            defender_id INTEGER NOT NULL,
            skill_name TEXT NOT NULL,
            damage INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)


# =====================================
# GET SKILL
# =====================================

def get_skill(user_id, skill_name):

    with db.connect() as conn:

        return conn.execute("""
        SELECT *
        FROM player_skills
        WHERE user_id = ?
        AND LOWER(skill_name) = LOWER(?)
        """, (user_id, skill_name)).fetchone()


# =====================================
# COOLDOWN
# =====================================

def check_cooldown(user_id, skill_name, cooldown):

    with db.connect() as conn:

        row = conn.execute("""
        SELECT last_used
        FROM combat_cooldowns
        WHERE user_id = ?
        AND skill_name = ?
        """, (user_id, skill_name)).fetchone()

        if not row:
            return True, 0

        remaining = cooldown - (time.time() - row["last_used"])

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
        DO UPDATE SET last_used = excluded.last_used
        """, (user_id, skill_name, time.time()))


# =====================================
# DEFENSE CALCULATION
# =====================================

def calculate_defense(player):

    defense = (
        player["VIT"] * 2 +
        player["AGI"] +
        player["SEN"]
    )

    return defense


# =====================================
# DAMAGE CALCULATION
# =====================================

def calculate_damage(attacker, defender, skill):

    base_damage = skill["damage"]

    attack_power = (
        attacker["STR"] * 2 +
        attacker["INT"] * 2 +
        attacker["AGI"]
    )

    defense = calculate_defense(defender)

    raw_damage = base_damage + (attack_power * 0.5)

    final_damage = raw_damage - (defense * 0.25)

    final_damage *= random.uniform(0.90, 1.10)

    return max(1, int(final_damage))


# =====================================
# USE SKILL
# =====================================

def use_skill(attacker_id, defender_id, skill_name):

    if attacker_id == defender_id:
        return False, "نمی‌تونی به خودت حمله کنی."

    attacker = db.get_player(attacker_id)
    defender = db.get_player(defender_id)

    if not attacker or not defender:
        return False, "یکی از بازیکنان پیدا نشد."

    skill = get_skill(attacker_id, skill_name)

    if not skill:
        return False, "این مهارت رو آزاد نکردی."

    if skill["skill_type"] not in ("attack", "special"):
        return False, "این مهارت برای حمله نیست."

    if attacker["mp"] < skill["mp_cost"]:
        return False, "MP کافی نداری."

    available, remaining = check_cooldown(
        attacker_id,
        skill["skill_name"],
        skill["cooldown"]
    )

    if not available:
        return False, f"این مهارت تا {remaining} ثانیه دیگه آماده نمی‌شه."

    if attacker["hp"] <= 0 or defender["hp"] <= 0:
        return False, "یکی از بازیکنان توان ادامه مبارزه رو نداره."

    damage = calculate_damage(
        attacker,
        defender,
        skill
    )

    new_hp = max(0, defender["hp"] - damage)
    new_mp = attacker["mp"] - skill["mp_cost"]

    with db.connect() as conn:

        conn.execute("""
        UPDATE players
        SET mp = ?
        WHERE user_id = ?
        """, (new_mp, attacker_id))

        conn.execute("""
        UPDATE players
        SET hp = ?
        WHERE user_id = ?
        """, (new_hp, defender_id))

        conn.execute("""
        INSERT INTO combat_history (
            attacker_id,
            defender_id,
            skill_name,
            damage
        )
        VALUES (?, ?, ?, ?)
        """, (
            attacker_id,
            defender_id,
            skill["skill_name"],
            damage
        ))

    set_cooldown(
        attacker_id,
        skill["skill_name"]
    )

    result = {
        "attacker_id": attacker_id,
        "defender_id": defender_id,
        "skill": skill["skill_name"],
        "damage": damage,
        "defender_hp": new_hp,
        "attacker_mp": new_mp,
        "defeated": new_hp <= 0
    }

    return True, result


# =====================================
# COMBAT HISTORY
# =====================================

def get_combat_history(user_id, limit=10):

    with db.connect() as conn:

        return conn.execute("""
        SELECT *
        FROM combat_history
        WHERE attacker_id = ?
        OR defender_id = ?
        ORDER BY id DESC
        LIMIT ?
        """, (user_id, user_id, limit)).fetchall()


# =====================================
# HP RECOVERY
# =====================================

def restore_player(user_id):

    with db.connect() as conn:

        player = conn.execute("""
        SELECT hp, mp
        FROM players
        WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not player:
            return False

        conn.execute("""
        UPDATE players
        SET hp = 100,
            mp = 100
        WHERE user_id = ?
        """, (user_id,))

    return True