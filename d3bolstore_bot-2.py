# ═══════════════════════════════════════════════════════════════
#  d3bolstore — بوت تيليجرام للأدمن
#  pip install python-telegram-bot firebase-admin requests
# ═══════════════════════════════════════════════════════════════

import logging
import requests
import urllib3
import json
import uuid
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import firebase_admin
from firebase_admin import credentials, firestore
import threading

urllib3.disable_warnings()

BOT_TOKEN    = "8996582641:AAH5wMl-IkSillxMFxXBT2m7uKlZi4jbLCA"
ADMIN_ID     = 7611141079
FIREBASE_KEY = "d3bol-store-firebase-adminsdk-fbsvc-f453bdf04d.json"
XUI_URL      = "https://109.199.102.153:2097/jT7j3ottPNQB983u7Q"
XUI_USER     = "admin"
XUI_PASS     = "admin1"
XUI_INBOUND  = 3
IP_LIMIT     = 1

logging.basicConfig(level=logging.INFO)

cred = credentials.Certificate(FIREBASE_KEY)
firebase_admin.initialize_app(cred)
db = firestore.client()

xui_session = requests.Session()

def xui_login():
    try:
        r = xui_session.post(f"{XUI_URL}/login",
            json={"username": XUI_USER, "password": XUI_PASS},
            verify=False, timeout=10)
        return r.ok and r.json().get("success")
    except:
        return False

def xui_add_client(email, months):
    try:
        if not xui_login():
            return None, "فشل تسجيل الدخول على 3x-ui"
        client_id = str(uuid.uuid4())
        expiry_ms = int((datetime.now() + timedelta(days=30*months)).timestamp() * 1000)
        payload = {
            "id": XUI_INBOUND,
            "settings": json.dumps({
                "clients": [{
                    "id": client_id,
                    "email": email,
                    "limitIp": IP_LIMIT,
                    "totalGB": 0,
                    "expiryTime": expiry_ms,
                    "enable": True,
                    "tgId": "",
                    "subId": "",
                    "reset": 0
                }]
            })
        }
        r = xui_session.post(f"{XUI_URL}/panel/api/inbounds/addClient",
            json=payload, verify=False, timeout=10)
        if r.ok and r.json().get("success"):
            return client_id, None
        return None, r.json().get("msg", "خطأ غير معروف")
    except Exception as e:
        return None, str(e)

def xui_get_vless_link(client_id, email):
    try:
        if not xui_login():
            return None
        r = xui_session.get(f"{XUI_URL}/panel/api/inbounds/list", verify=False, timeout=10)
        if not r.ok:
            return None
        for ib in r.json().get("obj", []):
            if ib["id"] == XUI_INBOUND:
                host = "109.199.102.153"
                port = ib.get("port", 80)
                net = "tcp"
                try:
                    stream = json.loads(ib.get("streamSettings", "{}"))
                    net = stream.get("network", "tcp")
                except:
                    pass
                return f"vless://{client_id}@{host}:{port}?type={net}&security=none#{email}"
        return None
    except:
        return None

def xui_get_client_stats(email):
    try:
        if not xui_login():
            return None
        r = xui_session.get(f"{XUI_URL}/panel/api/inbounds/getClientTraffics/{email}",
            verify=False, timeout=10)
        if r.ok and r.json().get("success"):
            return r.json().get("obj")
        return None
    except:
        return None

# ─── Firestore Listener ───────────────────────────────────────
def watch_orders(bot_app):
    def on_snapshot(col_snapshot, changes, read_time):
        for change in changes:
            if change.type.name == "ADDED":
                order = change.document.to_dict()
                if order.get("status") == "بانتظار التفعيل":
                    threading.Thread(
                        target=lambda: send_order_notification(bot_app, change.document.id, order),
                        daemon=True
                    ).start()

    db.collection("orders").where("status", "==", "بانتظار التفعيل").on_snapshot(on_snapshot)

def send_order_notification(bot_app, order_id, order):
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_notify_admin(bot_app, order_id, order))
    loop.close()

