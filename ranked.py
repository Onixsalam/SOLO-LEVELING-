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

logger = logging.getLogger(name)

=====================================

SETTINGS

=====================================

RANKED_CHAT_ID = os.getenv("RANKED_CHAT_ID")

SEARCH_INTERVAL = 10
ACCEPT_TIMEOUT = 60

MAX_POWER_DIFFERENCE = 500
MAX_RANK_DIFFERENCE = 500

=====================================

RANKS

=====================================

RANKS = [
(0, "Bronze"),
(1000, "Silver"),
(2000, "Gold"),
(3000, "Platinum"),
(4000, "Diamond"),
(5000, "Master"),
(6000, "Monarch")
]

def get_rank(points):

result = "Bronze"

for required, name in RANKS:

    if points >= required:
        result = name

return result

=====================================

DATABASE

=====================================

def init_ranked_db():

with db.connect() as conn:

    conn.execute("""
    CREATE TABLE IF NOT EXISTS ranked_queue (
        user_id INTEGER PRIMARY KEY,
        power INTEGER NOT NULL,
        points INTEGER NOT NULL,
        joined_at REAL NOT NULL
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS ranked_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        player1 INTEGER NOT NULL,
        player2 INTEGER NOT NULL,
        accepted1 INTEGER DEFAULT 0,
        accepted2 INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL,
        battle_message_id INTEGER,
        battle_chat_id INTEGER
    )
    """)

    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_ranked_status
    ON ranked_matches(status)
    """)

    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_ranked_players
    ON ranked_matches(player1, player2, status)
    """)

=====================================

PLAYER

=====================================

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

if lifecycle.get_revive_remaining(user_id) > 0:
    return True

return False

def player_in_match(user_id):

with db.connect() as conn:

    row = conn.execute("""
    SELECT id
    FROM ranked_matches
    WHERE status IN ('pending', 'starting', 'active')
    AND (
        player1 = ?
        OR player2 = ?
    )
    LIMIT 1
    """, (user_id, user_id)).fetchone()

return row is not None

=====================================

RANK PROFILE

=====================================

def get_rank_profile(user_id):

return lifecycle.get_rank_profile(user_id)

=====================================

JOIN QUEUE

=====================================

def join_queue(user_id):

player = get_player(user_id)

if not player:
    return False, "ابتدا با /start ثبت‌نام کن."

if is_dead(user_id):
    return False, "در وضعیت DEAD هستی و نمی‌تونی وارد Ranked بشی."

ranking = get_rank_profile(user_id)

if not ranking:
    return False, "اطلاعات رنک بازیکن پیدا نشد."

with db.connect() as conn:

    conn.execute("BEGIN IMMEDIATE")

    existing = conn.execute("""
    SELECT user_id
    FROM ranked_queue
    WHERE user_id = ?
    """, (user_id,)).fetchone()

    if existing:
        return False, "از قبل داخل صف جست‌وجو هستی."

    active = conn.execute("""
    SELECT id
    FROM ranked_matches
    WHERE status IN ('pending', 'starting', 'active')
    AND (
        player1 = ?
        OR player2 = ?
    )
    LIMIT 1
    """, (user_id, user_id)).fetchone()

    if active:
        return False, "تو یک مسابقه فعال داری."

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

=====================================

LEAVE QUEUE

=====================================

def leave_queue(user_id):

with db.connect() as conn:

    conn.execute("""
    DELETE FROM ranked_queue
    WHERE user_id = ?
    """, (user_id,))

=====================================

FIND OPPONENT

=====================================

def find_opponent(user_id):

