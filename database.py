import os
import sqlite3

from pathlib import Path
from contextlib import contextmanager


# ================= DATABASE SETTINGS =================

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "shadow_legacy.db"
)

DB_FILE = Path(DATABASE_PATH)

DB_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)


# ================= CONNECTION =================

@contextmanager
def connect():
    connection = sqlite3.connect(
        str(DB_FILE),
        timeout=30
    )

    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")

        yield connection

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_db_path():
    return str(DB_FILE.resolve())


# ================= DATABASE INIT =================

def init_db():
    with connect() as db:

        # PLAYERS
        db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                name TEXT DEFAULT 'Hunter',

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

                STR INTEGER DEFAULT 5,
                AGI INTEGER DEFAULT 5,
                VIT INTEGER DEFAULT 5,
                INT INTEGER DEFAULT 5,
                SEN INTEGER DEFAULT 5,

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

        # INVENTORY
        db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                item_type TEXT DEFAULT 'item',
                quantity INTEGER DEFAULT 1,

                FOREIGN KEY(user_id)
                REFERENCES players(user_id)
                ON DELETE CASCADE
            )
        """)

        # OLD SKILLS TABLE
        db.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                skill_name TEXT NOT NULL,
                damage INTEGER DEFAULT 10,
                skill_type TEXT DEFAULT 'attack',

                FOREIGN KEY(user_id)
                REFERENCES players(user_id)
                ON DELETE CASCADE
            )
        """)

        # PLAYER SKILLS
        db.execute("""
            CREATE TABLE IF NOT EXISTS player_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                skill_name TEXT NOT NULL,
                skill_type TEXT DEFAULT 'attack',
                damage INTEGER DEFAULT 10,
                mp_cost INTEGER DEFAULT 0,
                cooldown INTEGER DEFAULT 0,

                UNIQUE(user_id, skill_name),

                FOREIGN KEY(user_id)
                REFERENCES players(user_id)
                ON DELETE CASCADE
            )
        """)

        # SHADOWS
        db.execute("""
            CREATE TABLE IF NOT EXISTS shadows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                shadow_name TEXT NOT NULL,
                shadow_rank TEXT DEFAULT 'E',
                level INTEGER DEFAULT 1,
                loyalty INTEGER DEFAULT 50,

                FOREIGN KEY(user_id)
                REFERENCES players(user_id)
                ON DELETE CASCADE
            )
        """)

        # TITLES
        db.execute("""
            CREATE TABLE IF NOT EXISTS titles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title_name TEXT NOT NULL,
                active INTEGER DEFAULT 0,

                FOREIGN KEY(user_id)
                REFERENCES players(user_id)
                ON DELETE CASCADE
            )
        """)

        # MONSTER COLLECTION
        db.execute("""
            CREATE TABLE IF NOT EXISTS monsters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                monster_name TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,

                FOREIGN KEY(user_id)
                REFERENCES players(user_id)
                ON DELETE CASCADE
            )
        """)

        # BATTLE HISTORY
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

        # WORLD BOSS
        db.execute("""
            CREATE TABLE IF NOT EXISTS world_boss (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                boss_name TEXT,
                hp INTEGER,
                max_hp INTEGER,
                active INTEGER DEFAULT 0
            )
        """)

        # WORLD BOSS DAMAGE
        db.execute("""
            CREATE TABLE IF NOT EXISTS world_boss_damage (
                user_id INTEGER PRIMARY KEY,
                damage INTEGER DEFAULT 0,

                FOREIGN KEY(user_id)
                REFERENCES players(user_id)
                ON DELETE CASCADE
            )
        """)

        # INDEXES
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_inventory_user
            ON inventory(user_id)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_skills_user
            ON skills(user_id)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_player_skills_user
            ON player_skills(user_id)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_shadows_user
            ON shadows(user_id)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_battle_attacker
            ON battle_logs(attacker_id)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_battle_defender
            ON battle_logs(defender_id)
        """)

    migrate_db()


# ================= DATABASE MIGRATION =================

def migrate_db():
    with connect() as db:

        columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(players)"
            ).fetchall()
        }

        required_columns = {
            "username": "TEXT DEFAULT ''",
            "name": "TEXT DEFAULT 'Hunter'",
            "level": "INTEGER DEFAULT 1",
            "xp": "INTEGER DEFAULT 0",
            "gold": "INTEGER DEFAULT 500",
            "crystals": "INTEGER DEFAULT 50",
            "rank": "TEXT DEFAULT 'E'",
            "hp": "INTEGER DEFAULT 100",
            "max_hp": "INTEGER DEFAULT 100",
            "mp": "INTEGER DEFAULT 50",
            "max_mp": "INTEGER DEFAULT 50",
            "strength": "INTEGER DEFAULT 5",
            "agility": "INTEGER DEFAULT 5",
            "vitality": "INTEGER DEFAULT 5",
            "intelligence": "INTEGER DEFAULT 5",
            "sense": "INTEGER DEFAULT 5",
            "STR": "INTEGER DEFAULT 5",
            "AGI": "INTEGER DEFAULT 5",
            "VIT": "INTEGER DEFAULT 5",
            "INT": "INTEGER DEFAULT 5",
            "SEN": "INTEGER DEFAULT 5",
            "stat_points": "INTEGER DEFAULT 0",
            "power": "INTEGER DEFAULT 25",
            "wins": "INTEGER DEFAULT 0",
            "losses": "INTEGER DEFAULT 0",
            "kills": "INTEGER DEFAULT 0",
            "deaths": "INTEGER DEFAULT 0",
            "is_dead": "INTEGER DEFAULT 0"
        }

        for column, definition in required_columns.items():
            if column not in columns:
                db.execute(
                    f"ALTER TABLE players ADD COLUMN "
                    f"{column} {definition}"
                )

        # همگام‌سازی اولیه آمار قدیمی و جدید
        db.execute("""
            UPDATE players
            SET
                STR = COALESCE(strength, 5),
                AGI = COALESCE(agility, 5),
                VIT = COALESCE(vitality, 5),
                INT = COALESCE(intelligence, 5),
                SEN = COALESCE(sense, 5)
        """)

        # انتقال مهارت‌های قدیمی به جدول جدید
        db.execute("""
            INSERT OR IGNORE INTO player_skills (
                user_id,
                skill_name,
                skill_type,
                damage,
                mp_cost,
                cooldown
            )
            SELECT
                user_id,
                skill_name,
                skill_type,
                damage,
                0,
                0
            FROM skills
        """)

        # Trigger برای همگام‌سازی آمار
        db.execute("""
            CREATE TRIGGER IF NOT EXISTS sync_lower_stats
            AFTER UPDATE OF STR, AGI, VIT, INT, SEN
            ON players
            BEGIN
                UPDATE players
                SET
                    strength = NEW.STR,
                    agility = NEW.AGI,
                    vitality = NEW.VIT,
                    intelligence = NEW.INT,
                    sense = NEW.SEN
                WHERE user_id = NEW.user_id;
            END
        """)

        db.execute("""
            CREATE TRIGGER IF NOT EXISTS sync_upper_stats
            AFTER UPDATE OF strength, agility, vitality,
                            intelligence, sense
            ON players
            BEGIN
                UPDATE players
                SET
                    STR = NEW.strength,
                    AGI = NEW.agility,
                    VIT = NEW.vitality,
                    INT = NEW.intelligence,
                    SEN = NEW.sense
                WHERE user_id = NEW.user_id;
            END
        """)


# ================= PLAYER =================

def get_player(user_id):
    with connect() as db:
        return db.execute("""
            SELECT *
            FROM players
            WHERE user_id = ?
        """, (user_id,)).fetchone()


def register_player(user_id, username, name):
    with connect() as db:
        cursor = db.execute("""
            INSERT OR IGNORE INTO players (
                user_id,
                username,
                name
            )
            VALUES (?, ?, ?)
        """, (
            user_id,
            username or "",
            name or "Hunter"
        ))

    return cursor.rowcount == 1


def update_player(user_id, **values):
    allowed = {
        "username", "name",
        "level", "xp",
        "gold", "crystals",
        "rank",
        "hp", "max_hp",
        "mp", "max_mp",
        "strength", "agility",
        "vitality", "intelligence",
        "sense",
        "STR", "AGI", "VIT", "INT", "SEN",
        "stat_points", "power",
        "wins", "losses",
        "kills", "deaths",
        "is_dead"
    }

    values = {
        key: value
        for key, value in values.items()
        if key in allowed
    }

    if not values:
        return False

    columns = ", ".join(
        f"{key} = ?" for key in values
    )

    params = list(values.values()) + [user_id]

    with connect() as db:
        cursor = db.execute(
            f"""
            UPDATE players
            SET {columns}
            WHERE user_id = ?
            """,
            params
        )

    return cursor.rowcount > 0
# ================= INVENTORY =================

def add_item(user_id, item_name, item_type="item", quantity=1):
    if quantity <= 0:
        return False

    with connect() as db:
        db.execute("""
            INSERT INTO inventory (
                user_id,
                item_name,
                item_type,
                quantity
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
        """, (
            user_id,
            item_name,
            item_type,
            quantity
        ))

        row = db.execute("""
            SELECT id
            FROM inventory
            WHERE user_id = ?
            AND item_name = ?
        """, (user_id, item_name)).fetchone()

        if row:
            db.execute("""
                UPDATE inventory
                SET quantity = quantity + ?
                WHERE id = ?
                AND item_type = ?
            """, (
                quantity - 1,
                row["id"],
                item_type
            ))

    return True


def get_inventory(user_id):
    with connect() as db:
        return db.execute("""
            SELECT *
            FROM inventory
            WHERE user_id = ?
            AND quantity > 0
            ORDER BY id DESC
        """, (user_id,)).fetchall()


# ================= SKILLS =================

def get_skills(user_id):
    with connect() as db:
        return db.execute("""
            SELECT *
            FROM player_skills
            WHERE user_id = ?
            ORDER BY id
        """, (user_id,)).fetchall()


def add_skill(
    user_id,
    skill_name,
    damage=10,
    skill_type="attack",
    mp_cost=0,
    cooldown=0
):
    with connect() as db:
        db.execute("""
            INSERT OR IGNORE INTO player_skills (
                user_id,
                skill_name,
                skill_type,
                damage,
                mp_cost,
                cooldown
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            skill_name,
            skill_type,
            damage,
            mp_cost,
            cooldown
        ))


