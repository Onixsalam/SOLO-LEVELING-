import os
import sqlite3

from pathlib import Path
from contextlib import contextmanager


# ==================================================
# DATABASE SETTINGS
# ==================================================

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "shadow_legacy.db"
)

DB_FILE = Path(DATABASE_PATH)
DB_FILE.parent.mkdir(parents=True, exist_ok=True)


# ==================================================
# CONNECTION
# ==================================================

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


# ==================================================
# DATABASE INITIALIZATION
# ==================================================

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

        # OLD SKILLS
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

                damage INTEGER DEFAULT 0,
                result TEXT DEFAULT '',

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # WORLD BOSS
        db.execute("""
            CREATE TABLE IF NOT EXISTS world_boss (
                id INTEGER PRIMARY KEY CHECK(id = 1),

                boss_name TEXT,
                hp INTEGER DEFAULT 0,
                max_hp INTEGER DEFAULT 0,

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


# ==================================================
# DATABASE MIGRATION
# ==================================================

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

        newly_added = set()

        for column, definition in required_columns.items():

            if column not in columns:

                db.execute(
                    f"ALTER TABLE players ADD COLUMN "
                    f"{column} {definition}"
                )

                newly_added.add(column)

        # فقط در اولین اضافه شدن ستون‌های جدید،
        # مقدار آمار قدیمی به ستون‌های جدید منتقل می‌شود.
        stat_pairs = [
            ("STR", "strength"),
            ("AGI", "agility"),
            ("VIT", "vitality"),
            ("INT", "intelligence"),
            ("SEN", "sense")
        ]

        for upper, lower in stat_pairs:

            if upper in newly_added and lower not in newly_added:

                db.execute(f"""
                    UPDATE players
                    SET {upper} = COALESCE({lower}, 5)
                """)

            elif lower in newly_added and upper not in newly_added:

                db.execute(f"""
                    UPDATE players
                    SET {lower} = COALESCE({upper}, 5)
                """)

        # انتقال مهارت‌های قدیمی
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

        # حذف Triggerهای قدیمی برای ساخت نسخه امن‌تر
        db.execute("DROP TRIGGER IF EXISTS sync_lower_stats")
        db.execute("DROP TRIGGER IF EXISTS sync_upper_stats")

        # همگام‌سازی آمار در هر دو جهت
        db.execute("""
            CREATE TRIGGER sync_lower_stats
            AFTER UPDATE OF STR, AGI, VIT, INT, SEN
            ON players

            WHEN
                NEW.STR != OLD.STR OR
                NEW.AGI != OLD.AGI OR
                NEW.VIT != OLD.VIT OR
                NEW.INT != OLD.INT OR
                NEW.SEN != OLD.SEN

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
            CREATE TRIGGER sync_upper_stats
            AFTER UPDATE OF strength, agility, vitality,
                            intelligence, sense
            ON players

            WHEN
                NEW.strength != OLD.strength OR
                NEW.agility != OLD.agility OR
                NEW.vitality != OLD.vitality OR
                NEW.intelligence != OLD.intelligence OR
                NEW.sense != OLD.sense

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


# ==================================================
# PLAYER FUNCTIONS
# ==================================================

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

    assignments = ", ".join(
        f"{key} = ?" for key in values
    )

    parameters = list(values.values()) + [user_id]

    with connect() as db:

        cursor = db.execute(
            f"""
            UPDATE players
            SET {assignments}
            WHERE user_id = ?
            """,
            parameters
        )

    return cursor.rowcount > 0