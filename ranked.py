import os
import time
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

import database as db
import pvp_lifecycle as lifecycle


logger = logging.getLogger(__name__)

RANKED_CHAT_ID = os.getenv("RANKED_CHAT_ID")

SEARCH_INTERVAL = 10
ACCEPT_TIMEOUT = 60

MAX_POWER_DIFFERENCE = 500
MAX_RANK_DIFFERENCE = 500

RANKS = [
    ("Bronze", 0),
    ("Silver", 1000),
    ("Gold", 2000),
    ("Platinum", 3000),
    ("Diamond", 4000),
    ("Master", 5000),
    ("Monarch", 6000),
]


# ==================================================
# DATABASE
# ==================================================

def init_ranked_db():

    with db.connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ranked_queue (
                user_id INTEGER PRIMARY KEY,
                power INTEGER DEFAULT 0,
                points INTEGER DEFAULT 0,
                joined_at REAL NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ranked_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player1 INTEGER NOT NULL,
                player2 INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                player1_accepted INTEGER DEFAULT 0,
                player2_accepted INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                battle_chat_id INTEGER,
                battle_message_id INTEGER
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ranked_matches_status
            ON ranked_matches(status)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ranked_queue_joined
            ON ranked_queue(joined_at)
        """)


# ==================================================
# PLAYER
# ==================================================

def get_player(user_id):

    with db.connect() as conn:

        return conn.execute("""
            SELECT *
            FROM players
            WHERE user_id = ?
        """, (user_id,)).fetchone()


def is_dead(user_id):

    player = get_player(user_id)

    if not player:
        return True

    if player["is_dead"] or player["hp"] <= 0:
        return True

    return lifecycle.get_revive_remaining(user_id) > 0


def player_in_match(user_id):

    with db.connect() as conn:

        row = conn.execute("""
            SELECT id
            FROM ranked_matches
            WHERE (
                player1 = ?
                OR player2 = ?
            )
            AND status IN (
                'pending',
                'starting',
                'active'
            )
            LIMIT 1
        """, (
            user_id,
            user_id
        )).fetchone()

    return row is not None


# ==================================================
# RANK
# ==================================================

def get_rank(points):

    current = "Bronze"

    for name, minimum in RANKS:

        if points >= minimum:
            current = name

    return current


def get_rank_profile(user_id):

    ranking = lifecycle.get_ranking(user_id)

    if not ranking:

        return {
            "points": 0,
            "rank": "Bronze",
            "wins": 0,
            "losses": 0,
            "streak": 0
        }

    points = ranking["points"]

    return {
        "points": points,
        "rank": get_rank(points),
        "wins": ranking["wins"],
        "losses": ranking["losses"],
        "streak": ranking["win_streak"]
    }


# ==================================================
# QUEUE
# ==================================================

async def join_queue(user_id):

    player = get_player(user_id)

    if not player:
        return False, "اول با دستور /start ثبت‌نام کن."

    if is_dead(user_id):
        return False, "شخصیتت در حال احیاست."

    if player_in_match(user_id):
        return False, "تو در حال حاضر داخل یک مسابقه هستی."

    profile = get_rank_profile(user_id)

    power = player["power"]

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        existing = conn.execute("""
            SELECT user_id
            FROM ranked_queue
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if existing:
            return False, "تو از قبل داخل صف رنک هستی."

        conn.execute("""
            INSERT INTO ranked_queue (
                user_id,
                power,
                points,
                joined_at
            )
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            power,
            profile["points"],
            time.time()
        ))

    return True, "وارد صف رنک شدی."


async def leave_queue(user_id):

    with db.connect() as conn:

        conn.execute("""
            DELETE FROM ranked_queue
            WHERE user_id = ?
        """, (user_id,))


def find_opponent(user_id):

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        me = conn.execute("""
            SELECT *
            FROM ranked_queue
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not me:
            return None

        candidates = conn.execute("""
            SELECT *
            FROM ranked_queue
            WHERE user_id != ?
            ORDER BY
                ABS(points - ?) ASC,
                joined_at ASC
        """, (
            user_id,
            me["points"]
        )).fetchall()

        for enemy in candidates:

            p1 = conn.execute("""
                SELECT *
                FROM players
                WHERE user_id = ?
            """, (user_id,)).fetchone()

            p2 = conn.execute("""
                SELECT *
                FROM players
                WHERE user_id = ?
            """, (enemy["user_id"],)).fetchone()

            if not p1 or not p2:
                continue

            if p1["is_dead"] or p2["is_dead"]:
                continue

            if p1["hp"] <= 0 or p2["hp"] <= 0:
                continue

            if abs(me["power"] - enemy["power"]) > MAX_POWER_DIFFERENCE:
                continue

            if abs(me["points"] - enemy["points"]) > MAX_RANK_DIFFERENCE:
                continue

            now = time.time()

            revive1 = conn.execute("""
                SELECT revive_at
                FROM pvp_revives
                WHERE user_id = ?
            """, (user_id,)).fetchone()

            revive2 = conn.execute("""
                SELECT revive_at
                FROM pvp_revives
                WHERE user_id = ?
            """, (enemy["user_id"],)).fetchone()

            if revive1 and revive1["revive_at"] > now:
                continue

            if revive2 and revive2["revive_at"] > now:
                continue

            active = conn.execute("""
                SELECT id
                FROM ranked_matches
                WHERE (
                    player1 IN (?, ?)
                    OR player2 IN (?, ?)
                )
                AND status IN (
                    'pending',
                    'starting',
                    'active'
                )
                LIMIT 1
            """, (
                user_id,
                enemy["user_id"],
                user_id,
                enemy["user_id"]
            )).fetchone()

            if active:
                continue

            cursor = conn.execute("""
                INSERT INTO ranked_matches (
                    player1,
                    player2,
                    status,
                    created_at
                )
                VALUES (?, ?, 'pending', ?)
            """, (
                user_id,
                enemy["user_id"],
                now
            ))

            match_id = cursor.lastrowid

            conn.execute("""
                DELETE FROM ranked_queue
                WHERE user_id IN (?, ?)
            """, (
                user_id,
                enemy["user_id"]
            ))

            return match_id

    return None


# ==================================================
# SEARCH COMMAND
# ==================================================

async def ranked_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user
    message = update.effective_message
    chat = update.effective_chat

    if chat.type != "private":

        await message.reply_text(
            "برای جستجوی مسابقه رنک از چت خصوصی بات استفاده کن."
        )

        return

    if not RANKED_CHAT_ID:

        await message.reply_text(
            "سیستم رنک هنوز تنظیم نشده است."
        )

        return

    if not context.job_queue:

        await message.reply_text(
            "سیستم جستجوی مسابقه در دسترس نیست."
        )

        return

    success, result = await join_queue(user.id)

    if not success:

        await message.reply_text(result)
        return

    sent = await message.reply_text(
        "🔎 در حال جستجوی حریف...\n\n"
        "برای خروج از صف:\n"
        "/rankcancel"
    )

    context.job_queue.run_repeating(
        check_queue,
        interval=SEARCH_INTERVAL,
        first=SEARCH_INTERVAL,
        data={
            "user_id": user.id,
            "chat_id": sent.chat_id,
            "message_id": sent.message_id
        },
        name=f"rank_search_{user.id}"
    )


# ==================================================
# CHECK QUEUE
# ==================================================

async def check_queue(context: ContextTypes.DEFAULT_TYPE):

    data = context.job.data
    user_id = data["user_id"]

    match_id = find_opponent(user_id)

    if not match_id:
        return

    context.job.schedule_removal()

    with db.connect() as conn:

        match = conn.execute("""
            SELECT *
            FROM ranked_matches
            WHERE id = ?
        """, (match_id,)).fetchone()

    if not match:
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ قبول مسابقه",
                callback_data=f"rank_accept_{match_id}"
            ),
            InlineKeyboardButton(
                "❌ رد مسابقه",
                callback_data=f"rank_decline_{match_id}"
            )
        ]
    ])

    text = (
        "⚔️ حریف پیدا شد!\n\n"
        "هر دو بازیکن باید مسابقه را قبول کنند.\n"
        f"⏳ زمان پاسخ: {ACCEPT_TIMEOUT} ثانیه"
    )

    try:

        await context.bot.send_message(
            chat_id=match["player1"],
            text=text,
            reply_markup=keyboard
        )

        await context.bot.send_message(
            chat_id=match["player2"],
            text=text,
            reply_markup=keyboard
        )

    except Exception:

        await cancel_match(match_id)

        await notify_declined(
            context,
            {
                "player1": match["player1"],
                "player2": match["player2"]
            }
        )

        return

    context.job_queue.run_once(
        expire_match,
        ACCEPT_TIMEOUT,
        data={"match_id": match_id},
        name=f"rank_expire_{match_id}"
    )