# ================= SHADOWS =================

def get_shadows(user_id):
    with connect() as db:
        return db.execute("""
            SELECT *
            FROM shadows
            WHERE user_id = ?
            ORDER BY level DESC
        """, (user_id,)).fetchall()


def add_shadow(
    user_id,
    shadow_name,
    shadow_rank="E"
):
    with connect() as db:
        db.execute("""
            INSERT INTO shadows (
                user_id,
                shadow_name,
                shadow_rank
            )
            VALUES (?, ?, ?)
        """, (
            user_id,
            shadow_name,
            shadow_rank
        ))


# ================= TITLES =================

def get_titles(user_id):
    with connect() as db:
        return db.execute("""
            SELECT *
            FROM titles
            WHERE user_id = ?
            ORDER BY id DESC
        """, (user_id,)).fetchall()


def add_title(user_id, title_name):
    with connect() as db:
        db.execute("""
            INSERT INTO titles (
                user_id,
                title_name
            )
            VALUES (?, ?)
        """, (
            user_id,
            title_name
        ))


# ================= MONSTER COLLECTION =================

def get_monsters(user_id):
    with connect() as db:
        return db.execute("""
            SELECT *
            FROM monsters
            WHERE user_id = ?
            ORDER BY quantity DESC
        """, (user_id,)).fetchall()


