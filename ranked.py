import time

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


# =====================================
# SETTINGS
# =====================================

SEARCH_INTERVAL = 15
MAX_POWER_DIFFERENCE = 500
MAX_RANK_DIFFERENCE = 500


# =====================================
# DATABASE
# =====================================

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
            created_at REAL NOT NULL
        )
        """)


# =====================================
# PLAYER
# =====================================

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

    if player["is_dead"]:
        return True

    return lifecycle.get_revive_remaining(user_id) > 0


# =====================================
# QUEUE
# =====================================

def join_queue(user_id):

    player = get_player(user_id)

    if not player or is_dead(user_id):
        return False, "تو نمی‌تونی وارد صف مسابقات بشی."

    ranking = lifecycle.get_rank_profile(user_id)

    with db.connect() as conn:

        existing = conn.execute("""
        SELECT user_id
        FROM ranked_queue
        WHERE user_id = ?
        """, (user_id,)).fetchone()

        if existing:
            return False, "تو از قبل داخل صف مسابقات هستی."

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
            player["power"],
            ranking["points"],
            time.time()
        ))

    return True, "وارد صف Ranked Match شدی."


def leave_queue(user_id):

    with db.connect() as conn:

        conn.execute("""
        DELETE FROM ranked_queue
        WHERE user_id = ?
        """, (user_id,))


# =====================================
# FIND OPPONENT
# =====================================

def find_opponent(user_id):

    with db.connect() as conn:

        current = conn.execute("""
        SELECT *
        FROM ranked_queue
        WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not current:
            return None

        candidates = conn.execute("""
        SELECT *
        FROM ranked_queue
        WHERE user_id != ?
        ORDER BY ABS(power - ?) + ABS(points - ?) ASC
        """, (
            user_id,
            current["power"],
            current["points"]
        )).fetchall()

        for candidate in candidates:

            power_difference = abs(
                current["power"] - candidate["power"]
            )

            rank_difference = abs(
                current["points"] - candidate["points"]
            )

            if power_difference > MAX_POWER_DIFFERENCE:
                continue

            if rank_difference > MAX_RANK_DIFFERENCE:
                continue

            player1 = get_player(user_id)
            player2 = get_player(candidate["user_id"])

            if not player1 or not player2:
                continue

            if is_dead(user_id) or is_dead(candidate["user_id"]):
                continue

            conn.execute("""
            DELETE FROM ranked_queue
            WHERE user_id IN (?, ?)
            """, (
                user_id,
                candidate["user_id"]
            ))

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
                candidate["user_id"],
                time.time()
            ))

            return {
                "match_id": cursor.lastrowid,
                "opponent_id": candidate["user_id"]
            }

    return None


# =====================================
# START SEARCH
# =====================================

async def ranked_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    user_id = query.from_user.id

    if query.message.chat.type != "private":
        await query.answer(
            "این بخش فقط در چت خصوصی قابل استفاده است.",
            show_alert=True
        )
        return

    success, result = join_queue(user_id)

    if not success:
        await query.answer(result, show_alert=True)
        return

    await query.answer()

    await query.edit_message_text(
        "🔍 SEARCHING FOR OPPONENT...\n\n"
        "در حال پیدا کردن حریفی با قدرت و رنک نزدیک هستیم.\n\n"
        "برای لغو جست‌وجو از دکمه زیر استفاده کن.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "❌ Cancel Search",
                    callback_data="ranked_cancel"
                )
            ]
        ])
    )

    context.job_queue.run_repeating(
        check_queue,
        interval=SEARCH_INTERVAL,
        first=1,
        data={
            "user_id": user_id,
            "chat_id": query.message.chat_id,
            "message_id": query.message.message_id
        },
        name=f"ranked_{user_id}"
    )


# =====================================
# CHECK QUEUE
# =====================================

async def check_queue(context):

    data = context.job.data
    user_id = data["user_id"]

    with db.connect() as conn:

        queued = conn.execute("""
        SELECT user_id
        FROM ranked_queue
        WHERE user_id = ?
        """, (user_id,)).fetchone()

    if not queued:

        for job in context.job_queue.get_jobs_by_name(
            f"ranked_{user_id}"
        ):
            job.schedule_removal()

        return

    match = find_opponent(user_id)

    if not match:
        return

    for job in context.job_queue.get_jobs_by_name(
        f"ranked_{user_id}"
    ):
        job.schedule_removal()

    opponent_id = match["opponent_id"]
    match_id = match["match_id"]

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Accept",
                callback_data=f"rank_accept_{match_id}"
            ),

            InlineKeyboardButton(
                "❌ Decline",
                callback_data=f"rank_decline_{match_id}"
            )
        ]
    ])

    for player_id in (user_id, opponent_id):

        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=(
                    "⚔️ RANKED OPPONENT FOUND!\n\n"
                    "حریف مناسب پیدا شد.\n"
                    "برای شروع مسابقه، درخواست را قبول کن."
                ),
                reply_markup=keyboard
            )

        except Exception:
            cancel_match(match_id)
            await context.bot.send_message(
                chat_id=user_id,
                text="ارسال درخواست مسابقه ممکن نشد. جست‌وجو لغو شد."
            )
            return


# =====================================
# CANCEL MATCH
# =====================================

def cancel_match(match_id):

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
        """, (match_id,))

        conn.execute("""
        DELETE FROM ranked_queue
        WHERE user_id IN (?, ?)
        """, (
            match["player1"],
            match["player2"]
        ))


# =====================================
# ACCEPT / DECLINE
# =====================================

async def ranked_response(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    user_id = query.from_user.id

    data = query.data.split("_")
    action = data[1]
    match_id = int(data[2])

    with db.connect() as conn:

        match = conn.execute("""
        SELECT *
        FROM ranked_matches
        WHERE id = ?
        AND status = 'pending'
        """, (match_id,)).fetchone()

        if not match:
            await query.answer(
                "این درخواست دیگر فعال نیست.",
                show_alert=True
            )
            return

        if user_id not in (
            match["player1"],
            match["player2"]
        ):
            await query.answer(
                "این درخواست برای تو نیست.",
                show_alert=True
            )
            return

        if action == "decline":

            conn.execute("""
            UPDATE ranked_matches
            SET status = 'cancelled'
            WHERE id = ?
            """, (match_id,))

            await query.answer("درخواست رد شد.")

            await query.edit_message_text(
                "❌ مسابقه Ranked لغو شد."
            )

            other_id = (
                match["player2"]
                if user_id == match["player1"]
                else match["player1"]
            )

            try:
                await context.bot.send_message(
                    chat_id=other_id,
                    text="حریف درخواست مسابقه را رد کرد."
                )
            except Exception:
                pass

            return

        conn.execute("""
        UPDATE ranked_matches
        SET status = 'accepted'
        WHERE id = ?
        """, (match_id,))

    await query.answer("درخواست پذیرفته شد.")

    await query.edit_message_text(
        "✅ درخواست مسابقه پذیرفته شد.\n\n"
        "مرحله اتصال مسابقه به سیستم مبارزه "
        "در بخش بعدی پیاده‌سازی می‌شود."
    )