# ==================================================
# CANCEL / EXPIRE
# ==================================================

async def cancel_match(match_id):

    with db.connect() as conn:

        conn.execute("""
            UPDATE ranked_matches
            SET status = 'cancelled'
            WHERE id = ?
              AND status = 'pending'
        """, (match_id,))


async def expire_match(context: ContextTypes.DEFAULT_TYPE):

    match_id = context.job.data["match_id"]

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        match = conn.execute("""
            SELECT *
            FROM ranked_matches
            WHERE id = ?
              AND status = 'pending'
        """, (match_id,)).fetchone()

        if not match:
            return

        conn.execute("""
            UPDATE ranked_matches
            SET status = 'expired'
            WHERE id = ?
              AND status = 'pending'
        """, (match_id,))

    await notify_declined(
        context,
        {
            "player1": match["player1"],
            "player2": match["player2"]
        },
        expired=True
    )


async def notify_declined(
    context,
    data,
    expired=False
):

    text = (
        "⌛ زمان قبول مسابقه به پایان رسید."
        if expired
        else "❌ مسابقه لغو شد."
    )

    for user_id in (data["player1"], data["player2"]):

        try:

            await context.bot.send_message(
                chat_id=user_id,
                text=text
            )

        except Exception:
            pass


def remove_search_job(context, user_id):

    if not context.job_queue:
        return

    jobs = context.job_queue.get_jobs_by_name(
        f"rank_search_{user_id}"
    )

    for job in jobs:
        job.schedule_removal()
