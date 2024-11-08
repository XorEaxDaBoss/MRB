from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import logging
import requests
import asyncio
from fake_useragent import UserAgent
from faker import Faker
import mysql.connector
import random
import string
import os
import time
from datetime import datetime, timedelta
from keep_alive import keep_alive

keep_alive()

# Initialize the bot application
TOKEN = os.environ.get('TOKEN')
OWNER_ID = os.environ.get('OWNER_ID')
OWNER_USERNAME = 'gdbs2'
application = Application.builder().token(TOKEN).build()

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Faker
fake = Faker()

# Banner
banner = "Ohayo"
print("\033[31m", banner, "\033[0m")

# Database connection functions
def connect_db():
    return mysql.connector.connect(
        host=os.environ['DB_HOST'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        database=os.environ['DB_NAME']
    )

def close_db(connection):
    connection.close()

# Helper functions
def is_user_registered(user_id):
    if str(user_id) == OWNER_ID:
        return True
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()
    close_db(conn)
    return bool(result)

def get_user_credits(user_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT credits FROM users WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()
    close_db(conn)
    return result[0] if result else None

def increment_report_count():
    conn = connect_db()
    cursor = conn.cursor()
    today = datetime.now().date()
    cursor.execute(
        "INSERT INTO reports_count (date, total_reports) VALUES (%s, 1) "
        "ON DUPLICATE KEY UPDATE total_reports = total_reports + 1",
        (today,)
    )
    conn.commit()
    close_db(conn)

def update_user_report_time(user_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET last_report_time = NOW() WHERE user_id = %s",
        (user_id,)
    )
    conn.commit()
    close_db(conn)

def check_cooldown(user_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT last_report_time, account_type FROM users WHERE user_id = %s",
        (user_id,)
    )
    result = cursor.fetchone()
    close_db(conn)
    
    if not result or str(user_id) == OWNER_ID:
        return False
    
    last_time, account_type = result
    if account_type == 'FREE' and last_time:
        cooldown = timedelta(seconds=15)
        return datetime.now() - last_time < cooldown
    return False

def get_main_menu_keyboard(user_id):
    keyboard = [
        [KeyboardButton("📢 Report"), KeyboardButton("💾 Save Username"), KeyboardButton("🔌 Proxies")],
        [KeyboardButton("🛠️ Tools"), KeyboardButton("ℹ️ User Info"), KeyboardButton("💰 Credits")]
    ]
    if str(user_id) == OWNER_ID:
        keyboard.append([KeyboardButton("🔑 Keygen"), KeyboardButton("👑 Owner Panel")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = get_main_menu_keyboard(update.effective_user.id)
    message = "👋 Welcome back! Choose an option:"
    if update.callback_query:
        await update.callback_query.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def register_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "NoUsername"
    full_name = update.effective_user.full_name

    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()

    if result:
        await update.message.reply_text("You're already registered!")
    else:
        cursor.execute(
            "INSERT INTO users (user_id, username, name, account_type, credits) VALUES (%s, %s, %s, %s, %s)",
            (user_id, username, full_name, "FREE", 0)
        )
        conn.commit()
        await update.message.reply_text("Registration successful! Welcome to the bot.")
    
    close_db(conn)

# Generate Key (restricted to OWNER_ID)
async def generate_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if str(user_id) != OWNER_ID:
        await update.message.reply_text("Unauthorized access.")
        return

    try:
        credits = int(context.args[0])  # /keygen [amount]
    except (IndexError, ValueError):
        await update.message.reply_text("Please provide a valid credit amount. Usage: /keygen [amount]")
        return

    key_id = 'MRB-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO user_keys (key_id, credits) VALUES (%s, %s)", (key_id, credits))
    conn.commit()
    close_db(conn)
    await update.message.reply_text(f"Generated key: `{key_id}` with {credits} credits", parse_mode='Markdown')

# Generate a key with a specified amount of credits
async def generate_key_with_credits(update: Update, context: ContextTypes.DEFAULT_TYPE, credits: int):
    key_id = 'MRB-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO user_keys (key_id, credits) VALUES (%s, %s)", (key_id, credits))
    conn.commit()
    close_db(conn)
    await update.callback_query.edit_message_text(f"Generated key: `{key_id}` with {credits} credits", parse_mode='Markdown')

# Redeem Key
async def redeem_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        key_id = context.args[0]  # Assumes /redeem <key_id>
    except IndexError:
        await update.message.reply_text("Please enter a valid key. Usage: /redeem <key>")
        return

    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT credits, is_redeemed FROM user_keys WHERE key_id = %s", (key_id,))
    result = cursor.fetchone()
    if result and not result[1]:  # Check if key exists and is not redeemed
        credits = result[0]
        cursor.execute("UPDATE user_keys SET is_redeemed = TRUE, redeemed_by = %s, redeemed_at = NOW() WHERE key_id = %s", (update.effective_user.id, key_id))
        cursor.execute("UPDATE users SET credits = credits + %s, account_type = 'PREMIUM' WHERE user_id = %s", (credits, update.effective_user.id))
        conn.commit()
        response = f"Key redeemed successfully! {credits} credits added. Your account has been upgraded to PREMIUM."
    else:
        response = "Invalid or already redeemed key."
    close_db(conn)
    await update.message.reply_text(response)

# Function to retrieve user information
async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name, username, account_type, credits FROM users WHERE user_id = %s", (user_id,))
    user_data = cursor.fetchone()
    close_db(conn)
    if user_data:
        name, username, account_type, credits = user_data
        if str(user_id) == OWNER_ID:
            account_type = 'OWNER'
            credits = 'Unlimited'
        await update.message.reply_text(
            f"ℹ️ *User Info*\n\n"
            f"ID: {user_id}\n"
            f"Name: {name}\n"
            f"Username: @{username}\n"
            f"Type: {account_type}\n"
            f"Credits: {credits}",
            parse_mode='Markdown'
        )
    else:
        if str(user_id) == OWNER_ID:
            account_type = 'OWNER'
            name = update.effective_user.full_name
            username = update.effective_user.username or "NoUsername"
            credits = 'Unlimited'
            await update.message.reply_text(
                f"ℹ️ *User Info*\n\n"
                f"ID: {user_id}\n"
                f"Name: {name}\n"
                f"Username: @{username}\n"
                f"Type: {account_type}\n"
                f"Credits: {credits}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("User not registered.")

# Bin Lookup API call
async def bin_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bin_numbers = [bin.strip() for bin in update.message.text.strip().split(',')]
    result_text = ""
    try:
        for bin_number in bin_numbers:
            response = requests.get(f"https://bins.antipublic.cc/bins/{bin_number}")
            if response.status_code == 200:
                bin_info = response.json()
                result_text += f"BIN: {bin_number}\n"
                for key, value in bin_info.items():
                    result_text += f"{key.capitalize()}: {value}\n"
                result_text += "\n"
            else:
                result_text += f"BIN: {bin_number} - Not Found\n\n"
        await update.message.reply_text(result_text)
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {e}")
    context.user_data['awaiting_bin_input'] = False
    await send_main_menu(update, context)e

def send_report(target_user: str, proxy=None):
    username = fake.user_name()
    domain = fake.free_email_domain()
    email = f"{username}@{domain}"
    country_code = fake.country_calling_code()
    mobile_number = fake.random_number(digits=10)
    generated_number = f"{country_code}{mobile_number}"
    user_agent = UserAgent().random

    text = ("Hello sir/ma'am,\n\n"
            f"I would like to report a Telegram user who is engaging in suspicious and harmful activities. Their username is {target_user}. "
            "I believe they may be involved in scams and phishing attempts, which is causing harm to the community. "
            "I would appreciate it if you could look into this matter and take appropriate action.\n\n"
            "Thank you for your attention to this matter.")

    cookies = {
        'stel_ln': 'en',
        'stel_ssid': 'f578802e99c4b87012_3506401586024839227',
    }
    headers = {
        'User-Agent': user_agent,
        'Accept-Language': 'en,en-US;q=0.5',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://telegram.org',
        'Connection': 'keep-alive',
        'Referer': 'https://telegram.org/support',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
    }
    data = {
        'message': text,
        'email': email,
        'phone': generated_number,
        'setln': '',
    }

    try:
        proxy_dict = {'http': proxy, 'https': proxy} if proxy else None
        response = requests.post(
            'https://telegram.org/support',
            cookies=cookies,
            headers=headers,
            data=data,
            proxies=proxy_dict
        )
        response.raise_for_status()

        if "We will try to reply as soon as possible." in response.text:
            increment_report_count()
            return True, email
        return False, "Report Failed."
    except requests.exceptions.RequestException as e:
        return False, f"Error: {str(e)}"
       
# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_markup = get_main_menu_keyboard(update.effective_user.id)
    await update.message.reply_text(
        "👋 Welcome to *Ohayo Auto Report Bot*! Choose an option:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Handle button presses
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_user_registered(update.effective_user.id):
        await update.message.reply_text("Please register first using /reg command.")
        return

    text = update.message.text
    if text == "📢 Report":
        keyboard = [
            [
                InlineKeyboardButton("Single Report", callback_data='single_report'),
                InlineKeyboardButton("Mass Report", callback_data='mass_report')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Choose an action:", reply_markup=reply_markup)
    
    elif text == "🛠️ Tools":
        keyboard = [
            [
                InlineKeyboardButton("Bin Lookup", callback_data='bin_lookup'),
                InlineKeyboardButton("Anti-Public", callback_data='anti_public')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Choose a tool:", reply_markup=reply_markup)
    
    elif text == "💾 Save Username":
        context.user_data['awaiting_username'] = True
        await update.message.reply_text("Please enter the username of the scammer you want to report (e.g., @username):")
    
    elif text == "🔌 Proxies":
        context.user_data['awaiting_proxies'] = True
        await update.message.reply_text("Send your proxies in any format in one message or a file (.txt).")
    
    elif text == "ℹ️ User Info":
        await user_info(update, context)
    
    elif text == "💰 Credits":
        keyboard = [
            [
                InlineKeyboardButton("My Balance", callback_data='my_balance'),
                InlineKeyboardButton("Add Credits", url=f"https://t.me/{OWNER_USERNAME}?start=Buy%20key.%20🗝")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Choose an option:", reply_markup=reply_markup)
    
    elif text == "🔑 Keygen":
        if str(update.effective_user.id) == OWNER_ID:
            keyboard = [
                [
                    InlineKeyboardButton("100 Credits", callback_data='keygen_100'),
                    InlineKeyboardButton("200 Credits", callback_data='keygen_200'),
                    InlineKeyboardButton("1000 Credits", callback_data='keygen_1000')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Choose the amount of credits for the key:", reply_markup=reply_markup)
        else:
            await update.message.reply_text("Unauthorized access.")
    
    elif text == "👑 Owner Panel":
        if str(update.effective_user.id) == OWNER_ID:
            await show_owner_panel(update, context)
        else:
            await update.message.reply_text("Unauthorized access.")
    
    else:
        await handle_text(update, context)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    user_id = update.effective_user.id

    if data == 'single_report':
        target_user = await get_saved_username(user_id)
        if target_user:
            # Apply cooldown only for free users
            if str(user_id) != OWNER_ID:
                conn = connect_db()
                cursor = conn.cursor()
                cursor.execute("SELECT account_type FROM users WHERE user_id = %s", (user_id,))
                account_type = cursor.fetchone()[0]
                close_db(conn)

                if account_type == 'FREE':
                    last_report_time = context.user_data.get('last_report_time')
                    current_time = time.time()
                    if last_report_time:
                        time_diff = current_time - last_report_time
                        if time_diff < 15:
                            time_left = int(15 - time_diff)
                            await query.edit_message_text(f"Please wait {time_left} seconds before using Single Report again.")
                            return
                    # Update last report time
                    context.user_data['last_report_time'] = current_time

            # Check credits only for premium or owner users
            if account_type != 'FREE' and str(user_id) != OWNER_ID:
                credits = get_user_credits(user_id)
                if credits is None or credits < 1:
                    keyboard = [
                        [
                            InlineKeyboardButton("Add Credits", url=f"https://t.me/{OWNER_USERNAME}?start=Buy%20key.%20🗝")
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.edit_message_text("Insufficient credits. Please redeem a key to get more credits.", reply_markup=reply_markup)
                    await send_main_menu(update, context)
                    return
                # Deduct 1 credit for non-free users
                conn = connect_db()
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET credits = credits - 1 WHERE user_id = %s", (user_id,))
                conn.commit()
                # Check for downgrade to free if credits reach zero
                cursor.execute("SELECT credits FROM users WHERE user_id = %s", (user_id,))
                credits = cursor.fetchone()[0]
                if credits <= 0:
                    cursor.execute("UPDATE users SET account_type = 'FREE' WHERE user_id = %s", (user_id,))
                    conn.commit()
                close_db(conn)

            success, response_message = send_report(target_user)
            if success:
                blurred_email = blur_email(response_message)
                await query.edit_message_text(f"✅ {blurred_email} : Reported @{target_user}!")
            else:
                await query.edit_message_text(f"❌ Report failed: {response_message}")
            await send_main_menu(update, context)
        else:
            await query.edit_message_text("No username saved. Please use 'Save Username' to set a username first.")
            await send_main_menu(update, context)

    elif data == 'mass_report':
        # Mass report logic remains the same, requiring credits
        target_user = await get_saved_username(user_id)
        if target_user:
            keyboard = [
                [
                    InlineKeyboardButton("10 Reports - 9 Credits", callback_data='mass_10'),
                    InlineKeyboardButton("20 Reports - 17 Credits", callback_data='mass_20')
                ],
                [
                    InlineKeyboardButton("50 Reports - 40 Credits", callback_data='mass_50'),
                    InlineKeyboardButton("100 Reports - 75 Credits", callback_data='mass_100')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Choose the number of reports:", reply_markup=reply_markup)
        else:
            await query.edit_message_text("No username saved. Please use 'Save Username' to set a username first.")
            await send_main_menu(update, context)

    elif data.startswith('mass_'):
        count = int(data.split('_')[1])
        await start_mass_report(update, context, count)
        await send_main_menu(update, context)
    elif data == 'bin_lookup':
        context.user_data['awaiting_bin_input'] = True
        await query.edit_message_text("Please enter the BIN number(s), separated by commas:")
    elif data == 'anti_public':
        context.user_data['awaiting_anti_public_file'] = True
        await query.edit_message_text("Please upload a .txt file containing the card numbers.")
    elif data == 'my_balance':
        credits = get_user_credits(user_id)
        await query.edit_message_text(f"Your current balance is: {credits} credits.")
        await send_main_menu(update, context)
    elif data.startswith('keygen_'):
        if str(user_id) == OWNER_ID:
            credits = int(data.split('_')[1])
            await generate_key_with_credits(update, context, credits)
            await send_main_menu(update, context)
        else:
            await query.edit_message_text("Unauthorized access.")
    else:
        await query.edit_message_text("Unknown action.")

# Broadcast message to all users
async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    close_db(conn)

    sent = 0
    failed = 0
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user[0],
                text=f"📢 *Broadcast Message*\n\n{message}",
                parse_mode='Markdown'
            )
            sent += 1
        except Exception:
            failed += 1

    await update.message.reply_text(
        f"Broadcast completed!\n"
        f"✅ Sent: {sent}\n"
        f"❌ Failed: {failed}"
    )
    context.user_data['awaiting_broadcast'] = False

# Owner Panel Functions
async def show_owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("📊 Statistics", callback_data='owner_stats'),
            InlineKeyboardButton("📣 Broadcast", callback_data='owner_broadcast')
        ],
        [
            InlineKeyboardButton("👥 User Management", callback_data='owner_users'),
            InlineKeyboardButton("🔑 Key Management", callback_data='owner_keys')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👑 Owner Panel", reply_markup=reply_markup)

async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = connect_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    today = datetime.now().date()
    cursor.execute("SELECT total_reports FROM reports_count WHERE date = %s", (today,))
    today_reports = cursor.fetchone()
    today_reports = today_reports[0] if today_reports else 0
    
    cursor.execute("SELECT SUM(total_reports) FROM reports_count")
    total_reports = cursor.fetchone()[0] or 0
    
    stats_text = (
        f"📊 *Bot Statistics*\n\n"
        f"👥 Total Users: {total_users}\n"
        f"📈 Total Reports: {total_reports}\n"
        f"📊 Today's Reports: {today_reports}\n"
    )
    
    close_db(conn)
    await update.callback_query.edit_message_text(stats_text, parse_mode='Markdown')

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['awaiting_broadcast'] = True
    await update.callback_query.edit_message_text(
        "Please enter the message you want to broadcast to all users:"
    )

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    close_db(conn)
    
    sent = 0
    failed = 0
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user[0],
                text=f"📢 *Broadcast Message*\n\n{message}",
                parse_mode='Markdown'
            )
            sent += 1
        except Exception:
            failed += 1
    
    await update.message.reply_text(
        f"Broadcast completed!\n"
        f"✅ Sent: {sent}\n"
        f"❌ Failed: {failed}"
    )
    context.user_data['awaiting_broadcast'] = False

async def manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, account_type, credits, ban_until FROM users LIMIT 10")
    users = cursor.fetchall()
    close_db(conn)
    
    users_text = "👥 *User Management*\n\n"
    for user in users:
        banned = "🚫 Banned" if user[4] and user[4] > datetime.now() else "✅ Active"
        users_text += (
            f"ID: `{user[0]}`\n"
            f"Username: @{user[1]}\n"
            f"Type: {user[2]}\n"
            f"Credits: {user[3]}\n"
            f"Status: {banned}\n\n"
        )
    
    keyboard = [
        [
            InlineKeyboardButton("Ban User", callback_data='ban_user'),
            InlineKeyboardButton("Adjust Credits", callback_data='adjust_credits')
        ],
        [InlineKeyboardButton("« Back", callback_data='owner_panel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(users_text, reply_markup=reply_markup, parse_mode='Markdown')

async def manage_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT key_id, credits, is_redeemed, redeemed_by, redeemed_at 
        FROM user_keys 
        ORDER BY redeemed_at DESC 
        LIMIT 10
    """)
    keys = cursor.fetchall()
    close_db(conn)
    
    keys_text = "🔑 *Key Management*\n\n"
    for key in keys:
        status = "Used" if key[2] else "Available"
        redeemed_info = f"by {key[3]} at {key[4]}" if key[2] else "N/A"
        keys_text += (
            f"Key: `{key[0]}`\n"
            f"Credits: {key[1]}\n"
            f"Status: {status}\n"
            f"Redeemed: {redeemed_info}\n\n"
        )
    
    keyboard = [
        [InlineKeyboardButton("Generate New Key", callback_data='generate_key')],
        [InlineKeyboardButton("Revoke Key", callback_data='revoke_key')],
        [InlineKeyboardButton("« Back", callback_data='owner_panel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(keys_text, reply_markup=reply_markup, parse_mode='Markdown')
   
# Bin Lookup
async def bin_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bin_numbers = [bin.strip() for bin in update.message.text.strip().split(',')]
    result_text = ""
    
    try:
        for bin_number in bin_numbers:
            response = requests.get(f"https://bins.antipublic.cc/bins/{bin_number}")
            if response.status_code == 200:
                bin_info = response.json()
                result_text += (
                    f"🔹 BIN: `{bin_number}`\n"
                    f"💳 Brand: {bin_info.get('brand', 'Unknown')}\n"
                    f"🌎 Country: {bin_info.get('country', 'Unknown')}\n"
                    f"💱 Currency: {bin_info.get('currency', 'Unknown')}\n"
                    f"🏦 Bank: {bin_info.get('bank', 'Unknown')}\n"
                    f"📈 Level: {bin_info.get('level', 'Unknown')}\n"
                    f"🏷️ Type: {bin_info.get('type', 'Unknown')}\n\n"
                )
            else:
                result_text += f"BIN: {bin_number} - Not Found\n\n"
    except Exception as e:
        result_text += f"Error looking up BIN: {str(e)}\n\n"
    
    await update.message.reply_text(result_text, parse_mode='Markdown')
    context.user_data['awaiting_bin_input'] = False
    await send_main_menu(update, context)

# Anti-Public API and related functions
async def process_anti_public(update: Update, context: ContextTypes.DEFAULT_TYPE, card_numbers):
    try:
        response = requests.post(
            "https://api.antipublic.cc/cards", 
            json=card_numbers,
            headers={'Content-Type': 'application/json'}
        ).json()
        
        if all(key in response for key in ['public', 'private', 'private_percentage']):
            result_text = (
                f"Public CCs: {response['public']}\n"
                f"Private CCs: {response['private']}\n"
                f"{response['private_percentage']}% Private"
            )
        else:
            result_text = "Unexpected response format from Anti-Public API."
        
        await update.message.reply_text(result_text)
        
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")
    
    await send_main_menu(update, context)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    document = update.message.document
    if context.user_data.get('awaiting_proxies'):
        if document.mime_type == 'text/plain' or document.file_name.endswith('.txt'):
            file = await document.get_file()
            file_content = await file.download_as_bytearray()
            proxies_text = file_content.decode('utf-8')
            proxies = proxies_text.splitlines()
            context.user_data['proxies'] = [proxy.strip() for proxy in proxies if proxy.strip()]
            await update.message.reply_text(f"✅ Proxies saved: {len(context.user_data['proxies'])} proxies added.")
            context.user_data['awaiting_proxies'] = False
            await send_main_menu(update, context)
        else:
            await update.message.reply_text("Please upload a valid .txt file containing proxies.")
    elif context.user_data.get('awaiting_anti_public_file'):
        if document.mime_type == 'text/plain' or document.file_name.endswith('.txt'):
            file = await document.get_file()
            file_content = await file.download_as_bytearray()
            cards_text = file_content.decode('utf-8')
            card_numbers = cards_text.splitlines()
            await process_anti_public(update, context, card_numbers)
            context.user_data['awaiting_anti_public_file'] = False
        else:
            await update.message.reply_text("Please upload a valid .txt file containing card numbers.")
    else:
        await update.message.reply_text("I wasn't expecting a document. Please choose an option from the keyboard.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    user_id = update.effective_user.id

    if not is_user_registered(user_id):
        await update.message.reply_text("Please register first using /reg command.")
        return

    if context.user_data.get('awaiting_username'):
        target_user = text
        target_user_clean = target_user.lstrip('@').lower()
        blacklist = ['gdbs2']
        if target_user_clean in (user.lower() for user in blacklist):
            await update.message.reply_text("❌ You can't report that username! That username is either the owner of the bot or blacklisted.")
        else:
            await save_username(user_id, target_user_clean)
            await update.message.reply_text(f"✅ Username saved: @{target_user_clean}")
        context.user_data['awaiting_username'] = False
        await send_main_menu(update, context)
    elif context.user_data.get('awaiting_proxies'):
        proxies = text.splitlines()
        context.user_data['proxies'] = [proxy.strip() for proxy in proxies if proxy.strip()]
        await update.message.reply_text(f"✅ Proxies saved: {len(context.user_data['proxies'])} proxies added.")
        context.user_data['awaiting_proxies'] = False
        await send_main_menu(update, context)
    elif context.user_data.get('awaiting_bin_input'):
        await bin_lookup(update, context)
    elif context.user_data.get('awaiting_broadcast') and str(user_id) == OWNER_ID:
        await handle_broadcast_message(update, context)
    else:
        await update.message.reply_text("Please choose an option from the keyboard.")

# Username functions
async def save_username(user_id, username):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET saved_username = %s WHERE user_id = %s", (username, user_id))
    conn.commit()
    close_db(conn)

async def get_saved_username(user_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT saved_username FROM users WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()
    close_db(conn)
    return result[0] if result else None

def blur_email(email):
    try:
        local_part, domain = email.split('@')
        if len(local_part) <= 2:
            blurred_local = local_part[0] + '*' * (len(local_part) - 1)
        else:
            blurred_local = local_part[:2] + '***' + local_part[-1]
        return f"{blurred_local}@{domain}"
    except ValueError:
        return "Invalid email format"

async def handle_command_suggestions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    commands = [
        ("report", "Send a report"),
        ("reg", "Register to use the bot"),
        ("redeem", "Redeem a key"),
        ("help", "Show available commands"),
        ("user_info", "View your user information")
    ]
    
    if str(user_id) == OWNER_ID:
        owner_commands = [
            ("keygen", "Generate keys"),
            ("broadcast", "Send message to all users"),
            ("stats", "View bot statistics"),
            ("ban", "Ban a user"),
            ("unban", "Unban a user"),
            ("addcredits", "Add credits to a user"),
            ("removecredits", "Remove credits from a user")
        ]
        commands.extend(owner_commands)
    
    command_text = "Available commands:\n" + "\n".join([f"/{cmd} - {desc}" for cmd, desc in commands])
    await update.message.reply_text(command_text)

# Help command providing a list of available commands
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "/start - Start the bot\n"
        "/reg - Register as a new user\n"
        "/redeem <key> - Redeem a key to get credits\n"
        "/user_info - Get your user information\n"
    )
    if str(update.effective_user.id) == OWNER_ID:
        help_text += "/keygen <amount> - Generate a key with specified credits\n"
    await update.message.reply_text(help_text)

# Main function
def main():
    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reg", register_user))
    application.add_handler(CommandHandler("keygen", generate_key))
    application.add_handler(CommandHandler("redeem", redeem_key))
    application.add_handler(CommandHandler("user_info", user_info))
    application.add_handler(CommandHandler("help", help_command))
    
    # Message Handlers
    application.add_handler(MessageHandler(filters.Regex("^/"), handle_command_suggestions))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_buttons))
    application.add_handler(MessageHandler(filters.Document.FileExtension("txt"), handle_document))
    
    # Callback Query Handler
    application.add_handler(CallbackQueryHandler(button_callback))

    # Start the bot
    application.run_polling()
    print("Bot is running... Press Ctrl+C to stop.")

# Help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    help_text = (
        "Available commands:\n\n"
        "/start - Start the bot\n"
        "/reg - Register as a new user\n"
        "/redeem <key> - Redeem a key to get credits\n"
        "/user_info - Get your user information\n"
    )
    if str(user_id) == OWNER_ID:
        help_text += (
            "\nOwner Commands:\n"
            "/keygen <amount> - Generate a key with specified credits\n"
            "/broadcast - Send message to all users\n"
            "/stats - View bot statistics\n"
            "/ban <user_id> <duration> - Ban a user\n"
            "/unban <user_id> - Unban a user\n"
        )
    await update.message.reply_text(help_text)

if __name__ == '__main__':
    main()
