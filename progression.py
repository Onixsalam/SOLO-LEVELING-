import time
import logging

import database as db


logger = logging.getLogger(__name__)


# =====================================
# SETTINGS
# =====================================

MAX_LEVEL = 100
STAT_POINTS_PER_LEVEL = 5

STAT_COLUMNS = {
    "STR": "strength",
    "AGI": "agility",
    "VIT": "vitality",
    "INT": "intelligence",
    "SEN": "sense"
}


# =====================================
# DATABASE
# =====================================

def init_progression_db():

    with db.connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS player_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                skill_name TEXT NOT NULL,
                skill_type TEXT DEFAULT 'attack',
                damage INTEGER DEFAULT 0,
                mp_cost INTEGER DEFAULT 0,
                cooldown INTEGER DEFAULT 0,
                unlocked_at REAL DEFAULT 0,
                UNIQUE(user_id, skill_name),
                FOREIGN KEY(user_id)
                    REFERENCES players(user_id)
                    ON DELETE CASCADE
            )
        """)

        # مهاجرت دیتابیس‌های قدیمی
        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(player_skills)"
            ).fetchall()
        }

        if "unlocked_at" not in columns:
            conn.execute("""
                ALTER TABLE player_skills
                ADD COLUMN unlocked_at REAL DEFAULT 0
            """)

        if "skill_type" not in columns:
            conn.execute("""
                ALTER TABLE player_skills
                ADD COLUMN skill_type TEXT DEFAULT 'attack'
            """)

        if "damage" not in columns:
            conn.execute("""
                ALTER TABLE player_skills
                ADD COLUMN damage INTEGER DEFAULT 0
            """)

        if "mp_cost" not in columns:
            conn.execute("""
                ALTER TABLE player_skills
                ADD COLUMN mp_cost INTEGER DEFAULT 0
            """)

        if "cooldown" not in columns:
            conn.execute("""
                ALTER TABLE player_skills
                ADD COLUMN cooldown INTEGER DEFAULT 0
            """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_player_skills_user
            ON player_skills(user_id)
        """)


# =====================================
# XP
# =====================================

def required_xp(level):

    level = max(1, int(level))

    return 100 + (level * 50)


