import logging

import database as db
import config


logger = logging.getLogger(__name__)


# ==================================================
# SETTINGS
# ==================================================

STAT_POINTS_PER_LEVEL = getattr(
    config,
    "STAT_POINTS_PER_LEVEL",
    5
)

MAX_LEVEL = getattr(
    config,
    "MAX_LEVEL",
    100
)


# ==================================================
# SKILL DATABASE
# ==================================================

def init_progression_db():

    with db.connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS player_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                skill_name TEXT NOT NULL,
                skill_type TEXT NOT NULL,
                damage INTEGER DEFAULT 0,
                mp_cost INTEGER DEFAULT 0,
                cooldown INTEGER DEFAULT 0,
                unlocked_at INTEGER DEFAULT 1,
                FOREIGN KEY(user_id)
                    REFERENCES players(user_id)
                    ON DELETE CASCADE,
                UNIQUE(user_id, skill_name)
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_player_skills_user
            ON player_skills(user_id)
        """)


# ==================================================
# LEVEL SYSTEM
# ==================================================

def required_xp(level):

    level = max(1, int(level))

    return 100 + (level * 50)


def add_xp(user_id, amount):

    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return None

    if amount <= 0:
        return None

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        player = conn.execute("""
            SELECT xp, level, stat_points
            FROM players
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not player:
            return None

        xp = int(player["xp"] or 0) + amount
        level = int(player["level"] or 1)
        stat_points = int(player["stat_points"] or 0)

        old_level = level
        levels_gained = 0

        while (
            xp >= required_xp(level)
            and level < MAX_LEVEL
        ):

            xp -= required_xp(level)
            level += 1

            stat_points += STAT_POINTS_PER_LEVEL
            levels_gained += 1

        # در سطح نهایی XP بیشتر از مقدار موردنیاز ذخیره نمی‌شود.
        if level >= MAX_LEVEL:
            xp = 0

        conn.execute("""
            UPDATE players
            SET
                xp = ?,
                level = ?,
                stat_points = ?
            WHERE user_id = ?
        """, (
            xp,
            level,
            stat_points,
            user_id
        ))

    # بعد از ثبت XP، مهارت‌های قابل آزادسازی بررسی می‌شوند.
    newly_unlocked = unlock_available_skills(user_id)

    return {
        "xp_gained": amount,
        "level": level,
        "old_level": old_level,
        "levels_gained": levels_gained,
        "stat_points": stat_points,
        "new_skills": newly_unlocked
    }


# ==================================================
# STAT SYSTEM
# ==================================================

VALID_STATS = {
    "STR": "STR",
    "AGI": "AGI",
    "VIT": "VIT",
    "INT": "INT",
    "SEN": "SEN"
}


def calculate_power(strength, agility, vitality, intelligence, sense):

    return (
        int(strength) * 3
        + int(agility) * 2
        + int(vitality) * 2
        + int(intelligence) * 3
        + int(sense) * 2
    )


