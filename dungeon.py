import time
import random
import logging

import database as db

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

logger = logging.getLogger(__name__)


# =====================================
# DUNGEON SETTINGS
# =====================================

GATE_INTERVALS = {
    "E": 2 * 60 * 60,
    "D": 3 * 60 * 60,
    "C": 4 * 60 * 60,
    "B": 6 * 60 * 60,
    "A": 8 * 60 * 60,
    "S": 12 * 60 * 60
}

GATE_RANKS = ["E", "D", "C", "B", "A", "S"]

GATE_OPEN_SECONDS = 30 * 60

RED_GATE_CHANCE = 0.05
DOUBLE_DUNGEON_CHANCE = 0.03

MONSTERS = {
    "E": {
        "name": "Goblin",
        "hp": 150,
        "damage": 8,
        "xp": 50,
        "gold": 100
    },
    "D": {
        "name": "Orc Warrior",
        "hp": 300,
        "damage": 15,
        "xp": 100,
        "gold": 200
    },
    "C": {
        "name": "Lizardman",
        "hp": 600,
        "damage": 25,
        "xp": 180,
        "gold": 350
    },
    "B": {
        "name": "High Orc",
        "hp": 1000,
        "damage": 40,
        "xp": 300,
        "gold": 600
    },
    "A": {
        "name": "Demon Knight",
        "hp": 1800,
        "damage": 60,
        "xp": 500,
        "gold": 1000
    },
    "S": {
        "name": "Ancient Dragon",
        "hp": 3500,
        "damage": 90,
        "xp": 1000,
        "gold": 2000
    }
}


# =====================================
# DATABASE
# =====================================