def get_progression_info(user_id):

    with db.connect() as conn:

        player = conn.execute("""
            SELECT *
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
        "power": int(player["power"] or 0),
        "STR": int(player["STR"] or 0),
        "AGI": int(player["AGI"] or 0),
        "VIT": int(player["VIT"] or 0),
        "INT": int(player["INT"] or 0),
        "SEN": int(player["SEN"] or 0)
    }


# =====================================
# ADD XP
# =====================================

def add_xp(user_id, amount):

    amount = int(amount)

    if amount <= 0:
        return {
            "success": False,
            "message": "مقدار XP باید بیشتر از صفر باشد."
        }

    try:

        with db.connect() as conn:

            conn.execute("BEGIN IMMEDIATE")

            player = conn.execute("""
                SELECT level, xp, stat_points
                FROM players
                WHERE user_id = ?
            """, (user_id,)).fetchone()

            if not player:
                return {
                    "success": False,
                    "message": "بازیکن پیدا نشد."
                }

            level = int(player["level"] or 1)
            xp = int(player["xp"] or 0)
            points = int(player["stat_points"] or 0)

            if level >= MAX_LEVEL:

                return {
                    "success": True,
                    "level": level,
                    "xp": 0,
                    "levels_gained": 0,
                    "stat_points_gained": 0,
                    "message": "به حداکثر Level رسیده‌ای."
                }

            xp += amount
            levels_gained = 0

            while level < MAX_LEVEL:

                needed = required_xp(level)

                if xp < needed:
                    break

                xp -= needed
                level += 1
                levels_gained += 1

            if level >= MAX_LEVEL:
                xp = 0

            points_gained = (
                levels_gained * STAT_POINTS_PER_LEVEL
            )

            conn.execute("""
                UPDATE players
                SET level = ?,
                    xp = ?,
                    stat_points = stat_points + ?
                WHERE user_id = ?
            """, (
                level,
                xp,
                points_gained,
                user_id
            ))

        if levels_gained > 0:
            unlock_available_skills(user_id)

        return {
            "success": True,
            "level": level,
            "xp": xp,
            "levels_gained": levels_gained,
            "stat_points_gained": points_gained,
            "message": (
                f"{levels_gained} Level افزایش پیدا کردی!"
                if levels_gained
                else "XP دریافت شد."
            )
        }

    except Exception:

        logger.exception("XP update failed")

        return {
            "success": False,
            "message": "خطا در ثبت XP."
        }


# =====================================
# STAT UPGRADE
# =====================================

def upgrade_stat(user_id, stat_name):

    stat_name = str(stat_name).upper()

    if stat_name not in STAT_COLUMNS:

        return False, "ویژگی انتخاب‌شده معتبر نیست."

    lower_name = STAT_COLUMNS[stat_name]

    try:

        with db.connect() as conn:

            conn.execute("BEGIN IMMEDIATE")

            player = conn.execute("""
                SELECT *
                FROM players
                WHERE user_id = ?
            """, (user_id,)).fetchone()

            if not player:
                return False, "بازیکن پیدا نشد."

            points = int(player["stat_points"] or 0)

            if points <= 0:
                return False, "امتیاز ارتقای ویژگی نداری."

            current = int(
                player[stat_name]
                if player[stat_name] is not None
                else player[lower_name] or 0
            )

            new_value = current + 1

            conn.execute(f"""
                UPDATE players
                SET {stat_name} = ?,
                    stat_points = stat_points - 1
                WHERE user_id = ?
            """, (
                new_value,
                user_id
            ))

            # محاسبه قدرت کلی
            stats = conn.execute("""
                SELECT STR, AGI, VIT, INT, SEN
                FROM players
                WHERE user_id = ?
            """, (user_id,)).fetchone()

            power = (
                int(stats["STR"] or 0) * 3
                + int(stats["AGI"] or 0) * 2
                + int(stats["VIT"] or 0) * 2
                + int(stats["INT"] or 0) * 3
                + int(stats["SEN"] or 0) * 2
            )

            conn.execute("""
                UPDATE players
                SET power = ?
                WHERE user_id = ?
            """, (
                power,
                user_id
            ))

        return True, (
            f"ویژگی {stat_name} به {new_value} افزایش یافت."
        )

    except Exception:

        logger.exception("Stat upgrade failed")

        return False, "خطا در ارتقای ویژگی."


# =====================================
# CLASS SKILLS
# =====================================

CLASS_SKILLS = {

    "assassin": [
        {
            "level": 1,
            "name": "Shadow Strike",
            "type": "attack",
            "damage": 25,
            "mp": 5,
            "cooldown": 5
        },
        {
            "level": 3,
            "name": "Silent Step",
            "type": "movement",
            "damage": 0,
            "mp": 10,
            "cooldown": 15
        },
        {
            "level": 5,
            "name": "Assassin's Mark",
            "type": "special",
            "damage": 55,
            "mp": 20,
            "cooldown": 30
        }
    ],

    "fighter": [
        {
            "level": 1,
            "name": "Heavy Strike",
            "type": "attack",
            "damage": 30,
            "mp": 5,
            "cooldown": 5
        },
        {
            "level": 3,
            "name": "Power Break",
            "type": "attack",
            "damage": 45,
            "mp": 12,
            "cooldown": 15
        },
        {
            "level": 5,
            "name": "Warrior's Fury",
            "type": "special",
            "damage": 65,
            "mp": 25,
            "cooldown": 30
        }
    ],

    "tank": [
        {
            "level": 1,
            "name": "Shield Bash",
            "type": "attack",
            "damage": 20,
            "mp": 5,
            "cooldown": 5
        },
        {
            "level": 3,
            "name": "Iron Guard",
            "type": "defense",
            "damage": 0,
            "mp": 12,
            "cooldown": 15
        },
        {
            "level": 5,
            "name": "Fortress Breaker",
            "type": "special",
            "damage": 60,
            "mp": 25,
            "cooldown": 30
        }
    ],

    "mage": [
        {
            "level": 1,
            "name": "Arcane Bolt",
            "type": "attack",
            "damage": 30,
            "mp": 8,
            "cooldown": 5
        },
        {
            "level": 3,
            "name": "Mana Burst",
            "type": "attack",
            "damage": 45,
            "mp": 15,
            "cooldown": 15
        },
        {
            "level": 5,
            "name": "Arcane Explosion",
            "type": "special",
            "damage": 70,
            "mp": 30,
            "cooldown": 35
        }
    ],

    "ranger": [
        {
            "level": 1,
            "name": "Quick Shot",
            "type": "attack",
            "damage": 25,
            "mp": 5,
            "cooldown": 5
        },
        {
            "level": 3,
            "name": "Piercing Arrow",
            "type": "attack",
            "damage": 45,
            "mp": 12,
            "cooldown": 15
        },
        {
            "level": 5,
            "name": "Rain of Arrows",
            "type": "special",
            "damage": 65,
            "mp": 25,
            "cooldown": 30
        }
    ],

    "healer": [
        {
            "level": 1,
            "name": "Holy Bolt",
            "type": "attack",
            "damage": 20,
            "mp": 5,
            "cooldown": 5
        },
        {
            "level": 3,
            "name": "Healing Light",
            "type": "support",
            "damage": 0,
            "mp": 15,
            "cooldown": 20
        },
        {
            "level": 5,
            "name": "Divine Judgment",
            "type": "special",
            "damage": 60,
            "mp": 30,
            "cooldown": 35
        }
    ],

    "necromancer": [
        {
            "level": 1,
            "name": "Dark Bolt",
            "type": "attack",
            "damage": 30,
            "mp": 8,
            "cooldown": 5
        },
        {
            "level": 3,
            "name": "Shadow Drain",
            "type": "attack",
            "damage": 45,
            "mp": 15,
            "cooldown": 15
        },
        {
            "level": 5,
            "name": "Death's Call",
            "type": "special",
            "damage": 75,
            "mp": 30,
            "cooldown": 35
        }
    ]
}
# =====================================
# GET PLAYER CLASS
# =====================================

def get_player_class(user_id):

    with db.connect() as conn:

        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(awakenings)"
            ).fetchall()
        }

        if not columns:
            return None

        if "class_name" not in columns:
            return None

        row = conn.execute("""
            SELECT class_name
            FROM awakenings
            WHERE user_id = ?
            LIMIT 1
        """, (user_id,)).fetchone()

    if not row:
        return None

    return str(row["class_name"]).lower()


# =====================================
# UNLOCK SKILL
# =====================================

def unlock_skill(user_id, skill):

    with db.connect() as conn:

        conn.execute("""
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
            skill["name"],
            skill["type"],
            skill["damage"],
            skill["mp"],
            skill["cooldown"],
            time.time()
        ))

        row = conn.execute("""
            SELECT id
            FROM player_skills
            WHERE user_id = ?
            AND skill_name = ?
        """, (
            user_id,
            skill["name"]
        )).fetchone()

    return row is not None


