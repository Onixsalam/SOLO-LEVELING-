import sqlite3
import json
from config import DATABASE_NAME, START_GOLD, START_CRYSTALS


def connect():
    db = sqlite3.connect(DATABASE_NAME)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with connect() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            name TEXT DEFAULT '',
            level INTEGER DEFAULT 1,
            xp INTEGER DEFAULT 0,
            gold INTEGER DEFAULT 500,
            crystals INTEGER DEFAULT 50,
            rank TEXT DEFAULT 'E',
            hp INTEGER DEFAULT 100,
            max_hp INTEGER DEFAULT 100,
            mp INTEGER DEFAULT 50,
            max_mp INTEGER DEFAULT 50,
            strength INTEGER DEFAULT 5,
            agility INTEGER DEFAULT 5,
            vitality INTEGER DEFAULT 5,
            intelligence INTEGER DEFAULT 5,
            sense INTEGER DEFAULT 5,
            stat_points INTEGER DEFAULT 0,
            power INTEGER DEFAULT 25,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            kills INTEGER DEFAULT 0,
            deaths INTEGER DEFAULT 0,
            is_dead INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            item_type TEXT DEFAULT 'item',
            quantity INTEGER DEFAULT 1
        )
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            skill_name TEXT NOT NULL,
            damage INTEGER DEFAULT 10,
            skill_type TEXT DEFAULT 'attack'
        )
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS shadows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            shadow_name TEXT NOT NULL,
            shadow_rank TEXT DEFAULT 'E',
            level INTEGER DEFAULT 1,
            loyalty INTEGER DEFAULT 50
        )
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS titles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title_name TEXT NOT NULL,
            active INTEGER DEFAULT 0
        )
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS monsters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            monster_name TEXT NOT NULL,
            quantity INTEGER DEFAULT 1
        )
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS battle_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attacker_id INTEGER,
            defender_id INTEGER,
            damage INTEGER,
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS world_boss (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            boss_name TEXT,
            hp INTEGER,
            max_hp INTEGER,
            active INTEGER DEFAULT 0
        )
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS world_boss_damage (
            user_id INTEGER PRIMARY KEY,
            damage INTEGER DEFAULT 0
        )
        """)

        db.commit()


def get_player(user_id):
    with connect() as db:
        return db.execute(
            "SELECT * FROM players WHERE user_id = ?",
            (user_id,)
        ).fetchone()


def register_player(user_id, username, name):
    if get_player(user_id):
        return False

    with connect() as db:
        db.execute("""
        INSERT INTO players (
            user_id, username, name, gold, crystals
        )
        VALUES (?, ?, ?, ?, ?)
        """, (
            user_id,
            username or "",
            name or "Hunter",
            START_GOLD,
            START_CRYSTALS
        ))

        db.execute("""
        INSERT INTO skills (user_id, skill_name, damage, skill_type)
        VALUES (?, ?, ?, ?)
        """, (user_id, "Shadow Strike", 15, "attack"))

        db.commit()

    return True


def update_player(user_id, **values):
    allowed = {
        "username", "name", "level", "xp", "gold", "crystals",
        "rank", "hp", "max_hp", "mp", "max_mp",
        "strength", "agility", "vitality", "intelligence",
        "sense", "stat_points", "power", "wins", "losses",
        "kills", "deaths", "is_dead"
    }

    values = {
        key: value
        for key, value in values.items()
        if key in allowed
    }

    if not values:
        return

    columns = ", ".join(f"{key} = ?" for key in values)
    params = list(values.values()) + [user_id]

    with connect() as db:
        db.execute(
            f"UPDATE players SET {columns} WHERE user_id = ?",
            params
        )
        db.commit()


def add_item(user_id, item_name, item_type="item", quantity=1):
    with connect() as db:
        row = db.execute("""
        SELECT id, quantity FROM inventory
        WHERE user_id = ? AND item_name = ?
        """, (user_id, item_name)).fetchone()

        if row:
            db.execute("""
            UPDATE inventory SET quantity = quantity + ?
            WHERE id = ?
            """, (quantity, row["id"]))
        else:
            db.execute("""
            INSERT INTO inventory
            (user_id, item_name, item_type, quantity)
            VALUES (?, ?, ?, ?)
            """, (user_id, item_name, item_type, quantity))

        db.commit()


def get_inventory(user_id):
    with connect() as db:
        return db.execute("""
        SELECT * FROM inventory
        WHERE user_id = ? AND quantity > 0
        ORDER BY item_type, item_name
        """, (user_id,)).fetchall()


def get_skills(user_id):
    with connect() as db:
        return db.execute("""
        SELECT * FROM skills WHERE user_id = ?
        """, (user_id,)).fetchall()


def get_shadows(user_id):
    with connect() as db:
        return db.execute("""
        SELECT * FROM shadows WHERE user_id = ?
        """, (user_id,)).fetchall()


def get_titles(user_id):
    with connect() as db:
        return db.execute("""
        SELECT * FROM titles WHERE user_id = ?
        """, (user_id,)).fetchall()


def get_monsters(user_id):
    with connect() as db:
        return db.execute("""
        SELECT * FROM monsters WHERE user_id = ?
        """, (user_id,)).fetchall()


def add_battle_log(attacker_id, defender_id, damage, result):
    with connect() as db:
        db.execute("""
        INSERT INTO battle_logs
        (attacker_id, defender_id, damage, result)
        VALUES (?, ?, ?, ?)
        """, (attacker_id, defender_id, damage, result))
        db.commit()


def get_battle_history(user_id, limit=10):
    with connect() as db:
        return db.execute("""
        SELECT * FROM battle_logs
        WHERE attacker_id = ? OR defender_id = ?
        ORDER BY id DESC LIMIT ?
        """, (user_id, user_id, limit)).fetchall()


def save_world_boss(name, hp):
    with connect() as db:
        db.execute("""
        INSERT OR REPLACE INTO world_boss
        (id, boss_name, hp, max_hp, active)
        VALUES (1, ?, ?, ?, 1)
        """, (name, hp, hp))
        db.commit()


def get_world_boss():
    with connect() as db:
        return db.execute("""
        SELECT * FROM world_boss WHERE id = 1
        """).fetchone()


def damage_world_boss(user_id, damage):
    with connect() as db:
        boss = db.execute("""
        SELECT * FROM world_boss WHERE id = 1 AND active = 1
        """).fetchone()

        if not boss:
            return None

        actual_damage = min(damage, boss["hp"])
        new_hp = max(0, boss["hp"] - actual_damage)

        db.execute("""
        UPDATE world_boss SET hp = ? WHERE id = 1
        """, (new_hp,))

        db.execute("""
        INSERT INTO world_boss_damage (user_id, damage)
        VALUES (?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET damage = damage + excluded.damage
        """, (user_id, actual_damage))

        if new_hp == 0:
            db.execute("""
            UPDATE world_boss SET active = 0 WHERE id = 1
            """)

        db.commit()
        return new_hp


def get_world_boss_ranking():
    with connect() as db:
        return db.execute("""
        SELECT world_boss_damage.user_id,
               world_boss_damage.damage,
               players.name
        FROM world_boss_damage
        LEFT JOIN players
        ON players.user_id = world_boss_damage.user_id
        ORDER BY damage DESC
        LIMIT 10
        """).fetchall()