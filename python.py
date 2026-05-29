import json, os, random, requests, qrcode
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ========== CONFIG ==========
TOKEN = "YOUR_BOT_TOKEN"
OWNER_ID = 123456789
FORCE_CHANNEL = "@yourchannel"
BKASH = "01XXXXXXXXX"
NAGAD = "01XXXXXXXXX"
AI_API_KEY = "YOUR_GROQ_API_KEY"
DB_FILE = "database.json"
MIN_WITHDRAW = 50

# ========== DATABASE ==========
def load_db():
    if not os.path.exists(DB_FILE):
        data = {
            "users": {},
            "admins": [OWNER_ID],
            "bot_status": True,
            "prices": {"1day": 20, "7day": 100, "30day": 300},
            "withdrawals": [],
            "social_links": {
                "facebook": "https://facebook.com/yourpage",
                "youtube": "https://youtube.com/@yourchannel",
                "telegram": "https://t.me/yourchannel",
                "website": "https://yourwebsite.com"
            }
        }
        with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)
    with open(DB_FILE, "r") as f: return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)

db = load_db()

# ========== FORCE JOIN ==========
async def is_joined(bot, user_id):
    try:
        member = await bot.get_chat_member(FORCE_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except: return False

# ========== START ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global db
    user = update.effective_user
    uid = str(user.id)
    db = load_db()

    if not db["bot_status"] and user.id!= OWNER_ID:
        await update.message.reply_text("❌ Bot Offline")
        return

    if not await is_joined(context.bot, user.id):
        btn = [[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_CHANNEL.replace('@','')}")],
               [InlineKeyboardButton("✅ Joined", callback_data="checkjoin")]]
        await update.message.reply_text("❌ আগে Channel Join করো", reply_markup=InlineKeyboardMarkup(btn))
        return

    if uid not in db["users"]:
        db["users"][uid] = {
            "name": user.first_name, "balance": 0, "referrals": 0, "expiry": "Free",
            "last_bonus": "2000-01-01", "banned": False, "server": "Server 1",
            "xp": 0, "level": 1, "streak": 0 # NEW
        }
        if context.args:
            ref = context.args[0]
            if ref in db["users"] and ref!= uid:
                db["users"][ref]["balance"] += 10
                db["users"][ref]["referrals"] += 1
                await context.bot.send_message(ref, "🎉 +10 Tk Referral Bonus!")
        save_db(db)

    if db["users"][uid]["banned"]:
        await update.message.reply_text("❌ You Are Banned")
        return

    keyboard = [
        ["💰 Balance", "🎁 Daily Bonus"],
        ["👥 Referral", "💳 Buy Plan"],
        ["📱 Free MB", "🔍 Search"],
        ["🤖 AI Chat", "💳 Withdraw"],
        ["📷 QR Code", "ℹ️ Profile"],
        ["🌐 Social Links", "📞 Contact Admin"]
    ]
    if user.id in db["admins"]: keyboard.append(["⚙️ Admin Panel"])

    u = db["users"][uid]
    text = f"""👋 Welcome {u['name']}
💰 Balance: {u['balance']} Tk
📅 Plan: {u['expiry']}
👥 Referrals: {u['referrals']}
🏆 Level: {u['level']} | XP: {u['xp']}/{u['level']*50}
🌐 Server: {u['server']}"""
    await update.message.reply_text(text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

# ========== MESSAGES ==========
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global db
    uid = str(update.effective_user.id)
    text = update.message.text
    if uid not in db["users"]: return await start(update, context)
    u = db["users"][uid]

    # XP SYSTEM - NEW
    u['xp'] += random.randint(1, 5)
    if u['xp'] >= u['level'] * 50:
        u['xp'] -= u['level'] * 50
        u['level'] += 1
        await update.message.reply_text(f"🎉 Level Up! তুমি এখন Level {u['level']}")

    if context.user_data.get('ai_mode'): return await ai_reply(update, context, text)
    if context.user_data.get('waiting') == 'search':
        await update.message.reply_text(f"🔍 Google Search: https://www.google.com/search?q={text.replace(' ', '+')}")
        context.user_data['waiting'] = None; return

    # Withdraw Flow
    if context.user_data.get('waiting') == 'withdraw_method':
        context.user_data['method'] = text
        await update.message.reply_text("📱 তোমার BKASH/NAGAD নাম্বার লিখো:")
        context.user_data['waiting'] = 'withdraw_number'; return
    if context.user_data.get('waiting') == 'withdraw_number':
        method = context.user_data['method']; number = text; amount = u['balance']
        req = {"uid": uid, "name": u['name'], "amount": amount, "method": method, "number": number, "time": str(datetime.now())}
        db['withdrawals'].append(req); u['balance'] = 0; save_db(db)
        msg = f"📥 New Withdraw\n👤 {u['name']}\n🆔 {uid}\n💰 {amount} Tk\n💳 {method}\n📱 {number}"
        btn = [[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{uid}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject_{uid}")]]
        for admin_id in db['admins']: await context.bot.send_message(admin_id, msg, reply_markup=InlineKeyboardMarkup(btn))
        await update.message.reply_text("✅ Request Sent! Admin Approve করলে টাকা পাবে")
        context.user_data['waiting'] = None; return

    # Menu Options
    if text == "💰 Balance": await update.message.reply_text(f"💰 Balance: {u['balance']} Tk")

    elif text == "🎁 Daily Bonus":
        last = datetime.strptime(u['last_bonus'], "%Y-%m-%d").date()
        today = datetime.now().date()
        if today - last < timedelta(days=1):
            await update.message.reply_text("❌ 24h পর ট্রাই করো")
        else:
            # STREAK SYSTEM - NEW
            if last == today - timedelta(days=1): u['streak'] += 1
            else: u['streak'] = 1
            bonus = 3 + min(u['streak'], 10)
            u['balance'] += bonus
            u['last_bonus'] = str(today)
            save_db(db)
            await update.message.reply_text(f"🎁 +{bonus} Tk Added! 🔥 Streak: {u['streak']} দিন")

    elif text == "👥 Referral":
        link = f"https://t.me/{context.bot.username}?start={uid}"
        await update.message.reply_text(f"🔗 Referral Link:\n{link}\n\nPer Referral: +10 Tk")

    elif text == "💳 Buy Plan":
        btn = [[InlineKeyboardButton(f"1 Day - {db['prices']['1day']} Tk", callback_data="buy_1day")],
               [InlineKeyboardButton(f"7 Day - {db['prices']['7day']} Tk", callback_data="buy_7day")],
               [InlineKeyboardButton(f"30 Day - {db['prices']['30day']} Tk", callback_data="buy_30day")]]
        await update.message.reply_text("💳 Plan Select করো:", reply_markup=InlineKeyboardMarkup(btn))

    elif text == "📱 Free MB":
        btn = [[InlineKeyboardButton("Robi", callback_data="robi"), InlineKeyboardButton("Airtel", callback_data="airtel")],
               [InlineKeyboardButton("Banglalink", callback_data="bl"), InlineKeyboardButton("GP", callback_data="gp")]]
        await update.message.reply_text("📱 SIM Select করো:", reply_markup=InlineKeyboardMarkup(btn))

    elif text == "🔍 Search":
        await update.message.reply_text("🔍 কি সার্চ করবে লিখো")
        context.user_data['waiting'] = 'search'

    elif text == "🤖 AI Chat":
        context.user_data['ai_mode'] = True
        await update.message.reply_text("🤖 AI Chat ON\nStop করতে /stop লিখো")

    elif text == "💳 Withdraw":
        if u['balance'] < MIN_WITHDRAW:
            await update.message.reply_text(f"❌ Minimum {MIN_WITHDRAW} Tk লাগবে")
        else:
            await update.message.reply_text("💳 Payment Method লিখো: BKASH বা NAGAD")
            context.user_data['waiting'] = 'withdraw_method'

    elif text == "📷 QR Code": await update.message.reply_text("Usage: /qr YourText")

    elif text == "ℹ️ Profile":
        msg = f"""ℹ️ Your Profile ━━━━━━━━━━━━━━
🆔 User ID: {uid}
👤 Name: {u['name']}
💰 Balance: {u['balance']} Tk
🏆 Level: {u['level']} | XP: {u['xp']}/{u['level']*50}
🔥 Streak: {u['streak']} দিন
📅 Plan Expiry: {u['expiry']}
👥 Referrals: {u['referrals']}
🌐 Server: {u['server']}
━━━━━━━━━━━━━━"""
        await update.message.reply_text(msg)

    elif text == "🌐 Social Links":
        links = db["social_links"]
        msg = f"""🌐 Follow Us:
📘 Facebook: {links['facebook']}
▶️ YouTube: {links['youtube']}
📢 Telegram: {links['telegram']}
🌍 Website: {links['website']}"""
        await update.message.reply_text(msg)

    elif text == "📞 Contact Admin": await update.message.reply_text(f"📞 Admin: tg://user?id={OWNER_ID}")

    elif text == "⚙️ Admin Panel" and update.effective_user.id in db["admins"]:
        btn = [[InlineKeyboardButton("📊 Stats", callback_data="stats")],
               [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")],
               [InlineKeyboardButton("✏️ Edit Links", callback_data="editlinks")],
               [InlineKeyboardButton("🔴 Stop Bot", callback_data="stopbot")]]
        await update.message.reply_text("⚙️ Admin Panel", reply_markup=InlineKeyboardMarkup(btn))

# ========== CALLBACKS ==========
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global db
    query = update.callback_query
    uid = str(query.from_user.id)
    await query.answer()

    if query.data == "checkjoin":
        if await is_joined(context.bot, query.from_user.id):
            await query.message.reply_text("✅ Done! Send /start")
        else: await query.message.reply_text("❌ Join First")

    elif query.data.startswith("buy_"):
        plan = query.data.split("_")[1]
        price = db["prices"][plan]
        days = 1 if plan=="1day" else 7 if plan=="7day" else 30
        if db["users"][uid]["balance"] < price:
            await query.edit_message_text(f"❌ Balance কম। {price} Tk লাগবে")
        else:
            db["users"][uid]["balance"] -= price
            exp = datetime.now() + timedelta(days=days)
            db["users"][uid]["expiry"] = exp.strftime("%Y-%m-%d")
            save_db(db)
            await query.edit_message_text(f"✅ Plan Active! Expire: {db['users'][uid]['expiry']}")

    elif query.data in ["robi","airtel","bl","gp"]:
        offers = {"robi":"📱 Robi: *121*2*3#", "airtel":"📱 Airtel: *8444*1#", "bl":"📱 BL: MyBL App > Reward", "gp":"📱 GP: MyGP App > Free Internet"}
        await query.edit_message_text(offers[query.data])

    elif query.data.startswith("approve_") and query.from_user.id in db["admins"]:
        req_uid = query.data.split("_")[1]
        for req in db['withdrawals']:
            if req['uid'] == req_uid:
                db['withdrawals'].remove(req); save_db(db)
                await context.bot.send_message(req_uid, f"✅ Withdraw {req['amount']} Tk Approved!")
                await query.edit_message_text(f"✅ Approved {req['name']}"); break

    elif query.data.startswith("reject_") and query.from_user.id in db["admins"]:
        req_uid = query.data.split("_")[1]
        for req in db['withdrawals']:
            if req['uid'] == req_uid:
                db['withdrawals'].remove(req)
                db['users'][req_uid]['balance'] += req['amount']
                save_db(db)
                await context.bot.send_message(req_uid, f"❌ Withdraw {req['amount']} Tk Rejected")
                await query.edit_message_text(f"❌ Rejected {req['name']}"); break

    elif query.data == "stats" and query.from_user.id in db["admins"]:
        await query.edit_message_text(f"📊 Total Users: {len(db['users'])}\n💰 Total Balance: {sum(u['balance'] for u in db['users'].values())}")

    elif query.data == "stopbot" and query.from_user.id in db["admins"]:
        db["bot_status"] = False; save_db(db)
        await query.edit_message_text("❌ Bot Stopped")

    elif query.data == "editlinks" and query.from_user.id in db["admins"]:
        await query.message.reply_text("✏️ Send: fb|yt|tg|web\nEx: fb.com|yt.com|t.me|site.com")
        context.user_data['waiting'] = 'edit_links'

    elif context.user_data.get('waiting') == 'edit_links':
        try:
            fb, yt, tg, web = update.message.text.split("|")
            db["social_links"] = {"facebook": fb.strip(), "youtube": yt.strip(), "telegram": tg.strip(), "website": web.strip()}
            save_db(db)
            await update.message.reply_text("✅ Links Updated!")
            context.user_data['waiting'] = None
        except: await update.message.reply_text("❌ Wrong Format")

# ========== AI CHAT ==========
async def ai_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, question):
    if question == "/stop":
        context.user_data['ai_mode'] = False
        await update.message.reply_text("✅ AI Chat OFF")
        return
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
        data = {"model": "llama3-8b-8192", "messages": [{"role":"user","content":question}]}
        r = requests.post(url, headers=headers, json=data, timeout=30)
        reply = r.json()['choices'][0]['message']['content']
        await update.message.reply_text(reply)
    except: await update.message.reply_text("❌ AI Error")

# ========== QR COMMAND ==========
async def qr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("Usage: /qr Hello")
    text = " ".join(context.args)
    img = qrcode.make(text); img.save("qr.png")
    await update.message.reply_photo(open("qr.png","rb")); os.remove("qr.png")

# ========== TOP LEADERBOARD - NEW ==========
async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = sorted(db["users"].items(), key=lambda x: x[1]['balance'], reverse=True)[:10]
    msg = "🏆 Top 10 Richest Users\n━━━━━━━━━━━━━━\n"
    for i, (uid, data) in enumerate(users, 1):
        msg += f"{i}. {data['name']} - {data['balance']} Tk\n"
    await update.message.reply_text(msg)

# ========== BAN/UNBAN - NEW ==========
async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in db["admins"]: return
    if not context.args: return await update.message.reply_text("Usage: /ban user_id")
    ban_id = context.args[0]
    if ban_id in db["users"]:
        db["users"][ban_id]["banned"] = True; save_db(db)
        await update.message.reply_text(f"✅ {ban_id} ব্যান করা হলো")
        await context.bot.send_message(ban_id, "❌ তোমাকে ব্যান করা হয়েছে")

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in db["admins"]: return
    if not context.args: return await update.message.reply_text("Usage: /unban user_id")
    unban_id = context.args[0]
    if unban_id in db["users"]:
        db["users"][unban_id]["banned"] = False; save_db(db)
        await update.message.reply_text(f"✅ {unban_id} আনব্যান করা হলো")

# ========== MAIN ==========
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("qr", qr_cmd))
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
    print("✅ Bot Running...")
    app.run_polling()

if __name__ == "__main__":
    main()