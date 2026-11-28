# shop_cards.py
# Inventory, safe Shop purchases, and image-based player cards.
# Compatible with the database.py shown in the user's repository.

import io
import logging
import sqlite3
from PIL import Image, ImageDraw, ImageFont
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import database as db

log = logging.getLogger(__name__)

# Edit this catalogue to add/remove shop items.
SHOP_ITEMS = {
    "health_potion": {
        "name": "Health Potion",
        "type": "potion",
        "price": 100,
        "emoji": "❤️",
        "description": "Restores health (item storage only for now).",
    },
    "mana_potion": {
        "name": "Mana Potion",
        "type": "potion",
        "price": 100,
        "emoji": "🔵",
        "description": "Restores mana (item storage only for now).",
    },
    "iron_sword": {
        "name": "Iron Sword",
        "type": "weapon",
        "price": 250,
        "emoji": "⚔️",
        "description": "A basic hunter weapon.",
    },
    "hunter_armor": {
        "name": "Hunter Armor",
        "type": "armor",
        "price": 300,
        "emoji": "🛡",
        "description": "Basic protective equipment.",
    },
    "shadow_crystal": {
        "name": "Shadow Crystal",
        "type": "material",
        "price": 500,
        "emoji": "💎",
        "description": "A rare crafting material.",
    },
}