# ==================================================
# ACCEPT / DECLINE
# ==================================================

async def ranked_response(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    user_id = query.from_user.id

    parts = query.data.split("_")

    action = parts[1]
    match_id = int(parts[2])

    should_start = False
    notify_users = None
    answer_text = "درخواست ثبت شد."

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        match = conn.execute("""
            SELECT *
            FROM ranked_matches
            WHERE id = ?
        """, (match_id,)).fetchone()

        if not match or match["status"] != "pending":

            answer_text = "این مسابقه دیگر فعال نیست."

        elif user_id not in (
            match["player1"],
            match["player2"]
        ):

            answer_text = "این درخواست برای تو نیست."

        elif time.time() - match["created_at"] > ACCEPT_TIMEOUT:

            conn.execute("""
                UPDATE ranked_matches
                SET status = 'expired'
                WHERE id = ?
                  AND status = 'pending'
            """, (match_id,))

            answer_text = "زمان قبول مسابقه تمام شده است."

            notify_users = {
                "player1": match["player1"],
                "player2": match["player2"]
            }

        elif action == "decline":

            conn.execute("""
                UPDATE ranked_matches
                SET status = 'cancelled'
                WHERE id = ?
                  AND status = 'pending'
            """, (match_id,))

            answer_text = "مسابقه رد شد."

            notify_users = {
                "player1": match["player1"],
                "player2": match["player2"]
            }

        elif action == "accept":

            column = (
                "player1_accepted"
                if user_id == match["player1"]
                else "player2_accepted"
            )

            conn.execute(
                f"""
                UPDATE ranked_matches
                SET {column} = 1
                WHERE id = ?
                  AND status = 'pending'
                """,
                (match_id,)
            )

            updated = conn.execute("""
                SELECT *
                FROM ranked_matches
                WHERE id = ?
            """, (match_id,)).fetchone()

            if (
                updated["player1_accepted"]
                and updated["player2_accepted"]
            ):

                cursor = conn.execute("""
                    UPDATE ranked_matches
                    SET status = 'starting'
                    WHERE id = ?
                      AND status = 'pending'
                """, (match_id,))

                should_start = cursor.rowcount == 1

            answer_text = "مسابقه قبول شد."

        else:

            answer_text = "درخواست نامعتبر است."

    await query.answer(
        answer_text,
        show_alert=answer_text not in (
            "مسابقه قبول شد.",
            "درخواست ثبت شد."
        )
    )

    try:

        await query.edit_message_reply_markup(
            reply_markup=None
        )

    except Exception:
        pass

    if notify_users:

        await notify_declined(
            context,
            notify_users,
            expired=answer_text.startswith("زمان")
        )

    if should_start:

        await start_ranked_battle(
            context,
            match_id
        )


# ==================================================
# START RANKED BATTLE
# ==================================================

async def start_ranked_battle(context, match_id):

    if not RANKED_CHAT_ID:

        await cancel_starting_match(match_id)
        return

    with db.connect() as conn:

        match = conn.execute("""
            SELECT *
            FROM ranked_matches
            WHERE id = ?
              AND status = 'starting'
        """, (match_id,)).fetchone()

    if not match:
        return

    p1 = get_player(match["player1"])
    p2 = get_player(match["player2"])

    if not p1 or not p2:

        await cancel_starting_match(match_id)
        return

    if is_dead(match["player1"]) or is_dead(match["player2"]):

        await cancel_starting_match(match_id)
        return

    text = (
        "⚔️ RANKED MATCH ⚔️\n\n"
        f"👤 بازیکن اول: {p1['name']}\n"
        f"👤 بازیکن دوم: {p2['name']}\n\n"
        "برای حمله به همین پیام ریپلای کن "
        "و نام مهارتت را بنویس.\n\n"
        "🛡️ دفاع به‌صورت خودکار محاسبه می‌شود."
    )

    try:

        battle_message = await context.bot.send_message(
            chat_id=int(RANKED_CHAT_ID),
            text=text
        )

    except Exception:

        logger.exception("Could not send ranked battle message.")

        await cancel_starting_match(match_id)
        return

    try:

        with db.connect() as conn:

            conn.execute("BEGIN IMMEDIATE")

            current = conn.execute("""
                SELECT *
                FROM ranked_matches
                WHERE id = ?
                  AND status = 'starting'
            """, (match_id,)).fetchone()

            if not current:
                return

            conn.execute("""
                INSERT INTO pvp_matches (
                    chat_id,
                    message_id,
                    player1,
                    player2,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, 'active', ?)
            """, (
                battle_message.chat_id,
                battle_message.message_id,
                match["player1"],
                match["player2"],
                time.time()
            ))

            conn.execute("""
                UPDATE ranked_matches
                SET
                    status = 'active',
                    battle_chat_id = ?,
                    battle_message_id = ?
                WHERE id = ?
                  AND status = 'starting'
            """, (
                battle_message.chat_id,
                battle_message.message_id,
                match_id
            ))

    except Exception:

        logger.exception("Could not save ranked match.")

        try:

            await battle_message.edit_text(
                "❌ شروع مسابقه با خطا مواجه شد."
            )

        except Exception:
            pass

        await cancel_starting_match(match_id)
        return

    for user_id in (
        match["player1"],
        match["player2"]
    ):

        try:

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "🔥 مسابقه رنک شروع شد!\n\n"
                    "وارد گروه مسابقه شو و برای حمله "
                    "به پیام مبارزه ریپلای کن."
                )
            )

        except Exception:

            logger.info(
                "Could not notify ranked player %s",
                user_id
            )