# =====================================
# UNLOCK AVAILABLE SKILLS
# =====================================

def unlock_available_skills(user_id):

    player = db.get_player(user_id)

    if not player:
        return []

    player_class = get_player_class(user_id)

    if not player_class:
        return []

    skills = CLASS_SKILLS.get(
        player_class,
        []
    )

    level = int(player["level"] or 1)

    unlocked = []

    for skill in skills:

        if level < skill["level"]:
            continue

        if unlock_skill(user_id, skill):
            unlocked.append(skill["name"])

    return unlocked


# =====================================
# GET PLAYER SKILLS
# =====================================

def get_player_skills(user_id):

    with db.connect() as conn:

        return conn.execute("""
            SELECT *
            FROM player_skills
            WHERE user_id = ?
            ORDER BY unlocked_at ASC
        """, (user_id,)).fetchall()


# =====================================
# CHECK SKILL
# =====================================

def has_player_skill(user_id, skill_name):

    with db.connect() as conn:

        row = conn.execute("""
            SELECT id
            FROM player_skills
            WHERE user_id = ?
            AND LOWER(skill_name) = LOWER(?)
            LIMIT 1
        """, (
            user_id,
            skill_name
        )).fetchone()

    return row is not None


# =====================================
# SKILLS TEXT
# =====================================

def skills_text(user_id):

    skills = get_player_skills(user_id)

    if not skills:

        return (
            "⚔️ هنوز هیچ مهارتی آزاد نکرده‌ای."
        )

    text = "⚔️ مهارت‌های تو\n\n"

    for skill in skills:

        text += (
            f"🔹 {skill['skill_name']}\n"
            f"نوع: {skill['skill_type']}\n"
            f"آسیب: {skill['damage']}\n"
            f"هزینه MP: {skill['mp_cost']}\n"
            f"Cooldown: {skill['cooldown']} ثانیه\n\n"
        )

    return text