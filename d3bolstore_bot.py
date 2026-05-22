import logging
import requests
import urllib3
import json
import uuid
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import firebase_admin
from firebase_admin import credentials, firestore

urllib3.disable_warnings()

BOT_TOKEN    = "8996582641:AAH5wMl-IkSillxMFxXBT2m7uKlZi4jbLCA"
ADMIN_ID     = 7611141079
FIREBASE_KEY = "d3bol-store-firebase-adminsdk-fbsvc-71efad078f.json"
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

# ─── 3x-ui ───────────────────────────────────────────────────
def xui_login():
    try:
        r = xui_session.post(f"{XUI_URL}/login",
            json={"username": XUI_USER, "password": XUI_PASS},
            verify=False, timeout=10)
        return r.ok and r.json().get("success")
    except Exception as e:
        print(f"XUI login error: {e}")
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
        print(f"XUI add client response: {r.status_code} - {r.text}")
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
    except Exception as e:
        print(f"VLESS link error: {e}")
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

# ─── Handlers ────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("غير مصرح لك.")
        return
    await update.message.reply_text(
        "اهلا بك في بوت دعبول ستور\n\n"
        "سارسل لك كل طلب جديد فور وصوله.\n"
        "اضغط تفعيل تلقائي وانا اسوي كل شي!"
    )

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return

    parts = query.data.split("|", 1)
    action, doc_id = parts[0], parts[1]

    # ─── موافقة/رفض حساب ─────────────────────────────────────
    if action == "approve_user":
        db.collection("users").document(doc_id).update({"status": "active"})
        user_doc = db.collection("users").document(doc_id).get()
        if user_doc.exists:
            tg = user_doc.to_dict().get("telegram","").replace("@","")
            if tg and tg != "غير محدد":
                try:
                    await ctx.bot.send_message(
                        chat_id=f"@{tg}",
                        text="تم تفعيل حسابك في دعبول ستور!\n\nيمكنك الان تسجيل الدخول والاشتراك"
                    )
                except Exception as e:
                    print(f"Telegram notify error: {e}")
        await query.edit_message_text(query.message.text + "\n\n✅ تم تفعيل الحساب")
        return

    elif action == "reject_user":
        db.collection("users").document(doc_id).update({"status": "rejected"})
        user_doc = db.collection("users").document(doc_id).get()
        if user_doc.exists:
            tg = user_doc.to_dict().get("telegram","").replace("@","")
            if tg and tg != "غير محدد":
                try:
                    await ctx.bot.send_message(
                        chat_id=f"@{tg}",
                        text="عذرا، تم رفض طلب تسجيل حسابك. للاستفسار تواصل مع الادمن."
                    )
                except:
                    pass
        await query.edit_message_text(query.message.text + "\n\n❌ تم رفض الحساب")
        return

    # ─── رفض طلب ─────────────────────────────────────────────
    if action == "reject":
        db.collection("orders").document(doc_id).update({"status": "مرفوض"})
        await query.edit_message_text(query.message.text + "\n\n❌ تم رفض الطلب")

    # ─── تفعيل طلب ───────────────────────────────────────────
    elif action == "activate":
        await query.edit_message_text(query.message.text + "\n\nجاري التفعيل التلقائي...")

        order_doc = db.collection("orders").document(doc_id).get()
        if not order_doc.exists:
            await ctx.bot.send_message(ADMIN_ID, "الطلب غير موجود!")
            return

        order = order_doc.to_dict()
        months = order.get("months", 1)
        user_name = order.get("userName", "user").replace(" ", "_")
        client_email = f"{user_name}_{doc_id[-6:]}"

        print(f"Adding client: {client_email}, months: {months}")
        client_id, error = xui_add_client(client_email, months)

        if error:
            await ctx.bot.send_message(ADMIN_ID, f"فشل التفعيل على 3x-ui:\n{error}")
            return

        vless_link = xui_get_vless_link(client_id, client_email)
        expires = (datetime.now() + timedelta(days=30*months)).strftime("%Y-%m-%d")

        db.collection("orders").document(doc_id).update({
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
                        f"تم تفعيل اشتراكك!\n\n"
                        f"السيرفر: {order.get('plan','')}\n"
                        f"ينتهي: {expires}\n"
                        f"IP Limit: {IP_LIMIT} جهاز\n\n"
                        f"كود VPN:\n{vless_link or client_id}"
                    )
                )
            except Exception as e:
                await ctx.bot.send_message(ADMIN_ID, f"ما قدرت ارسل للمستخدم: {e}")

        await ctx.bot.send_message(
            ADMIN_ID,
            f"تم التفعيل!\n{user_name}\nينتهي: {expires}\n{client_email}"
        )