def upgrade_stat(user_id, stat, amount=1):

    if not isinstance(stat, str):
        return False, "ویژگی نامعتبر است."

    stat = stat.upper()

    if stat not in VALID_STATS:
        return False, "ویژگی نامعتبر است."

    if not isinstance(amount, int) or amount < 1:
        return False, "مقدار نامعتبر است."

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        player = conn.execute("""
            SELECT *
            FROM players
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not player:
            return False, "بازیکن پیدا نشد."

        available_points = int(
            player["stat_points"] or 0
        )

        if available_points < amount:
            return False, "امتیاز کافی نداری."

        current_value = int(
            player[stat] or 0
        )

        new_value = current_value + amount
        remaining_points = available_points - amount

        conn.execute(f"""
            UPDATE players
            SET
                {stat} = ?,
                stat_points = ?
            WHERE user_id = ?
        """, (
            new_value,
            remaining_points,
            user_id
        ))

        # محاسبه قدرت با مقدار جدید ویژگی‌ها
        values = {
            "STR": int(player["STR"] or 0),
            "AGI": int(player["AGI"] or 0),
            "VIT": int(player["VIT"] or 0),
            "INT": int(player["INT"] or 0),
            "SEN": int(player["SEN"] or 0)
        }

        values[stat] = new_value

        power = calculate_power(
            values["STR"],
            values["AGI"],
            values["VIT"],
            values["INT"],
            values["SEN"]
        )

        conn.execute("""
            UPDATE players
            SET power = ?
            WHERE user_id = ?
        """, (
            power,
            user_id
        ))

    return (
        True,
        f"{stat} با موفقیت {amount} واحد افزایش پیدا کرد."
    )


# ==================================================
# CLASS SKILLS
# ==================================================

CLASS_SKILLS = {

    "assassin": [
        ("Shadow Slash", "attack", 30, 10, 3, 1),
        ("Phantom Step", "movement", 0, 15, 5, 3),
        ("Death Mark", "special", 50, 25, 8, 5)
    ],

    "fighter": [
        ("Heavy Strike", "attack", 35, 10, 3, 1),
        ("Combat Rush", "movement", 0, 15, 5, 3),
        ("Fury Breaker", "special", 55, 25, 8, 5)
    ],

    "tank": [
        ("Shield Bash", "attack", 25, 10, 3, 1),
        ("Iron Wall", "defense", 0, 15, 5, 3),
        ("Guardian Roar", "special", 40, 25, 8, 5)
    ],

    "mage": [
        ("Dark Bolt", "attack", 35, 15, 3, 1),
        ("Mana Shield", "defense", 0, 20, 5, 3),
        ("Arcane Burst", "special", 60, 35, 8, 5)
    ],

    "ranger": [
        ("Piercing Shot", "attack", 35, 10, 3, 1),
        ("Quick Escape", "movement", 0, 15, 5, 3),
        ("Storm Arrow", "special", 55, 25, 8, 5)
    ],

    "healer": [
        ("Light Strike", "attack", 20, 10, 3, 1),
        ("Healing Light", "defense", 0, 20, 5, 3),
        ("Divine Blessing", "special", 45, 30, 8, 5)
    ],

    "necromancer": [
        ("Shadow Strike", "attack", 35, 15, 3, 1),
        ("Shadow Guard", "defense", 0, 20, 5, 3),
        ("Death Authority", "special", 65, 35, 8, 5)
    ]
}
# ==================================================
# UNLOCK AVAILABLE SKILLS
# ==================================================

def unlock_available_skills(user_id):

    unlocked = []

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        player = conn.execute("""
            SELECT level
            FROM players
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not player:
            return []

        awakening = conn.execute("""
            SELECT class_id
            FROM awakenings
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not awakening:
            return []

        class_id = awakening["class_id"]

        skills = CLASS_SKILLS.get(
            class_id,
            []
        )

        level = int(player["level"] or 1)

        for (
            name,
            skill_type,
            damage,
            mp,
            cooldown,
            required_level
        ) in skills:

            if level < required_level:
                continue

            cursor = conn.execute("""
                INSERT OR IGNORE INTO player_skills (
                    user_id,
                    skill_name,
                    skill_type,
                    damage,
                    mp_cost,
                    cooldown,
                    unlocked_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                name,
                skill_type,
                damage,
                mp,
                cooldown,
                required_level
            ))

            if cursor.rowcount == 1:
                unlocked.append(name)

    return unlocked


# ==================================================
# GET PLAYER SKILLS
# ==================================================

def get_player_skills(user_id):

    with db.connect() as conn:

        return conn.execute("""
            SELECT *
            FROM player_skills
            WHERE user_id = ?
            ORDER BY unlocked_at ASC, id ASC
        """, (user_id,)).fetchall()


# ==================================================
# CHECK SKILL OWNERSHIP
# ==================================================

def has_player_skill(user_id, skill_name):

    with db.connect() as conn:

        result = conn.execute("""
            SELECT id
            FROM player_skills
            WHERE user_id = ?
              AND skill_name = ?
        """, (
            user_id,
            skill_name
        )).fetchone()

    return result is not None


# ==================================================
# SKILL DISPLAY
# ==================================================

def skills_text(user_id):

    skills = get_player_skills(user_id)

    if not skills:

        return (
            "⚔️ YOUR SKILLS\n\n"
            "هنوز هیچ مهارتی آزاد نکردی.\n"
            "با افزایش Level مهارت‌های جدید دریافت می‌کنی."
        )

    lines = [
        "⚔️ YOUR SKILLS",
        ""
    ]

    for skill in skills:

        lines.append(
            f"🔹 {skill['skill_name']}\n"
            f"نوع: {skill['skill_type']}\n"
            f"قدرت: {skill['damage']}\n"
            f"هزینه MP: {skill['mp_cost']}\n"
            f"Cooldown: {skill['cooldown']}s\n"
        )

    return "\n".join(lines)


# ==================================================
# PLAYER PROGRESSION INFO
# ==================================================

def get_progression_info(user_id):

    with db.connect() as conn:

        player = conn.execute("""
            SELECT
                level,
                xp,
                stat_points,
                STR,
                AGI,
                VIT,
                INT,
                SEN,
                power
            FROM players
            WHERE user_id = ?
        """, (user_id,)).fetchone()

    if not player:
        return None

    level = int(player["level"] or 1)

    return {
        "level": level,
        "xp": int(player["xp"] or 0),
        "required_xp": required_xp(level),
        "stat_points": int(player["stat_points"] or 0),
        "STR": int(player["STR"] or 0),
        "AGI": int(player["AGI"] or 0),
        "VIT": int(player["VIT"] or 0),
        "INT": int(player["INT"] or 0),
        "SEN": int(player["SEN"] or 0),
        "power": int(player["power"] or 0)
    }