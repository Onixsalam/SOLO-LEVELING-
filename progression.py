import database as db


# =========================
# SKILL DATABASE
# =========================

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
            FOREIGN KEY(user_id) REFERENCES players(user_id),
            UNIQUE(user_id, skill_name)
        )
        """)


# =========================
# LEVEL SYSTEM
# =========================

def required_xp(level):

    return 100 + (level * 50)


def add_xp(user_id, amount):

    if amount <= 0:
        return None

    with db.connect() as conn:

        player = conn.execute(
            "SELECT * FROM players WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        if not player:
            return None

        xp = player["xp"] + amount
        level = player["level"]
        stat_points = player["stat_points"]

        levels_gained = 0

        while xp >= required_xp(level):

            xp -= required_xp(level)
            level += 1
            stat_points += 5
            levels_gained += 1

        conn.execute("""
        UPDATE players
        SET xp = ?,
            level = ?,
            stat_points = ?
        WHERE user_id = ?
        """, (xp, level, stat_points, user_id))

    return {
        "xp_gained": amount,
        "level": level,
        "levels_gained": levels_gained,
        "stat_points": stat_points
    }


# =========================
# STAT UPGRADE
# =========================

VALID_STATS = {
    "STR": "STR",
    "AGI": "AGI",
    "VIT": "VIT",
    "INT": "INT",
    "SEN": "SEN"
}


def upgrade_stat(user_id, stat, amount=1):

    stat = stat.upper()

    if stat not in VALID_STATS:
        return False, "ویژگی نامعتبر است."

    if not isinstance(amount, int) or amount < 1:
        return False, "مقدار نامعتبر است."

    with db.connect() as conn:

        player = conn.execute(
            "SELECT * FROM players WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        if not player:
            return False, "بازیکن پیدا نشد."

        if player["stat_points"] < amount:
            return False, "امتیاز کافی نداری."

        new_value = player[stat] + amount
        remaining = player["stat_points"] - amount

        conn.execute(f"""
        UPDATE players
        SET {stat} = ?,
            stat_points = ?
        WHERE user_id = ?
        """, (new_value, remaining, user_id))

        power = (
            player["STR"] * 3 +
            player["AGI"] * 2 +
            player["VIT"] * 2 +
            player["INT"] * 3 +
            player["SEN"] * 2
        )

        conn.execute("""
        UPDATE players
        SET power = ?
        WHERE user_id = ?
        """, (power, user_id))

    return True, f"{stat} با موفقیت {amount} واحد افزایش پیدا کرد."


# =========================
# SKILL LIST
# =========================

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


# =========================
# UNLOCK SKILLS
# =========================

def unlock_available_skills(user_id):

    with db.connect() as conn:

        player = conn.execute(
            "SELECT * FROM players WHERE user_id = ?",
            (user_id,)
        ).fetchone()

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

        skills = CLASS_SKILLS.get(class_id, [])

        unlocked = []

        for name, skill_type, damage, mp, cooldown, level in skills:

            if player["level"] < level:
                continue

            exists = conn.execute("""
            SELECT id FROM player_skills
            WHERE user_id = ? AND skill_name = ?
            """, (user_id, name)).fetchone()

            if exists:
                continue

            conn.execute("""
            INSERT INTO player_skills (
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
                level
            ))

            unlocked.append(name)

        return unlocked


# =========================
# GET PLAYER SKILLS
# =========================

def get_player_skills(user_id):

    with db.connect() as conn:

        return conn.execute("""
        SELECT *
        FROM player_skills
        WHERE user_id = ?
        ORDER BY unlocked_at ASC
        """, (user_id,)).fetchall()


# =========================
# SKILL DISPLAY
# =========================

def skills_text(user_id):

    skills = get_player_skills(user_id)

    if not skills:
        return "⚔️ هنوز هیچ مهارتی آزاد نکردی."

    text = "⚔️ YOUR SKILLS\n\n"

    for skill in skills:

        text += (
            f"🔹 {skill['skill_name']}\n"
            f"نوع: {skill['skill_type']}\n"
            f"قدرت: {skill['damage']}\n"
            f"هزینه MP: {skill['mp_cost']}\n"
            f"Cooldown: {skill['cooldown']}s\n\n"
        )

    return text