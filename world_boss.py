import os
import time
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

import database as db


logger = logging.getLogger(__name__)

BOSS_MAX_HP = 100000
BOSS_ATTACK_COOLDOWN = 10

BOSS_REWARD_GOLD = 1000
BOSS_REWARD_CRYSTALS = 100
BOSS_REWARD_XP = 500


def get_admin_ids():
    raw = os.getenv("BOSS_ADMIN_IDS", "")
    result = set()

    for item in raw.split(","):
        item = item.strip()

        if item.isdigit():
            result.add(int(item))

    return result


def is_boss_admin(user_id):
    return user_id in get_admin_ids()


def init_world_boss_db():
    with db.connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS world_boss (
                id INTEGER PRIMARY KEY,
                boss_name TEXT NOT NULL,
                hp INTEGER NOT NULL,
                max_hp INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 0
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS world_boss_damage (
                user_id INTEGER PRIMARY KEY,
                damage INTEGER NOT NULL DEFAULT 0
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS world_boss_cooldowns (
                user_id INTEGER PRIMARY KEY,
                last_attack REAL NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS world_boss_rewards (
                user_id INTEGER PRIMARY KEY,
                rewarded_at REAL NOT NULL
            )
        """)

        conn.execute("""
            INSERT OR IGNORE INTO world_boss
            (id, boss_name, hp, max_hp, active)
            VALUES (1, 'Shadow Monarch', 100000, 100000, 0)
        """)


def get_boss():
    with db.connect() as conn:
        return conn.execute("""
            SELECT *
            FROM world_boss
            WHERE id = 1
        """).fetchone()


def get_boss_damage():
    with db.connect() as conn:
        return conn.execute("""
            SELECT user_id, damage
            FROM world_boss_damage
            ORDER BY damage DESC
        """).fetchall()


def start_boss():
    with db.connect() as conn:
        conn.execute("""
            UPDATE world_boss
            SET boss_name = ?,
                hp = ?,
                max_hp = ?,
                active = 1
            WHERE id = 1
        """, (
            "Shadow Monarch",
            BOSS_MAX_HP,
            BOSS_MAX_HP
        ))

        conn.execute("DELETE FROM world_boss_damage")
        conn.execute("DELETE FROM world_boss_cooldowns")
        conn.execute("DELETE FROM world_boss_rewards")


def stop_boss():
    with db.connect() as conn:
        conn.execute("""
            UPDATE world_boss
            SET active = 0
            WHERE id = 1
        """)


def get_player_skill(user_id, skill_name):
    with db.connect() as conn:
        return conn.execute("""
            SELECT *
            FROM player_skills
            WHERE user_id = ?
              AND LOWER(skill_name) = LOWER(?)
            LIMIT 1
        """, (user_id, skill_name)).fetchone()


def get_player(user_id):
    with db.connect() as conn:
        return conn.execute("""
            SELECT *
            FROM players
            WHERE user_id = ?
        """, (user_id,)).fetchone()


def get_attack_cooldown(user_id):
    with db.connect() as conn:
        row = conn.execute("""
            SELECT last_attack
            FROM world_boss_cooldowns
            WHERE user_id = ?
        """, (user_id,)).fetchone()

    if not row:
        return 0

    remaining = BOSS_ATTACK_COOLDOWN - (time.time() - row["last_attack"])
    return max(0, int(remaining))


def calculate_boss_damage(player, skill):
    skill_damage = max(0, int(skill["damage"]))

    strength = int(player["STR"])
    intelligence = int(player["INT"])

    skill_type = str(skill["skill_type"]).lower()

    if skill_type == "special":
        damage = skill_damage + intelligence * 2
    else:
        damage = skill_damage + strength * 2

    return max(1, damage)


async def worldboss_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "🌍 World Boss فقط در گروه قابل استفاده است."
        )
        return

    boss = get_boss()

    if not boss or not boss["active"]:
        await update.message.reply_text(
            "🌑 در حال حاضر هیچ World Boss فعالی وجود ندارد."
        )
        return

    percentage = (boss["hp"] / boss["max_hp"]) * 100

    await update.message.reply_text(
        f"🌑 WORLD BOSS\n\n"
        f"👑 Boss: {boss['boss_name']}\n"
        f"❤️ HP: {boss['hp']:,} / {boss['max_hp']:,}\n"
        f"📊 Health: {percentage:.1f}%\n\n"
        f"⚔️ برای حمله:\n"
        f"/wbattack نام_مهارت"
    )


async def bossstart_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "این دستور فقط در گروه قابل استفاده است."
        )
        return

    if not is_boss_admin(user.id):
        await update.message.reply_text(
            "⛔ اجازه شروع World Boss را نداری."
        )
        return

    start_boss()

    await update.message.reply_text(
        "🌑 WORLD BOSS HAS SPAWNED!\n\n"
        "👑 Shadow Monarch\n"
        f"❤️ HP: {BOSS_MAX_HP:,}\n\n"
        "⚔️ بازیکنان می‌توانند با مهارت‌هایشان حمله کنند.\n"
        "دستور مشاهده وضعیت: /worldboss"
    )
async def wbattack_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "⚠️ حمله به World Boss فقط در گروه امکان‌پذیر است."
        )
        return

    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text(
            "⚔️ اسم مهارتت را وارد کن:\n"
            "/wbattack Shadow Strike"
        )
        return

    player = get_player(user_id)

    if not player:
        await update.message.reply_text(
            "❌ ابتدا ربات را در خصوصی با /start فعال کن."
        )
        return

    if player["is_dead"]:
        await update.message.reply_text(
            "💀 تا زمان احیا نمی‌توانی حمله کنی."
        )
        return

    boss = get_boss()

    if not boss or not boss["active"]:
        await update.message.reply_text(
            "🌑 هیچ World Boss فعالی وجود ندارد."
        )
        return

    remaining = get_attack_cooldown(user_id)

    if remaining > 0:
        await update.message.reply_text(
            f"⏳ برای حمله بعدی {remaining} ثانیه صبر کن."
        )
        return

    skill_name = " ".join(context.args)
    skill = get_player_skill(user_id, skill_name)

    if not skill:
        await update.message.reply_text(
            "❌ این مهارت را نداری."
        )
        return

    if str(skill["skill_type"]).lower() not in ("attack", "special"):
        await update.message.reply_text(
            "❌ این مهارت برای حمله مناسب نیست."
        )
        return

    mp