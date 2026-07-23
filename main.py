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
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            user_id INTEGER,
            category TEXT
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
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    keyboard = [
        [InlineKeyboardButton("💳 شراء بطاقات الإنترنت", callback_data="buy_cards")],
        [InlineKeyboardButton("🚀 تشغيل البوت (Start)", callback_data="main_menu")]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ لوحة تحكم المشرف (Admin)", callback_data="admin_panel")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"🌐 أهلاً بك في SYRIA NET 🌐 {user_name} في متجر بطاقات شبكة الإنترنت 🌐\n\n"
        "يمكنك من خلال هذا البوت شراء بطاقات الإنترنت الخاصة بالشبكة بشكل فوري وتلقائي.\n"
        "شكراً لاختياركم SYRIA NET 💙"
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
    user_id = query.from_user.id
    
    if query.data == "buy_cards":
        keyboard = [
            [InlineKeyboardButton("🌐 فئة 5 جيجا (70 ل.س)", callback_data="cat_5G"), InlineKeyboardButton("🌐 فئة 10 جيجا (100 ل.س)", callback_data="cat_10G")],
            [InlineKeyboardButton("🌐 فئة 20 جيجا (250 ل.س)", callback_data="cat_20G"), InlineKeyboardButton("🌐 فئة 30 جيجا (300 ل.س)", callback_data="cat_30G")],
            [InlineKeyboardButton("🌐 فئة 50 جيجا (500 ل.س)", callback_data="cat_50G"), InlineKeyboardButton("🌐 فئة 100 جيجا (700 ل.س)", callback_data="cat_100G")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text="اختر فئة البطاقات التي تريد شراءها:",
            reply_markup=reply_markup
        )
        
    elif query.data == "admin_panel" and user_id == ADMIN_ID:
        conn = sqlite3.connect('shop.db')
        cursor = conn.cursor()
        stats_text = "📊 إحصائيات ومخزون البطاقات:\n\n"
        for cat in CATEGORY_PRICES.keys():
            cursor.execute("SELECT COUNT(*) FROM cards WHERE category = ? AND is_sold = 0", (cat,))
            available = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM cards WHERE category = ? AND is_sold = 1", (cat,))
            sold = cursor.fetchone()[0]
            stats_text += f"📦 فئة {cat}: متوفر ({available}) | مباع ({sold})\n"
        conn.close()
        
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
            text=f"📤 *تم اختيار فئة: {cat_target}*\n\n"
                 f"الآن قم بإرسال ملف الـ PDF الخاص بهذه الفئة مباشرة هنا في المحادثة.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
    elif query.data.startswith("cat_"):
        category_name = query.data.replace("cat_", "")
        price = CATEGORY_PRICES.get(category_name, 0)
        
        context.user_data['selected_category'] = category_name
        context.user_data['selected_price'] = price
        context.user_data['waiting_for_tx'] = True
        
        keyboard = [
            [InlineKeyboardButton("❌ إلغاء العملية", callback_data="buy_cards")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=f"لقد اخترت فئة: {category_name}.\n"
                 f"💰 المبلغ المطلوب: {price} ليرة سورية\n\n"
                 f"💸 طريقة الدفع عبر شام كاش:\n"
                 f"يرجى تحويل المبلغ إلى الحساب التالي:\n`{WALLET_ID}`\n\n"
                 f"بعد التحويل، أرسل رقم المعاملة (Transaction ID) هنا لاستلام البطاقة فورا.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
    elif query.data == "main_menu":
        context.user_data['waiting_for_tx'] = False
        context.user_data.pop('target_pdf_category', None)
        await start(update, context)

async def verify_shamcash_transaction(tx_id: str, expected_amount: float) -> bool:
    headers = {
        "Authorization": f"Bearer {SHAMCASH_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(SHAMCASH_API_URL, headers=headers, timeout=15) as response:
                if response.status == 200:
                    transactions = await response.json()
                    if isinstance(transactions, list):
                        for tx in transactions:
                            if str(tx.get("id")) == str(tx_id) and float(tx.get("amount", 0)) >= float(expected_amount):
                                return True
        return False
    except Exception as e:
        logging.error(f"Error connecting to Sham Cash API: {e}")
        return False

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
        f"✅ تمت إضافة *{added}* بطاقة جديدة بنجاح إلى فئة {target_category}!",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_tx', False):
        return
        
    tx_id = update.message.text.strip()
    user_id = update.effective_user.id
    category = context.user_data.get('selected_category')
    expected_price = context.user_data.get('selected_price', 0)
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions WHERE transaction_id = ?", (tx_id,))
    if cursor.fetchone():
        conn.close()
        await update.message.reply_text("⚠️ عذراً، رقم المعاملة هذا تم استخدامه مسبقاً!")
        return

    await update.message.reply_text("⏳ جاري التحقق من المعاملة وتسليم البطاقة...")
    
    is_valid_payment = await verify_shamcash_transaction(tx_id, expected_price)
    
    if is_valid_payment:
        cursor.execute("SELECT id, username, password FROM cards WHERE category = ? AND is_sold = 0 LIMIT 1", (category,))
        card = cursor.fetchone()
        
        if card:
            card_id, card_user, card_pass = card
            cursor.execute("UPDATE cards SET is_sold = 1 WHERE id = ?", (card_id,))
            cursor.execute("INSERT INTO transactions (transaction_id, user_id, category) VALUES (?, ?, ?)", (tx_id, user_id, category))
            conn.commit()
            conn.close()
            
            context.user_data['waiting_for_tx'] = False
            
            # إرسال البطاقة للمشتري
            await update.message.reply_text(
                f"✅ تم تأكيد الدفع بنجاح! إليك تفاصيل بطاقتك:\n\n"
                f"📦 الفئة: {category}\n"
                f"👤 اسم المستخدم: {card_user}\n"
                f"🔑 كلمة المرور: {card_pass}\n\n"
                f"شكراً لاستخدامك متجر syria net ❤️",
                parse_mode="Markdown"
            )

            # إرسال إشعار فوري للأدمن
            try:
                buyer_username = update.effective_user.username
                buyer_name = update.effective_user.first_name
                admin_notification = (
                    f"🔔 *عملية شراء جديدة ناجحة!*\n\n"
                    f"👤 العميل: {buyer_name} (ID: {user_id})\n"
                    f"🔗 المعرف: @{buyer_username if buyer_username else 'لا يوجد'}\n"
                    f"📦 الفئة المشتراة: {category}\n"
                    f"💳 رقم المعاملة: {tx_id}\n"
                    f"🔑 البطاقة المسلمة:\n"
                    f"• المستخدم: {card_user}\n"
                    f"• الباسورد: {card_pass}"
                )
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=admin_notification,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logging.error(f"Failed to send admin notification: {e}")
        else:
            conn.close()
            await update.message.reply_text("⚠️ عذراً، نفدت بطاقات هذه الفئة حالياً من النظام!")
    else:
        conn.close()
        await update.message.reply_text("❌ لم يتم العثور على معاملة صحيحة بهذا الرقم أو أن المبلغ غير مطابق.")

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
    
    import asyncio
    
    async def main():
        await start_web_server()
        print("البوت يعمل الآن مع خادم الويب ودعم رفع ملفات الـ PDF...")
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        # يبقي التطبيق مستمراً بالعمل
        stop_event = asyncio.Event()
        await stop_event.wait()

    if __name__ == '__main__':
        init_db()
        TOKEN = "8901147731:AAFvgxlnhB5HI5dtycMxzygvobmu1lvcHCQ"
        app = ApplicationBuilder().token(TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        asyncio.run(main())