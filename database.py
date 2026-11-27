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
# ==================================================
# INVENTORY FUNCTIONS
# ==================================================

def add_item(user_id, item_name, quantity=1, item_type="item"):

    quantity = int(quantity)

    if quantity <= 0:
        return False

    with connect() as db:

        item = db.execute("""
            SELECT id
            FROM inventory
            WHERE user_id = ?
              AND item_name = ?
              AND item_type = ?
        """, (
            user_id,
            item_name,
            item_type
        )).fetchone()

        if item:

            db.execute("""
                UPDATE inventory
                SET quantity = quantity + ?
                WHERE id = ?
            """, (
                quantity,
                item["id"]
            ))

        else:

            db.execute("""
                INSERT INTO inventory (
                    user_id,
                    item_name,
                    item_type,
                    quantity
                )
                VALUES (?, ?, ?, ?)
            """, (
                user_id,
                item_name,
                item_type,
                quantity
            ))

    return True


def remove_item(user_id, item_name, quantity=1):

    quantity = int(quantity)

    if quantity <= 0:
        return False

    with connect() as db:

        item = db.execute("""
            SELECT id, quantity
            FROM inventory
            WHERE user_id = ?
              AND item_name = ?
        """, (
            user_id,
            item_name
        )).fetchone()

        if not item or item["quantity"] < quantity:
            return False

        remaining = item["quantity"] - quantity

        if remaining == 0:

            db.execute("""
                DELETE FROM inventory
                WHERE id = ?
            """, (item["id"],))

        else:

            db.execute("""
                UPDATE inventory
                SET quantity = ?
                WHERE id = ?
            """, (
                remaining,
                item["id"]
            ))

    return True


def get_inventory(user_id):

    with connect() as db:

        return db.execute("""
            SELECT *
            FROM inventory
            WHERE user_id = ?
            ORDER BY item_name
        """, (user_id,)).fetchall()


# ==================================================
# SKILL FUNCTIONS
# ==================================================

