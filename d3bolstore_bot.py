# ═══════════════════════════════════════════════════════════════
#  d3bolstore — بوت تيليجرام للأدمن
#  pip install python-telegram-bot firebase-admin requests
# ═══════════════════════════════════════════════════════════════

import logging
import asyncio
import requests
import urllib3
import json
import uuid
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import firebase_admin
from firebase_admin import credentials, firestore

urllib3.disable_warnings()

# ─── إعدادات ─────────────────────────────────────────────────
BOT_TOKEN    = "8996582641:AAH5wMl-IkSillxMFxXBT2m7uKlZi4jbLCA"
ADMIN_ID     = 7611141079
FIREBASE_KEY = "d3bol-store-firebase-adminsdk-fbsvc-f453bdf04d.json"

# 3x-ui
XUI_URL      = "https://109.199.102.153:2097/jT7j3ottPNQB983u7Q"
XUI_USER     = "admin"
XUI_PASS     = "admin1"
XUI_INBOUND  = 3       # ID الـ inbound
IP_LIMIT     = 1       # حد الأجهزة
# ─────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)

# Firebase init
cred = credentials.Certificate(FIREBASE_KEY)
firebase_admin.initialize_app(cred)
db = firestore.client()

# 3x-ui session
xui_session = requests.Session()

def xui_login():
    try:
        r = xui_session.post(f"{XUI_URL}/login",
            json={"username": XUI_USER, "password": XUI_PASS},
            verify=False, timeout=10)
        return r.ok and r.json().get("success")
    except:
        return False

