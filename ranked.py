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


# ==========================================
# SETTINGS
# ==========================================

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


# ==========================================
# DATABASE
# ==========================================

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
            CREATE INDEX IF NOT EXISTS
            idx_ranked_matches_status
            ON ranked_matches(status)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_ranked_queue_joined
            ON ranked_queue(joined_at)
        """)


# ==========================================
# PLAYER
# ==========================================

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
            WHERE (player1 = ? OR player2 = ?)
            AND status IN ('pending', 'starting', 'active')
            LIMIT 1
        """, (
            user_id,
            user_id
        )).fetchone()

    return row is not None


# ==========================================
# RANK
# ==========================================

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


# ==========================================
# QUEUE
# ==========================================

async def join_queue(user_id):

    player = get_player(user_id)

    if not player:
        return False, "ابتدا با دستور /start ثبت‌نام کن."

    if is_dead(user_id):
        return False, "شخصیتت در حال احیاست و فعلاً نمی‌توانی وارد رنک شوی."

    if player_in_match(user_id):
        return False, "در حال حاضر داخل یک مسابقه هستی."

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
            return False, "از قبل داخل صف رنک هستی."

        # بررسی مجدد داخل تراکنش
        active = conn.execute("""
            SELECT id
            FROM ranked_matches
            WHERE (player1 = ? OR player2 = ?)
            AND status IN ('pending', 'starting', 'active')
            LIMIT 1
        """, (
            user_id,
            user_id
        )).fetchone()

        if active:
            return False, "در حال حاضر داخل یک مسابقه هستی."

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


def remove_search_job(context, user_id):

    if not context.job_queue:
        return

    jobs = context.job_queue.get_jobs_by_name(
        f"rank_search_{user_id}"
    )

    for job in jobs:
        job.schedule_removal()


