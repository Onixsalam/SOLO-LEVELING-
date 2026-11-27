import os
import time
import logging

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

import database as db
import pvp_lifecycle as lifecycle


logger = logging.getLogger(__name__)

RANKED_CHAT_ID = os.getenv("RANKED_CHAT_ID")

SEARCH_INTERVAL = 10
ACCEPT_TIMEOUT = 60

MAX_POWER_DIFFERENCE = 500
MAX_RANK_DIFFERENCE = 500

RANKS = [
    (0, "Bronze"),
    (1000, "Silver"),
    (2000, "Gold"),
    (3000, "Platinum"),
    (4000, "Diamond"),
    (5000, "Master"),
    (6000, "Monarch")
]


# =====================================
# DATABASE
# =====================================

def init_ranked_db():

    with db.connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ranked_queue (
                user_id INTEGER PRIMARY KEY,
                joined_at INTEGER NOT NULL
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
                created_at INTEGER NOT NULL,
                battle_chat_id INTEGER,
                battle_message_id INTEGER
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_ranked_status
            ON ranked_matches(status)
        """)

        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(ranked_matches)"
            ).fetchall()
        }

        if "battle_chat_id" not in columns:
            conn.execute("""
                ALTER TABLE ranked_matches
                ADD COLUMN battle_chat_id INTEGER
            """)

        if "battle_message_id" not in columns:
            conn.execute("""
                ALTER TABLE ranked_matches
                ADD COLUMN battle_message_id INTEGER
            """)


# =====================================
# PLAYER DATA
# =====================================

def get_player(user_id):

    with db.connect() as conn:

        return conn.execute("""
            SELECT *
            FROM players
            WHERE user_id = ?
        """, (user_id,)).fetchone()


def get_rank_points(user_id):

    ranking = lifecycle.get_ranking(user_id)

    if not ranking:
        return 0

    return int(ranking["points"] or 0)


def get_rank_name(points):

    rank_name = "Bronze"

    for required, name in RANKS:

        if points >= required:
            rank_name = name

    return rank_name


def is_dead(user_id):

    player = get_player(user_id)

    if not player:
        return True

    return bool(
        player["is_dead"] or player["hp"] <= 0
    )


def is_in_match(user_id):

    with db.connect() as conn:

        row = conn.execute("""
            SELECT id
            FROM ranked_matches
            WHERE status IN (
                'pending',
                'starting',
                'active'
            )
            AND (
                player1 = ?
                OR player2 = ?
            )
            LIMIT 1
        """, (
            user_id,
            user_id
        )).fetchone()

        if row:
            return True

        row = conn.execute("""
            SELECT id
            FROM pvp_matches
            WHERE status IN (
                'active',
                'finishing'
            )
            AND (
                player1 = ?
                OR player2 = ?
            )
            LIMIT 1
        """, (
            user_id,
            user_id
        )).fetchone()

    return row is not None


# =====================================
# QUEUE
# =====================================

def join_queue(user_id):

    if not get_player(user_id):
        return False, "ابتدا ربات را در چت خصوصی Start کن."

    if is_dead(user_id):
        return False, "شخصیت تو در وضعیت مرگ قرار دارد."

    if is_in_match(user_id):
        return False, "تو در حال حاضر داخل یک مبارزه هستی."

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        existing = conn.execute("""
            SELECT user_id
            FROM ranked_queue
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if existing:
            return False, "تو از قبل داخل صف Ranked هستی."

        conn.execute("""
            INSERT INTO ranked_queue (
                user_id,
                joined_at
            )
            VALUES (?, ?)
        """, (
            user_id,
            int(time.time())
        ))

    return True, "وارد صف Ranked شدی."


def leave_queue(user_id):

    with db.connect() as conn:

        cursor = conn.execute("""
            DELETE FROM ranked_queue
            WHERE user_id = ?
        """, (user_id,))

    return cursor.rowcount > 0


# =====================================
# MATCHMAKING
# =====================================

def find_opponent(user_id):

    player = get_player(user_id)

    if not player:
        return None

    my_points = get_rank_points(user_id)
    my_power = int(player["power"] or 0)

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        queued = conn.execute("""
            SELECT user_id
            FROM ranked_queue
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not queued:
            return None

        candidates = conn.execute("""
            SELECT q.user_id, q.joined_at,
                   p.power, p.hp, p.is_dead
            FROM ranked_queue q
            JOIN players p
                ON p.user_id = q.user_id
            WHERE q.user_id != ?
            ORDER BY q.joined_at ASC
        """, (user_id,)).fetchall()

        for candidate in candidates:

            opponent_id = candidate["user_id"]

            if candidate["is_dead"] or candidate["hp"] <= 0:
                conn.execute("""
                    DELETE FROM ranked_queue
                    WHERE user_id = ?
                """, (opponent_id,))
                continue

            if candidate["user_id"] == user_id:
                continue

            opponent_points = get_rank_points(
                opponent_id
            )

            opponent_power = int(
                candidate["power"] or 0
            )

            if abs(my_points - opponent_points) > MAX_RANK_DIFFERENCE:
                continue

            if abs(my_power - opponent_power) > MAX_POWER_DIFFERENCE:
                continue

            active = conn.execute("""
                SELECT id
                FROM ranked_matches
                WHERE status IN (
                    'pending',
                    'starting',
                    'active'
                )
                AND (
                    player1 IN (?, ?)
                    OR player2 IN (?, ?)
                )
                LIMIT 1
            """, (
                user_id,
                opponent_id,
                user_id,
                opponent_id
            )).fetchone()

            if active:
                continue

            conn.execute("""
                INSERT INTO ranked_matches (
                    player1,
                    player2,
                    status,
                    player1_accepted,
                    player2_accepted,
                    created_at
                )
                VALUES (?, ?, 'pending', 0, 0, ?)
            """, (
                user_id,
                opponent_id,
                int(time.time())
            ))

            match_id = conn.execute(
                "SELECT last_insert_rowid()"
            ).fetchone()[0]

            conn.execute("""
                DELETE FROM ranked_queue
                WHERE user_id IN (?, ?)
            """, (
                user_id,
                opponent_id
            ))

            return {
                "id": match_id,
                "player1": user_id,
                "player2": opponent_id
            }

    return None


# =====================================
# SEARCH JOB
# =====================================

async def ranked_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    if message.chat.type != "private":
        await message.reply_text(
            "جستجوی Ranked فقط در چت خصوصی انجام می‌شود."
        )
        return

    if not RANKED_CHAT_ID:

        await message.reply_text(
            "⚠️ بخش Ranked هنوز تنظیم نشده است."
        )
        return

    if not context.job_queue:

        await message.reply_text(
            "سیستم زمان‌بندی ربات فعال نیست."
        )
        return

    success, result_message = join_queue(user.id)

    if not success:

        await message.reply_text(result_message)
        return

    await message.reply_text(
        "🔎 جستجوی حریف Ranked آغاز شد.\n"
        "برای خروج از صف از /rankcancel استفاده کن."
    )

    remove_search_job(context, user.id)

    context.job_queue.run_repeating(
        check_queue,
        interval=SEARCH_INTERVAL,
        first=1,
        data={"user_id": user.id},
        name=f"ranked_search_{user.id}",
        chat_id=user.id
    )


def remove_search_job(context, user_id):

    if not context.job_queue:
        return

    jobs = context.job_queue.get_jobs_by_name(
        f"ranked_search_{user_id}"
    )

    for job in jobs:
        job.schedule_removal()


# =====================================
# CHECK QUEUE
# =====================================

async def check_queue(context):

    user_id = context.job.data["user_id"]

    if not get_player(user_id):
        remove_search_job(context, user_id)
        leave_queue(user_id)
        return

    if is_dead(user_id) or is_in_match(user_id):
        remove_search_job(context, user_id)
        leave_queue(user_id)
        return

    match = find_opponent(user_id)

    if not match:
        return

    remove_search_job(context, match["player1"])
    remove_search_job(context, match["player2"])

    await send_accept_request(
        context,
        match["id"],
        match["player1"],
        match["player2"]
    )
# =====================================
# ACCEPT REQUEST
# =====================================

async def send_accept_request(
    context,
    match_id,
    player1,
    player2
):

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ قبول مبارزه",
                callback_data=f"rankaccept_{match_id}"
            ),
            InlineKeyboardButton(
                "❌ رد مبارزه",
                callback_data=f"rankdecline_{match_id}"
            )
        ]
    ])

    text = (
        "⚔️ حریف Ranked پیدا شد!\n\n"
        "برای شروع مبارزه، هر دو بازیکن باید تأیید کنند.\n"
        f"⏳ مهلت تأیید: {ACCEPT_TIMEOUT} ثانیه"
    )

    for user_id in (player1, player2):

        try:

            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=keyboard
            )

        except Exception:

            logger.exception(
                "Could not send ranked invitation to %s",
                user_id
            )

            cancel_match(match_id)
            return

    context.job_queue.run_once(
        expire_match,
        ACCEPT_TIMEOUT,
        data={"match_id": match_id},
        name=f"ranked_expire_{match_id}"
    )


def cancel_match(match_id):

    with db.connect() as conn:

        match = conn.execute("""
            SELECT player1, player2
            FROM ranked_matches
            WHERE id = ?
            AND status IN ('pending', 'starting')
        """, (match_id,)).fetchone()

        if not match:
            return False

        conn.execute("""
            UPDATE ranked_matches
            SET status = 'cancelled'
            WHERE id = ?
        """, (match_id,))

    return True


# =====================================
# EXPIRE MATCH
# =====================================

async def expire_match(context):

    match_id = context.job.data["match_id"]

    with db.connect() as conn:

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
            SET status = 'cancelled'
            WHERE id = ?
            AND status = 'pending'
        """, (match_id,))

    for user_id in (
        match["player1"],
        match["player2"]
    ):

        try:

            await context.bot.send_message(
                chat_id=user_id,
                text="⏰ زمان تأیید مبارزه تمام شد. مبارزه لغو شد."
            )

        except Exception:
            logger.exception("Could not notify player")


# =====================================
# ACCEPT / DECLINE
# =====================================

async def ranked_response(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query:
        return

    await query.answer()

    if query.message.chat.type != "private":
        return

    parts = query.data.split("_")

    if len(parts) != 2:
        return

    action = parts[0]
    try:
        match_id = int(parts[1])
    except ValueError:
        return

    user_id = query.from_user.id

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        match = conn.execute("""
            SELECT *
            FROM ranked_matches
            WHERE id = ?
            AND status = 'pending'
        """, (match_id,)).fetchone()

        if not match:

            await query.edit_message_text(
                "این درخواست دیگر فعال نیست."
            )
            return

        if user_id not in (
            match["player1"],
            match["player2"]
        ):

            await query.answer(
                "این درخواست متعلق به تو نیست.",
                show_alert=True
            )
            return

        if action == "rankdecline":

            conn.execute("""
                UPDATE ranked_matches
                SET status = 'cancelled'
                WHERE id = ?
                AND status = 'pending'
            """, (match_id,))

            declined = True

        elif action == "rankaccept":

            declined = False

            if user_id == match["player1"]:

                conn.execute("""
                    UPDATE ranked_matches
                    SET player1_accepted = 1
                    WHERE id = ?
                """, (match_id,))

            else:

                conn.execute("""
                    UPDATE ranked_matches
                    SET player2_accepted = 1
                    WHERE id = ?
                """, (match_id,))

            updated = conn.execute("""
                SELECT *
                FROM ranked_matches
                WHERE id = ?
            """, (match_id,)).fetchone()

            both_accepted = (
                updated["player1_accepted"]
                and updated["player2_accepted"]
            )

            if both_accepted:

                conn.execute("""
                    UPDATE ranked_matches
                    SET status = 'starting'
                    WHERE id = ?
                    AND status = 'pending'
                """, (match_id,))

        else:
            return

    if action == "rankdecline":

        await query.edit_message_text(
            "❌ درخواست مبارزه رد شد."
        )

        for player_id in (
            match["player1"],
            match["player2"]
        ):

            if player_id != user_id:

                try:
                    await context.bot.send_message(
                        player_id,
                        "حریف درخواست مبارزه را رد کرد."
                    )
                except Exception:
                    pass

        return

    await query.edit_message_text(
        "✅ تأیید تو ثبت شد."
    )

    if not both_accepted:
        return

    jobs = context.job_queue.get_jobs_by_name(
        f"ranked_expire_{match_id}"
    )

    for job in jobs:
        job.schedule_removal()

    await start_ranked_battle(
        context,
        match_id
    )


# =====================================
# START BATTLE
# =====================================

async def start_ranked_battle(
    context,
    match_id
):

    with db.connect() as conn:

        match = conn.execute("""
            SELECT *
            FROM ranked_matches
            WHERE id = ?
            AND status = 'starting'
        """, (match_id,)).fetchone()

    if not match:
        return

    player1 = match["player1"]
    player2 = match["player2"]

    if is_dead(player1) or is_dead(player2):
        cancel_match(match_id)
        return

    if not RANKED_CHAT_ID:
        cancel_match(match_id)
        return

    try:

        battle_message = await context.bot.send_message(
            chat_id=int(RANKED_CHAT_ID),
            text=(
                "🏆 مبارزه Ranked آغاز شد!\n\n"
                f"🔴 بازیکن اول: {player1}\n"
                f"🔵 بازیکن دوم: {player2}\n\n"
                "برای حمله، نام مهارتت را با Reply به همین پیام بفرست."
            )
        )

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
                    match_type,
                    ranked_match_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, 'active', 'ranked', ?, ?)
            """, (
                battle_message.chat_id,
                battle_message.message_id,
                player1,
                player2,
                match_id,
                int(time.time())
            ))

            conn.execute("""
                UPDATE ranked_matches
                SET status = 'active',
                    battle_chat_id = ?,
                    battle_message_id = ?
                WHERE id = ?
                AND status = 'starting'
            """, (
                battle_message.chat_id,
                battle_message.message_id,
                match_id
            ))

        for player_id in (player1, player2):

            await context.bot.send_message(
                chat_id=player_id,
                text=(
                    "⚔️ مبارزه Ranked تو شروع شد!\n"
                    f"حریف: {player2 if player_id == player1 else player1}\n"
                    f"گروه مبارزه: {RANKED_CHAT_ID}"
                )
            )

    except Exception:

        logger.exception(
            "Could not start ranked battle"
        )

        cancel_match(match_id)


# =====================================
# CANCEL SEARCH
# =====================================

async def ranked_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user
    message = update.effective_message

    if not user or not message:
        return

    remove_search_job(context, user.id)

    removed = leave_queue(user.id)

    if removed:

        await message.reply_text(
            "جستجوی Ranked لغو شد."
        )

    else:

        await message.reply_text(
            "تو داخل صف جستجوی Ranked نیستی."
        )


# =====================================
# RANK COMMAND
# =====================================

async def rank_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if not user:
        return

    ranking = lifecycle.get_ranking(user.id)

    if not ranking:

        points = 0
        wins = 0
        losses = 0
        streak = 0

    else:

        points = ranking["points"]
        wins = ranking["wins"]
        losses = ranking["losses"]
        streak = ranking["streak"]

    rank_name = get_rank_name(points)

    await update.effective_message.reply_text(
        "🏆 وضعیت Ranked تو\n\n"
        f"🎖 رتبه: {rank_name}\n"
        f"⭐ امتیاز: {points}\n"
        f"🥇 برد: {wins}\n"
        f"💀 باخت: {losses}\n"
        f"🔥 استریک برد: {streak}"
    )


# =====================================
# SETUP
# =====================================

def setup_ranked(application):

    init_ranked_db()

    application.add_handler(
        CommandHandler(
            "ranked",
            ranked_search
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
            "rank",
            rank_command
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            ranked_response,
            pattern=r"^rank(accept|decline)_\d+$"
        )
    )

    logger.info(
        "Ranked system loaded successfully"
    )