# -*- coding: utf-8 -*-
"""
بۆتی فەیک سێرڤیس - ڤیو / ڕیاکت / پۆست / دەنگ / مێمبەر / ماسس ڕیپۆرت
هەموو شتێک ڕاستەقینەیە بە ئەکاونتەکانی تیلیگرام
"""
import asyncio
import sqlite3
import time
import random
import os

from telethon import TelegramClient, events, Button, functions, types
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, SessionPasswordNeededError, RPCError
)

# ================== زانیاریەکان ==================
API_ID = 36735157
API_HASH = "e7cd7bc7a8df4f52a4ac57af4bc18b1f"
BOT_TOKEN = "8595349606:AAHr4lib-s3EYGDACHoB_mokCtMM7ClqWjc"
ADMIN_ID = 8101656671

# ================== داتابەیس ==================
db = sqlite3.connect("bot_database.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    points INTEGER DEFAULT 0,
    referrer INTEGER DEFAULT 0,
    join_date TEXT,
    last_daily REAL DEFAULT 0
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS accounts(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT,
    session TEXT,
    added_at TEXT
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS orders(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    service TEXT,
    link TEXT,
    amount INTEGER,
    status TEXT,
    date TEXT
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS logs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT,
    date TEXT
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS blocked(
    user_id INTEGER PRIMARY KEY
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY,
    value TEXT
)""")
db.commit()

DEFAULT_SETTINGS = {
    "gift_amount": "50",       # نرخی هەدیەی ڕۆژانە
    "ref_points": "25",        # خاڵی بانگهێشتکردن
    "price_view": "1",         # خاڵ بۆ هەر ڤیوێک
    "price_react": "1",        # خاڵ بۆ هەر ڕیاکتییەک
    "price_post": "1",         # خاڵ بۆ هەر شەیرێک
    "price_vote": "1",         # خاڵ بۆ هەر دەنگێک
    "price_member": "2",       # خاڵ بۆ هەر مێمبەرێک
    "force_channel": ""        # چەناڵی جۆینی ناچاری
}
for k, v in DEFAULT_SETTINGS.items():
    cur.execute("INSERT OR IGNORE INTO settings VALUES(?,?)", (k, v))
db.commit()


def get_set(key):
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    r = cur.fetchone()
    return r[0] if r else DEFAULT_SETTINGS.get(key, "")


def set_set(key, value):
    cur.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, str(value)))
    db.commit()


def add_log(text):
    t = time.strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("INSERT INTO logs(text,date) VALUES(?,?)", (text, t))
    db.commit()


def add_points(user_id, amount):
    cur.execute("UPDATE users SET points=points+? WHERE user_id=?", (amount, user_id))
    db.commit()


def get_points(user_id):
    cur.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
    r = cur.fetchone()
    return r[0] if r else 0


def is_blocked(user_id):
    cur.execute("SELECT * FROM blocked WHERE user_id=?", (user_id,))
    return cur.fetchone() is not None


# ================== بۆت ==================
bot = TelegramClient("bot_main", API_ID, API_HASH)
bot_state = {}   # بۆ فلۆوی ئادمین
user_state = {}  # بۆ فلۆوی بەکارهێنەر

EMOJIS = ["👍", "❤️", "🔥", "😮", "😂", "🎉", "🥰", "👏", "😢", "🤔"]


def extract_target(text):
    """لینک یان یوزەرنێمی چەناڵ دەکاتەوە"""
    text = text.strip()
    if "t.me/" in text:
        text = text.split("t.me/")[-1].split("?")[0].split("/")[0]
    if text.startswith("@"):
        text = text[1:]
    return text


async def get_account_clients(count):
    """ئەکاونتەکان دەهێنێتەوە و کڵاینت دروست دەکات"""
    cur.execute("SELECT id, phone, session FROM accounts LIMIT ?", (count,))
    rows = cur.fetchall()
    clients = []
    for r in rows:
        c = TelegramClient(StringSession(r[2]), API_ID, API_HASH)
        clients.append((r[0], r[1], c))
    return clients


async def connect_all(clients):
    good = []
    for acc_id, phone, c in clients:
        try:
            await c.connect()
            if await c.is_user_authorized():
                good.append((acc_id, phone, c))
            else:
                await c.disconnect()
        except Exception as e:
            add_log(f"❌ ئەکاونت {phone}: {e}")
    return good


async def resolve(client, target):
    return await client.get_entity(target)


# ================== ئیشەکان (فەیک ڤیو/ڕیاکت/...) ==================
async def do_views(target, amount):
    logs = []
    clients = await get_account_clients(amount)
    good = await connect_all(clients)
    if not good:
        return ["❌ هیچ ئەکاونتێک بەردەست نییە"]
    entity = None
    done = 0
    for acc_id, phone, c in good:
        try:
            if entity is None:
                entity = await resolve(c, target)
            msgs = await c.get_messages(entity, limit=20)
            ids = [m.id for m in msgs if m.id > 0]
            if ids:
                await c(functions.messages.GetMessagesViewsRequest(
                    peer=entity, id=ids, increment=True))
                done += 1
                logs.append(f"✅ {phone}: ڤیو درا بۆ {len(ids)} پۆست")
        except FloodWaitError as e:
            logs.append(f"⏳ {phone}: فلود وەیت {e.seconds}چرکە")
        except Exception as e:
            logs.append(f"❌ {phone}: {str(e)[:60]}")
        finally:
            await c.disconnect()
    logs.append(f"📊 کۆی ڤیو: {done} ئەکاونت")
    return logs


async def do_reacts(target, amount):
    logs = []
    clients = await get_account_clients(amount)
    good = await connect_all(clients)
    if not good:
        return ["❌ هیچ ئەکاونتێک بەردەست نییە"]
    entity = None
    done = 0
    for acc_id, phone, c in good:
        try:
            if entity is None:
                entity = await resolve(c, target)
            msgs = await c.get_messages(entity, limit=20)
            for m in msgs[:random.randint(3, 10)]:
                if m.id > 0:
                    try:
                        await c(functions.messages.SendReactionRequest(
                            peer=entity, msg_id=m.id,
                            reaction=types.ReactionEmoji(emoticon=random.choice(EMOJIS))))
                    except RPCError:
                        pass
            done += 1
            logs.append(f"✅ {phone}: ڕیاکت درا")
        except FloodWaitError as e:
            logs.append(f"⏳ {phone}: فلود وەیت {e.seconds}چرکە")
        except Exception as e:
            logs.append(f"❌ {phone}: {str(e)[:60]}")
        finally:
            await c.disconnect()
    logs.append(f"📊 کۆی ڕیاکت: {done} ئەکاونت")
    return logs


async def do_posts(target, amount):
    """پۆستەکانی چەناڵ بە ئەکاونتەکان شەیر/فۆروەرد دەکرێن"""
    logs = []
    clients = await get_account_clients(amount)
    good = await connect_all(clients)
    if not good:
        return ["❌ هیچ ئەکاونتێک بەردەست نییە"]
    entity = None
    done = 0
    for acc_id, phone, c in good:
        try:
            if entity is None:
                entity = await resolve(c, target)
            msgs = await c.get_messages(entity, limit=5)
            if msgs:
                m = random.choice(msgs)
                await c.forward_messages("me", m.id, entity)  # بۆ سیڤد مەسج
                done += 1
                logs.append(f"✅ {phone}: پۆستی فۆروەرد کرا")
        except FloodWaitError as e:
            logs.append(f"⏳ {phone}: فلود وەیت {e.seconds}چرکە")
        except Exception as e:
            logs.append(f"❌ {phone}: {str(e)[:60]}")
        finally:
            await c.disconnect()
    logs.append(f"📊 کۆی شەیر: {done} ئەکاونت")
    return logs


async def do_votes(target, amount):
    logs = []
    clients = await get_account_clients(amount)
    good = await connect_all(clients)
    if not good:
        return ["❌ هیچ ئەکاونتێک بەردەست نییە"]
    entity = None
    done = 0
    for acc_id, phone, c in good:
        try:
            if entity is None:
                entity = await resolve(c, target)
            msgs = await c.get_messages(entity, limit=50)
            polls = [m for m in msgs if m.poll]
            if polls:
                p = random.choice(polls)
                options = p.poll.poll.answers
                opt = random.choice(options).option
                await c(functions.messages.SendVoteRequest(
                    peer=entity, msg_id=p.id, options=[opt]))
                done += 1
                logs.append(f"✅ {phone}: دەنگ درا")
        except FloodWaitError as e:
            logs.append(f"⏳ {phone}: فلود وەیت {e.seconds}چرکە")
        except Exception as e:
            logs.append(f"❌ {phone}: {str(e)[:60]}")
        finally:
            await c.disconnect()
    logs.append(f"📊 کۆی دەنگ: {done} ئەکاونت")
    return logs


async def do_members(target, amount):
    logs = []
    clients = await get_account_clients(amount)
    good = await connect_all(clients)
    if not good:
        return ["❌ هیچ ئەکاونتێک بەردەست نییە"]
    clients = good
    done = 0
    for acc_id, phone, c in clients:
        try:
            await c(functions.channels.JoinChannelRequest(target))
            done += 1
            logs.append(f"✅ {phone}: جۆین کرا")
        except FloodWaitError as e:
            logs.append(f"⏳ {phone}: فلود وەیت {e.seconds}چرکە")
        except Exception as e:
            logs.append(f"❌ {phone}: {str(e)[:60]}")
        finally:
            await c.disconnect()
    logs.append(f"📊 کۆی مێمبەر: {done} ئەکاونت")
    return logs


async def do_mass_report(target, amount):
    logs = []
    clients = await get_account_clients(amount)
    good = await connect_all(clients)
    if not good:
        return ["❌ هیچ ئەکاونتێک بەردەست نییە"]
    entity = None
    all_ids = []
    done = 0
    for acc_id, phone, c in good:
        try:
            if entity is None:
                entity = await resolve(c, target)
                msgs = await c.get_messages(entity, limit=50)
                all_ids = [m.id for m in msgs if m.id > 0]
            if not all_ids:
                logs.append(f"⚠️ هیچ پۆستێک نەدۆزرا")
                break
            # هەر ئەکاونت پۆستی ڕاندۆم ڕیپۆرت دەکات (بەبێ دووبارە)
            sample = random.sample(all_ids, min(len(all_ids), random.randint(10, 20)))
            await c(functions.messages.ReportRequest(
                peer=entity, id=sample, reason=types.InputReportReasonSpam()))
            done += 1
            logs.append(f"🚨 {phone}: ڕیپۆرت درا بۆ {len(sample)} پۆست")
        except FloodWaitError as e:
            logs.append(f"⏳ {phone}: فلود وەیت {e.seconds}چرکە")
        except Exception as e:
            logs.append(f"❌ {phone}: {str(e)[:60]}")
        finally:
            await c.disconnect()
    logs.append(f"📊 کۆی ڕیپۆرت: {done} ئەکاونت")
    return logs


SERVICES = {
    "view": ("👁 ڤیو", do_views, "price_view"),
    "react": ("❤️ ڕیاکت", do_reacts, "price_react"),
    "post": ("📤 پۆست", do_posts, "price_post"),
    "vote": ("🗳 دەنگدان", do_votes, "price_vote"),
    "member": ("👥 مێمبەر", do_members, "price_member"),
}


# ================== پانێڵی ئادمین ==================
def admin_panel():
    cur.execute("SELECT COUNT(*) FROM accounts")
    accs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users")
    usrs = cur.fetchone()[0]
    return (
        f"👨‍💼 **پانێڵی ئادمین**\n\n"
        f"👤 بەکارهێنەران: {usrs}\n"
        f"📱 ئەکاونتەکان: {accs}\n\n"
        f"🎉 نرخی هەدیەی ڕۆژانە: {get_set('gift_amount')}\n"
        f"🎁 خاڵی بانگهێشت: {get_set('ref_points')}\n"
        f"👁 نرخی ڤیو: {get_set('price_view')}\n"
        f"❤️ نرخی ڕیاکت: {get_set('price_react')}\n"
        f"📤 نرخی پۆست: {get_set('price_post')}\n"
        f"🗳 نرخی دەنگ: {get_set('price_vote')}\n"
        f"👥 نرخی مێمبەر: {get_set('price_member')}\n"
        f"🔒 جۆینی ناچاری: {get_set('force_channel') or 'نەخێر'}"
    ), [
        [Button.inline("📱 زیادکردنی ئەکاونت", b"addacc"),
         Button.inline("📋 ئەکاونتەکان", b"listacc")],
        [Button.inline("🚨 ماسس ڕیپۆرت", b"massrep"),
         Button.inline("🧾 ئۆردەرەکان", b"orders")],
        [Button.inline("🎁 دیاریکردنی هەدیەی ڕۆژانە", b"setgift"),
         Button.inline("🎁 خاڵی بانگهێشت", b"setref")],
        [Button.inline("💰 دیاریکردنی نرخەکان", b"setprice")],
        [Button.inline("🔒 جۆینی ناچاری", b"setforce")],
        [Button.inline("🚫 بلۆککردن", b"block"),
         Button.inline("✅ ئەنبلۆککردن", b"unblock")],
        [Button.inline("💸 ناردنی خاڵ", b"sendpts")],
        [Button.inline("📊 لۆگەکان", b"logs"),
         Button.inline("📢 ناردنی نامە بۆ هەموو", b"broadcast")]
    ]


def user_panel(user_id):
    pts = get_points(user_id)
    return (
        f"👋 بەخێربێیت!\n\n"
        f"💰 خاڵەکانت: **{pts}**\n\n"
        f"👇 خزمەتگوزاریەکانیشت بەکارهێنە "
    ), [
        [Button.inline("🎁 هەدیەی ڕۆژانە", b"daily")],
        [Button.inline("🛒 داواکردنی سێرڤیس", b"order")],
        [Button.inline("🔗 لینکی بانگهێشتم", b"mylink"),
         Button.inline("💰 خاڵەکانم", b"mypoints")]
    ]


async def check_force_join(user_id):
    ch = get_set("force_channel")
    if not ch:
        return True
    try:
        await bot(functions.channels.GetParticipantRequest(
            channel=ch, participant=user_id))
        return True
    except Exception:
        return False


# ================== هاندلەرەکان ==================
@bot.on(events.NewMessage(pattern=r"^/start(.*)"))
async def start(event):
    uid = event.sender_id
    if is_blocked(uid):
        return
    args = event.pattern_match.group(1).strip()

    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    if not cur.fetchone():
        ref = 0
        if args.startswith("ref_"):
            try:
                ref = int(args[4:])
            except ValueError:
                ref = 0
        cur.execute(
            "INSERT INTO users(user_id, points, referrer, join_date) VALUES(?,?,?,?)",
            (uid, 0, ref, time.strftime("%Y-%m-%d %H:%M")))
        db.commit()
        add_log(f"🆕 بەکارهێنەری نوێ: {uid} (ڕێفێر: {ref})")
        if ref and ref != uid:
            bonus = int(get_set("ref_points"))
            add_points(ref, bonus)
            try:
                await bot.send_message(ref,
                    f"🎉 کەسێک بە لینکەت هات!\n💰 +{bonus} خاڵ")
            except Exception:
                pass

    if uid == ADMIN_ID:
        txt, kb = admin_panel()
        await event.reply(txt, buttons=kb)
    else:
        ok = await check_force_join(uid)
        if not ok:
            await event.reply(
                f"🔒 بۆ بەکارهێنانی بۆت، سەرەتا ببە ئەندامی چەناڵ:\n"
                f"👉 {get_set('force_channel')}\n\n"
                f"دوای جۆینکردن /start بنێرەوە.",
                buttons=Button.url("🔔 جۆینکردن", get_set("force_channel")))
            return
        txt, kb = user_panel(uid)
        await event.reply(txt, buttons=kb)


@bot.on(events.CallbackQuery)
async def callbacks(event):
    uid = event.sender_id
    if is_blocked(uid):
        await event.answer("تۆ بلۆک کراویت!", alert=True)
        return
    data = event.data.decode()

    # ---------- بەکارهێنەر ----------
    if uid != ADMIN_ID:
        if data == "daily":
            now = time.time()
            cur.execute("SELECT last_daily FROM users WHERE user_id=?", (uid,))
            r = cur.fetchone()
            if r and now - r[0] < 86400:
                rem = int(86400 - (now - r[0]))
                h, m = rem // 3600, (rem % 3600) // 60
                await event.answer(f"⏳ دەبێت {h}کاتژمێر و {m}خولەک چاوەڕێ بکەیت!", alert=True)
            else:
                gift = int(get_set("gift_amount"))
                cur.execute("UPDATE users SET last_daily=?, points=points+? WHERE user_id=?",
                            (now, gift, uid))
                db.commit()
                add_log(f"🎁 هەدیەی ڕۆژانە: {uid} (+{gift})")
                await event.answer(f"🎉 +{gift} خاڵ درا!", alert=True)
                await event.edit(user_panel(uid)[0], buttons=user_panel(uid)[1])

        elif data == "mypoints":
            await event.answer(f"💰 خاڵەکانت: {get_points(uid)}", alert=True)

        elif data == "mylink":
            me = await bot.get_me()
            await event.answer(f"🔗 لینکەت:\nhttps://t.me/{me.username}?start=ref_{uid}", alert=True)

        elif data == "order":
            kb = [[Button.inline(name, f"ord:{key}")] for key, (name, _, _) in SERVICES.items()]
            kb.append([Button.inline("🔙 گەڕانەوە", b"back")])
            await event.edit("🛒 کام سێرڤیس دەتەوێت؟\n\n"
                            "💵 نرخەکان:\n"
                            f"👁 ڤیو: {get_set('price_view')} خاڵ\n"
                            f"❤️ ڕیاکت: {get_set('price_react')} خاڵ\n"
                            f"📤 پۆست: {get_set('price_post')} خاڵ\n"
                            f"🗳 دەنگ: {get_set('price_vote')} خاڵ\n"
                            f"👥 مێمبەر: {get_set('price_member')} خاڵ", buttons=kb)

        elif data == "back":
            txt, kb = user_panel(uid)
            await event.edit(txt, buttons=kb)

        elif data.startswith("ord:"):
            key = data[4:]
            user_state[uid] = {"step": "link", "service": key}
            await event.edit("📤 تکایە لینکی چەناڵ یان یوزەرنێمەکە بنێرە:\n"
                             "نموونە: https://t.me/channel یان @channel")
        return

    # ---------- ئادمین ----------
    if data == "addacc":
        bot_state[ADMIN_ID] = {"step": "acc_phone"}
        await event.edit("📱 ژمارەی تیلیگرام بنێرە لەگەڵ + (نموونە: +9647701234567)")

    elif data == "listacc":
        cur.execute("SELECT id, phone, added_at FROM accounts")
        rows = cur.fetchall()
        if not rows:
            await event.answer("هیچ ئەکاونتێک نییە", alert=True)
            return
        txt = "📋 **ئەکاونتەکان:**\n\n"
        for r in rows:
            txt += f"🆔 {r[0]} | 📱 {r[1]} | 📅 {r[2]}\n"
        await event.edit(txt)

    elif data == "massrep":
        bot_state[ADMIN_ID] = {"step": "rep_link"}
        await event.edit("🚨 لینکی چەناڵەکە بنێرە بۆ ماسس ڕیپۆرت:")

    elif data == "orders":
        cur.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 20")
        rows = cur.fetchall()
        if not rows:
            await event.answer("#هیچ ئۆردەرێک نییە", alert=True)
            return
        txt = "🧾 **دوایین ٢٠ ئۆردەر:**\n\n"
        for r in rows:
            txt += f"#{r[0]} | {r[3]} | {r[2]} | ژمارە: {r[4]} | {r[5]} | {r[1]}\n"
        await event.edit(txt)

    elif data == "logs":
        cur.execute("SELECT text, date FROM logs ORDER BY id DESC LIMIT 30")
        rows = cur.fetchall()
        if not rows:
            await event.answer("هیچ لۆگێک نییە", alert=True)
            return
        txt = "📊 **دوایین لۆگەکان:**\n\n"
        for t, d in rows:
            txt += f"[{d}] {t}\n"
        await event.edit(txt if len(txt) < 4000 else txt[:4000])

    elif data == "setgift":
        bot_state[ADMIN_ID] = {"step": "set_gift"}
        await event.edit("🎁 ژمارەی خاڵی هەدیەی ڕۆژانە بنێرە:")

    elif data == "setref":
        bot_state[ADMIN_ID] = {"step": "set_ref"}
        await event.edit("🎁 ژمارەی خاڵی بانگهێشتکردن بنێرە:")

    elif data == "setprice":
        kb = [
            [Button.inline(f"👁 ڤیو ({get_set('price_view')})", b"pv"),
             Button.inline(f"❤️ ڕیاکت ({get_set('price_react')})", b"pr")],
            [Button.inline(f"📤 پۆست ({get_set('price_post')})", b"pp"),
             Button.inline(f"🗳 دەنگ ({get_set('price_vote')})", b"pv2")],
            [Button.inline(f"👥 مێمبەر ({get_set('price_member')})", b"pm")],
        ]
        await event.edit("💰 کام نرخ دەگۆڕیت؟", buttons=kb)

    elif data == "setforce":
        bot_state[ADMIN_ID] = {"step": "set_force"}
        await event.edit("🔒 لینکی چەناڵی ناچاری بنێرە (بۆ لابردن بنێرە: off):")

    elif data == "block":
        bot_state[ADMIN_ID] = {"step": "block_user"}
        await event.edit("🚫 ئایدی بەکارهێنەر بنێرە بۆ بلۆککردن:")

    elif data == "unblock":
        bot_state[ADMIN_ID] = {"step": "unblock_user"}
        await event.edit("✅ ئایدی بەکارهێنەر بنێرە بۆ ئەنبلۆککردن:")

    elif data == "sendpts":
        bot_state[ADMIN_ID] = {"step": "send_pts_id"}
        await event.edit("💸 ئایدی بەکارهێنەر بنێرە:")

    elif data == "broadcast":
        bot_state[ADMIN_ID] = {"step": "broadcast"}
        await event.edit("📢 نامەکەت بنێرە بۆ هەموو بەکارهێنەران:")

    elif data in ("pv", "pr", "pp", "pv2", "pm"):
        key = {"pv": "price_view", "pr": "price_react", "pp": "price_post",
               "pv2": "price_vote", "pm": "price_member"}[data]
        bot_state[ADMIN_ID] = {"step": "set_price", "key": key}
        await event.edit("💰 ژمارەی خاڵ بۆ ئەم سێرڤیسە بنێرە:")

    await event.answer()


# ================== نامەکان ==================
@bot.on(events.NewMessage())
async def messages(event):
    uid = event.sender_id
    txt = event.raw_text
    if is_blocked(uid) or not txt:
        return

    # ===== ڕەوتی زیادکردنی ئەکاونت (ئادمین) =====
    st = bot_state.get(ADMIN_ID)
    if uid == ADMIN_ID and st:
        step = st["step"]

        if step == "acc_phone":
            phone = txt.strip()
            await event.reply("⏳ چاوەڕێ بکە... کۆد دەنێردرێت...")
            c = TelegramClient(StringSession(), API_ID, API_HASH)
            await c.connect()
            try:
                sent = await c.send_code_request(phone)
                bot_state[ADMIN_ID] = {
                    "step": "acc_code", "phone": phone,
                    "phone_code_hash": sent.phone_code_hash, "client": c}
                await event.reply("✅ کۆد نێردرا بۆ تیلیگرامت.\n\n"
                                  "🔐 تکایە کۆدەکە بنێرە:")
            except Exception as e:
                await c.disconnect()
                bot_state.pop(ADMIN_ID, None)
                await event.reply(f"❌ هەڵە: {e}")
            return

        elif step == "acc_code":
            code = txt.strip()
            try:
                await st["client"].sign_in(
                    phone=st["phone"], code=code,
                    phone_code_hash=st["phone_code_hash"])
                sess = st["client"].session.save()
                cur.execute("INSERT INTO accounts(phone, session, added_at) VALUES(?,?,?)",
                            (st["phone"], sess, time.strftime("%Y-%m-%d %H:%M")))
                db.commit()
                add_log(f"📱 ئەکاونت زیادکرا: {st['phone']}")
                await st["client"].disconnect()
                bot_state.pop(ADMIN_ID, None)
                await event.reply("🎉 ئەکاونتەکە بە سەرکەوتوویی زیادکرا!",
                                  buttons=admin_panel()[1])
            except SessionPasswordNeededError:
                bot_state[ADMIN_ID]["step"] = "acc_pass"
                await event.reply("🔑 وشەی نهێنی دوو هێندی (2FA) بنێرە:")
            except Exception as e:
                await event.reply(f"❌ کۆد هەڵەیە: {e}")
            return

        elif step == "acc_pass":
            try:
                await st["client"].sign_in(password=txt.strip())
                sess = st["client"].session.save()
                cur.execute("INSERT INTO accounts(phone, session, added_at) VALUES(?,?,?)",
                            (st["phone"], sess, time.strftime("%Y-%m-%d %H:%M")))
                db.commit()
                add_log(f"📱 ئەکاونت زیادکرا: {st['phone']}")
                await st["client"].disconnect()
                bot_state.pop(ADMIN_ID, None)
                await event.reply("🎉 ئەکاونتەکە زیادکرا!",
                                  buttons=admin_panel()[1])
            except Exception as e:
                await event.reply(f"❌ وشەی نهێنی هەڵەیە: {e}")
            return

        if step == "rep_link":
            bot_state[ADMIN_ID] = {"step": "rep_count", "link": extract_target(txt)}
            await event.reply("🔢 چەند ئەکاونت بەکاربهێنم؟")
            return

        if step == "rep_count":
            try:
                n = int(txt.strip())
            except ValueError:
                await event.reply("❌ تکایە ژمارە بنێرە")
                return
            link = bot_state[ADMIN_ID]["link"]
            bot_state.pop(ADMIN_ID, None)
            await event.reply(f"🚨 ماسس ڕیپۆرت دەست پێدەکات بۆ {link} بە {n} ئەکاونت...")
            logs = await do_mass_report(link, n)
            add_log(f"🚨 ماسس ڕیپۆرت: {link} ({n})")
            await event.reply("\n".join(logs)[:4000])
            return

        if step == "set_gift":
            set_set("gift_amount", txt.strip())
            bot_state.pop(ADMIN_ID, None)
            await event.reply("✅ گۆڕدرا!", buttons=admin_panel()[1])
            return

        if step == "set_ref":
            set_set("ref_points", txt.strip())
            bot_state.pop(ADMIN_ID, None)
            await event.reply("✅ گۆڕدرا!", buttons=admin_panel()[1])
            return

        if step == "set_price":
            set_set(st["key"], txt.strip())
            bot_state.pop(ADMIN_ID, None)
            await event.reply("✅ گۆڕدرا!", buttons=admin_panel()[1])
            return

        if step == "set_force":
            v = txt.strip()
            set_set("force_channel", "" if v.lower() == "off" else v)
            bot_state.pop(ADMIN_ID, None)
            await event.reply("✅ گۆڕدرا!", buttons=admin_panel()[1])
            return

        if step == "block_user":
            try:
                bid = int(txt.strip())
                cur.execute("INSERT OR REPLACE INTO blocked VALUES(?)", (bid,))
                db.commit()
                add_log(f"🚫 بلۆک: {bid}")
                bot_state.pop(ADMIN_ID, None)
                await event.reply("✅ بلۆک کرا!", buttons=admin_panel()[1])
            except Exception:
                await event.reply("❌ ئایدی هەڵەیە")
            return

        if step == "unblock_user":
            try:
                bid = int(txt.strip())
                cur.execute("DELETE FROM blocked WHERE user_id=?", (bid,))
                db.commit()
                add_log(f"✅ ئەنبلۆک: {bid}")
                bot_state.pop(ADMIN_ID, None)
                await event.reply("✅ ئەنبلۆک کرا!", buttons=admin_panel()[1])
            except Exception:
                await event.reply("❌ ئایدی هەڵەیە")
            return

        if step == "send_pts_id":
            try:
                bot_state[ADMIN_ID] = {"step": "send_pts_amount", "uid": int(txt.strip())}
                await event.reply("💸 چەند خاڵ؟")
            except Exception:
                await event.reply("❌ ئایدی هەڵەیە")
            return

        if step == "send_pts_amount":
            try:
                amt = int(txt.strip())
                tid = st["uid"]
                cur.execute("INSERT OR IGNORE INTO users(user_id, points, join_date) VALUES(?,?,?)",
                            (tid, 0, time.strftime("%Y-%m-%d")))
                db.commit()
                add_points(tid, amt)
                add_log(f"💸 {ADMIN_ID} → {tid}: {amt} خاڵ")
                try:
                    await bot.send_message(tid, f"💰 {amt} خاڵت پێدرا!")
                except Exception:
                    pass
                bot_state.pop(ADMIN_ID, None)
                await event.reply("✅ نێردرا!", buttons=admin_panel()[1])
            except Exception:
                await event.reply("❌ ژمارە هەڵەیە")
            return

        if step == "broadcast":
            cur.execute("SELECT user_id FROM users WHERE user_id != ?", (ADMIN_ID,))
            rows = cur.fetchall()
            ok = 0
            for (r,) in rows:
                try:
                    await bot.send_message(r, txt)
                    ok += 1
                    await asyncio.sleep(0.1)
                except Exception:
                    pass
            add_log(f"📢 بانگهێشت: {ok}")
            bot_state.pop(ADMIN_ID, None)
            await event.reply(f"✅ نێردرا بۆ {ok} بەکارهێنەر", buttons=admin_panel()[1])
            return

    # ===== ڕەوتی داواکردنی سێرڤیس (بەکارهێنەر + ئادمین) =====
    us = user_state.get(uid)
    if us:
        if us["step"] == "link":
            us["link"] = extract_target(txt)
            us["step"] = "amount"
            await event.reply("🔢 ژمارەی داواکاریەکەت چەند بێت؟")
            return

        if us["step"] == "amount":
            try:
                amt = int(txt.strip())
            except ValueError:
                await event.reply("❌ تکایە ژمارە بنێرە")
                return
            if amt < 1:
                await event.reply("❌ ژمارە دەبێت لە ١ زیاتر بێت")
                return
            key = us["service"]
            link = us["link"]
            name, func, price_key = SERVICES[key]
            price = int(get_set(price_key)) * amt
            pts = get_points(uid)
            if pts < price:
                await event.reply(f"❌ خاڵت کەمە!\n💰 پێویستە: {price}\n💰 خاڵت: {pts}")
                user_state.pop(uid, None)
                return
            add_points(uid, -price)
            user_state.pop(uid, None)
            cur.execute("INSERT INTO orders(user_id, service, link, amount, status, date) VALUES(?,?,?,?,?,?)",
                        (uid, name, link, amt, "⏳ لە جێبەجێکردندایە",
                         time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            add_log(f"🛒 ئۆردەر: {uid} | {name} | {link} | {amt}")
            await event.reply(f"⏳ داواکاریەکەت وەردەگیرا!\n"
                             f"{name} × {amt}\n💰 -{price} خاڵ\n"
                             f"🔥 دەستپێدەکات...")
            # جێبەجێکردن
            logs = await func(link, amt)
            cur.execute("UPDATE orders SET status='✅ تەواوبوو' WHERE user_id=? AND service=? AND link=? ORDER BY id DESC LIMIT 1",
                        (uid, name, link))
            db.commit()
            add_log("\n".join(logs)[:500])
            await bot.send_message(uid, "✅ **داواکاریەکەت تەواوبوو!**\n\n" +
                                   "\n".join(logs)[:3000])
            return


async def main():
    await bot.start(bot_token=BOT_TOKEN)
    me = await bot.get_me()
    print(f"✅ بۆت کاری پێدەکرێت: @{me.username}")
    add_log("🤀 بۆت چالاککرا")
    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
