import sqlite3
import logging
import os
import aiohttp
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

WALLET_ID = "107117163cf0a37a101368c97757028e"
SHAMCASH_API_URL = f"https://api-shamcash.com/api/v1/wallets/shamcash/{WALLET_ID}/transactions"
SHAMCASH_API_TOKEN = "sk_a897445f9f116c1b7df7b421339149459b289288cf90c6c915762f61bd83d1ba"

ADMIN_ID = 1683289084

CATEGORY_PRICES = {
    "5G": 70,
    "10G": 100,
    "20G": 250,
    "30G": 300,
    "50G": 500,
    "100G": 700
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
        f"أهلاً بك يا {user_name} في متجر بطاقات شبكة الإنترنت 🌐\n\n"
        "يمكنك من خلال هذا البوت شراء بطاقات الإنترنت الخاصة بالشبكة بشكل فوري وتلقائي."
        "للتوصل مع الدعم @mak77588"
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
        stats_text = "📊 *إحصائيات ومخزون البطاقات:*\n\n"
        for cat in CATEGORY_PRICES.keys():
            cursor.execute("SELECT COUNT(*) FROM cards WHERE category = ? AND is_sold = 0", (cat,))
            available = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM cards WHERE category = ? AND is_sold = 1", (cat,))
            sold = cursor.fetchone()[0]
            stats_text += f"📦 فئة {cat}: متوفر ({available}) | مباع ({sold})\n"
        conn.close()
        
        keyboard = [
            [InlineKeyboardButton("➕ إضافة بطاقات (أرسل ملف PDF واختار الفئة)", callback_data="admin_upload_help")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text=stats_text + "\n💡 *لإضافة بطاقات:* اختر الفئة أولاً من الأزرار أدناه أو أرسل ملف PDF ثم حدد الفئة.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
    elif query.data == "admin_upload_help" and user_id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("📥 رفع لـ 5G", callback_data="up_5G"), InlineKeyboardButton("📥 رفع لـ 10G", callback_data="up_10G")],
            [InlineKeyboardButton("📥 رفع لـ 20G", callback_data="up_20G"), InlineKeyboardButton("📥 رفع لـ 30G", callback_data="up_30G")],
            [InlineKeyboardButton("📥 رفع لـ 50G", callback_data="up_50G"), InlineKeyboardButton("📥 رفع لـ 100G", callback_data="up_100G")],
            [InlineKeyboardButton("🔙 لوحة التحكم", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="اختر الفئة التي تريد إضافة ملف الـ PDF إليها:", reply_markup=reply_markup)

    elif query.data.startswith("up_") and user_id == ADMIN_ID:
        cat_target = query.data.replace("up_", "")
        context.user_data['waiting_for_pdf_category'] = cat_target
        keyboard = [[InlineKeyboardButton("🔙 إلغاء", callback_data="admin_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text=f"📂 حسناً، أرسل الآن ملف الـ *PDF* الخاص بفئة *{cat_target}* وسيقوم البوت بقراءته وإضافة البطاقات تلقائياً.",
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
            text=f"لقد اخترت فئة: *{category_name}*.\n"
                 f"💰 *المبلغ المطلوب:* {price} ليرة سورية\n\n"
                 f"💸 *طريقة الدفع عبر شام كاش:*\n"
                 f"يرجى تحويل المبلغ إلى الحساب التالي:\n`{WALLET_ID}`\n\n"
                 f"بعد التحويل، *أرسل رقم المعاملة (Transaction ID)* هنا لاستلام البطاقة فورا.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
    elif query.data == "main_menu":
        context.user_data['waiting_for_tx'] = False
        context.user_data.pop('waiting_for_pdf_category', None)
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # معالجة رفع ملف الـ PDF من قبل المشرف
    if user_id == ADMIN_ID and context.user_data.get('waiting_for_pdf_category'):
        target_cat = context.user_data.get('waiting_for_pdf_category')
        
        if update.message.document:
            file = await update.message.document.get_file()
            file_path = "temp_cards.pdf"
            await file.download_to_drive(file_path)
            
            added_count = 0
            try:
                reader = PdfReader(file_path)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                
                # تحليل النص المستخرج من ملف الـ PDF واستخراج الحسابات وكلمات المرور
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                
                # خوارزمية ذكية للبحث عن أرقام الهواتف أو أسمائهم وكلمات المرور في النص
                i = 0
                while i < len(lines) - 1:
                    line = lines[i]
                    # البحث عن الأرقام التي تبدأ بـ 09 (اسم المستخدم)
                    if line.startswith("09") and len(line) == 10:
                        usr = line
                        # البحث عن كلمة المرور في الأسطر القريبة التالية
                        for j in range(1, 4):
                            if i + j < len(lines):
                                potential_pwd = lines[i + j]
                                if potential_pwd.isdigit() and len(potential_pwd) >= 4:
                                    pwd = potential_pwd
                                    conn = sqlite3.connect('shop.db')
                                    cursor = conn.cursor()
                                    cursor.execute("SELECT id FROM cards WHERE category = ? AND username = ? AND password = ?", (target_cat, usr, pwd))
                                    if not cursor.fetchone():
                                        cursor.execute("INSERT INTO cards (category, username, password, is_sold) VALUES (?, ?, ?, 0)", (target_cat, usr, pwd))
                                        added_count += 1
                                    conn.commit()
                                    conn.close()
                                    break
                    i += 1
                
                if os.path.exists(file_path):
                    os.remove(file_path)
                    
                context.user_data.pop('waiting_for_pdf_category', None)
                await update.message.reply_text(f"✅ تمت إضافة *{added_count}* بطاقة جديدة بنجاح إلى فئة *{target_cat}*!", parse_mode="Markdown")
            except Exception as e:
                if os.path.exists(file_path):
                    os.remove(file_path)
                await update.message.reply_text(f"❌ حدث خطأ أثناء قراءة ملف الـ PDF: {e}")
        else:
            await update.message.reply_text("⚠️ يرجى إرسال ملف PDF صالح.")
        return

    # معالجة استقبال رقم المعاملة من المستخدم العادي
    if not context.user_data.get('waiting_for_tx', False):
        return
        
    tx_id = update.message.text.strip()
    category = context.user_data.get('selected_category')
    expected_price = context.user_data.get('selected_price', 0)
    
    conn = sqlite3.connect('shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions WHERE transaction_id = ?", (tx_id,))
    if cursor.fetchone():
        conn.close()
        await update.message.reply_text("⚠️ عذراً، رقم المعاملة هذا تم استخدامه مسبقاً!")
        return

    await update.message.reply_text(f"⏳ جاري التحقق من رقم المعاملة ({tx_id}) عبر شام كاش...", parse_mode="Markdown")
    
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
            
            await update.message.reply_text(
                f"✅ *تم تأكيد الدفع بنجاح! إليك تفاصيل بطاقتك:*\n\n"
                f"📦 الفئة: {category}\n"
                f"👤 اسم المستخدم: {card_user}\n"
                f"🔑 كلمة المرور: {card_pass}\n\n"
                f"شكراً لاستخدامك متجرنا ❤️",
                parse_mode="Markdown"
            )
        else:
            conn.close()
            await update.message.reply_text("⚠️ عذراً، نفدت بطاقات هذه الفئة حالياً من النظام!")
    else:
        conn.close()
        await update.message.reply_text("❌ لم يتم العثور على معاملة مطابقة لهذا الرقم في سجلات شام كاش. تأكد من صحة الرقم.")

if __name__ == '__main__':
    init_db()
    TOKEN = "8901147731:AAFvgxlnhB5HI5dtycMxzygvobmu1lvcHCQ"
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL | (filters.TEXT & ~filters.COMMAND), handle_message))
    
    print("البوت يعمل الآن مع دعم رفع ملفات الـ PDF وقراءة البطاقات...")
    app.run_polling()