with db.connect() as conn:

    conn.execute("BEGIN IMMEDIATE")

    current = conn.execute("""
    SELECT *
    FROM ranked_queue
    WHERE user_id = ?
    """, (user_id,)).fetchone()

    if not current:
        return None

    # بررسی اینکه بازیکن قبلاً وارد مسابقه نشده باشد

    active = conn.execute("""
    SELECT id
    FROM ranked_matches
    WHERE status IN ('pending', 'starting', 'active')
    AND (
        player1 = ?
        OR player2 = ?
    )
    LIMIT 1
    """, (user_id, user_id)).fetchone()

    if active:

        conn.execute("""
        DELETE FROM ranked_queue
        WHERE user_id = ?
        """, (user_id,))

        return None

    candidates = conn.execute("""
    SELECT q.*
    FROM ranked_queue q
    JOIN players p ON p.user_id = q.user_id
    WHERE q.user_id != ?
    AND p.is_dead = 0
    ORDER BY
        ABS(q.power - ?) + ABS(q.points - ?) ASC
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

        # بررسی وضعیت احیای حریف

        revive = conn.execute("""
        SELECT revive_at
        FROM pvp_revives
        WHERE user_id = ?
        """, (candidate["user_id"],)).fetchone()

        if revive and revive["revive_at"] > int(time.time()):
            continue

        # بررسی مسابقه فعال حریف

        candidate_active = conn.execute("""
        SELECT id
        FROM ranked_matches
        WHERE status IN ('pending', 'starting', 'active')
        AND (
            player1 = ?
            OR player2 = ?
        )
        LIMIT 1
        """, (
            candidate["user_id"],
            candidate["user_id"]
        )).fetchone()

        if candidate_active:
            continue

        now = time.time()

        cursor = conn.execute("""
        INSERT INTO ranked_matches (
            player1,
            player2,
            accepted1,
            accepted2,
            status,
            created_at,
            expires_at
        )
        VALUES (?, ?, 0, 0, 'pending', ?, ?)
        """, (
            user_id,
            candidate["user_id"],
            now,
            now + ACCEPT_TIMEOUT
        ))

        conn.execute("""
        DELETE FROM ranked_queue
        WHERE user_id IN (?, ?)
        """, (
            user_id,
            candidate["user_id"]
        ))

        return {
            "match_id": cursor.lastrowid,
            "player1": user_id,
            "player2": candidate["user_id"]
        }

return None

=====================================

SEARCH BUTTON

=====================================

async def ranked_search(
update: Update,
context: ContextTypes.DEFAULT_TYPE
):

query = update.callback_query
user_id = query.from_user.id

if query.message.chat.type != "private":

    await query.answer(
        "این بخش فقط در چت خصوصی است.",
        show_alert=True
    )

    return

if not RANKED_CHAT_ID:

    await query.answer(
        "گروه Ranked Arena هنوز تنظیم نشده.",
        show_alert=True
    )

    return

if not context.job_queue:

    await query.answer(
        "سیستم جست‌وجو در دسترس نیست.",
        show_alert=True
    )

    return

success, result = join_queue(user_id)

if not success:

    await query.answer(
        result,
        show_alert=True
    )

    return

await query.answer()

await query.edit_message_text(
    "🔍 RANKED MATCH SEARCH\n\n"
    "در حال پیدا کردن حریف مناسب...\n\n"
    "⚔️ جست‌وجو بر اساس قدرت و امتیاز رنک انجام می‌شه.",
    reply_markup=InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "❌ Cancel Search",
                callback_data="ranked_cancel"
            )
        ]
    ])
)

# جلوگیری از ساخت Job تکراری

remove_search_job(context, user_id)

context.job_queue.run_repeating(
    check_queue,
    interval=SEARCH_INTERVAL,
    first=1,
    data={
        "user_id": user_id,
        "chat_id": query.message.chat_id
    },
    name=f"ranked_search_{user_id}"
)

=====================================

CHECK QUEUE

=====================================

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

    remove_search_job(context, user_id)
    return

match = find_opponent(user_id)

if not match:
    return

remove_search_job(context, user_id)

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

sent_players = []

for player_id in (
    match["player1"],
    match["player2"]
):

    try:

        await context.bot.send_message(
            chat_id=player_id,
            text=(
                "⚔️ RANKED OPPONENT FOUND!\n\n"
                "حریف مناسبی پیدا شد.\n"
                "۶۰ ثانیه فرصت داری درخواست رو قبول کنی."
            ),
            reply_markup=keyboard
        )

        sent_players.append(player_id)

    except Exception:

        cancel_match(match_id)

        leave_queue(match["player1"])
        leave_queue(match["player2"])

        for sent_id in sent_players:

            try:
                await context.bot.send_message(
                    chat_id=sent_id,
                    text="❌ ارسال درخواست برای حریف ممکن نشد. مسابقه لغو شد."
                )
            except Exception:
                pass

        return

context.job_queue.run_once(
    expire_match,
    when=ACCEPT_TIMEOUT,
    data={"match_id": match_id},
    name=f"rank_expire_{match_id}"
)

=====================================

REMOVE SEARCH JOB

=====================================

def remove_search_job(context, user_id):

if not context.job_queue:
    return

for job in context.job_queue.get_jobs_by_name(
    f"ranked_search_{user_id}"
):

    job.schedule_removal()

=====================================

CANCEL MATCH

=====================================

def cancel_match(match_id):

with db.connect() as conn:

    match = conn.execute("""
    SELECT *
    FROM ranked_matches
    WHERE id = ?
    AND status = 'pending'
    """, (match_id,)).fetchone()

    if not match:
        return None

    conn.execute("""
    UPDATE ranked_matches
    SET status = 'cancelled'
    WHERE id = ?
    AND status = 'pending'
    """, (match_id,))

return match

=====================================

EXPIRE MATCH

=====================================

async def expire_match(context):

match_id = context.job.data["match_id"]

match = cancel_match(match_id)

if not match:
    return

for player_id in (
    match["player1"],
    match["player2"]
):

    try:

        await context.bot.send_message(
            chat_id=player_id,
            text=(
                "⌛ درخواست Ranked منقضی شد.\n"
                "یکی از بازیکن‌ها در زمان مقرر پاسخ نداد."
            )
        )

    except Exception:
        pass

=====================================

ACCEPT / DECLINE

=====================================

async def ranked_response(
update: Update,
context: ContextTypes.DEFAULT_TYPE
):

query = update.callback_query
user_id = query.from_user.id

parts = query.data.split("_")

action = parts[1]
match_id = int(parts[2])

other_id = None
should_start = False
declined = False
expired = False

with db.connect() as conn:

    conn.execute("BEGIN IMMEDIATE")

    match = conn.execute("""
    SELECT *
    FROM ranked_matches
    WHERE id = ?
    AND status = 'pending'
    """, (match_id,)).fetchone()

    if not match:

        await query.answer(
            "این درخواست فعال نیست.",
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

    other_id = (
        match["player2"]
        if user_id == match["player1"]
        else match["player1"]
    )

    if time.time() > match["expires_at"]:

        conn.execute("""
        UPDATE ranked_matches
        SET status = 'cancelled'
        WHERE id = ?
        AND status = 'pending'
        """, (match_id,))

        expired = True

    elif action == "decline":

        conn.execute("""
        UPDATE ranked_matches
        SET status = 'cancelled'
        WHERE id = ?
        AND status = 'pending'
        """, (match_id,))

        declined = True

    elif action == "accept":

        column = (
            "accepted1"
            if user_id == match["player1"]
            else "accepted2"
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

        if updated["accepted1"] and updated["accepted2"]:

            claim = conn.execute("""
            UPDATE ranked_matches
            SET status = 'starting'
            WHERE id = ?
            AND status = 'pending'
            AND accepted1 = 1
            AND accepted2 = 1
            """, (match_id,))

            should_start = claim.rowcount == 1

if expired:

    await query.answer(
        "زمان درخواست تمام شده.",
        show_alert=True
    )

    await query.edit_message_text(
        "⌛ درخواست مسابقه منقضی شد."
    )

    try:
        await context.bot.send_message(
            chat_id=other_id,
            text="⌛ درخواست Ranked منقضی شد."
        )
    except Exception:
        pass

    return

if declined:

    await query.answer("درخواست رد شد.")

    await query.edit_message_text(
        "❌ مسابقه لغو شد."
    )

    try:
        await context.bot.send_message(
            chat_id=other_id,
            text="❌ حریف درخواست مسابقه را رد کرد."
        )
    except Exception:
        pass

    return

await query.answer("درخواست پذیرفته شد.")

await query.edit_message_text(
    "✅ درخواست مسابقه پذیرفته شد."
)

if should_start:

    await start_ranked_battle(
        context,
        match_id
    )

else:

    try:

        await context.bot.send_message(
            chat_id=other_id,
            text="حریف درخواست رو قبول کرد. منتظر تأیید تو هستیم."
        )

    except Exception:
        pass

=====================================

START RANKED BATTLE

=====================================

async def start_ranked_battle(
context,
match_id
):

if not RANKED_CHAT_ID:

    with db.connect() as conn:

        conn.execute("""
        UPDATE ranked_matches
        SET status = 'cancelled'
        WHERE id = ?
        AND status = 'starting'
        """, (match_id,))

    return

with db.connect() as conn:

    match = conn.execute("""
    SELECT *
    FROM ranked_matches
    WHERE id = ?
    AND status = 'starting'
    AND accepted1 = 1
    AND accepted2 = 1
    """, (match_id,)).fetchone()

if not match:
    return

player1 = get_player(match["player1"])
player2 = get_player(match["player2"])

if not player1 or not player2:

    cancel_starting_match(match_id)
    return

if is_dead(match["player1"]) or is_dead(match["player2"]):

    cancel_starting_match(match_id)

    for player_id in (
        match["player1"],
        match["player2"]
    ):

        try:
            await context.bot.send_message(
                chat_id=player_id,
                text="❌ مسابقه لغو شد؛ یکی از بازیکنان در وضعیت DEAD قرار دارد."
            )
        except Exception:
            pass

    return

try:

    battle_message = await context.bot.send_message(
        chat_id=int(RANKED_CHAT_ID),
        text=(
            "🏆 RANKED MATCH STARTED!\n\n"
            f"👤 {player1['name']}\n"
            f"❤️ HP: {player1['hp']}\n\n"
            "⚔️ VS ⚔️\n\n"
            f"👤 {player2['name']}\n"
            f"❤️ HP: {player2['hp']}\n\n"
            "برای حمله، روی همین پیام ریپلای کن "
            "و اسم یکی از مهارت‌های خودت رو بنویس."
        )
    )

except Exception:

    logger.exception(
        "Could not send ranked battle message."
    )

    cancel_starting_match(match_id)

    for player_id in (
        match["player1"],
        match["player2"]
    ):

        try:
            await context.bot.send_message(
                chat_id=player_id,
                text="❌ امکان شروع مسابقه در گروه آرنا وجود نداشت."
            )
        except Exception:
            pass

    return

# ثبت پیام مبارزه و فعال‌سازی مسابقه

with db.connect() as conn:

    conn.execute("BEGIN IMMEDIATE")

    current = conn.execute("""
    SELECT status
    FROM ranked_matches
    WHERE id = ?
    """, (match_id,)).fetchone()

    if not current or current["status"] != "starting":
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
    SET status = 'active',
        battle_message_id = ?,
        battle_chat_id = ?
    WHERE id = ?
    AND status = 'starting'
    """, (
        battle_message.message_id,
        battle_message.chat_id,
        match_id
    ))

