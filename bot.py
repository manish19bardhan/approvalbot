import asyncio
import logging
import os
from datetime import datetime, timezone

from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    ChatJoinRequest,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

import db
from config import (
    ADMIN_IDS,
    BOT_TOKEN,
    CHANNEL_ID,
    EXPIRY_CHECK_INTERVAL,
    PLANS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("premium")
router = Router()


# ---------- helpers ----------

def plan_seconds(p: dict) -> int:
    if "days" in p:
        return int(p["days"]) * 86400
    if "minutes" in p:
        return int(p["minutes"]) * 60
    return 0


# ---------- keyboards ----------

def main_kb(is_prem):
    rows = []
    if is_prem:
        rows.append([InlineKeyboardButton(text="✅ My Membership", callback_data="sub:status")])
        rows.append([InlineKeyboardButton(text="🔄 Extend", callback_data="mem:plans")])
    else:
        rows.append([InlineKeyboardButton(text="💎 Buy Membership", callback_data="mem:plans")])
    rows.append([InlineKeyboardButton(text="🏠 Start", callback_data="go:start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plans_kb():
    rows = []
    for pid, p in PLANS.items():
        rows.append([InlineKeyboardButton(
            text=f"{p['label']} — {p['stars']} ⭐",
            callback_data=f"buy:{pid}",
        )])
    rows.append([InlineKeyboardButton(text="🏠 Start", callback_data="go:start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Start", callback_data="go:start")]
    ])


def balance_confirm_kb(pid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yes, Pay Now", callback_data=f"pay:{pid}")],
        [InlineKeyboardButton(text="➕ No, Show Top-Up Steps", callback_data=f"topup:{pid}")],
        [InlineKeyboardButton(text="⬅️ Back to plans", callback_data="mem:plans")],
    ])


def topup_kb(pid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Open Web Telegram", url="https://web.telegram.org")],
        [InlineKeyboardButton(text="🔄 I've Topped Up — Retry", callback_data=f"buy:{pid}")],
        [InlineKeyboardButton(text="⬅️ Back to plans", callback_data="mem:plans")],
    ])


def fmt_left(row):
    exp = datetime.fromisoformat(row["expires_at"])
    now = datetime.now(timezone.utc)
    secs = int((exp - now).total_seconds())

    if secs <= 0:
        return "expired"
    if secs < 60:
        return f"{secs}s left"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60}s left"
    if secs < 86400:
        return f"{secs // 3600}h {(secs % 3600) // 60}m left"

    d = secs // 86400
    h = (secs % 86400) // 3600
    return f"{d}d {h}h left"


async def approve_pending(bot: Bot, user_id: int) -> bool:
    pending = db.get_join_request(user_id)
    if not pending:
        return False
    try:
        await bot.approve_chat_join_request(pending["chat_id"], user_id)
        db.clear_join_request(user_id)
        return True
    except TelegramBadRequest as e:
        log.warning("approve failed user=%s: %s", user_id, e)
        return False


# ---------- /start ----------

@router.message(CommandStart())
async def cmd_start(msg: Message):
    db.upsert_user(msg.from_user)
    active = db.get_active(msg.from_user.id)

    if active:
        text = (
            f"👋 Welcome back, <b>{msg.from_user.first_name}</b>\n\n"
            f"✅ Active until <b>{fmt_left(active)}</b>"
        )
    else:
        text = (
            f"👋 Welcome, <b>{msg.from_user.first_name}</b>\n\n"
            "🔒 This bot gates access to a private channel.\n\n"
            "<b>How it works:</b>\n"
            "1️⃣ Open the channel link\n"
            "2️⃣ Tap <b>Request to Join</b>\n"
            "3️⃣ Come back and buy a plan\n"
            "4️⃣ Bot approves you automatically\n\n"
            "⚠️ <b>Before you buy:</b> make sure you have enough ⭐ Stars. "
            "If your balance is too low, top up first: "
            "<b>Settings → My Stars → Top Up Balance</b>."
        )

    await msg.answer(text, reply_markup=main_kb(bool(active)), parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "go:start")