def get_skills(user_id):

    with connect() as db:

        return db.execute("""
            SELECT *
            FROM player_skills
            WHERE user_id = ?
            ORDER BY skill_name
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

        cursor = db.execute("""
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

    return cursor.rowcount == 1


def has_skill(user_id, skill_name):

    with connect() as db:

        row = db.execute("""
            SELECT 1
            FROM player_skills
            WHERE user_id = ?
              AND skill_name = ?
        """, (
            user_id,
            skill_name
        )).fetchone()

    return row is not None


# ==================================================
# SHADOW FUNCTIONS
# ==================================================

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
    shadow_rank="E",
    level=1,
    loyalty=50
):

    with connect() as db:

        cursor = db.execute("""
            INSERT INTO shadows (
                user_id,
                shadow_name,
                shadow_rank,
                level,
                loyalty
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            user_id,
            shadow_name,
            shadow_rank,
            level,
            loyalty
        ))

    return cursor.lastrowid


# ==================================================
# TITLE FUNCTIONS
# ==================================================

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

        cursor = db.execute("""
            INSERT OR IGNORE INTO titles (
                user_id,
                title_name
            )
            VALUES (?, ?)
        """, (
            user_id,
            title_name
        ))

    return cursor.lastrowid


# ==================================================
# MONSTER COLLECTION FUNCTIONS
# ==================================================

def get_monsters(user_id):

    with connect() as db:

        return db.execute("""
            SELECT *
            FROM monsters
            WHERE user_id = ?
            ORDER BY monster_name
        """, (user_id,)).fetchall()


def add_monster(user_id, monster_name, quantity=1):

    quantity = int(quantity)

    if quantity <= 0:
        return False

    with connect() as db:

        monster = db.execute("""
            SELECT id
            FROM monsters
            WHERE user_id = ?
              AND monster_name = ?
        """, (
            user_id,
            monster_name
        )).fetchone()

        if monster:

            db.execute("""
                UPDATE monsters
                SET quantity = quantity + ?
                WHERE id = ?
            """, (
                quantity,
                monster["id"]
            ))

        else:

            db.execute("""
                INSERT INTO monsters (
                    user_id,
                    monster_name,
                    quantity
                )
                VALUES (?, ?, ?)
            """, (
                user_id,
                monster_name,
                quantity
            ))

    return True


# ==================================================
# BATTLE HISTORY
# ==================================================

def add_battle_log(
    attacker_id,
    defender_id,
    damage,
    result=""
):

    with connect() as db:

        cursor = db.execute("""
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

    return cursor.lastrowid


def get_battle_history(user_id, limit=20):

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


# ==================================================
# WORLD BOSS
# ==================================================

def set_world_boss(boss_name, hp):

    hp = max(0, int(hp))

    with connect() as db:

        db.execute("""
            INSERT INTO world_boss (
                id,
                boss_name,
                hp,
                max_hp,
                active
            )
            VALUES (1, ?, ?, ?, 1)

            ON CONFLICT(id) DO UPDATE SET
                boss_name = excluded.boss_name,
                hp = excluded.hp,
                max_hp = excluded.max_hp,
                active = 1
        """, (
            boss_name,
            hp,
            hp
        ))

        db.execute("""
            DELETE FROM world_boss_damage
        """)

    return True


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

        if not boss or boss["hp"] <= 0:
            return None

        actual_damage = min(damage, boss["hp"])

        new_hp = boss["hp"] - actual_damage

        db.execute("""
            UPDATE world_boss
            SET hp = ?
            WHERE id = 1
              AND active = 1
        """, (new_hp,))

        db.execute("""
            INSERT INTO world_boss_damage (
                user_id,
                damage
            )
            VALUES (?, ?)

            ON CONFLICT(user_id) DO UPDATE SET
                damage = damage + excluded.damage
        """, (
            user_id,
            actual_damage
        ))

        if new_hp <= 0:

            db.execute("""
                UPDATE world_boss
                SET active = 0
                WHERE id = 1
            """)

        return {
            "damage": actual_damage,
            "hp": new_hp,
            "max_hp": boss["max_hp"],
            "defeated": new_hp <= 0
        }


def get_world_boss_ranking(limit=10):

    with connect() as db:

        return db.execute("""
            SELECT
                w.user_id,
                w.damage,
                p.name,
                p.username

            FROM world_boss_damage w

            LEFT JOIN players p
                ON p.user_id = w.user_id

            ORDER BY w.damage DESC

            LIMIT ?
        """, (limit,)).fetchall()


# ==================================================
# PLAYER RANKING
# ==================================================

def get_top_players(limit=10):

    with connect() as db:

        return db.execute("""
            SELECT *
            FROM players
            ORDER BY power DESC, level DESC
            LIMIT ?
        """, (limit,)).fetchall()


# ==================================================
# PLAYER COUNT
# ==================================================

def get_player_count():

    with connect() as db:

        row = db.execute("""
            SELECT COUNT(*) AS total
            FROM players
        """).fetchone()

    return row["total"]


# ==================================================
# HEALTH AND RESOURCE FUNCTIONS
# ==================================================

def restore_player(user_id):

    with connect() as db:

        cursor = db.execute("""
            UPDATE players
            SET
                hp = max_hp,
                mp = max_mp
            WHERE user_id = ?
        """, (user_id,))

    return cursor.rowcount > 0


def change_gold(user_id, amount):

    amount = int(amount)

    with connect() as db:

        cursor = db.execute("""
            UPDATE players
            SET gold = gold + ?
            WHERE user_id = ?
              AND gold + ? >= 0
        """, (
            amount,
            user_id,
            amount
        ))

    return cursor.rowcount > 0


def change_crystals(user_id, amount):

    amount = int(amount)

    with connect() as db:

        cursor = db.execute("""
            UPDATE players
            SET crystals = crystals + ?
            WHERE user_id = ?
              AND crystals + ? >= 0
        """, (
            amount,
            user_id,
            amount
        ))

    return cursor.rowcount > 0