def init_dungeon_db():
    with db.connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS dungeon_gates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gate_rank TEXT NOT NULL,
                gate_type TEXT DEFAULT 'normal',
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                status TEXT DEFAULT 'open'
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS dungeon_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gate_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                entered_at INTEGER NOT NULL,
                status TEXT DEFAULT 'active',
                UNIQUE(gate_id, user_id),
                FOREIGN KEY(gate_id)
                    REFERENCES dungeon_gates(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS dungeon_battles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gate_id INTEGER NOT NULL UNIQUE,
                monster_name TEXT NOT NULL,
                monster_hp INTEGER NOT NULL,
                max_hp INTEGER NOT NULL,
                monster_damage INTEGER NOT NULL,
                status TEXT DEFAULT 'active',
                FOREIGN KEY(gate_id)
                    REFERENCES dungeon_gates(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS dungeon_cooldowns (
                user_id INTEGER PRIMARY KEY,
                last_entry INTEGER DEFAULT 0
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS dungeon_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                gate_id INTEGER NOT NULL,
                xp INTEGER DEFAULT 0,
                gold INTEGER DEFAULT 0,
                item_name TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                UNIQUE(user_id, gate_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS dungeon_schedule (
                gate_rank TEXT PRIMARY KEY,
                next_spawn INTEGER NOT NULL
            )
        """)

        now = int(time.time())

        for rank, interval in GATE_INTERVALS.items():
            conn.execute("""
                INSERT OR IGNORE INTO dungeon_schedule (
                    gate_rank,
                    next_spawn
                )
                VALUES (?, ?)
            """, (rank, now + interval))


# =====================================
# GATE CREATION
# =====================================

def create_gate(gate_rank, gate_type="normal"):
    if gate_rank not in GATE_INTERVALS:
        return None

    now = int(time.time())

    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")

        existing = conn.execute("""
            SELECT id
            FROM dungeon_gates
            WHERE gate_rank = ?
            AND status = 'open'
            AND expires_at > ?
        """, (gate_rank, now)).fetchone()

        if existing:
            return existing["id"]

        cursor = conn.execute("""
            INSERT INTO dungeon_gates (
                gate_rank,
                gate_type,
                created_at,
                expires_at,
                status
            )
            VALUES (?, ?, ?, ?, 'open')
        """, (
            gate_rank,
            gate_type,
            now,
            now + GATE_OPEN_SECONDS
        ))

        gate_id = cursor.lastrowid

        monster = MONSTERS[gate_rank]

        multiplier = 2 if gate_type == "double" else 1

        conn.execute("""
            INSERT INTO dungeon_battles (
                gate_id,
                monster_name,
                monster_hp,
                max_hp,
                monster_damage
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            gate_id,
            monster["name"],
            monster["hp"] * multiplier,
            monster["hp"] * multiplier,
            monster["damage"] * multiplier
        ))

        return gate_id


def spawn_random_gate():
    gate_type = "normal"
    gate_rank = random.choice(GATE_RANKS)

    roll = random.random()

    if roll < RED_GATE_CHANCE:
        gate_type = "red"

    elif roll < RED_GATE_CHANCE + DOUBLE_DUNGEON_CHANCE:
        gate_type = "double"

    return create_gate(gate_rank, gate_type)


# =====================================
# GATE SCHEDULER
# =====================================

def check_gate_spawns():
    now = int(time.time())

    with db.connect() as conn:
        schedules = conn.execute("""
            SELECT *
            FROM dungeon_schedule
        """).fetchall()

    spawned_any = False

    for schedule in schedules:
        if schedule["next_spawn"] > now:
            continue

        rank = schedule["gate_rank"]

        try:
            create_gate(rank)
            spawned_any = True

            with db.connect() as conn:
                conn.execute("""
                    UPDATE dungeon_schedule
                    SET next_spawn = ?
                    WHERE gate_rank = ?
                """, (
                    now + GATE_INTERVALS[rank],
                    rank
                ))

        except Exception:
            logger.exception(
                "Could not spawn %s Gate",
                rank
            )

    # Roll for a special gate only when a scheduled gate is spawned.
    # This prevents a 60-second scheduler from creating special gates constantly.
    if spawned_any:
        try:
            roll = random.random()
            if roll < RED_GATE_CHANCE:
                create_gate(random.choice(GATE_RANKS), "red")
            elif roll < RED_GATE_CHANCE + DOUBLE_DUNGEON_CHANCE:
                create_gate(random.choice(GATE_RANKS), "double")
        except Exception:
            logger.exception("Could not spawn a special Gate")


def close_expired_gates():
    now = int(time.time())

    with db.connect() as conn:
        # Gateهایی که کسی واردشان نشده، پس از ۳۰ دقیقه بسته می‌شوند.
        # Gate دارای بازیکن فعال باز می‌ماند تا مبارزه تمام شود.
        conn.execute("""
            UPDATE dungeon_gates
            SET status = 'closed'
            WHERE status = 'open'
            AND expires_at <= ?
            AND NOT EXISTS (
                SELECT 1
                FROM dungeon_entries e
                WHERE e.gate_id = dungeon_gates.id
                AND e.status = 'active'
            )
        """, (now,))


# =====================================
# GATE INFORMATION
# =====================================

def get_open_gates():
    now = int(time.time())

    with db.connect() as conn:
        return conn.execute("""
            SELECT
                g.*,
                COUNT(e.user_id) AS players_inside
            FROM dungeon_gates g
            LEFT JOIN dungeon_entries e
                ON e.gate_id = g.id
            WHERE g.status = 'open'
            AND g.expires_at > ?
            GROUP BY g.id
            ORDER BY g.created_at DESC
        """, (now,)).fetchall()


def gate_text():
    gates = get_open_gates()

    if not gates:
        return (
            "🏰 DUNGEON GATES\n\n"
            "در حال حاضر هیچ Gate بازی وجود ندارد.\n"
            "Gateهای جدید طبق زمان‌بندی ظاهر می‌شوند."
        )

    text = "🏰 ACTIVE DUNGEON GATES\n"
    text += "━━━━━━━━━━━━━━━━━━\n\n"

    for gate in gates:
        remaining = max(
            0,
            gate["expires_at"] - int(time.time())
        )

        minutes = remaining // 60

        gate_type = {
            "normal": "Normal",
            "red": "🔴 RED GATE",
            "double": "⚔️ DOUBLE DUNGEON"
        }.get(gate["gate_type"], "Normal")

        text += (
            f"🆔 Gate #{gate['id']}\n"
            f"Rank: {gate['gate_rank']}\n"
            f"Type: {gate_type}\n"
            f"Players: {gate['players_inside']}\n"
            f"Time left: {minutes} minutes\n\n"
        )

    return text


def gate_keyboard():
    gates = get_open_gates()

    buttons = []

    for gate in gates:
        buttons.append([
            InlineKeyboardButton(
                f"Enter {gate['gate_rank']} Gate #{gate['id']}",
                callback_data=f"dungeon_enter_{gate['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "🔄 Refresh",
            callback_data="dungeon_refresh"
        )
    ])

    return InlineKeyboardMarkup(buttons)
# =====================================
# ENTER DUNGEON
# =====================================

def enter_dungeon(user_id, gate_id):
    now = int(time.time())

    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")

        player = conn.execute("""
            SELECT *
            FROM players
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not player:
            return False, "ابتدا ثبت‌نام کن."

        if player["is_dead"]:
            return False, "تا زمان احیا نمی‌توانی وارد Dungeon شوی."

        gate = conn.execute("""
            SELECT *
            FROM dungeon_gates
            WHERE id = ?
            AND status = 'open'
            AND expires_at > ?
        """, (gate_id, now)).fetchone()

        if not gate:
            return False, "این Gate دیگر در دسترس نیست."

        previous = conn.execute("""
            SELECT id
            FROM dungeon_entries
            WHERE gate_id = ?
            AND user_id = ?
        """, (gate_id, user_id)).fetchone()

        if previous:
            return False, "قبلاً وارد این Gate شده‌ای."

        active = conn.execute("""
            SELECT id
            FROM dungeon_entries
            WHERE user_id = ?
            AND status = 'active'
        """, (user_id,)).fetchone()

        if active:
            return False, "در حال حاضر داخل یک Dungeon هستی."

        conn.execute("""
            INSERT INTO dungeon_entries (
                gate_id,
                user_id,
                entered_at,
                status
            )
            VALUES (?, ?, ?, 'active')
        """, (
            gate_id,
            user_id,
            now
        ))

    return True, (
        f"⚔️ وارد Gate شماره {gate_id} شدی!\n\n"
        "برای مشاهده وضعیت و مبارزه از دستور /dungeon استفاده کن."
    )


# =====================================
# DUNGEON STATUS
# =====================================

def get_player_dungeon(user_id):
    with db.connect() as conn:
        return conn.execute("""
            SELECT
                e.gate_id,
                e.status AS entry_status,
                g.gate_rank,
                g.gate_type,
                b.monster_name,
                b.monster_hp,
                b.max_hp,
                b.status AS battle_status
            FROM dungeon_entries e
            JOIN dungeon_gates g
                ON g.id = e.gate_id
            JOIN dungeon_battles b
                ON b.gate_id = e.gate_id
            WHERE e.user_id = ?
            AND e.status = 'active'
            ORDER BY e.entered_at DESC
            LIMIT 1
        """, (user_id,)).fetchone()


def dungeon_status_text(user_id):
    dungeon = get_player_dungeon(user_id)

    if not dungeon:
        return (
            "🏰 DUNGEON STATUS\n\n"
            "تو در حال حاضر داخل هیچ Dungeon نیستی.\n"
            "برای دیدن Gateهای فعال دستور /gates را بزن."
        )

    return (
        "🏰 DUNGEON STATUS\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Gate: #{dungeon['gate_id']}\n"
        f"Rank: {dungeon['gate_rank']}\n"
        f"Type: {dungeon['gate_type']}\n\n"
        f"👹 Monster: {dungeon['monster_name']}\n"
        f"❤️ Monster HP: {dungeon['monster_hp']}/"
        f"{dungeon['max_hp']}\n\n"
        "برای حمله:\n"
        "/dattack نام_مهارت"
    )


# =====================================
# DUNGEON ATTACK
# =====================================

def dungeon_attack(user_id, skill_name):
    if not skill_name or len(skill_name) > 60:
        return False, "نام مهارت معتبر نیست."

    skill_name = skill_name.strip()

    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")

        entry = conn.execute("""
            SELECT gate_id
            FROM dungeon_entries
            WHERE user_id = ?
            AND status = 'active'
            LIMIT 1
        """, (user_id,)).fetchone()

        if not entry:
            return False, "داخل Dungeon نیستی."

        player = conn.execute("""
            SELECT *
            FROM players
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not player or player["is_dead"]:
            return False, "نمی‌توانی در این وضعیت حمله کنی."

        skill = conn.execute("""
            SELECT *
            FROM player_skills
            WHERE user_id = ?
            AND LOWER(skill_name) = LOWER(?)
        """, (
            user_id,
            skill_name
        )).fetchone()

        if not skill:
            return False, "این مهارت را نداری."

        if skill["skill_type"] not in ("attack", "special"):
            return False, "این مهارت برای حمله مناسب نیست."

        if player["mp"] < skill["mp_cost"]:
            return False, "MP کافی نداری."

        battle = conn.execute("""
            SELECT *
            FROM dungeon_battles
            WHERE gate_id = ?
            AND status = 'active'
        """, (entry["gate_id"],)).fetchone()

        if not battle:
            return False, "این مبارزه تمام شده است."

        damage = (
            int(skill["damage"])
            + int(player["STR"]) * 2
            + int(player["INT"])
        )

        damage = max(1, damage)

        new_hp = max(
            0,
            battle["monster_hp"] - damage
        )

        conn.execute("""
            UPDATE players
            SET mp = mp - ?
            WHERE user_id = ?
        """, (
            skill["mp_cost"],
            user_id
        ))

        conn.execute("""
            UPDATE dungeon_battles
            SET monster_hp = ?
            WHERE gate_id = ?
        """, (
            new_hp,
            entry["gate_id"]
        ))

        if new_hp > 0:
            return True, (
                f"⚔️ {skill['skill_name']}!\n"
                f"Damage: {damage}\n"
                f"Monster HP: {new_hp}/{battle['max_hp']}"
            )

        conn.execute("""
            UPDATE dungeon_battles
            SET status = 'cleared'
            WHERE gate_id = ?
        """, (entry["gate_id"],))

        entries = conn.execute("""
            SELECT user_id
            FROM dungeon_entries
            WHERE gate_id = ?
            AND status = 'active'
        """, (entry["gate_id"],)).fetchall()

        gate_rank = conn.execute("""
            SELECT gate_rank, gate_type
            FROM dungeon_gates
            WHERE id = ?
        """, (entry["gate_id"],)).fetchone()

        reward = MONSTERS[gate_rank["gate_rank"]]

        multiplier = (
            2 if gate_rank["gate_type"] == "double" else 1
        )

        for member in entries:
            member_id = member["user_id"]

            cursor = conn.execute("""
                INSERT OR IGNORE INTO dungeon_rewards (
                    user_id,
                    gate_id,
                    xp,
                    gold,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                member_id,
                entry["gate_id"],
                reward["xp"] * multiplier,
                reward["gold"] * multiplier,
                int(time.time())
            ))

            if cursor.rowcount == 1:
                conn.execute("""
                    UPDATE players
                    SET gold = gold + ?
                    WHERE user_id = ?
                """, (
                    reward["gold"] * multiplier,
                    member_id
                ))

            conn.execute("""
                UPDATE dungeon_entries
                SET status = 'completed'
                WHERE gate_id = ?
                AND user_id = ?
            """, (
                entry["gate_id"],
                member_id
            ))

    # افزودن XP بعد از پایان تراکنش اصلی
    try:
        from progression import add_xp

        for member in entries:
            add_xp(
                member["user_id"],
                reward["xp"] * multiplier
            )

        try:
            from daily_quests import add_quest_progress

            add_quest_progress(
                user_id,
                "dungeon",
                1
            )
        except Exception:
            logger.exception("Dungeon quest update failed")

    except Exception:
        logger.exception("Dungeon reward XP failed")

    return True, (
        "🏆 DUNGEON CLEARED!\n\n"
        f"👹 Monster defeated: {battle['monster_name']}\n"
        f"⚔️ Final damage: {damage}\n"
        f"⭐ XP reward: {reward['xp'] * multiplier}\n"
        f"💰 Gold reward: {reward['gold'] * multiplier}"
    )


# =====================================
# TELEGRAM COMMANDS
# =====================================

async def gates_command(update, context):
    if update.effective_chat.type != "private":
        await update.effective_message.reply_text(
            "این دستور فقط در چت خصوصی قابل استفاده است."
        )
        return

    if not db.get_player(update.effective_user.id):
        await update.effective_message.reply_text(
            "ابتدا /start را اجرا کن."
        )
        return

    await update.effective_message.reply_text(
        gate_text(),
        reply_markup=gate_keyboard()
    )


async def dungeon_command(update, context):
    if update.effective_chat.type != "private":
        await update.effective_message.reply_text(
            "این دستور فقط در چت خصوصی قابل استفاده است."
        )
        return

    user_id = update.effective_user.id

    if not db.get_player(user_id):
        await update.effective_message.reply_text(
            "ابتدا /start را اجرا کن."
        )
        return

    await update.effective_message.reply_text(
        dungeon_status_text(user_id)
    )


async def dungeon_attack_command(update, context):
    if update.effective_chat.type != "private":
        await update.effective_message.reply_text(
            "این دستور فقط در چت خصوصی قابل استفاده است."
        )
        return

    user_id = update.effective_user.id

    if not db.get_player(user_id):
        await update.effective_message.reply_text(
            "ابتدا /start را اجرا کن."
        )
        return

    if not context.args:
        await update.effective_message.reply_text(
            "روش استفاده:\n/dattack نام_مهارت"
        )
        return

    success, message = dungeon_attack(
        user_id,
        " ".join(context.args)
    )

    await update.effective_message.reply_text(message)


async def dungeon_callback(update, context):
    query = update.callback_query

    if (
        not query.message
        or query.message.chat.type != "private"
        or query.message.chat.id != query.from_user.id
    ):
        await query.answer(
            "این منو فقط در چت خصوصی قابل استفاده است.",
            show_alert=True
        )
        return

    user_id = query.from_user.id

    if not db.get_player(user_id):
        await query.answer(
            "ابتدا /start را اجرا کن.",
            show_alert=True
        )
        return

    if query.data == "dungeon_refresh":
        await query.answer("بروزرسانی شد.")

        await query.edit_message_text(
            gate_text(),
            reply_markup=gate_keyboard()
        )
        return

    try:
        gate_id = int(query.data.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        await query.answer(
            "Gate نامعتبر است.",
            show_alert=True
        )
        return

    success, message = enter_dungeon(
        user_id,
        gate_id
    )

    await query.answer(
        "ورود موفق بود!" if success else message,
        show_alert=not success
    )

    if success:
        await query.message.reply_text(
            message + "\n\n" + dungeon_status_text(user_id)
        )


# =====================================
# SETUP
# =====================================

def setup_dungeon(application):
    init_dungeon_db()

    check_gate_spawns()
    close_expired_gates()

    if application.job_queue:
        application.job_queue.run_repeating(
            dungeon_scheduler,
            interval=60,
            first=10,
            name="dungeon_scheduler"
        )

    application.add_handler(
        CommandHandler("gates", gates_command)
    )

    application.add_handler(
        CommandHandler("dungeon", dungeon_command)
    )

    application.add_handler(
        CommandHandler("dattack", dungeon_attack_command)
    )

    application.add_handler(
        CallbackQueryHandler(
            dungeon_callback,
            pattern=r"^(dungeon_refresh|dungeon_enter_\d+)$"
        )
    )


async def dungeon_scheduler(context):
    try:
        check_gate_spawns()
        close_expired_gates()
    except Exception:
        logger.exception("Dungeon scheduler failed")