# ==========================================
# FIND OPPONENT
# ==========================================

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

        now = time.time()

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

            if abs(
                me["power"] - enemy["power"]
            ) > MAX_POWER_DIFFERENCE:
                continue

            if abs(
                me["points"] - enemy["points"]
            ) > MAX_RANK_DIFFERENCE:
                continue

            # بررسی زمان احیا
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

            # جلوگیری از مسابقه هم‌زمان
            active = conn.execute("""
                SELECT id
                FROM ranked_matches
                WHERE (
                    player1 IN (?, ?)
                    OR player2 IN (?, ?)
                )
                AND status IN ('pending', 'starting', 'active')
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

            return {
                "match_id": match_id,
                "player1": user_id,
                "player2": enemy["user_id"]
            }

    return None
# ==========================================
# START SEARCH
# ==========================================

async def start_search(update, context, user_id):

    if update.effective_chat.type != "private":

        if update.callback_query:
            await update.callback_query.answer(
                "جست‌وجوی رنک فقط در چت خصوصی است.",
                show_alert=True
            )

        else:
            await update.effective_message.reply_text(
                "جست‌وجوی رنک فقط در چت خصوصی است."
            )

        return

    if not RANKED_CHAT_ID:

        message = (
            "سیستم رنک هنوز تنظیم نشده است.\n"
            "مدیر بات باید RANKED_CHAT_ID را در Railway تنظیم کند."
        )

        if update.callback_query:
            await update.callback_query.answer(
                message,
                show_alert=True
            )
        else:
            await update.effective_message.reply_text(message)

        return

    if not context.job_queue:

        message = "سیستم جست‌وجوی مسابقه در دسترس نیست."

        if update.callback_query:
            await update.callback_query.answer(
                message,
                show_alert=True
            )
        else:
            await update.effective_message.reply_text(message)

        return

    success, message = await join_queue(user_id)

    if update.callback_query:

        await update.callback_query.answer(
            message,
            show_alert=not success
        )

    if not success:

        if update.callback_query:
            await update.callback_query.message.reply_text(message)
        else:
            await update.effective_message.reply_text(message)

        return

    sent = await context.bot.send_message(
        chat_id=user_id,
        text=(
            "🔎 در حال جست‌وجوی حریف...\n\n"
            "⏳ لطفاً منتظر بمان.\n"
            "برای خروج از صف از /rankcancel استفاده کن."
        )
    )

    context.job_queue.run_repeating(
        check_queue,
        interval=SEARCH_INTERVAL,
        first=SEARCH_INTERVAL,
        data={
            "user_id": user_id,
            "chat_id": sent.chat_id,
            "message_id": sent.message_id
        },
        name=f"rank_search_{user_id}"
    )


async def ranked_search(update, context):

    user = update.effective_user

    if not user:
        return

    await start_search(
        update,
        context,
        user.id
    )


async def ranked_search_callback(update, context):

    query = update.callback_query

    if not query.message or query.message.chat.type != "private":
        await query.answer(
            "این بخش فقط در چت خصوصی قابل استفاده است.",
            show_alert=True
        )
        return

    await start_search(
        update,
        context,
        query.from_user.id
    )


# ==========================================
# QUEUE CHECK
# ==========================================

async def check_queue(context):

    user_id = context.job.data["user_id"]

    if is_dead(user_id):

        await leave_queue(user_id)
        remove_search_job(context, user_id)

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="جست‌وجوی رنک لغو شد؛ شخصیتت در حال احیاست."
            )
        except Exception:
            pass

        return

    match_data = find_opponent(user_id)

    if not match_data:
        return

    match_id = match_data["match_id"]

    player1 = match_data["player1"]
    player2 = match_data["player2"]

    remove_search_job(context, player1)
    remove_search_job(context, player2)

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
        "هر دو بازیکن باید مسابقه را قبول کنند.\n\n"
        f"⏳ زمان پاسخ: {ACCEPT_TIMEOUT} ثانیه"
    )

    try:

        await context.bot.send_message(
            chat_id=player1,
            text=text,
            reply_markup=keyboard
        )

        await context.bot.send_message(
            chat_id=player2,
            text=text,
            reply_markup=keyboard
        )

    except Exception:

        logger.exception(
            "Could not send ranked acceptance messages."
        )

        await cancel_match(match_id)

        for uid in (player1, player2):

            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text="مسابقه لغو شد؛ ارسال پیام به یکی از بازیکنان ممکن نبود."
                )
            except Exception:
                pass

        return

    context.job_queue.run_once(
        expire_match,
        ACCEPT_TIMEOUT,
        data={"match_id": match_id},
        name=f"rank_expire_{match_id}"
    )


# ==========================================
# CANCEL / EXPIRE MATCH
# ==========================================

async def cancel_match(match_id):

    with db.connect() as conn:

        conn.execute("""
            UPDATE ranked_matches
            SET status = 'cancelled'
            WHERE id = ?
            AND status = 'pending'
        """, (match_id,))


async def expire_match(context):

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

    for user_id in (
        match["player1"],
        match["player2"]
    ):

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="⌛ زمان قبول مسابقه به پایان رسید."
            )
        except Exception:
            pass


async def notify_declined(context):

    data = context.job.data

    for user_id in (
        data["player1"],
        data["player2"]
    ):

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ مسابقه توسط یکی از بازیکنان رد شد."
            )
        except Exception:
            pass


# ==========================================
# ACCEPT / DECLINE
# ==========================================

async def ranked_response(update, context):

    query = update.callback_query
    user_id = query.from_user.id

    try:

        _, action, match_id_text = query.data.split("_")
        match_id = int(match_id_text)

    except (ValueError, TypeError):

        await query.answer(
            "درخواست نامعتبر است.",
            show_alert=True
        )

        return

    if query.message.chat.type != "private":

        await query.answer(
            "این درخواست فقط در چت خصوصی معتبر است.",
            show_alert=True
        )

        return

    should_start = False
    declined = False

    with db.connect() as conn:

        conn.execute("BEGIN IMMEDIATE")

        match = conn.execute("""
            SELECT *
            FROM ranked_matches
            WHERE id = ?
        """, (match_id,)).fetchone()

        if not match or match["status"] != "pending":

            await query.answer(
                "این مسابقه دیگر فعال نیست.",
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

        if time.time() - match["created_at"] > ACCEPT_TIMEOUT:

            conn.execute("""
                UPDATE ranked_matches
                SET status = 'expired'
                WHERE id = ?
                AND status = 'pending'
            """, (match_id,))

            await query.answer(
                "زمان قبول مسابقه تمام شده.",
                show_alert=True
            )

            return

        if action == "decline":

            conn.execute("""
                UPDATE ranked_matches
                SET status = 'cancelled'
                WHERE id = ?
                AND status = 'pending'
            """, (match_id,))

            declined = True

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
                updated
                and updated["player1_accepted"]
                and updated["player2_accepted"]
            ):

                cursor = conn.execute("""
                    UPDATE ranked_matches
                    SET status = 'starting'
                    WHERE id = ?
                    AND status = 'pending'
                """, (match_id,))

                should_start = cursor.rowcount == 1

        else:

            await query.answer(
                "درخواست نامعتبر است.",
                show_alert=True
            )

            return

    if declined:

        await query.answer("مسابقه رد شد.")

        if context.job_queue:

            context.job_queue.run_once(
                notify_declined,
                0,
                data={
                    "player1": match["player1"],
                    "player2": match["player2"]
                }
            )

        try:
            await query.edit_message_reply_markup(
                reply_markup=None
            )
        except Exception:
            pass

        return

    await query.answer("مسابقه قبول شد.")

    try:
        await query.edit_message_reply_markup(
            reply_markup=None
        )
    except Exception:
        pass

    if should_start:
        await start_ranked_battle(
            context,
            match_id
        )


# ==========================================
# START RANKED BATTLE
# ==========================================

async def start_ranked_battle(context, match_id):

    if not RANKED_CHAT_ID:

        await cancel_starting_match(match_id)
        return

    try:
        chat_id = int(RANKED_CHAT_ID)
    except ValueError:
        logger.error("RANKED_CHAT_ID is not a valid integer.")
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

    player1 = get_player(match["player1"])
    player2 = get_player(match["player2"])

    if not player1 or not player2:
        await cancel_starting_match(match_id)
        return

    if is_dead(match["player1"]) or is_dead(match["player2"]):
        await cancel_starting_match(match_id)
        return

    text = (
        "⚔️ RANKED MATCH ⚔️\n\n"
        f"👤 بازیکن اول: {player1['name']}\n"
        f"❤️ HP: {player1['hp']}/{player1['max_hp']}\n\n"
        "VS\n\n"
        f"👤 بازیکن دوم: {player2['name']}\n"
        f"❤️ HP: {player2['hp']}/{player2['max_hp']}\n\n"
        "برای حمله، به همین پیام ریپلای کن "
        "و نام یکی از مهارت‌های آزادشده‌ات را بنویس.\n"
        "دفاع به‌صورت خودکار محاسبه می‌شود."
    )

    try:

        battle_message = await context.bot.send_message(
            chat_id=chat_id,
            text=text
        )

    except Exception:

        logger.exception("Could not create ranked battle message.")

        await cancel_starting_match(match_id)
        return

    try:

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

        logger.exception("Could not save ranked battle.")

        await cancel_starting_match(match_id)

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="مسابقه به دلیل خطای ثبت اطلاعات لغو شد."
            )
        except Exception:
            pass

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
            pass


async def cancel_starting_match(match_id):

    with db.connect() as conn:

        conn.execute("""
            UPDATE ranked_matches
            SET status = 'cancelled'
            WHERE id = ?
            AND status = 'starting'
        """, (match_id,))


# ==========================================
# CANCEL SEARCH
# ==========================================

async def ranked_cancel(update, context):

    user_id = update.effective_user.id

    await leave_queue(user_id)

    remove_search_job(
        context,
        user_id
    )

    await update.effective_message.reply_text(
        "از صف جست‌وجوی رنک خارج شدی."
    )


# ==========================================
# RANK PROFILE
# ==========================================

async def rank_command(update, context):

    user_id = update.effective_user.id

    if not get_player(user_id):

        await update.effective_message.reply_text(
            "ابتدا با /start ثبت‌نام کن."
        )

        return

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


# ==========================================
# SETUP
# ==========================================

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
            ranked_search_callback,
            pattern=r"^ranked_search$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            ranked_response,
            pattern=r"^rank_(accept|decline)_\d+$"
        )
    )