async def cancel_starting_match(match_id):

    with db.connect() as conn:

        conn.execute("""
            UPDATE ranked_matches
            SET status = 'cancelled'
            WHERE id = ?
              AND status = 'starting'
        """, (match_id,))


# ==================================================
# CANCEL SEARCH
# ==================================================

async def ranked_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    await leave_queue(user_id)

    remove_search_job(
        context,
        user_id
    )

    await update.effective_message.reply_text(
        "از صف جستجوی رنک خارج شدی."
    )


# ==================================================
# RANK COMMAND
# ==================================================

async def rank_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    profile = get_rank_profile(user_id)

    text = (
        "🏆 RANK PROFILE\n\n"
        f"🥇 رتبه: {profile['rank']}\n"
        f"⭐ امتیاز: {profile['points']}\n"
        f"✅ برد: {profile['wins']}\n"
        f"❌ باخت: {profile['losses']}\n"
        f"🔥 برد متوالی: {profile['streak']}"
    )

    await update.effective_message.reply_text(text)


# ==================================================
# SETUP
# ==================================================

def setup_ranked(application):

    init_ranked_db()

    application.add_handler(
        CommandHandler(
            "rank",
            rank_command
        )
    )

    application.add_handler(
        CommandHandler(
            "rankcancel",
            ranked_cancel
        )
    )

    application.add_handler(
        CommandHandler(
            "ranked",
            ranked_search
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            ranked_response,
            pattern=r"^rank_(accept|decline)_\d+$"
        )
    )