async def cb_go_start(cb: CallbackQuery):
    db.upsert_user(cb.from_user)
    active = db.get_active(cb.from_user.id)

    if active:
        text = (
            f"👋 <b>{cb.from_user.first_name}</b>\n\n"
            f"✅ Active until <b>{fmt_left(active)}</b>"
        )
    else:
        text = (
            f"👋 Welcome, <b>{cb.from_user.first_name}</b>\n\n"
            "🔒 This bot gates access to a private channel.\n\n"
            "<b>How it works:</b>\n"
            "1️⃣ Open the channel link\n"
            "2️⃣ Tap <b>Request to Join</b>\n"
            "3️⃣ Come back and buy a plan\n"
            "4️⃣ Bot approves you automatically\n\n"
            "⚠️ <b>Before you buy:</b> make sure you have enough ⭐ Stars. "
            "If not, top up first: <b>Settings → My Stars → Top Up Balance</b>."
        )

    try:
        await cb.message.edit_text(text, reply_markup=main_kb(bool(active)), parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        pass
    await cb.answer()


@router.callback_query(F.data == "menu:home")
async def cb_home(cb: CallbackQuery):
    active = db.get_active(cb.from_user.id)
    text = f"✅ Active until <b>{fmt_left(active)}</b>" if active else "Pick an option:"
    try:
        await cb.message.edit_text(text, reply_markup=main_kb(bool(active)), parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        pass
    await cb.answer()


# ---------- plans ----------

@router.callback_query(F.data == "mem:plans")
async def cb_plans(cb: CallbackQuery):
    active = db.get_active(cb.from_user.id)
    if active:
        text = (
            f"🔄 <b>Extend</b>\n\nCurrent: <b>{fmt_left(active)}</b>\n\n"
            "Days add on top."
        )
    else:
        text = (
            "💎 <b>Premium Membership</b>\n\n"
            "Pick a plan:"
        )
    try:
        await cb.message.edit_text(text, reply_markup=plans_kb(), parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        pass
    await cb.answer()


# ---------- buy: confirmation screen ----------

@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(cb: CallbackQuery):
    pid = cb.data.split(":", 1)[1]
    p = PLANS.get(pid)
    if not p:
        await cb.answer("Unknown plan.", show_alert=True)
        return

    text = (
        f"💎 <b>{p['label']}</b>\n\n"
        f"Cost: <b>{p['stars']} ⭐</b>\n\n"
        f"⚠️ <b>Before paying, check your Star balance.</b>\n\n"
        f"Do you have <b>{p['stars']} Stars</b> ready in your wallet?\n\n"
        f"<b>Not sure?</b> Open <b>Settings → My Stars</b> in Telegram to see your balance.\n\n"
        f"• <b>Yes</b> → proceed to pay.\n"
        f"• <b>No</b> → we'll show top-up steps first."
    )
    try:
        await cb.message.edit_text(text, reply_markup=balance_confirm_kb(pid), parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        pass
    await cb.answer()


# ---------- pay: send invoice ----------

@router.callback_query(F.data.startswith("pay:"))
async def cb_pay(cb: CallbackQuery, bot: Bot):
    pid = cb.data.split(":", 1)[1]
    p = PLANS.get(pid)
    if not p:
        await cb.answer("Unknown plan.", show_alert=True)
        return

    if "days" in p:
        desc = f"Private channel access for {p['days']} days."
    elif "minutes" in p:
        desc = f"Private channel access for {p['minutes']} minute(s)."
    else:
        desc = "Private channel access."

    try:
        await bot.send_invoice(
            chat_id=cb.from_user.id,
            title=f"Channel Access — {p['label']}",
            description=desc,
            payload=f"plan:{pid}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=p["label"], amount=p["stars"])],
        )
        await cb.answer("Invoice sent — check above.")
    except TelegramBadRequest as e:
        log.warning("invoice send failed user=%s: %s", cb.from_user.id, e)
        await cb.answer(
            "Stars failed to open. Top up manually: Settings → My Stars → Top Up Balance.",
            show_alert=True,
        )


# ---------- topup ----------

@router.callback_query(F.data.startswith("topup:"))
async def cb_topup(cb: CallbackQuery):
    pid = cb.data.split(":", 1)[1]
    p = PLANS.get(pid)
    label = p["label"] if p else "your plan"
    stars = p["stars"] if p else "?"

    text = (
        f"➕ <b>Top Up Stars First</b>\n\n"
        f"You need <b>{stars} ⭐</b> to buy <b>{label}</b>.\n\n"
        f"<b>How to top up:</b>\n\n"
        f"1️⃣ Open Telegram <b>Settings</b>\n"
        f"2️⃣ Tap <b>My Stars</b>\n"
        f"3️⃣ Tap <b>Top Up Balance</b>\n"
        f"4️⃣ Buy at least <b>{stars} ⭐</b>\n\n"
        f"<b>After you top up</b>, tap the 🔄 button below to try again."
    )
    try:
        await cb.message.edit_text(text, reply_markup=topup_kb(pid), parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        pass
    await cb.answer()


# ---------- payment ----------

@router.pre_checkout_query()
async def on_pre_checkout(pc: PreCheckoutQuery):
    parts = pc.invoice_payload.split(":")
    if len(parts) != 2 or parts[0] != "plan" or parts[1] not in PLANS:
        await pc.answer(ok=False, error_message="Invalid plan.")
        return
    await pc.answer(ok=True)


@router.message(F.successful_payment)
async def on_paid(msg: Message, bot: Bot):
    sp = msg.successful_payment
    _, pid = sp.invoice_payload.split(":")
    p = PLANS[pid]

    seconds = plan_seconds(p)

    db.upsert_user(msg.from_user)
    db.add_stars(msg.from_user.id, sp.total_amount)
    db.create_purchase(
        user_id=msg.from_user.id,
        plan_id=pid,
        duration_seconds=seconds,
        stars=sp.total_amount,
        charge_id=sp.telegram_payment_charge_id,
    )

    approved = await approve_pending(bot, msg.from_user.id)

    if approved:
        await msg.answer(
            f"✅ Payment received — <b>{sp.total_amount} ⭐</b>\n\n"
            "🎉 You're a member. Open the channel to start watching.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await msg.answer(
            f"✅ Payment received — <b>{sp.total_amount} ⭐</b>\n\n"
            "Now open the channel link and tap <b>Request to Join</b> — "
            "the bot will approve you automatically.",
            parse_mode=ParseMode.HTML,
        )
    log.info("paid user=%s stars=%s plan=%s seconds=%s",
             msg.from_user.id, sp.total_amount, pid, seconds)


# ---------- join request gate ----------

@router.chat_join_request()
async def on_join_request(req: ChatJoinRequest, bot: Bot):
    uid = req.from_user.id
    db.upsert_user(req.from_user)

    if db.is_premium(uid):
        try:
            await bot.approve_chat_join_request(req.chat.id, uid)
            try:
                await bot.send_message(uid, "✅ Approved. Welcome!")
            except TelegramBadRequest:
                pass
            log.info("approved user=%s", uid)
        except TelegramBadRequest as e:
            log.error("approve failed user=%s: %s", uid, e)
        return

    db.save_join_request(uid, req.chat.id)

    try:
        await bot.send_message(
            uid,
            "🔒 <b>Private Channel</b>\n\n"
            "Request received — membership required.\n\n"
            "Buy a plan below. The bot approves you automatically once "
            "payment is confirmed.\n\n"
            "⚠️ <b>Before you buy:</b> make sure you have enough ⭐ Stars. "
            "If not, top up first: Settings → My Stars → Top Up Balance.",
            reply_markup=plans_kb(),
            parse_mode=ParseMode.HTML,
        )
    except TelegramBadRequest as e:
        log.warning("DM failed user=%s: %s", uid, e)
        try:
            await bot.decline_chat_join_request(req.chat.id, uid)
        except TelegramBadRequest:
            pass


# ---------- subscription status ----------

@router.callback_query(F.data == "sub:status")
async def cb_status(cb: CallbackQuery):
    active = db.get_active(cb.from_user.id)
    if not active:
        text = "No active subscription."
    else:
        plan = PLANS.get(active["plan_id"], {}).get("label", active["plan_id"])
        text = (
            f"✅ <b>Active Membership</b>\n\n"
            f"Plan: {plan}\n"
            f"Expires: <b>{fmt_left(active)}</b>"
        )
    try:
        await cb.message.edit_text(text, reply_markup=back_kb(), parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        pass
    await cb.answer()


# ---------- admin ----------

def is_admin(uid):
    return uid in ADMIN_IDS


@router.message(Command("stats"))
async def cmd_stats(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    s = db.stats()
    await msg.answer(
        f"📊 <b>Stats</b>\n\n"
        f"Users: {s['users']}\n"
        f"Active subs: {s['active']}\n"
        f"Purchases: {s['purchases']}\n"
        f"Stars earned: {s['stars']} ⭐",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("grant"))
async def cmd_grant(msg: Message, bot: Bot):
    if not is_admin(msg.from_user.id):
        return
    parts = msg.text.split()
    if len(parts) != 3:
        await msg.answer("Usage: /grant <user_id> <days>")
        return
    try:
        uid = int(parts[1]); days = int(parts[2])
    except ValueError:
        await msg.answer("Numbers only.")
        return
    ref = f"adm-{uid}-{datetime.now().timestamp()}"
    db.create_purchase(
        user_id=uid, plan_id="admin",
        duration_seconds=days * 86400, stars=0, charge_id=ref,
    )
    approved = await approve_pending(bot, uid)
    await msg.answer(f"✅ Granted {days}d to {uid}." + (" Auto-approved." if approved else ""))


@router.message(Command("revoke"))
async def cmd_revoke(msg: Message, bot: Bot):
    if not is_admin(msg.from_user.id):
        return
    parts = msg.text.split()
    if len(parts) != 2:
        await msg.answer("Usage: /revoke <user_id>")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await msg.answer("User ID must be a number.")
        return
    try:
        await bot.ban_chat_member(CHANNEL_ID, uid)
        await bot.unban_chat_member(CHANNEL_ID, uid)
        await msg.answer(f"✅ Kicked {uid}.")
    except TelegramBadRequest as e:
        await msg.answer(f"Kick failed: {e}")


@router.message(Command("broadcast"))
async def cmd_broadcast(msg: Message, bot: Bot):
    if not is_admin(msg.from_user.id):
        return
    text = msg.text.partition(" ")[2].strip()
    if not text:
        await msg.answer("Usage: /broadcast <text>")
        return
    sent = 0
    for uid in db.all_paid_user_ids():
        try:
            await bot.send_message(uid, text)
            sent += 1
            await asyncio.sleep(0.05)
        except TelegramBadRequest:
            continue
    await msg.answer(f"✅ Sent to {sent} users.")


# ---------- expiry worker ----------

async def expiry_worker(bot: Bot):
    log.info("expiry worker started (interval=%ss)", EXPIRY_CHECK_INTERVAL)
    while True:
        try:
            rows = db.get_expired()
            for row in rows:
                uid = row["user_id"]
                try:
                    await bot.ban_chat_member(CHANNEL_ID, uid)
                    await bot.unban_chat_member(CHANNEL_ID, uid)
                    db.mark_kicked(row["id"])
                    log.info("kicked expired user=%s", uid)
                    try:
                        await bot.send_message(
                            uid,
                            "⏰ Membership expired. Removed from the channel. Use /start to renew.",
                        )
                    except TelegramBadRequest:
                        pass
                except TelegramBadRequest as e:
                    log.warning("kick failed user=%s: %s", uid, e)
                    db.mark_kicked(row["id"])
        except Exception as e:
            log.exception("expiry worker error: %s", e)
        await asyncio.sleep(EXPIRY_CHECK_INTERVAL)


# ---------- HTTP server (for Render health check) ----------

async def health(request):
    return web.Response(text="OK")


async def start_web_server():
    port = int(os.environ.get("PORT", 8080))
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("HTTP server listening on port %s", port)


# ---------- main ----------

async def main():
    db.init()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(CHANNEL_ID, me.id)
        if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            log.warning("Bot NOT admin in channel %s.", CHANNEL_ID)
    except TelegramBadRequest as e:
        log.warning("channel check failed: %s", e)

    asyncio.create_task(expiry_worker(bot))
    await start_web_server()

    log.info("bot starting…")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())