# ─── استقبال صورة الحوالة ────────────────────────────────────
async def receive_receipt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_tg = update.effective_user.username or ""
    first_name = update.effective_user.first_name or ""

    # جيب آخر طلب بانتظار التفعيل لهذا المستخدم
    try:
        orders_q = db.collection("orders").where("userTelegram", "==", f"@{user_tg}").where("status", "==", "بانتظار التفعيل").stream()
        order_doc = None
        order_data = None
        for o in orders_q:
            order_doc = o
            order_data = o.to_dict()
            break

        photo = update.message.photo[-1]
        caption = (
            f"صورة حوالة جديدة!\n\n"
            f"المستخدم: {first_name}\n"
            f"تيليجرام: @{user_tg}\n"
        )

        if order_data:
            caption += (
                f"\nالطلب: {order_data.get('plan','')}\n"
                f"السعر: {order_data.get('price',0):,} د.ع\n"
                f"رقم الطلب: {order_data.get('orderId','')}"
            )
            keyboard = [[
                InlineKeyboardButton("✅ تفعيل تلقائي", callback_data=f"activate|{order_doc.id}"),
                InlineKeyboardButton("❌ رفض", callback_data=f"reject|{order_doc.id}"),
            ]]
            await ctx.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=photo.file_id,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await ctx.bot.send_photo(chat_id=ADMIN_ID, photo=photo.file_id, caption=caption)

        await update.message.reply_text(
            "تم ارسال صورة الحوالة!\n"
            "سيتم مراجعتها وتفعيل اشتراكك قريبا"
        )
    except Exception as e:
        print(f"Receipt error: {e}")
        await update.message.reply_text("وصلت الصورة! سيتواصل معك الادمن قريبا.")

# ─── مزامنة الصرف ────────────────────────────────────────────
async def sync_usage(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("جاري المزامنة...")
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
    await update.message.reply_text(f"تم تحديث {updated} مشترك")

async def list_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    orders = db.collection("orders").where("status", "==", "نشط").stream()
    text = "الطلبات النشطة:\n\n"
    count = 0
    for o in orders:
        d = o.to_dict()
        text += f"- {d.get('userName','')} - {d.get('plan','')} - {d.get('expires','')}\n"
        count += 1
    if count == 0:
        text = "ما في طلبات نشطة."
    await update.message.reply_text(text)

# ─── Firestore Listeners ──────────────────────────────────────
# Global event loop reference
_main_loop = None

def setup_listeners(app):
    def on_orders_snapshot(col_snapshot, changes, read_time):
        for change in changes:
            if change.type.name == "ADDED":
                order = change.document.to_dict()
                if order.get("status") == "بانتظار التفعيل":
                    if _main_loop and _main_loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            notify_new_order(app, change.document.id, order),
                            _main_loop
                        )

    def on_users_snapshot(col_snapshot, changes, read_time):
        for change in changes:
            if change.type.name == "ADDED":
                user = change.document.to_dict()
                if user.get("status") == "pending":
                    if _main_loop and _main_loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            notify_new_user(app, change.document.id, user),
                            _main_loop
                        )

    db.collection("orders").where("status", "==", "بانتظار التفعيل").on_snapshot(on_orders_snapshot)
    db.collection("users").where("status", "==", "pending").on_snapshot(on_users_snapshot)

async def notify_new_order(app, order_id, order):
    text = (
        f"طلب جديد!\n\n"
        f"رقم الطلب: {order.get('orderId','')}\n"
        f"الاسم: {order.get('userName','')}\n"
        f"الايميل: {order.get('userEmail','')}\n"
        f"تيليجرام: {order.get('userTelegram','')}\n\n"
        f"السيرفر: {order.get('plan','')}\n"
        f"المدة: {order.get('duration','')}\n"
        f"السعر: {order.get('price',0):,} د.ع\n"
        f"طريقة الدفع: {order.get('paymentMethod','')}\n"
    )
    keyboard = [[
        InlineKeyboardButton("✅ تفعيل تلقائي", callback_data=f"activate|{order_id}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"reject|{order_id}"),
    ]]
    try:
        await app.bot.send_message(
            chat_id=ADMIN_ID,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        print(f"Notify order error: {e}")

async def notify_new_user(app, user_id, user):
    text = (
        f"تسجيل حساب جديد!\n\n"
        f"الاسم: {user.get('name','')}\n"
        f"البريد: {user.get('email','')}\n"
        f"تيليجرام: {user.get('telegram','')}\n"
        f"التاريخ: {str(user.get('createdAt',''))[:10]}\n"
    )
    keyboard = [[
        InlineKeyboardButton("✅ موافقة", callback_data=f"approve_user|{user_id}"),
        InlineKeyboardButton("❌ رفض الحساب", callback_data=f"reject_user|{user_id}"),
    ]]
    try:
        await app.bot.send_message(
            chat_id=ADMIN_ID,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        print(f"Notify user error: {e}")

# ─── Main ─────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("orders", list_orders))
    app.add_handler(CommandHandler("sync",   sync_usage))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, receive_receipt))

    async def post_init(application):
        global _main_loop
        _main_loop = asyncio.get_event_loop()
        import threading
        t = threading.Thread(target=setup_listeners, args=(application,), daemon=True)
        t.start()

    app.post_init = post_init

    print("✅ بوت دعبول ستور شغال...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
