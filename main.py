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
from keep_alive import keep_alive

keep_alive()

# Initialize the bot application
TOKEN = os.environ.get('TOKEN')  # Ensure to set your TOKEN in the environment variables
OWNER_ID = os.environ.get('OWNER_ID')  # Set OWNER_ID in environment variables
application = Application.builder().token(TOKEN).build()

# Set up logging for debugging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Faker for generating fake user data
fake = Faker()

# Banner for console output
banner = "Ohayo"

print("\033[31m", banner, "\033[0m")

# Database connection functions
def connect_db():
    """Connect to the MySQL database"""
    return mysql.connector.connect(
        host=os.environ['DB_HOST'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        database=os.environ['DB_NAME']
    )

def close_db(connection):
    """Close the MySQL database connection"""
    connection.close()

# Function to send a report request
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

    # Define cookies and headers
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
        if proxy:
            proxy_dict = {
                'http': proxy,
                'https': proxy,
            }
        else:
            proxy_dict = None

        response = requests.post('https://telegram.org/support', cookies=cookies,
                                 headers=headers, data=data, proxies=proxy_dict)
        response.raise_for_status()

        if "We will try to reply as soon as possible." in response.text:
            return f"{email} : Report done for {target_user}!"
        else:
            return "Report Failed."
    except requests.exceptions.RequestException as e:
        return "Error: " + str(e)

# Start command with custom keyboard
def get_main_menu_keyboard():
    keyboard = [
        [KeyboardButton("Report"), KeyboardButton("Save Username"), KeyboardButton("Proxies")],
        [KeyboardButton("Tools"), KeyboardButton("User Info"), KeyboardButton("Redeem Key")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_markup = get_main_menu_keyboard()
    await update.message.reply_text(
        "👋 Welcome to *Ohayo Auto Report Bot*! Choose an option:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Handle button presses
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    if text == "Report":
        # Show "Choose an action." with buttons "Single Report", "Mass Report"
        keyboard = [
            [
                InlineKeyboardButton("Single Report", callback_data='single_report'),
                InlineKeyboardButton("Mass Report", callback_data='mass_report')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Choose an action:",
            reply_markup=reply_markup
        )
    elif text == "Tools":
        # Show "Choose a tool." with buttons "Bin Lookup", "Anti-Public"
        keyboard = [
            [
                InlineKeyboardButton("Bin Lookup", callback_data='bin_lookup'),
                InlineKeyboardButton("Anti-Public", callback_data='anti_public')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Choose a tool:",
            reply_markup=reply_markup
        )
    elif text == "Save Username":
        context.user_data['awaiting_username'] = True
        await update.message.reply_text(
            "Please enter the username to save:"
        )
    elif text == "Proxies":
        context.user_data['awaiting_proxies'] = True
        await update.message.reply_text(
            "Send your proxies in any format in one message or a file (.txt)."
        )
    elif text == "User Info":
        await user_info(update, context)
    elif text == "Redeem Key":
        await update.message.reply_text("Please enter your key using the command /redeem <key>")
    else:
        await handle_text(update, context)

# Handle inline button callbacks
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'single_report':
        target_user = context.user_data.get('saved_username')
        if target_user:
            response_message = send_report(target_user)
            await query.edit_message_text(f"✅ {response_message}")
            await send_main_menu(update, context)
        else:
            await query.edit_message_text("No username saved. Please use 'Save Username' to set a username first.")
            await send_main_menu(update, context)
    elif data == 'mass_report':
        target_user = context.user_data.get('saved_username')
        if target_user:
            keyboard = [
                [
                    InlineKeyboardButton("10", callback_data='mass_10'),
                    InlineKeyboardButton("20", callback_data='mass_20'),
                    InlineKeyboardButton("50", callback_data='mass_50'),
                    InlineKeyboardButton("100", callback_data='mass_100')
                ],
                [InlineKeyboardButton("Custom", callback_data='mass_custom')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Choose the number of reports:",
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text("No username saved. Please use 'Save Username' to set a username first.")
            await send_main_menu(update, context)
    elif data.startswith('mass_'):
        if data == 'mass_custom':
            context.user_data['awaiting_custom_count'] = True
            await query.edit_message_text("Enter the number of reports:")
        else:
            count = int(data.split('_')[1])
            await start_mass_report(update, context, count)
            await send_main_menu(update, context)
    elif data == 'bin_lookup':
        context.user_data['awaiting_bin_input'] = True
        await query.edit_message_text("Please enter the BIN number(s), separated by commas:")
    elif data == 'anti_public':
        context.user_data['awaiting_anti_public_input'] = True
        await query.edit_message_text("Please enter the card number(s), separated by commas:")
    else:
        await query.edit_message_text("Unknown action.")
# Bin Lookup API call
async def bin_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_bin_input'):
        bin_numbers = update.message.text.strip().split(',')
        try:
            response = requests.post(
                "https://bins.antipublic.cc/bins",
                json=bin_numbers
            ).json()
            result_text = ""
            for bin_info in response:
                for key, value in bin_info.items():
                    result_text += f"{key}: {value}\n"
                result_text += "\n"
            await update.message.reply_text(result_text)
        except Exception as e:
            await update.message.reply_text(f"An error occurred: {e}")
        context.user_data['awaiting_bin_input'] = False
        await send_main_menu(update, context)

# Anti-Public API call
async def anti_public_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_anti_public_input'):
        card_numbers = update.message.text.strip().split(',')
        try:
            response = requests.post(
                "https://api.antipublic.cc/cards",
                json=card_numbers
            ).json()
            result_text = (
                f"Public CCs: {response['public']}\n"
                f"Private CCs: {response['private']}\n"
                f"{response['private_percentage']}% private"
            )
            await update.message.reply_text(result_text)
        except Exception as e:
            await update.message.reply_text(f"An error occurred: {e}")
        context.user_data['awaiting_anti_public_input'] = False
        await send_main_menu(update, context)

# Generate Key (restricted to OWNER_ID)
async def generate_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if str(user_id) != OWNER_ID:
        await update.message.reply_text("Unauthorized access.")
        return

    credits = 100  # Example credit amount
    key_id = 'MRB-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO user_keys (key_id, credits) VALUES (%s, %s)", (key_id, credits))
    conn.commit()
    close_db(conn)
    await update.message.reply_text(f"Generated key: {key_id} with {credits} credits")

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
        cursor.execute("UPDATE users SET credits = credits + %s WHERE user_id = %s", (credits, update.effective_user.id))
        conn.commit()
        response = f"Key redeemed successfully! {credits} credits added."
    else:
        response = "Invalid or already redeemed key."
    close_db(conn)
    await update.message.reply_text(response)

# Display User Info
async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name, username, account_type, credits FROM users WHERE user_id = %s", (update.effective_user.id,))
    user_data = cursor.fetchone()
    close_db(conn)
    if user_data:
        name, username, account_type, credits = user_data
        await update.message.reply_text(
            f"ℹ️ *User Info*\n\n"
            f"ID: {update.effective_user.id}\n"
            f"Name: {name}\n"
            f"Username: @{username}\n"
            f"Type: {account_type}\n"
            f"Credits: {credits}",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("User not registered.")

# Handle text messages based on context
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    if context.user_data.get('awaiting_username'):
        # Save the username
        target_user = text
        # Remove '@' prefix if present
        target_user_clean = target_user.lstrip('@').lower()
        # Define the blacklist
        blacklist = ['gdbs2']
        if target_user_clean in (user.lower() for user in blacklist):
            await update.message.reply_text(
                "❌ You can't report that username! That username is either the owner of the bot or blacklisted."
            )
        else:
            context.user_data['saved_username'] = target_user
            await update.message.reply_text(f"✅ Username saved: {target_user}")
        context.user_data['awaiting_username'] = False
        await send_main_menu(update, context)
    elif context.user_data.get('awaiting_proxies'):
        # Save the proxies
        proxies = text.splitlines()
        context.user_data['proxies'] = [proxy.strip()
                                        for proxy in proxies if proxy.strip()]
        await update.message.reply_text(f"✅ Proxies saved: {len(context.user_data['proxies'])} proxies added.")
        context.user_data['awaiting_proxies'] = False
        await send_main_menu(update, context)
    elif context.user_data.get('awaiting_custom_count'):
        try:
            count = int(text)
            await start_mass_report(update, context, count)
            await send_main_menu(update, context)
        except ValueError:
            await update.message.reply_text("Please provide a valid number or type /start to go back.")
    elif context.user_data.get('awaiting_bin_input'):
        await bin_lookup(update, context)
    elif context.user_data.get('awaiting_anti_public_input'):
        await anti_public_check(update, context)
    else:
        await update.message.reply_text("Sorry, I didn't understand that. Please choose an option from the keyboard.")

# Handle document uploads (proxies)
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('awaiting_proxies'):
        document = update.message.document
        if document.mime_type == 'text/plain' or document.file_name.endswith('.txt'):
            file = await document.get_file()
            file_content = await file.download_as_bytearray()
            proxies_text = file_content.decode('utf-8')
            proxies = proxies_text.splitlines()
            context.user_data['proxies'] = [proxy.strip()
                                            for proxy in proxies if proxy.strip()]
            await update.message.reply_text(f"✅ Proxies saved: {len(context.user_data['proxies'])} proxies added.")
            context.user_data['awaiting_proxies'] = False
            await send_main_menu(update, context)
        else:
            await update.message.reply_text("Please upload a valid .txt file containing proxies.")
    else:
        await update.message.reply_text("I wasn't expecting a document. Please choose an option from the keyboard.")

# Handle single report using saved username
async def single_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target_user = context.user_data.get('saved_username')
    if target_user:
        response_message = send_report(target_user)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ {response_message}")
        await send_main_menu(update, context)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="No username saved. Please use 'Save Username' to set a username first.")

# Start mass report with specified count
async def start_mass_report(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int) -> None:
    target_user = context.user_data.get('saved_username')
    if not target_user:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="No username saved. Please use 'Save Username' to set a username first.")
        return

    # Send an initial message to be updated with progress
    progress_message = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🚀 Starting mass report for {target_user}...")

    # Loop through the specified number of reports
    for i in range(count):
        # Determine proxy to use
        if 'proxies' in context.user_data and context.user_data['proxies']:
            proxies = context.user_data['proxies']
            proxy = proxies[i % len(proxies)]  # Rotate proxies
        else:
            proxy = None

        response_message = send_report(target_user, proxy=proxy)

        # Update the progress in the same message bubble
        progress_bar = '█' * ((i+1)*10//count) + \
            '░' * (10 - ((i+1)*10//count))
        await progress_message.edit_text(f"Report {i+1}/{count}: {response_message}\nProgress: [{progress_bar}]")
        await asyncio.sleep(0.2)  # Add delay to avoid rate limiting

    # Finalize the message once all reports are completed
    await progress_message.edit_text("✅ All reports were done successfully! Thank you for using Ohayo Auto Report Bot! 🧑‍💻")
    await send_main_menu(update, context)

# Command handlers
def main():
    # Initialize Application
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("generate_key", generate_key))
    application.add_handler(CommandHandler("redeem", redeem_key))
    application.add_handler(CommandHandler("user_info", user_info))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_buttons))
    application.add_handler(MessageHandler(filters.Document.FileExtension("txt"), handle_document))
    application.add_handler(CallbackQueryHandler(button_callback))

    # Start the bot
    application.run_polling()
    print("Bot is running... Press Ctrl+C to stop.")

if __name__ == '__main__':
    main()
