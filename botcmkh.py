import os
import telebot
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # لتقليل استخدام الذاكرة
import matplotlib.pyplot as plt
from io import BytesIO
import requests
import json
import datetime
import pytz
from threading import Thread
from flask import Flask
import time
import logging
from telebot import types
import talib

# ------ الإعدادات الأساسية ------ #
TOKEN = os.getenv('6613881787:AAGKbvKR5lMGDJ0GtsTWIuU9UDuuh0BLYzU')  # توكن البوت من متغيرات البيئة
ADMIN_ID = os.getenv('5983183138')  # أيدي الأدمن من متغيرات البيئة
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ------ قاعدة البيانات ------ #
DB_FILE = "trading_bot_db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {
            "users": {},
            "subscriptions": {
                "trial": {"duration": 7, "messages": 10, "price": 0},
                "basic": {"duration": 30, "messages": 50, "price": 10},
                "pro": {"duration": 90, "messages": 200, "price": 25},
                "vip": {"duration": 365, "messages": 1000, "price": 100}
            },
            "signals": []
        }
    with open(DB_FILE) as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# ------ نظام الاشتراكات ------ #
def check_subscription(user_id):
    db = load_db()
    user = db["users"].get(str(user_id))
    
    if not user:
        return False, "⚠️ أنت غير مشترك! استخدم /subscribe للاشتراك"
    
    expiry = datetime.datetime.fromisoformat(user["expiry_date"])
    if datetime.datetime.now(pytz.utc) > expiry:
        return False, "❌ انتهت صلاحية اشتراكك! استخدم /subscribe لتجديده"
    
    if user.get("used_messages", 0) >= user["message_limit"]:
        return False, "❌ لقد استهلكت جميع رسائلك! استخدم /subscribe لشراء المزيد"
    
    return True, ""

def update_message_count(user_id):
    db = load_db()
    if str(user_id) in db["users"]:
        db["users"][str(user_id)]["used_messages"] = db["users"][str(user_id)].get("used_messages", 0) + 1
        save_db(db)

def add_subscription(user_id, plan_name):
    db = load_db()
    
    if plan_name not in db["subscriptions"]:
        return False, "خطة غير صالحة"
    
    plan = db["subscriptions"][plan_name]
    expiry_date = datetime.datetime.now(pytz.utc) + datetime.timedelta(days=plan["duration"])
    
    db["users"][str(user_id)] = {
        "plan": plan_name,
        "expiry_date": expiry_date.isoformat(),
        "subscribe_date": datetime.datetime.now(pytz.utc).isoformat(),
        "message_limit": plan["messages"],
        "used_messages": 0
    }
    
    save_db(db)
    return True, "تم تفعيل الاشتراك بنجاح"

# ------ التحليل الفني ------ #
def get_crypto_data(symbol, interval='4h', limit=50):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        logging.error(f"Error fetching data: {str(e)}")
        return None

def analyze_symbol(symbol):
    df = get_crypto_data(symbol)
    if df is None:
        return None, "❌ فشل في الحصول على بيانات السوق"
    
    # حساب المؤشرات الفنية
    df['SMA_20'] = df['close'].rolling(20).mean()
    df['RSI'] = talib.RSI(df['close'], timeperiod=14)
    df['MACD'], df['MACD_signal'], _ = talib.MACD(df['close'])
    
    # تحديد مستويات الدعم والمقاومة
    support = df['low'].min()
    resistance = df['high'].max()
    
    # إنشاء الرسم البياني
    plt.figure(figsize=(10, 6))
    plt.plot(df['timestamp'], df['close'], label='السعر', color='blue')
    plt.plot(df['timestamp'], df['SMA_20'], label='المتوسط 20', color='orange')
    plt.axhline(support, color='green', linestyle='--', alpha=0.7, label='دعم')
    plt.axhline(resistance, color='red', linestyle='--', alpha=0.7, label='مقاومة')
    plt.title(f"تحليل {symbol}")
    plt.legend()
    plt.xticks(rotation=45)
    
    # حفظ الرسم في ذاكرة المؤقتة
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    # إنشاء التوصية
    last_close = df['close'].iloc[-1]
    recommendation = "📊 التوصية: "
    if last_close > df['SMA_20'].iloc[-1] and df['RSI'].iloc[-1] < 70:
        recommendation += "🟢 شراء (اتجاه صاعد)"
    elif last_close < df['SMA_20'].iloc[-1] and df['RSI'].iloc[-1] > 30:
        recommendation += "🔴 بيع (اتجاه هابط)"
    else:
        recommendation += "🟡 احتفظ (سوق متذبذب)"
    
    analysis = f"""
📈 تحليل {symbol}
💰 السعر الحالي: {last_close:.2f}
📊 RSI: {df['RSI'].iloc[-1]:.2f} {'(تشبع شرائي) ⚠️' if df['RSI'].iloc[-1] > 70 else '(تشبع بيعي) 📉' if df['RSI'].iloc[-1] < 30 else ''}
📈 MACD: {'صاعد 📈' if df['MACD'].iloc[-1] > df['MACD_signal'].iloc[-1] else 'هابط 📉'}

🔽 أقوى دعم: {support:.2f}
🔼 أقوى مقاومة: {resistance:.2f}

{recommendation}
"""
    
    return buf, analysis