async def _notify_admin(bot_app, order_id, order):
    text = (
        f"🔔 *طلب جديد!*\n\n"
        f"🆔 رقم الطلب: `{order.get('orderId','—')}`\n"
        f"👤 الاسم: {order.get('userName','—')}\n"
        f"📧 الإيميل: {order.get('userEmail','—')}\n"
        f"✈️ تيليجرام: {order.get('userTelegram','—')}\n\n"
        f"📦 السيرفر: *{order.get('plan','—')}*\n"
        f"⏱ المدة: {order.get('duration','—')}\n"
        f"💰 السعر: {order.get('price',0):,} د.ع\n"
        f"💳 طريقة الدفع: {order.get('paymentMethod','—')}\n"
        f"🧾 اسم الملف المرفق: {order.get('receiptFileName','لا يوجد')}\n"
    )
    keyboard = [[
        InlineKeyboardButton("✅ تفعيل تلقائي", callback_data=f"activate|{order_id}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"reject|{order_id}"),
    ]]
    await bot_app.bot.send_message(
        chat_id=ADMIN_ID,
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ─── Handlers ────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ غير مصرح لك.")
        return
    await update.message.reply_text(
        "👋 أهلاً بك في بوت دعبول ستور\n\n"
        "🔔 سأرسل لك كل طلب جديد فور وصوله.\n"
        "✅ اضغط تفعيل تلقائي وأنا أسوي كل شي!"
    )

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return

    action, order_id = query.data.split("|", 1)

    if action == "reject":
        db.collection("orders").document(order_id).update({"status": "مرفوض"})
        await query.edit_message_text(query.message.text + "\n\n❌ *تم رفض الطلب*", parse_mode="Markdown")

    elif action == "activate":
        await query.edit_message_text(query.message.text + "\n\n⏳ *جاري التفعيل التلقائي...*", parse_mode="Markdown")

        order_doc = db.collection("orders").document(order_id).get()
        if not order_doc.exists:
            await ctx.bot.send_message(ADMIN_ID, "❌ الطلب غير موجود!")
            return

        order = order_doc.to_dict()
        months = order.get("months", 1)
        user_name = order.get("userName", "user").replace(" ", "_")
        client_email = f"{user_name}_{order_id[-6:]}"

        client_id, error = xui_add_client(client_email, months)
        if error:
            await ctx.bot.send_message(ADMIN_ID, f"❌ فشل التفعيل:\n{error}")
            return

        vless_link = xui_get_vless_link(client_id, client_email)
        expires = (datetime.now() + timedelta(days=30*months)).strftime("%Y-%m-%d")

        db.collection("orders").document(order_id).update({
            "status": "نشط",
            "vpnCode": vless_link or client_id,
            "clientEmail": client_email,
            "clientId": client_id,
            "expires": expires,
            "activatedAt": datetime.now().isoformat(),
            "usedGB": 0,
            "totalGB": 0,
        })

        user_tg = order.get("userTelegram", "")
        if user_tg and user_tg not in ["غير محدد", ""]:
            try:
                tg = user_tg.replace("@", "")
                await ctx.bot.send_message(
                    chat_id=f"@{tg}",
                    text=(
                        f"✅ *تم تفعيل اشتراكك!*\n\n"
                        f"📦 {order.get('plan','—')}\n"
                        f"📅 ينتهي: {expires}\n"
                        f"🔒 IP Limit: {IP_LIMIT} جهاز\n\n"
                        f"🔑 *كود VPN:*\n`{vless_link or client_id}`"
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                await ctx.bot.send_message(ADMIN_ID, f"⚠️ ما قدرت أرسل للمستخدم: {e}")

        await ctx.bot.send_message(
            ADMIN_ID,
            f"✅ *تم التفعيل!*\n👤 {user_name}\n📅 ينتهي: {expires}\n🔑 `{client_email}`",
            parse_mode="Markdown"
        )

async def sync_usage(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("⏳ جاري المزامنة...")
    orders = db.collection("orders").where("status", "==", "نشط").stream()
    updated = 0
    for o in orders:
        data = o.to_dict()
        client_email = data.get("clientEmail")
        if not client_email:
            continue
        stats = xui_get_client_stats(client_email)
        if stats:
            used_bytes = stats.get("up", 0) + stats.get("down", 0)
            used_gb = round(used_bytes / (1024**3), 2)
            db.collection("orders").document(o.id).update({"usedGB": used_gb})
            updated += 1
    await update.message.reply_text(f"✅ تم تحديث {updated} مشترك")

async def list_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    orders = db.collection("orders").where("status", "==", "نشط").stream()
    text = "📋 *الطلبات النشطة:*\n\n"
    count = 0
    for o in orders:
        d = o.to_dict()
        text += f"• {d.get('userName','—')} — {d.get('plan','—')} — {d.get('expires','—')}\n"
        count += 1
    if count == 0:
        text = "ما في طلبات نشطة."
    await update.message.reply_text(text, parse_mode="Markdown")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("orders", list_orders))
    app.add_handler(CommandHandler("sync",   sync_usage))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Start Firestore watcher in background
    watcher_thread = threading.Thread(target=watch_orders, args=(app,), daemon=True)
    watcher_thread.start()

    print("✅ بوت دعبول ستور شغال...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