def xui_add_client(email: str, months: int):
    """يضيف كلايانت على 3x-ui ويرجع الـ UUID"""
    try:
        if not xui_login():
            return None, "فشل تسجيل الدخول على 3x-ui"

        client_id = str(uuid.uuid4())
        expiry_ms = int((datetime.now() + timedelta(days=30 * months)).timestamp() * 1000)

        payload = {
            "id": XUI_INBOUND,
            "settings": json.dumps({
                "clients": [{
                    "id": client_id,
                    "email": email,
                    "limitIp": IP_LIMIT,
                    "totalGB": 0,          # غير محدود
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
        else:
            return None, r.json().get("msg", "خطأ غير معروف")
    except Exception as e:
        return None, str(e)

def xui_get_client_stats(email: str):
    """يجيب إحصائيات الكلايانت (صرف + انتهاء)"""
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

def xui_get_vless_link(client_id: str, email: str):
    """يولّد رابط VLESS للكلايانت"""
    try:
        if not xui_login():
            return None

        r = xui_session.get(f"{XUI_URL}/panel/api/inbounds/list",
            verify=False, timeout=10)

        if not r.ok:
            return None

        inbounds = r.json().get("obj", [])
        for ib in inbounds:
            if ib["id"] == XUI_INBOUND:
                # بناء رابط VLESS
                host = "109.199.102.153"
                port = ib.get("port", 80)
                net = "tcp"
                try:
                    stream = json.loads(ib.get("streamSettings", "{}"))
                    net = stream.get("network", "tcp")
                except:
                    pass

                link = f"vless://{client_id}@{host}:{port}?type={net}&security=none#{email}"
                return link
        return None
    except:
        return None

# ─── إرسال إشعار طلب جديد للأدمن ────────────────────────────
async def notify_admin(app, order_id: str, order: dict):
    months = order.get("months", 1)
    text = (
        f"🔔 *طلب جديد!*\n\n"
        f"🆔 رقم الطلب: `{order.get('orderId','—')}`\n"
        f"👤 الاسم: {order.get('userName','—')}\n"
        f"📧 الإيميل: {order.get('userEmail','—')}\n"
        f"✈️ تيليجرام: {order.get('userTelegram','—')}\n\n"
        f"📦 السيرفر: *{order.get('plan','—')}*\n"
        f"⏱ المدة: {order.get('duration','—')} ({months} شهر)\n"
        f"💰 السعر: {order.get('price',0):,} د.ع\n"
        f"💳 طريقة الدفع: {order.get('paymentMethod','—')}\n"
        f"📅 التاريخ: {order.get('date','—')}\n"
    )
    keyboard = [[
        InlineKeyboardButton("✅ تفعيل تلقائي", callback_data=f"activate|{order_id}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"reject|{order_id}"),
    ]]
    await app.bot.send_message(
        chat_id=ADMIN_ID,
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ─── Firestore Listener ───────────────────────────────────────
def watch_orders(app):
    def on_snapshot(col_snapshot, changes, read_time):
        for change in changes:
            if change.type.name == "ADDED":
                order = change.document.to_dict()
                if order.get("status") == "بانتظار التفعيل":
                    asyncio.run_coroutine_threadsafe(
                        notify_admin(app, change.document.id, order),
                        app.loop
                    )
    db.collection("orders").where("status", "==", "بانتظار التفعيل").on_snapshot(on_snapshot)

# ─── /start ──────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ غير مصرح لك.")
        return
    await update.message.reply_text(
        "👋 أهلاً بك في بوت دعبول ستور\n\n"
        "🔔 سأرسل لك كل طلب جديد فور وصوله.\n"
        "✅ اضغط 'تفعيل تلقائي' وأنا أسوي كل شي!"
    )

# ─── أزرار التفعيل / الرفض ────────────────────────────────────
async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        return

    action, order_id = query.data.split("|", 1)

    if action == "reject":
        db.collection("orders").document(order_id).update({"status": "مرفوض"})
        await query.edit_message_text(
            query.message.text + "\n\n❌ *تم رفض الطلب*",
            parse_mode="Markdown"
        )

    elif action == "activate":
        await query.edit_message_text(
            query.message.text + "\n\n⏳ *جاري التفعيل التلقائي...*",
            parse_mode="Markdown"
        )

        # جلب بيانات الطلب
        order_doc = db.collection("orders").document(order_id).get()
        if not order_doc.exists:
            await ctx.bot.send_message(ADMIN_ID, "❌ الطلب غير موجود!")
            return

        order = order_doc.to_dict()
        months = order.get("months", 1)
        user_email = order.get("userEmail", "").replace("@", "_").replace(".", "_")
        user_name = order.get("userName", "user")

        # اسم الكلايانت = اسم المستخدم + رقم عشوائي
        client_email = f"{user_name}_{order_id[-6:]}"

        # إضافة الكلايانت على 3x-ui
        client_id, error = xui_add_client(client_email, months)

        if error:
            await ctx.bot.send_message(ADMIN_ID,
                f"❌ فشل التفعيل على 3x-ui:\n{error}")
            return

        # توليد رابط VLESS
        vless_link = xui_get_vless_link(client_id, client_email)
        expires = (datetime.now() + timedelta(days=30 * months)).strftime("%Y-%m-%d")

        # تحديث Firestore
        db.collection("orders").document(order_id).update({
            "status": "نشط",
            "vpnCode": vless_link or client_id,
            "clientEmail": client_email,
            "clientId": client_id,
            "expires": expires,
            "activatedAt": datetime.now().isoformat(),
            "usedGB": 0,
            "totalGB": 0,  # 0 = غير محدود
        })

        # إرسال إشعار للمستخدم على تيليجرام
        user_tg = order.get("userTelegram", "")
        if user_tg and user_tg not in ["غير محدد", ""]:
            try:
                tg = user_tg.replace("@", "")
                await ctx.bot.send_message(
                    chat_id=f"@{tg}",
                    text=(
                        f"✅ *تم تفعيل اشتراكك!*\n\n"
                        f"📦 السيرفر: {order.get('plan','—')}\n"
                        f"📅 ينتهي في: {expires}\n"
                        f"🔒 IP Limit: {IP_LIMIT} جهاز\n\n"
                        f"🔑 *كود VPN الخاص بك:*\n`{vless_link or client_id}`\n\n"
                        f"يمكنك رؤية الكود وصرفك في داشبوردك على الموقع 🚀"
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                await ctx.bot.send_message(ADMIN_ID, f"⚠️ ما قدرت أرسل للمستخدم: {e}")

        # تأكيد للأدمن
        await ctx.bot.send_message(
            ADMIN_ID,
            f"✅ *تم التفعيل بنجاح!*\n\n"
            f"👤 {user_name}\n"
            f"🔑 Client: `{client_email}`\n"
            f"📅 ينتهي: {expires}\n"
            f"🔒 IP Limit: {IP_LIMIT}",
            parse_mode="Markdown"
        )

# ─── أمر تحديث الصرف (يدوي أو cron) ─────────────────────────
async def sync_usage(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text("⏳ جاري مزامنة الصرف...")

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
            db.collection("orders").document(o.id).update({
                "usedGB": used_gb,
                "totalGB": 0,  # غير محدود
            })
            updated += 1

    await update.message.reply_text(f"✅ تم تحديث الصرف لـ {updated} مشترك")

# ─── أمر قائمة الطلبات النشطة ────────────────────────────────
async def list_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    orders = db.collection("orders").where("status", "==", "نشط").stream()
    text = "📋 *الطلبات النشطة:*\n\n"
    count = 0
    for o in orders:
        d = o.to_dict()
        text += (f"• {d.get('userName','—')} — {d.get('plan','—')}\n"
                 f"  ينتهي: {d.get('expires','—')} | "
                 f"صرف: {d.get('usedGB',0)} GB\n\n")
        count += 1
    if count == 0:
        text = "ما في طلبات نشطة."
    await update.message.reply_text(text, parse_mode="Markdown")

# ─── تشغيل البوت ─────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("orders",  list_orders))
    app.add_handler(CommandHandler("sync",    sync_usage))
    app.add_handler(CallbackQueryHandler(button_handler))

    watch_orders(app)
    print("✅ بوت دعبول ستور شغال...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