def add_monster(user_id, monster_name):
    with connect() as db:
        row = db.execute("""
            SELECT id
            FROM monsters
            WHERE user_id = ?
            AND monster_name = ?
        """, (
            user_id,
            monster_name
        )).fetchone()

        if row:
            db.execute("""
                UPDATE monsters
                SET quantity = quantity + 1
                WHERE id = ?
            """, (row["id"],))

        else:
            db.execute("""
                INSERT INTO monsters (
                    user_id,
                    monster_name,
                    quantity
                )
                VALUES (?, ?, 1)
            """, (
                user_id,
                monster_name
            ))


# ================= BATTLE HISTORY =================

def add_battle_log(
    attacker_id,
    defender_id,
    damage,
    result
):
    with connect() as db:
        db.execute("""
            INSERT INTO battle_logs (
                attacker_id,
                defender_id,
                damage,
                result
            )
            VALUES (?, ?, ?, ?)
        """, (
            attacker_id,
            defender_id,
            damage,
            result
        ))


def get_battle_history(user_id, limit=10):
    limit = max(1, min(int(limit), 100))

    with connect() as db:
        return db.execute("""
            SELECT *
            FROM battle_logs
            WHERE attacker_id = ?
            OR defender_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (
            user_id,
            user_id,
            limit
        )).fetchall()


# ================= WORLD BOSS =================

def save_world_boss(name, hp):
    hp = max(1, int(hp))

    with connect() as db:
        db.execute("""
            INSERT OR REPLACE INTO world_boss (
                id,
                boss_name,
                hp,
                max_hp,
                active
            )
            VALUES (1, ?, ?, ?, 1)
        """, (
            name,
            hp,
            hp
        ))

        db.execute("""
            DELETE FROM world_boss_damage
        """)


def get_world_boss():
    with connect() as db:
        return db.execute("""
            SELECT *
            FROM world_boss
            WHERE id = 1
        """).fetchone()


def damage_world_boss(user_id, damage):
    damage = max(0, int(damage))

    if damage <= 0:
        return None

    with connect() as db:
        db.execute("BEGIN IMMEDIATE")

        boss = db.execute("""
            SELECT *
            FROM world_boss
            WHERE id = 1
            AND active = 1
        """).fetchone()

        if not boss:
            return None

        actual_damage = min(
            damage,
            boss["hp"]
        )

        new_hp = max(
            0,
            boss["hp"] - actual_damage
        )

        db.execute("""
            UPDATE world_boss
            SET hp = ?,
                active = ?
            WHERE id = 1
        """, (
            new_hp,
            1 if new_hp > 0 else 0
        ))

        db.execute("""
            INSERT INTO world_boss_damage (
                user_id,
                damage
            )
            VALUES (?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET
                damage = damage + excluded.damage
        """, (
            user_id,
            actual_damage
        ))

        return new_hp


def get_world_boss_ranking():
    with connect() as db:
        return db.execute("""
            SELECT
                world_boss_damage.user_id,
                world_boss_damage.damage,
                players.name
            FROM world_boss_damage
            LEFT JOIN players
                ON players.user_id = world_boss_damage.user_id
            ORDER BY world_boss_damage.damage DESC
            LIMIT 10
        """).fetchall()