# ---------- Atomic purchase ----------
def purchase_item(user_id: int, item_key: str):
    """Return (success, reason, remaining_gold). Gold and inventory change atomically."""
    item = SHOP_ITEMS.get(item_key)
    if not item:
        return False, "نامعتبر", None

    price = int(item["price"])
    if price <= 0:
        return False, "قیمت نامعتبر", None

    try:
        # Use the repository's connection context. BEGIN IMMEDIATE serializes
        # concurrent purchases; both the debit and item grant commit together.
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")

            player = conn.execute(
                "SELECT gold FROM players WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()

            if player is None:
                conn.rollback()
                return False, "بازیکن پیدا نشد", None

            if int(player["gold"]) < price:
                conn.rollback()
                return False, "سکه کافی نیست", int(player["gold"])

            debit = conn.execute(
                """
                UPDATE players
                SET gold = gold - ?
                WHERE user_id = ? AND gold >= ?
                """,
                (price, int(user_id), price),
            )
            if debit.rowcount != 1:
                conn.rollback()
                return False, "پرداخت انجام نشد", int(player["gold"])

            # Grant item inside the SAME transaction. If this fails, the
            # context manager rolls back the Gold debit as well.
            existing = conn.execute(
                """
                SELECT id FROM inventory
                WHERE user_id = ? AND item_name = ? AND item_type = ?
                LIMIT 1
                """,
                (int(user_id), item["name"], item["type"]),
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE inventory SET quantity = quantity + 1 WHERE id = ?",
                    (existing["id"],),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO inventory (user_id, item_name, item_type, quantity)
                    VALUES (?, ?, ?, 1)
                    """,
                    (int(user_id), item["name"], item["type"]),
                )

            remaining = conn.execute(
                "SELECT gold FROM players WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()["gold"]

        return True, "ok", int(remaining)

    except Exception:
        log.exception("Shop purchase failed for user_id=%s item=%s", user_id, item_key)
        return False, "خطای داخلی؛ هیچ پولی کسر نشد", None


# ---------- Image card renderer ----------
W, H = 1000, 700
BG = (8, 12, 27)
PANEL = (18, 27, 51)
CYAN = (69, 211, 255)
PURPLE = (154, 104, 255)
WHITE = (238, 244, 255)
MUTED = (150, 166, 194)
GREEN = (83, 225, 167)
RED = (255, 104, 130)


def _font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _base(title, subtitle="SHADOW LEGACY"):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    # Subtle diagonal tech lines and glow-like panels.
    for x in range(-H, W, 90):
        d.line((x, 0, x + H, H), fill=(15, 23, 43), width=2)
    d.rounded_rectangle((28, 28, W-28, H-28), radius=30,
                        outline=PURPLE, width=3)
    d.rounded_rectangle((48, 48, W-48, 150), radius=22, fill=PANEL,
                        outline=(45, 70, 111), width=2)
    d.text((78, 66), title.upper(), font=_font(42, True), fill=WHITE)
    d.text((80, 119), subtitle.upper(), font=_font(17, True), fill=CYAN)
    return im, d


def _panel(d, box, title):
    d.rounded_rectangle(box, radius=22, fill=PANEL, outline=(49, 73, 113), width=2)
    x1, y1, _, _ = box
    d.text((x1+24, y1+18), title.upper(), font=_font(19, True), fill=CYAN)


def _bar(d, x, y, width, label, value, maximum, color):
    maximum = max(1, int(maximum))
    value = max(0, min(int(value), maximum))
    d.text((x, y), f"{label}  {value:,}/{maximum:,}", font=_font(20, True), fill=WHITE)
    top = y + 34
    d.rounded_rectangle((x, top, x+width, top+20), radius=10, fill=(37, 47, 70))
    fill_w = int(width * value / maximum)
    if fill_w:
        d.rounded_rectangle((x, top, x+fill_w, top+20), radius=10, fill=color)


def _stat(d, x, y, label, value):
    d.rounded_rectangle((x, y, x+250, y+82), radius=16, fill=(25, 38, 67),
                        outline=(53, 78, 120), width=1)
    d.text((x+18, y+12), label, font=_font(17, True), fill=MUTED)
    d.text((x+18, y+38), f"{int(value):,}", font=_font(27, True), fill=WHITE)


def _send_image(update, image, caption):
    bio = io.BytesIO()
    bio.name = "shadow_legacy_card.png"
    image.save(bio, format="PNG", optimize=True)
    bio.seek(0)
    return update.effective_message.reply_photo(
        photo=InputFile(bio, filename=bio.name),
        caption=caption,
    )


def render_profile(player):
    im, d = _base("Hunter Profile")
    _panel(d, (65, 185, 935, 625), "Hunter identity")
    d.ellipse((105, 260, 335, 490), fill=(34, 48, 83), outline=PURPLE, width=7)
    d.text((170, 315), "H", font=_font(110, True), fill=CYAN)
    d.text((390, 265), str(player["name"] or "Hunter")[:24], font=_font(40, True), fill=WHITE)
    d.text((392, 330), f"RANK  {player['rank']}", font=_font(26, True), fill=PURPLE)
    d.text((392, 390), f"LEVEL  {player['level']}", font=_font(30, True), fill=CYAN)
    d.text((392, 450), f"POWER  {int(player['power']):,}", font=_font(30, True), fill=WHITE)
    d.text((105, 555), f"GOLD  {int(player['gold']):,}", font=_font(23, True), fill=GREEN)
    d.text((520, 555), f"CRYSTALS  {int(player['crystals']):,}", font=_font(23, True), fill=CYAN)
    return im


def render_status(player):
    im, d = _base("Status Window")
    _panel(d, (65, 180, 935, 635), "Hunter parameters")
    _bar(d, 105, 235, 780, "HP", player["hp"], player["max_hp"], RED)
    _bar(d, 105, 315, 780, "MP", player["mp"], player["max_mp"], CYAN)
    vals = [
        ("STR", player["STR"]), ("AGI", player["AGI"]),
        ("VIT", player["VIT"]), ("INT", player["INT"]),
        ("SEN", player["SEN"]), ("STAT POINTS", player["stat_points"]),
    ]
    positions = [(105, 405), (375, 405), (645, 405),
                 (105, 510), (375, 510), (645, 510)]
    for (label, value), (x, y) in zip(vals, positions):
        _stat(d, x, y, label, value)
    return im


def render_list_card(title, rows, empty_label="No records yet"):
    im, d = _base(title)
    _panel(d, (65, 185, 935, 635), "Collection")
    rows = list(rows)
    if not rows:
        d.text((110, 300), empty_label, font=_font(30, True), fill=MUTED)
    else:
        for i, row in enumerate(rows[:8]):
            y = 245 + i * 45
            name = str(row[0])[:30]
            detail = str(row[1]) if len(row) > 1 else ""
            d.text((110, y), f"{i+1:02d}", font=_font(20, True), fill=PURPLE)
            d.text((180, y), name, font=_font(23, True), fill=WHITE)
            if detail:
                d.text((720, y+3), detail[:18], font=_font(18), fill=CYAN)
    return im


# ---------- Telegram UI ----------
def shop_keyboard():
    rows = []
    for key, item in SHOP_ITEMS.items():
        rows.append([InlineKeyboardButton(
            f"{item['emoji']} {item['name']} — {item['price']} Gold",
            callback_data=f"sl_buy:{key}",
        )])
    rows.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="menu_home")])
    return InlineKeyboardMarkup(rows)


async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    player = db.get_player(update.effective_user.id)
    if not player:
        await update.effective_message.reply_text("ابتدا /start را اجرا کن.")
        return
    lines = [f"🪙 Gold: {player['gold']}", "", "برای خرید، یک آیتم را انتخاب کن:"]
    for item in SHOP_ITEMS.values():
        lines.append(f"{item['emoji']} {item['name']} — {item['price']} Gold")
    await update.effective_message.reply_text("\n".join(lines), reply_markup=shop_keyboard())


async def inventory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_inventory(update.effective_user.id)
    if not rows:
        await update.effective_message.reply_text("🎒 Inventory خالی است.")
        return
    lines = ["🎒 INVENTORY"]
    for row in rows:
        lines.append(f"• {row['item_name']} × {row['quantity']} ({row['item_type']})")
    await update.effective_message.reply_text("\n".join(lines))


async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q.message or q.message.chat.type != "private" or q.from_user.id != q.message.chat.id:
        await q.answer("این فروشگاه متعلق به شخص دیگری است.", show_alert=True)
        return
    item_key = q.data.split(":", 1)[1]
    ok, reason, remaining = purchase_item(q.from_user.id, item_key)
    if ok:
        await q.answer("خرید انجام شد.")
        item = SHOP_ITEMS[item_key]
        await q.edit_message_text(
            f"✅ خرید موفق!\n{item['emoji']} {item['name']}\n🪙 موجودی باقی‌مانده: {remaining}",
            reply_markup=shop_keyboard(),
        )
    else:
        # No debit is committed on failure.
        msg = "❌ خرید ناموفق بود؛ هیچ Goldای از حسابت کم نشد."
        if reason == "سکه کافی نیست" and remaining is not None:
            msg += f"\nموجودی فعلی: {remaining} Gold"
        await q.answer(msg, show_alert=True)


async def card_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    player = db.get_player(update.effective_user.id)
    if not player:
        await update.effective_message.reply_text("ابتدا /start را اجرا کن.")
        return
    kind = context.args[0].lower() if context.args else "profile"
    if kind == "profile":
        image = render_profile(player)
        await _send_image(update, image, "👤 Profile Card")
    elif kind == "status":
        image = render_status(player)
        await _send_image(update, image, "📊 Status Card")
    elif kind == "inventory":
        rows = [(r["item_name"], f"x{r['quantity']}") for r in db.get_inventory(update.effective_user.id)]
        await _send_image(update, render_list_card("Inventory", rows), "🎒 Inventory Card")
    elif kind == "shadows":
        rows = [(r["shadow_name"], f"{r['shadow_rank']} • Lv {r['level']}") for r in db.get_shadows(update.effective_user.id)]
        await _send_image(update, render_list_card("Shadow Army", rows), "🌑 Shadow Card")
    elif kind == "titles":
        rows = [(r["title_name"], "ACTIVE" if r["active"] else "") for r in db.get_titles(update.effective_user.id)]
        await _send_image(update, render_list_card("Titles", rows), "🏆 Title Card")
    elif kind == "monsters":
        rows = [(r["monster_name"], f"x{r['quantity']}") for r in db.get_monsters(update.effective_user.id)]
        await _send_image(update, render_list_card("Monster Collection", rows), "👹 Monster Collection Card")
    else:
        await update.effective_message.reply_text(
            "استفاده:\n/card profile\n/card status\n/card inventory\n/card shadows\n/card titles\n/card monsters"
        )


def setup_shop_cards(application):
    application.add_handler(CommandHandler("shop", shop_command))
    application.add_handler(CommandHandler("inventory", inventory_command))
    application.add_handler(CommandHandler("card", card_command))
    application.add_handler(CallbackQueryHandler(shop_callback, pattern=r"^sl_buy:"))