# ------ أوامر البوت الأساسية ------ #
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_msg = """
🚀 *مرحباً بك في بوت التداول الذكي المتقدم* 🚀

📌 *الميزات الرئيسية:*
- تحليل فني متقدم مع رسوم بيانية
- توصيات تداول فورية
- نظام اشتراكات متكامل
- إشارات تداول احترافية

⚡ *الأوامر المتاحة:*
/analyze [رمز] - تحليل عملة (مثال: /analyze BTCUSDT)
/subscribe - الاشتراك في البوت
/myinfo - معلومات اشتراكك
/support - الدعم الفني

👑 للأدمن: /admin
"""
    bot.send_message(message.chat.id, welcome_msg, parse_mode='Markdown')

@bot.message_handler(commands=['analyze'])
def handle_analysis(message):
    try:
        # التحقق من الاشتراك
        auth, msg = check_subscription(message.from_user.id)
        if not auth:
            bot.reply_to(message, msg)
            return
        
        symbol = message.text.split()[1].upper()
        bot.send_message(message.chat.id, f"🔍 جاري تحليل {symbol}...")
        
        # التحليل الفني
        chart, analysis = analyze_symbol(symbol)
        
        if chart:
            bot.send_photo(message.chat.id, chart, caption=analysis, parse_mode='Markdown')
            update_message_count(message.from_user.id)
        else:
            bot.reply_to(message, analysis)
            
    except IndexError:
        bot.reply_to(message, "⚠️ يرجى تحديد رمز العملة (مثال: /analyze BTCUSDT)")
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ: {str(e)}")

