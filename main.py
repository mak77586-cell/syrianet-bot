import sqlite3
import logging
import os
import re
import aiohttp
from aiohttp import web
from pypdf import PdfReader
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
import asyncio

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

WALLET_ID = "25fdea6d11e9cef055fe64b50d29c5a4"
SHAMCASH_API_URL = f"https://api-shamcash.com/api/v1/wallets/shamcash/{WALLET_ID}/transactions"
SHAMCASH_API_TOKEN = "sk_81e3f9bbc05f7f43a52d65c2848cbd20a77bf2102b2fd4b8bd9d80178257a64a"

ADMIN_ID = 5429133552

CATEGORY_PRICES = {
    "5G": 70,
    "10G": 140,
    "20G": 250,
    "30G": 300,
    "50G": 450,
    "100G": 750
}

def init_db():
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            is_sold INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            user_id INTEGER,
            amount REAL
        )
    ''')
    conn.commit()
    conn.close()

def import_cards_from_pdf(pdf_path, target_category):
    if not os.path.exists(pdf_path):
        return 0
    
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted + "\n"
            
    all_numbers = re.findall(r'\b\d{4,8}\b', text)
    added_count = 0
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    
    for i in range(0, len(all_numbers) - 1, 2):
        usr = all_numbers[i]
        pwd = all_numbers[i+1]
        
        cursor.execute("SELECT id FROM cards WHERE category = ? AND username = ? AND password = ?", (target_category, usr, pwd))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO cards (category, username, password, is_sold) VALUES (?, ?, ?, 0)", (target_category, usr, pwd))
            added_count += 1
            
    conn.commit()
    conn.close()
    return added_count

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_name = user.first_name
    
    # تسجيل المستخدم في قاعدة البيانات إذا لمש يكن موجوداً
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0.0)", (user_id,))
    conn.commit()
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("💳 شراء بطاقة", callback_data="buy_cards")],
        [InlineKeyboardButton("💳 محفظتي ومعلوماتي", callback_data="my_wallet"), InlineKeyboardButton("➕ شحن الرصيد", callback_data="topup_menu")]
    ]
    if user_id == ADMIN_ID:
        keyboard.insert(0, [InlineKeyboardButton("⚙️ لوحة تحكم المشرف (Admin)", callback_data="admin_panel")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"🌐 أهلاً بك في SYRIA NET يا {user_name} 🌐\n\n"
        "يمكنك من خلال هذا البوت شحن رصيدك وشراء بطاقات الإنترنت الخاصة بالشبكة بشكل فوري وتلقائي.\n"
        "شكراً لاستخدامك خدماتنا 💙\n"
        "للتواصل مع الدعم @Alibdawa"
    )

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text=welcome_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text=welcome_text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_id = user.id
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    
    if query.data == "buy_cards":
        keyboard = []
        for cat, price in CATEGORY_PRICES.items():
            cursor.execute("SELECT COUNT(*) FROM cards WHERE category = ? AND is_sold = 0", (cat,))
            count = cursor.fetchone()[0]
            keyboard.append([InlineKeyboardButton(f"فئة {cat} - {price} ل.س (متوفر: {count})", callback_data=f"cat_{cat}")])
        keyboard.append([InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text="🛒 *اختر الفئة التي تريد شراءها:*",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
    elif query.data == "my_wallet":
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        balance = row[0] if row else 0.0
        
        wallet_text = (
            f"👤 *معلومات حسابك:*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ الاسم: {user.full_name}\n"
            f"🆔 معرف المستخدم (ID): {user_id}\n"
            f"💳 الرصيد الحالي: {balance:,.0f} ل.س\n"
            f"━━━━━━━━━━━━━━━━━━━"
        )
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ شحن الرصيد", callback_data="topup_menu")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]
        ])
        await query.edit_message_text(text=wallet_text, parse_mode="Markdown", reply_markup=reply_markup)

    elif query.data == "topup_menu":
        context.user_data['waiting_for_tx'] = True
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء العملية", callback_data="main_menu")]])
        await query.edit_message_text(
            text=f"➕ *شحن الرصيد عبر شام كاش*\n\n"
                 f"رقم محفظتنا للاستلام:\n`{WALLET_ID}`\n\n"
                 f"الرجاء تحويل المبلغ، ثم إرسال *رقم المعاملة (Transaction ID)* هنا في رسالة نصية لشحن محفظتك تلقائياً:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
    elif query.data == "admin_panel" and user_id == ADMIN_ID:
        stats_text = "📊 إحصائيات ومخزون البطاقات:\n\n"
        for cat in CATEGORY_PRICES.keys():
            cursor.execute("SELECT COUNT(*) FROM cards WHERE category = ? AND is_sold = 0", (cat,))
            available = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM cards WHERE category = ? AND is_sold = 1", (cat,))
            sold = cursor.fetchone()[0]
            stats_text += f"📦 فئة {cat}: متوفر ({available}) | مباع ({sold})\n"
        
        keyboard = [
            [InlineKeyboardButton("📥 رفع PDF لفئة 5G", callback_data="set_pdf_5G"), InlineKeyboardButton("📥 رفع PDF لفئة 10G", callback_data="set_pdf_10G")],
            [InlineKeyboardButton("📥 رفع PDF لفئة 20G", callback_data="set_pdf_20G"), InlineKeyboardButton("📥 رفع PDF لفئة 30G", callback_data="set_pdf_30G")],
            [InlineKeyboardButton("📥 رفع PDF لفئة 50G", callback_data="set_pdf_50G"), InlineKeyboardButton("📥 رفع PDF لفئة 100G", callback_data="set_pdf_100G")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text=stats_text + "\n💡 لإضافة بطاقات: اختر الفئة من الأزرار أدناه ثم أرسل ملف الـ PDF الخاص بها.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    elif query.data.startswith("set_pdf_") and user_id == ADMIN_ID:
        cat_target = query.data.replace("set_pdf_", "")
        context.user_data['target_pdf_category'] = cat_target
        keyboard = [[InlineKeyboardButton("🔙 لوحة التحكم", callback_data="admin_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text=f"📤 تم اختيار فئة: {cat_target}\n\n"
                 f"الآن قم بإرسال ملف الـ PDF الخاص بهذه الفئة مباشرة هنا في المحادثة.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
    elif query.data.startswith("cat_"):
        category_name = query.data.replace("cat_", "")
        price = CATEGORY_PRICES.get(category_name, 0)
        
        # التحقق من رصيد المستخدم
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        balance = row[0] if row else 0.0

        if balance < price:
            await query.edit_message_text(
                text=f"❌ عذراً، رصيدك غير كافٍ لشراء فئة {category_name}.\n"
                     f"سعر البطاقة: {price} ل.س\n"
                     f"رصيدك الحالي: {balance} ل.س\n\n"
                     f"يرجى شحن محفظتك أولاً.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ شحن الرصيد", callback_data="topup_menu")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="buy_cards")]
                ])
            )
            conn.close()
            return

        # الخصم من الرصيد ومنح البطاقة فوراً
        cursor.execute("SELECT id, username, password FROM cards WHERE category = ? AND is_sold = 0 LIMIT 1", (category_name,))
        card = cursor.fetchone()

        if card:
            card_id, card_user, card_pass = card
            new_balance = balance - price
            cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
            cursor.execute("UPDATE cards SET is_sold = 1 WHERE id = ?", (card_id,))
            conn.commit()
            conn.close()

            await query.edit_message_text(
                text=f"✅ *تم الشراء بنجاح!*\n\n"
                     f"📦 الفئة: {category_name}\n"
                     f"👤 اسم المستخدم: {card_user}\n"
                     f"🔑 كلمة المرور: {card_pass}\n\n"
                     f"💰 رصيدك المتبقي: {new_balance:,.0f} ل.س\n"
                     f"شكراً لاستخدامك متجر syria net ❤️",
                parse_mode="Markdown"
            )

            # إشعار الأدمن بعملية الشراء
            try:
                buyer_username = user.username
                buyer_name = user.full_name
                admin_notification = (
                    f"🔔 عملية شراء جديدة ناجحة!\n\n"
                    f"👤 العميل: {buyer_name} (ID: {user_id})\n"
                    f"🔗 المعرف: @{buyer_username if buyer_username else 'لا يوجد'}\n"
                    f"📦 الفئة المشتراة: {category_name}\n"
                    f"💰 السعر المخصوم: {price} ل.س\n"
                    f"🔑 البطاقة المسلمة:\n"
                    f"• المستخدم: {card_user}\n"
                    f"• الباسورد: {card_pass}"
                )
                await context.bot.send_message(chat_id=ADMIN_ID, text=admin_notification, parse_mode="Markdown")
            except Exception as e:
                logging.error(f"Failed to send admin notification: {e}")
        else:
            conn.close()
            await query.edit_message_text(
                text="⚠️ عذراً، نفدت بطاقات هذه الفئة حالياً من النظام.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="buy_cards")]])
            )
        return
        
    elif query.data == "main_menu":
        context.user_data['waiting_for_tx'] = False
        context.user_data.pop('target_pdf_category', None)
        conn.close()
        await start(update, context)
        
    conn.close()

async def verify_shamcash_transaction(tx_id: str) -> dict:
    headers = {
        "Authorization": f"Bearer {SHAMCASH_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(SHAMCASH_API_URL, headers=headers, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    transactions = data if isinstance(data, list) else data.get("data", data.get("transactions", []))
                    for tx in transactions:
                        t_id = str(tx.get("id", tx.get("tranId", tx.get("transaction_id", ""))))
                        if t_id == str(tx_id):
                            amount = float(tx.get("amount", 0))
                            return {"status": True, "amount": amount}
        return {"status": False, "amount": 0}
    except Exception as e:
        logging.error(f"Error connecting to Sham Cash API: {e}")
        return {"status": False, "amount": 0}

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
        
    target_category = context.user_data.get('target_pdf_category')
    if not target_category:
        await update.message.reply_text("⚠️ يرجى أولاً الدخول إلى لوحة التحكم واختيار الفئة التي تريد رفع ملف الـ PDF لها.")
        return
        
    doc = update.message.document
    file = await context.bot.get_file(doc.file_id)
    
    pdf_file_path = "temp_upload.pdf"
    await file.download_to_drive(pdf_file_path)
    
    added = import_cards_from_pdf(pdf_file_path, target_category)
    
    if os.path.exists(pdf_file_path):
        os.remove(pdf_file_path)
        
    context.user_data['target_pdf_category'] = None
    await update.message.reply_text(
        f"✅ تمت إضافة {added} بطاقة جديدة بنجاح إلى فئة {target_category}!",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_tx', False):
        return
        
    tx_id = update.message.text.strip()
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT transaction_id FROM transactions WHERE transaction_id = ?", (tx_id,))
    if cursor.fetchone():
        conn.close()
        await update.message.reply_text("⚠️ عذراً، رقم المعاملة هذا تم استخدامه مسبقاً من قبل!")
        return

    msg = await update.message.reply_text("⏳ جاري التحقق من صحة المعاملة عبر شبكة شام كاش...")
    
    result = await verify_shamcash_transaction(tx_id)
    
    if result["status"]:
        amount = result["amount"]
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        cursor.execute("INSERT INTO transactions (transaction_id, user_id, amount) VALUES (?, ?, ?)", (tx_id, user_id, amount))
        conn.commit()
        
        # جلب الرصيد الجديد
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        new_balance = cursor.fetchone()[0]
        conn.close()
        
        context.user_data['waiting_for_tx'] = False
        
        await msg.edit_text(
            f"✅ *تم تأكيد المعاملة بنجاح!*\n"
            f"💰 تمت إضافة {amount:,.0f} ل.س إلى محفظتك.\n"
            f"💳 رصيدك الحالي: {new_balance:,.0f} ل.س",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛒 شراء بطاقة", callback_data="buy_cards")]]),
            parse_mode="Markdown"
        )
    else:
        conn.close()
        await msg.edit_text("❌ لم يتم العثور على المعاملة أو أنها غير صحيحة. تأكد من رقم المعاملة وحاول مجدداً.")

# خادم ويب مصغر لمنع انطفاء البوت على Render
async def handle_web(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app_web = web.Application()
    app_web.router.add_get("/", handle_web)
    runner = web.AppRunner(app_web)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

if __name__ == '__main__':
    init_db()
    TOKEN = "8901147731:AAFvgxlnhB5HI5dtycMxzygvobmu1lvcHCQ"
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    async def main():
        await start_web_server()
        print("البوت يعمل الآن مع خادم الويب ونظام المحفظة المتكامل...")
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        stop_event = asyncio.Event()
        await stop_event.wait()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("تم إيقاف البوت.")