for player_id in (
    match["player1"],
    match["player2"]
):

    try:

        await context.bot.send_message(
            chat_id=player_id,
            text=(
                "🏆 مسابقه Ranked شروع شد!\n"
                "به گروه Ranked Arena برو و روی پیام مبارزه ریپلای کن."
            )
        )

    except Exception:
        pass

def cancel_starting_match(match_id):

with db.connect() as conn:

    conn.execute("""
    UPDATE ranked_matches
    SET status = 'cancelled'
    WHERE id = ?
    AND status = 'starting'
    """, (match_id,))

=====================================

CANCEL SEARCH BUTTON

=====================================

async def ranked_cancel(
update: Update,
context: ContextTypes.DEFAULT_TYPE
):

query = update.callback_query
user_id = query.from_user.id

leave_queue(user_id)

remove_search_job(context, user_id)

await query.answer(
    "جست‌وجو لغو شد."
)

await query.edit_message_text(
    "❌ Ranked Search Cancelled"
)

=====================================

RANK PROFILE

=====================================

async def rank_command(
update: Update,
context: ContextTypes.DEFAULT_TYPE
):

user_id = update.effective_user.id

if not get_player(user_id):

    await update.effective_message.reply_text(
        "ابتدا با /start ثبت‌نام کن."
    )

    return

profile = get_rank_profile(user_id)

if not profile:
    await update.effective_message.reply_text(
        "اطلاعات رنک پیدا نشد."
    )
    return

await update.effective_message.reply_text(
    "🏆 RANK PROFILE\n\n"
    f"🥇 Rank: {profile['rank'