# ------ نظام الاشتراكات ------ #
@bot.message_handler(commands=['subscribe'])
def show_subscription_plans(message):
    db = load_db()
    markup = types.InlineKeyboardMarkup()
    
    for plan, details in db["subscriptions"].items():
        btn = types.InlineKeyboardButton(
            f"{plan.upper()} - {details['duration']} يوم - {details['messages']} رسالة - ${details['price']}",
            callback_data=f"sub_{plan}"
        )
        markup.add(btn)
    
    bot.send_message(
        message.chat.id,
        "📌 اختر خطة الاشتراك المناسبة لك:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('sub_'))
def handle_subscription_selection(call):
    plan = call.data.split('_')[1]
    db = load_db()
    
    if plan not in db["subscriptions"]:
        bot.answer_callback_query(call.id, "خطة غير صالحة")
        return
    
    success, message = add_subscription(call.from_user.id, plan)
    
    if success:
        plan_data = db["subscriptions"][plan]
        expiry_date = datetime.datetime.fromisoformat(db["users"][str(call.from_user.id)]["expiry_date"])
        
        response = f"""
🎉 *تم تفعيل اشتراكك بنجاح!*

الخطة: {plan.upper()}
المدة: {plan_data['duration']} يوم
الرسائل المتاحة: {plan_data['messages']}
تاريخ الانتهاء: {expiry_date.strftime('%Y-%m-%d')}

يمكنك البدء باستخدام البوت الآن!
"""
        bot.send_message(call.message.chat.id, response, parse_mode='Markdown')
    else:
        bot.send_message(call.message.chat.id, f"❌ فشل في الاشتراك: {message}")

@bot.message_handler(commands=['myinfo'])
def user_info(message):
    db = load_db()
    user_id = str(message.from_user.id)
    user = db["users"].get(user_id)
    
    if not user:
        bot.reply_to(message, "❌ ليس لديك اشتراك نشط. استخدم /subscribe للاشتراك")
        return
    
    expiry = datetime.datetime.fromisoformat(user["expiry_date"])
    remaining_days = (expiry - datetime.datetime.now(pytz.utc)).days
    remaining_msgs = user["message_limit"] - user.get("used_messages", 0)
    
    info = f"""
📋 *معلومات اشتراكك:*

🔹 الخطة: {user['plan'].upper()}
📅 تاريخ البدء: {datetime.datetime.fromisoformat(user['subscribe_date']).strftime('%Y-%m-%d')}
⏳ تاريخ الانتهاء: {expiry.strftime('%Y-%m-%d')}
📆 الأيام المتبقية: {remaining_days}
✉️ الرسائل المتبقية: {remaining_msgs}/{user['message_limit']}
"""
    bot.reply_to(message, info, parse_mode='Markdown')

# ------ واجهة الأدمن ------ #
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "❌ ليس لديك صلاحية الوصول")
        return
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("عرض الإحصائيات", callback_data="admin_stats"),
        types.InlineKeyboardButton("إضافة اشتراك", callback_data="admin_add_sub")
    )
    
    bot.reply_to(message, "👑 لوحة تحكم الإدارة", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def handle_admin_callback(call):
    if str(call.from_user.id) != ADMIN_ID:
        bot.answer_callback_query(call.id, "ليس لديك الصلاحية")
        return
    
    if call.data == "admin_stats":
        show_statistics(call.message)
    elif call.data == "admin_add_sub":
        request_user_id(call.message)

def show_statistics(message):
    db = load_db()
    total_users = len(db["users"])
    active_users = sum(1 for u in db["users"].values() 
                      if datetime.datetime.fromisoformat(u["expiry_date"]) > datetime.datetime.now(pytz.utc))
    
    text = f"""
📊 *إحصائيات النظام:*
    
👥 إجمالي المستخدمين: {total_users}
🟢 مستخدمين نشطين: {active_users}
    
📈 توزيع الخطط:
"""
    plan_counts = {}
    for user in db["users"].values():
        plan = user["plan"]
        plan_counts[plan] = plan_counts.get(plan, 0) + 1
    
    for plan, count in plan_counts.items():
        text += f"- {plan.capitalize()}: {count} مستخدم\n"
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

def request_user_id(message):
    msg = bot.send_message(message.chat.id, "أرسل معرف المستخدم (User ID):")
    bot.register_next_step_handler(msg, process_user_id)

def process_user_id(message):
    try:
        user_id = message.text.strip()
        db = load_db()
        plans = list(db["subscriptions"].keys())
        
        keyboard = types.InlineKeyboardMarkup()
        for plan in plans:
            keyboard.add(types.InlineKeyboardButton(plan.capitalize(), callback_data=f"addsub_{user_id}_{plan}"))
        
        bot.send_message(message.chat.id, f"اختر خطة للمستخدم {user_id}:", reply_markup=keyboard)
    
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('addsub_'))
def confirm_add_subscription(call):
    _, user_id, plan = call.data.split('_')
    
    success, message = add_subscription(user_id, plan)
    if success:
        bot.answer_callback_query(call.id, "✅ تم تفعيل الاشتراك")
        bot.send_message(call.message.chat.id, f"تم تفعيل اشتراك {plan} للمستخدم {user_id}")
    else:
        bot.answer_callback_query(call.id, "❌ فشل التفعيل")

# ------ إبقاء البوت نشطًا ------ #
@app.route('/')
def home():
    return "Trading Bot is Running!"

def keep_alive():
    app.run(host='0.0.0.0', port=8000)

def ping_server():
    while True:
        try:
            requests.get("https://your-bot-name.onrender.com")  # استبدل برابط تطبيقك
            time.sleep(300)  # كل 5 دقائق
        except:
            time.sleep(60)

def run_bot():
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            logging.error(f"Bot error: {str(e)}")
            time.sleep(10)

# ------ تشغيل النظام ------ #
if __name__ == '__main__':
    # إعداد التسجيل
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # تشغيل الخدمات المساندة
    Thread(target=keep_alive, daemon=True).start()
    Thread(target=ping_server, daemon=True).start()
    
    # تشغيل البوت الرئيسي
    logging.info("Starting Trading Bot...")
    run_bot()