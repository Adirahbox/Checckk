import os
import random
import string
import time
import datetime
import requests
import re
import base64
import asyncio
import sqlite3
import shutil
from concurrent.futures import ThreadPoolExecutor
from telethon import TelegramClient, events, Button
from flask import Flask
import threading
from shared import (
    PLANS, get_user_plan, is_user_banned, upgrade_user,
    PLAN_FILES, GC_FILE, BANBIN_FILE, BANNEDU_FILE,
    is_group_authorized, authorize_group, deauthorize_group,
    get_personal_usage_count, increment_personal_usage,
    is_user_in_cooldown, update_user_cooldown,
    is_user_registered, register_user, can_user_use_command,
    increment_gate_usage, get_gate_usage_count, get_user_session
)
from tools.tooling import (
    status_command, redeem_command, sk_command,
    bin_command, gen_command, fake_command,
    gate_command, gauth_command
)
from gates.auth.stauth import StripeAuthChecker, handle_stripe_auth, handle_mass_stripe_auth
from gates.charge.scharge import handle_stripe_charge
from gates.mass.masscharge import handle_mass_stripe_charge
from gates.charge.scharge5 import handle_sp_charge, sp_help
from addups.restrictt import is_user_restricted, restrict_user_command, unrestrict_user_command
from addups.notwork import is_command_disabled, disable_command, enable_command, disable_command_handler, enable_command_handler, get_command_offline_message  # ✅ ADDED IMPORT

# Telegram API credentials
api_id = os.getenv('TELEGRAM_API_ID', '12313459')
api_hash = os.getenv('TELEGRAM_API_HASH', 'd2f81736492abbfcc50e1fdceffdab96')
bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '7517892696:AAFMwc4QSGEHzS4IlQvg1yeQJtU6dkRORHM')

# Session management
SESSIONS_FOLDER = "sessions"
os.makedirs(SESSIONS_FOLDER, exist_ok=True)

# Thread pool for concurrent requests
thread_pool = ThreadPoolExecutor(max_workers=50)

def generate_session_name():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

def init_client():
    # Clean up old session files
    for filename in os.listdir(SESSIONS_FOLDER):
        file_path = os.path.join(SESSIONS_FOLDER, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

    # Create a consistent session name
    session_name = os.path.join(SESSIONS_FOLDER, 'bot_session')

    # Configure client with connection retries
    client = TelegramClient(
        session_name,
        api_id,
        api_hash,
        connection_retries=5,
        retry_delay=2,
        auto_reconnect=True
    )

    # Set up database connection with timeout
    try:
        conn = sqlite3.connect(f'{session_name}.session', timeout=10)
        conn.close()
    except sqlite3.Error as e:
        print(f"Database connection error: {e}")
        if os.path.exists(f'{session_name}.session'):
            try:
                os.remove(f'{session_name}.session')
            except Exception as e:
                print(f"Failed to remove session file: {e}")

    return client

# Initialize client with error handling
try:
    client = init_client()
    client.start(bot_token=bot_token)
except Exception as e:
    print(f"Failed to initialize client: {e}")
    for file in os.listdir(SESSIONS_FOLDER):
        if file.startswith('bot_') and file.endswith('.session'):
            try:
                os.remove(os.path.join(SESSIONS_FOLDER, file))
            except:
                pass
    print("Restarting bot...")
    client = init_client()
    client.start(bot_token=bot_token)

# User sessions and plans
user_sessions = {}
user_stop_signals = {}
user_results = {}

# Proxy list (replace with your own proxy list or API endpoint)
PROXY_LIST = [
    "http://user:pass@ip1:port",
    "http://user:pass@ip2:port",
    "http://user:pass@ip3:port",
]

def get_new_proxy():
    return random.choice(PROXY_LIST)

def random_alphanumeric(length=4):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def random_emoji():
    emojis = ["😎", "🤖", "🃏", "⚡", "🌀", "🎰", "🎯", "💎", "🔥", "🌟", "🪙", "💳", "💸", "🧿", "📊"]
    return random.choice(emojis)

async def bin_lookup(bin):
    try:
        response = await asyncio.to_thread(requests.get, f"https://bins.antipublic.cc/bins/{bin}")
        return response.json()
    except Exception as e:
        return None

def is_user_in_any_plan(user_id):
    for plan, file_name in PLAN_FILES.items():
        if os.path.exists(file_name):
            with open(file_name, 'r') as f:
                if str(user_id) in f.read().splitlines():
                    return True
    return False

def downgrade_user(user_id):
    # Remove user from all plan files except FREE
    for plan, file_name in PLAN_FILES.items():
        if plan != "FREE" and os.path.exists(file_name):
            with open(file_name, 'r') as f:
                lines = f.readlines()
            with open(file_name, 'w') as f:
                for line in lines:
                    if line.strip() != str(user_id):
                        f.write(line)

    # Add user to FREE.txt
    if not os.path.exists(PLAN_FILES["FREE"]):
        with open(PLAN_FILES["FREE"], 'w') as f:
            f.write(f"{user_id}\n")
    else:
        with open(PLAN_FILES["FREE"], 'a') as f:
            f.write(f"{user_id}\n")
    return True

def is_bin_banned(bin):
    if not os.path.exists(BANBIN_FILE):
        return False
    with open(BANBIN_FILE, 'r') as f:
        banned_bins = f.read().splitlines()
    return str(bin) in banned_bins

def ban_bin(bin):
    with open(BANBIN_FILE, 'a') as f:
        f.write(f"{bin}\n")

def unban_bin(bin):
    if not os.path.exists(BANBIN_FILE):
        return False

    with open(BANBIN_FILE, 'r') as f:
        banned_bins = f.read().splitlines()

    if str(bin) not in banned_bins:
        return False

    with open(BANBIN_FILE, 'w') as f:
        for banned_bin in banned_bins:
            if banned_bin.strip() != str(bin):
                f.write(f"{banned_bin}\n")

    return True

def ban_user(user_id):
    with open(BANNEDU_FILE, 'a') as f:
        f.write(f"{user_id}\n")

def unban_user(user_id):
    if not os.path.exists(BANNEDU_FILE):
        return False

    with open(BANNEDU_FILE, 'r') as f:
        banned_users = f.read().splitlines()

    if str(user_id) not in banned_users:
        return False

    with open(BANNEDU_FILE, 'w') as f:
        for banned_user in banned_users:
            if banned_user.strip() != str(user_id):
                f.write(f"{banned_user}\n")

    return True

def generate_redeem_code(days, num_codes=1):
    codes = []
    for _ in range(num_codes):
        part1 = random_alphanumeric(4)
        part2 = random_alphanumeric(4)
        code = f"WAYNE-DAD-{part1}-{part2}"

        expiration_date = datetime.datetime.now() + datetime.timedelta(days=days)
        expiration_date_str = expiration_date.strftime("%Y-%m-%d")

        with open(GC_FILE, 'a') as f:
            f.write(f"{code}|{expiration_date_str}\n")

        codes.append((code, expiration_date_str))
    return codes

async def check_group_auth(event):
    if event.is_private:
        return True

    chat = await event.get_chat()
    if not is_group_authorized(chat.id):
        await event.respond("⛔ This group is not authorized to use the bot.")
        return False
    return True

# Decorator to check registration status
def registered_required(func):
    async def wrapper(event):
        user_id = event.sender_id
        if not is_user_registered(user_id):
            await event.respond(
                "🔐 You need to register first!\n"
                "Use /register command to get started.",
                buttons=[Button.inline("📝 Register Now", b"register_user")]
            )
            return
        return await func(event)
    return wrapper

# Command to generate redeem codes
@client.on(events.NewMessage(pattern=r'^/gc\s|^\.gc\s'))
@registered_required
async def generate_code(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan != "GOD":
        await event.respond("🚫 You do not have permission to generate redeem codes.")
        return

    args = event.message.text.split()
    if len(args) < 3:
        await event.respond(
            "🎁 **How to use /gc**\n\n"
            "Generate gift codes for PLUS plan:\n\n"
            "`/gc <days> <num_codes>`\n\n"
            "📋 **Examples:**\n"
            "`/gc 30 5` - Generate 5 codes valid for 30 days\n"
            "`/gc 90 1` - Generate 1 code valid for 90 days\n\n"
            "📦 Maximum 10 codes at once\n"
            "🎰 Codes can be redeemed with /redeem command"
        )
        return

    try:
        days = int(args[1])
        num_codes = int(args[2])
        if days < 1 or days > 365:
            await event.respond("❌ Invalid number of days. Please provide a value between 1 and 365")
            return
        if num_codes < 1 or num_codes > 10:
            await event.respond("❌ Invalid number of codes. Please provide a value between 1 and 10.")
            return
    except ValueError:
        await event.respond("❌ Invalid input. Please provide valid integers for days and number of codes.")
        return

    codes = generate_redeem_code(days, num_codes)
    response = "🎉 Redeem codes generated successfully!\n\n"
    for code, expiration_date in codes:
        response += f"🎁 **Code:** `{code}`\n📅 Expiration Date: `{expiration_date}`\n\n"

    response += (
        "📝 **How to Redeem Your Code:**\n"
        "1️⃣ Use the command `/redeem <your_code>` to redeem your gift code.\n"
        f"2️⃣ Each code is valid for **{days} days**.\n"
        "3️⃣ Enjoy your upgraded plan!\n"
        "4️⃣ Redeem at @WayneCHK_bot"
    )
    await event.respond(response)

# Help command for /gc
@client.on(events.NewMessage(pattern=r'^/gc$|^\.gc$'))
@registered_required
async def gc_help(event):
    if not await check_group_auth(event):
        return

    await event.respond(
        "🎁 **How to use /gc**\n\n"
        "Generate gift codes for PLUS plan:\n\n"
        "`/gc <days> <num_codes>`\n\n"
        "📋 **Examples:**\n"
        "`/gc 30 5` - Generate 5 codes valid for 30 days\n"
        "`/gc 90 1` - Generate 1 code valid for 90 days\n\n"
        "📦 Maximum 10 codes at once\n"
        "🎰 Codes can be redeemed with /redeem command"
    )

# Callback handler for the "Generate Code" button
@client.on(events.CallbackQuery(data=b"generate_code_command"))
@registered_required
async def generate_code_command_callback(event):
    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan != "GOD":
        await event.respond("🚫 You do not have permission to generate redeem codes.")
        return

    await event.respond(
        "🎁 **How to use /gc**\n\n"
        "Generate gift codes for PLUS plan:\n\n"
        "`/gc <days> <num_codes>`\n\n"
        "📋 **Examples:**\n"
        "`/gc 30 5` - Generate 5 codes valid for 30 days\n"
        "`/gc 90 1` - Generate 1 code valid for 90 days\n\n"
        "📦 Maximum 10 codes at once\n"
        "🎰 Codes can be redeemed with /redeem command",
        buttons=[Button.inline("🔙 Back to Admin", b"admin_commands")]
    )

# Callback handler for exit command
@client.on(events.CallbackQuery(data=b"exit_command"))
async def exit_command(event):
    await event.delete()
    await event.respond("❌ Command exited!")

# Command to redeem a gift code
@client.on(events.NewMessage(pattern=r'^/redeem\s|^\.redeem\s'))
@registered_required
async def redeem(event):
    if is_command_disabled('/redeem'):
        offline_message = get_command_offline_message('/redeem')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return
    asyncio.create_task(redeem_command(event))

# Help command for /redeem
@client.on(events.NewMessage(pattern=r'^/redeem$|^\.redeem$'))
@registered_required
async def redeem_help(event):
    if is_command_disabled('/redeem'):
        offline_message = get_command_offline_message('/redeem')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return
    await event.respond(
        "🎁 **How to Redeem a Gift Code**\n\n"
        "Use the following format:\n\n"
        "`/redeem <code>`\n\n"
        "📋 **Example:**\n"
        "`/redeem WAYNE-DAD-ABCD-1234`\n\n"
        "✅ Enjoy your upgraded plan!"
    )

# Callback handler for the "Redeem" button in Tools menu
@client.on(events.CallbackQuery(data=b"redeem_command"))
@registered_required
async def redeem_command_callback(event):
    if not await check_group_auth(event):
        return
    asyncio.create_task(redeem_command(event))

# Command to scan website payment gateways
@client.on(events.NewMessage(pattern=r'^/gate\s|^\.gate\s'))
@registered_required
async def gate(event):
    if is_command_disabled('/gate'):
        offline_message = get_command_offline_message('/gate')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return
    asyncio.create_task(gate_command(event))

# Help command for /gate
@client.on(events.NewMessage(pattern=r'^/gate$|^\.gate$'))
@registered_required
async def gate_help(event):
    if is_command_disabled('/gate'):
        offline_message = get_command_offline_message('/gate')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return
    await event.respond(
        "🔍 **How to Scan Website Payment Gateways**\n\n"
        "Use the following format:\n\n"
        "`/gate <website_url>`\n\n"
        "📋 **Example:**\n"
        "`/gate https://example.com`\n\n"
        "✅ The bot will analyze the payment gateways used on the website."
    )

# Callback handler for the "Gate" button in Tools menu
@client.on(events.CallbackQuery(data=b"gate_command"))
@registered_required
async def gate_command_callback(event):
    if not await check_group_auth(event):
        return
    asyncio.create_task(gate_command(event))

# Update the Tools menu to include the /gate option
@client.on(events.CallbackQuery(data=b"tools_commands"))
@registered_required
async def tools_commands(event):
    if not await check_group_auth(event):
        return

    if is_user_banned(event.sender_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    await event.edit(
        "🧰 **Tools Commands**\n"
        "Here are the tools commands:",
        buttons=[
            [Button.inline("📊 /status", b"status_command"), Button.inline("🎁 /redeem", b"redeem_command")],
            [Button.inline("🎰 /bin", b"bin_command"), Button.inline("🏠 /fake", b"fake_command")],
            [Button.inline("📦 /gen", b"gen_command"), Button.inline("🔍 /gate", b"gate_command")],
            [Button.inline("🔙 Back to 𝑴𝒂𝒊𝒏 𝑴𝒆𝒏𝒖 ", b"enter_world")]
        ]
    )

# Group Authorization Command
@client.on(events.NewMessage(pattern=r'^/gauth\s|^\.gauth\s'))
@registered_required
async def gauth(event):
    asyncio.create_task(gauth_command(event))

# Help command for /gauth
@client.on(events.NewMessage(pattern=r'^/gauth$|^\.gauth$'))
@registered_required
async def gauth_help(event):
    await event.respond(
        "🔐 **How to Authorize a Group**\n\n"
        "Use this command in the group you want to authorize:\n\n"
        "`/gauth` - Adds the group to authorized list\n\n"
        "🔒 Only GOD/ADMIN plan users can use this command."
    )

# Callback handler for the "Gauth" button in Tools menu
@client.on(events.CallbackQuery(data=b"gauth_command"))
@registered_required
async def gauth_command_callback(event):
    if not await check_group_auth(event):
        return
    asyncio.create_task(gauth_command(event))

# Group Deauthorization Command
@client.on(events.NewMessage(pattern=r'^/dauth\s|^\.dauth\s'))
@registered_required
async def dauth(event):
    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to deauthorize groups.")
        return

    if not event.is_group and not event.is_channel:
        await event.respond("❌ This command can only be used in groups/channels.")
        return

    chat = await event.get_chat()
    if deauthorize_group(chat.id):
        await event.respond(f"✅ Group {chat.title} (ID: {chat.id}) has been deauthorized!")
    else:
        await event.respond(f"ℹ️ Group {chat.title} (ID: {chat.id}) was not authorized.")

# Help command for /dauth
@client.on(events.NewMessage(pattern=r'^/dauth$|^\.dauth$'))
@registered_required
async def dauth_help(event):
    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to deauthorize groups.")
        return

    await event.respond(
        "❌ **How to Deauthorize a Group**\n\n"
        "Use this command in the group you want to deauthorize:\n\n"
        "`/dauth` - Removes the group from authorized list\n\n"
        "🔒 Only GOD/ADMIN plan users can use this command."
    )

# Callback handler for the "Dauth" button in Tools menu
@client.on(events.CallbackQuery(data=b"dauth_command"))
@registered_required
async def dauth_command_callback(event):
    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to deauthorize groups.")
        return

    await event.respond(
        "❌ **How to Deauthorize a Group**\n\n"
        "Use this command in the group you want to deauthorize:\n\n"
        "`/dauth` - Removes the group from authorized list\n\n"
        "🔒 Only GOD/ADMIN plan users can use this command."
    )

# Callback handler for the "Status" button in Tools menu - FIXED
@client.on(events.CallbackQuery(data=b"status_command"))
@registered_required
async def status_command_callback(event):
    if not await check_group_auth(event):
        return
    # Directly call status_command instead of just showing help
    await status_command(event)

# Command to check user plan status - FIXED to show actual status
@client.on(events.NewMessage(pattern=r'^/status\s|^\.status\s'))
@registered_required
async def status(event):
    if is_command_disabled('/status'):
        offline_message = get_command_offline_message('/status')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return
    # Show actual status, not help
    await status_command(event)

# Help command for /status - Only show help when command is used without parameters
@client.on(events.NewMessage(pattern=r'^/status$|^\.status$'))
@registered_required
async def status_help(event):
    if is_command_disabled('/status'):
        offline_message = get_command_offline_message('/status')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return
    # Show actual status instead of help message
    await status_command(event)

# Command to check Stripe secret key
@client.on(events.NewMessage(pattern=r'^/sk\s|^\.sk\s'))
@registered_required
async def sk(event):
    if is_command_disabled('/sk'):
        offline_message = get_command_offline_message('/sk')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return
    asyncio.create_task(sk_command(event))

# Help command for /sk
@client.on(events.NewMessage(pattern=r'^/sk$|^\.sk$'))
@registered_required
async def sk_help(event):
    if is_command_disabled('/sk'):
        offline_message = get_command_offline_message('/sk')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return
    await event.respond(
        "🔑 **How to Check Stripe Secret Key**\n\n"
        "Use the following format:\n\n"
        "`/sk <stripe_secret_key>`\n\n"
        "📋 **Example:**\n"
        "`/sk sk_live_xxxxxxxxxxxxxxxxxxxxxxxx`\n\n"
        "✅ The bot will validate the Stripe secret key and show account information."
    )

# Callback handler for the "SK" button in Tools menu
@client.on(events.CallbackQuery(data=b"sk_command"))
@registered_required
async def sk_command_callback(event):
    if not await check_group_auth(event):
        return
    asyncio.create_task(sk_command(event))

# Callback handler for the "BIN" button in Tools menu
@client.on(events.CallbackQuery(data=b"bin_command"))
@registered_required
async def bin_command_callback(event):
    if not await check_group_auth(event):
        return
    asyncio.create_task(bin_command(event))

# Command to check BIN
@client.on(events.NewMessage(pattern=r'^/bin\s|^\.bin\s'))
@registered_required
async def bin(event):
    if is_command_disabled('/bin'):
        offline_message = get_command_offline_message('/bin')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return
    asyncio.create_task(bin_command(event))

# Help command for /bin
@client.on(events.NewMessage(pattern=r'^/bin$|^\.bin$'))
@registered_required
async def bin_help(event):
    if is_command_disabled('/bin'):
        offline_message = get_command_offline_message('/bin')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return
    await event.respond(
        "🎰 **How to Check BIN Information**\n\n"
        "Use the following format:\n\n"
        "`/bin <6-digit_BIN>`\n\n"
        "📋 **Examples:**\n"
        "`/bin 123456`\n"
        "`/bin 411111`\n\n"
        "✅ Get detailed information about any BIN number."
    )

# Command to generate fake address
@client.on(events.NewMessage(pattern=r'^/fake\s|^\.fake\s'))
@registered_required
async def fake(event):
    if is_command_disabled('/fake'):
        offline_message = get_command_offline_message('/fake')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return
    asyncio.create_task(fake_command(event))

# Help command for /fake
@client.on(events.NewMessage(pattern=r'^/fake$|^\.fake$'))
@registered_required
async def fake_help(event):
    if is_command_disabled('/fake'):
        offline_message = get_command_offline_message('/fake')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return
    await event.respond(
        "🏠 **How to Generate Fake Address**\n\n"
        "Simply use:\n\n"
        "`/fake`\n\n"
        "✅ The bot will generate a random US address with all necessary details."
    )

# Callback handler for the "Fake" button in Tools menu
@client.on(events.CallbackQuery(data=b"fake_command"))
@registered_required
async def fake_command_callback(event):
    if not await check_group_auth(event):
        return
    asyncio.create_task(fake_command(event))

# Callback handler for the "Gen" button in Tools menu
@client.on(events.CallbackQuery(data=b"gen_command"))
@registered_required
async def gen_command_callback(event):
    if not await check_group_auth(event):
        return
    asyncio.create_task(gen_command(event))

# Command to check a single CC using Stripe Auth - CHANGED FROM /auth TO /chk
@client.on(events.NewMessage(pattern=r'^/chk\s|^\.chk\s'))
@registered_required
async def chk(event):
    if is_command_disabled('/chk'):
        offline_message = get_command_offline_message('/chk')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    # Check usage limits - pass is_gate_command=True
    can_use, reason = can_user_use_command(user_id, event.is_group, is_gate_command=True)
    if not can_use:
        await event.respond(reason)
        return

    # For FREE users in private chats, increment personal usage
    if not event.is_group and user_plan == "FREE":
        increment_personal_usage(user_id)

    asyncio.create_task(chk_task(event))

# Help command for /chk
@client.on(events.NewMessage(pattern=r'^/chk$|^\.chk$'))
@registered_required
async def chk_help(event):
    if is_command_disabled('/chk'):
        offline_message = get_command_offline_message('/chk')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return

    await event.respond(
        "🔐 **How to Check Card**\n\n"
        "Use the following format to check card:\n\n"
        "`/chk <cc|mm|yy|cvv>`\n\n"
        "📋 **Examples:**\n"
        "`/chk 1234567891238547|12|2025|123`\n\n"
        "✅ Enjoy your card checking!"
    )

@registered_required
async def chk_task(event):
    try:
        user_id = event.sender_id
        session = get_user_session(user_id)
        username_tg = event.sender.username or "Unknown"
        card_details = event.message.text.replace('/chk', '').replace('.chk', '').strip()

        if not card_details:
            await event.respond("ℹ️ Please provide card details in the format: `/chk <cc|mes|ano|cvv>`")
            return

        parts = re.split(r'[:|,; ]', card_details)
        if len(parts) < 4:
            await event.respond("❌ Invalid card format. Use: `/chk <cc|mes|ano|cvv>`")
            return

        cc, mes, ano, cvv = [part.strip() for part in parts[:4]]

        if len(ano) == 2:
            ano = '20' + ano

        checker = StripeAuthChecker(session)

        processing_msg = await event.respond(
            f"⏳ Processing card: `{cc[:6]}XXXXXX{cc[-4:]}`\n"
            f"Please wait (this may take 15-20 seconds)..."
        )

        try:
            result = await asyncio.to_thread(checker.check_card, cc, mes, ano, cvv)
            response = checker.format_response(result, username_tg)

            # Update gate usage and cooldown
            increment_gate_usage(user_id)
            update_user_cooldown(user_id)

            await processing_msg.delete()
            await event.respond(response)

            if 'Login failed' in result['message']:
                await event.respond(
                    "🔐 **Login Failed**\n\n"
                    "The bot cannot currently authenticate with the website.\n"
                    "Possible reasons:\n"
                    "1️⃣ Website is down\n"
                    "2️⃣ Login credentials changed\n"
                    "3️⃣ New security measures added\n\n"
                    "🆘 Please contact @D_A_DYY for support."
                )

        except Exception as e:
            await processing_msg.delete()
            await event.respond(f"❌ Error processing card: {str(e)}")
    except Exception as e:
        await event.respond(f"❌ Error in chk command: {str(e)}")

# Stripe Auth Checker Command
@client.on(events.NewMessage(pattern=r'^/au\s|^\.au\s'))
@registered_required
async def stripe_check(event):
    if is_command_disabled('/au'):
        offline_message = get_command_offline_message('/au')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    # Check usage limits - pass is_gate_command=True
    can_use, reason = can_user_use_command(user_id, event.is_group, is_gate_command=True)
    if not can_use:
        await event.respond(reason)
        return

    # For FREE users in private chats, increment personal usage
    if not event.is_group and user_plan == "FREE":
        increment_personal_usage(user_id)

    asyncio.create_task(handle_stripe_auth(event))

# Help command for /au
@client.on(events.NewMessage(pattern=r'^/au$|^\.au$'))
@registered_required
async def au_help(event):
    if is_command_disabled('/au'):
        offline_message = get_command_offline_message('/au')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return

    await event.respond(
        "🎰 **How to Check Stripe Auth**\n\n"
        "Use the following format to check card:\n\n"
        "`/au <cc|mm|yy|cvv>`\n\n"
        "📋 **Examples:**\n"
        "`/au 1234567891238547|12|2025|123`\n\n"
    )

# Mass Stripe Auth Checker Command with strict limits
@client.on(events.NewMessage(pattern=r'^/mau\s|^\.mau\s'))
@registered_required
async def mass_stripe_check(event):
    if is_command_disabled('/mau'):
        offline_message = get_command_offline_message('/mau')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    # Check usage limits - pass is_gate_command=True
    can_use, reason = can_user_use_command(user_id, event.is_group, is_gate_command=True)
    if not can_use:
        await event.respond(reason)
        return

    # For FREE users in private chats, increment personal usage
    if not event.is_group and user_plan == "FREE":
        increment_personal_usage(user_id)

    asyncio.create_task(handle_mass_stripe_auth(event))

# Help command for /mau
@client.on(events.NewMessage(pattern=r'^/mau$|^\.mau$'))
@registered_required
async def mau_help(event):
    if is_command_disabled('/mau'):
        offline_message = get_command_offline_message('/mau')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return

    await event.respond(
        "🔄 **How to Mass Check Stripe Auth**\n\n"
        "Use the following format to check up to 5 cards:\n\n"
        "`/mau`\n"
        "`cc|mm|yy|cvv`\n"
        "...\n\n"
        "📋 **Example:**\n"
        "`/mau`\n"
        "`1234567891238547|12|2025|123`\n"
    )

# Command to check Stripe charge
@client.on(events.NewMessage(pattern=r'^/sc\s|^\.sc\s'))
@registered_required
async def stripe_charge(event):
    if is_command_disabled('/sc'):
        offline_message = get_command_offline_message('/sc')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    # Check usage limits - pass is_gate_command=True
    can_use, reason = can_user_use_command(user_id, event.is_group, is_gate_command=True)
    if not can_use:
        await event.respond(reason)
        return

    # For FREE users in private chats, increment personal usage
    if not event.is_group and user_plan == "FREE":
        increment_personal_usage(user_id)

    asyncio.create_task(handle_stripe_charge(event))

# Help command for /sc
@client.on(events.NewMessage(pattern=r'^/sc$|^\.sc$'))
@registered_required
async def sc_help_command(event):
    if is_command_disabled('/sc'):
        offline_message = get_command_offline_message('/sc')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return

    await event.respond(
        "💰 **How to Check Stripe Charge 10$**\n\n"
        "`/sc <cc|mm|yy|cvv>`\n\n"
        "📋 **Examples:**\n"
        "`/sc 1234567891238547|12|2025|123`\n\n"
    )

# Command to check $5 charge
@client.on(events.NewMessage(pattern=r'^/sp\s|^\.sp\s'))
@registered_required
async def sp_charge(event):
    if is_command_disabled('/sp'):
        offline_message = get_command_offline_message('/sp')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    # Check usage limits - pass is_gate_command=True
    can_use, reason = can_user_use_command(user_id, event.is_group, is_gate_command=True)
    if not can_use:
        await event.respond(reason)
        return

    # For FREE users in private chats, increment personal usage
    if not event.is_group and user_plan == "FREE":
        increment_personal_usage(user_id)

    asyncio.create_task(handle_sp_charge(event))

# Help command for /sp
@client.on(events.NewMessage(pattern=r'^/sp$|^\.sp$'))
@registered_required
async def sp_help_command(event):
    if is_command_disabled('/sp'):
        offline_message = get_command_offline_message('/sp')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return

    await sp_help(event)

# Command to handle mass stripe charge
@client.on(events.NewMessage(pattern=r'^/msc\s|^\.msc\s'))
@registered_required
async def msc(event):
    if is_command_disabled('/msc'):
        offline_message = get_command_offline_message('/msc')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return
    await handle_mass_stripe_charge(event)

# Help command for /msc
@client.on(events.NewMessage(pattern=r'^/msc$|^\.msc$'))
@registered_required
async def msc_help(event):
    if is_command_disabled('/msc'):
        offline_message = get_command_offline_message('/msc')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return

    await event.respond(
        "📁 **How to use Mass Stripe Charge**\n\n"
        "Send a text file containing credit cards with the /msc command:\n\n"
        "**Format:** `cc|mm|yy|cvv` (one per line)\n\n"
        "📋 **Example file content:**\n"
        "4111111111111113|12|2025|123\n\n"
 
    )

# Command to generate CCs
@client.on(events.NewMessage(pattern=r'^/gen\s|^\.gen\s'))
@registered_required
async def gen(event):
    if is_command_disabled('/gen'):
        offline_message = get_command_offline_message('/gen')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return

    user_id = event.sender_id

    # For FREE users in private chats, increment personal usage
    if not event.is_group and get_user_plan(user_id) == "FREE":
        increment_personal_usage(user_id)

    asyncio.create_task(gen_command(event))

# Help command for /gen
@client.on(events.NewMessage(pattern=r'^/gen$|^\.gen$'))
@registered_required
async def gen_help(event):
    if is_command_disabled('/gen'):
        offline_message = get_command_offline_message('/gen')
        await event.respond(offline_message)
        return
    if not await check_group_auth(event):
        return

    await event.respond(
        "📦 **How to Generate Credit Cards**\n\n"
        "`/gen <BIN> <amount>`\n\n"
        "📋 **Examples:**\n"
        "`/gen 543210 5` - Generate 5 cards with BIN 543210\n\n"
        "✅ The bot will generate valid credit card numbers."
    )

# Command to start the bot (handles both /start and Start button)
@client.on(events.NewMessage(pattern=r'^/start$|^\.start$'))
async def start(event):
    asyncio.create_task(start_task(event))

async def start_task(event):
    user_id = event.sender_id

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    # Check group authorization for non-private messages
    if not event.is_private:
        chat = await event.get_chat()
        if not is_group_authorized(chat.id):
            await event.respond("⛔ This group is not authorized to use the bot.")
            return

    if is_user_registered(user_id):
        user_plan = get_user_plan(user_id)
        await event.respond(
            f"👋 Welcome back!\n\n"
            f"💎 You're registered as {user_plan} user.\n"
            "🧰 Use /cmds to see available commands.",
            buttons=[Button.inline("📋 Show Commands", b"enter_world")]
        )
    else:
        await event.respond(
            "👋 Welcome to WAYNE TECH\n\n"
            "🔐 You need to register before using the bot.\n"
            "📝 Click the button below to register:",
            buttons=[Button.inline("📝 Register Now", b"register_user")]
        )

# Register command
@client.on(events.NewMessage(pattern=r'^/register\s|^\.register\s'))
async def register_command(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if is_user_registered(user_id):
        user_plan = get_user_plan(user_id)
        await event.respond(f"ℹ️ You're already registered as {user_plan} user!")
        return

    if register_user(user_id):
        await event.respond(
            "🎉 Registration Successful!\n\n"
            "🆓 You've been registered as a FREE user.\n"
            "🧰 Now you can use all the bot commands.\n\n"
            "📋 Use /cmds to see available commands.",
            buttons=[Button.inline("📋 Show Commands", b"enter_world")]
        )
    else:
        await event.respond("❌ Failed to register. Please try again.")

# Help command for /register
@client.on(events.NewMessage(pattern=r'^/register$|^\.register$'))
async def register_help(event):
    if not await check_group_auth(event):
        return

    await event.respond(
        "📝 **How to Register**\n\n"
        "Simply use:\n\n"
        "`/register`\n\n"
        "✅ This will register you as a FREE user and give you access to all bot commands."
    )

# Callback handler for the "Register" button
@client.on(events.CallbackQuery(data=b"register_user"))
async def register_user_callback(event):
    await register_command(event)

# Command to display available commands
@client.on(events.NewMessage(pattern=r'^/cmds\s|^\.cmds\s'))
async def cmds(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    await event.respond(
        "🦇 𝑽𝒆𝒓𝒔𝒊𝒐𝒏: 𝟐.𝟎.𝟎\n"
        "📋 𝑨𝒗𝒂𝒊𝒍𝒂𝒃𝒍𝒆 𝒄𝒐𝒎𝒎𝒂𝒏𝒅𝒔:\n\n"
        "🔍 𝑪𝒍𝒊𝒄𝒌 𝒃𝒆𝒍𝒐𝒘 𝒕𝒐 𝒆𝒙𝒑𝒍𝒐𝒓𝒆 𝒕𝒉𝒆 𝒄𝒐𝒎𝒎𝒂𝒏𝒅𝒔:",
        buttons=[Button.inline("🚪 🦇 𝑬𝑵𝑻𝑬𝑹 𝑻𝑯𝑬 𝑾𝑶𝑹𝑳𝑫 🦇", b"enter_world")]
    )

# Help command for /cmds
@client.on(events.NewMessage(pattern=r'^/cmds$|^\.cmds$'))
async def cmds_help(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    await event.respond(
        "𝑽𝒆𝒓𝒔𝒊𝒐𝒏: 𝟐.𝟎.𝟎\n"
        "𝑨𝒗𝒂𝒊𝒍𝒂𝒃𝒍𝒆 𝒄𝒐𝒎𝒎𝒂𝒏𝒅𝒔:\n\n"
        "𝑪𝒍𝒊𝒄𝒌 𝒃𝒆𝒍𝒐𝒘 𝒕𝒐 𝒆𝒙𝒑𝒍𝒐𝒓𝒆 𝒕𝒉𝒆 𝒄𝒐𝒎𝒎𝒂𝒏𝒅𝒔:",
        buttons=[Button.inline("🚪 🦇 𝑬𝑵𝑻𝑬𝑹 𝑻𝑯𝑬 𝑾𝑶𝑹𝑳𝑫 🦇", b"enter_world")]
    )

# Callback handler for the "🦇 𝑬𝑵𝑻𝑬𝑹 𝑻𝑯𝑬 𝑾𝑶𝑹𝑳𝑫 🦇" button
@client.on(events.CallbackQuery(data=b"enter_world"))
async def enter_world(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    await event.edit(
        "𝑴𝒂𝒊𝒏 𝑴𝒆𝒏𝒖 \n"
        "𝑽𝒆𝒓𝒔𝒊𝒐𝒏: 𝟐.𝟎.𝟎\n\n"
        "𝐂𝐡𝐨𝐨𝐬𝐞 𝐚 𝐬𝐞𝐜𝐭𝐢𝐨𝐧:",
        buttons=[
            [Button.inline("🍀 𝑩𝒂𝒔𝒊𝒄", b"basic_commands"), Button.inline("🔒 Admins", b"admin_commands")],
            [Button.inline("🛠️ 𝙏𝙤𝙤𝙡𝙨 ", b"tools_commands"), Button.inline("🔍 Gates", b"gates_commands")],
            [Button.inline("❌ 𝑬𝒙𝒊𝒕 ", b"exit_command")]
        ]
    )

# Callback handler for the "Basic" section
@client.on(events.CallbackQuery(data=b"basic_commands"))
async def basic_commands(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    buttons = [
        [Button.inline("🏠 /start", b"start_command"), Button.inline("📝 /register", b"register_command")],
        [Button.inline("🔙 Back to 𝑴𝒂𝒊𝒏 𝑴𝒆𝒏𝒖 ", b"enter_world")]
    ]
    await event.edit(
        "🍀 𝑩𝒂𝒔𝒊𝒄 Commands\n"
        "Here are the basic commands you can use:",
        buttons=buttons
    )

# Callback handler for the "Start" button in Basic menu
@client.on(events.CallbackQuery(data=b"start_command"))
async def start_command_callback(event):
    await start(event)

# Callback handler for the "Register" button in Basic menu
@client.on(events.CallbackQuery(data=b"register_command"))
async def register_command_callback(event):
    await register_command(event)

# Callback handler for the "Admins" section
@client.on(events.CallbackQuery(data=b"admin_commands"))
@registered_required
async def admin_commands(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    # Check if user is restricted from admin menu
    if is_user_restricted(user_id):
        await event.respond(
            "🚫 **ACCESS DENIED** 🚫\n\n"
            "⚡ *By Order of the Peaky Blinders* ⚡\n\n"
            "❌ You don't have permission to access the Admin Menu!\n"
            "🔒 Contact @D_A_DYY if you believe this is an error.\n\n"
            "🏴‍☠️ *No fookin' fighting in here* 🏴‍☠️"
        )
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to access admin commands.")
        return

    await event.edit(
        "🔒 Admin Commands\n"
        "Here are the admin commands:",
        buttons=[
            [Button.inline("⬆️ /𝒖𝒑𝒈𝒓𝒂𝒅𝒆", b"upgrade_command"), Button.inline("⛔ /𝒃𝒂𝒏𝒃𝒊𝒏", b"banbin_command")],
            [Button.inline("✅ /𝒖𝒏𝒃𝒂𝒏𝒃𝒊𝒏", b"unbanbin_command"), Button.inline("🎁 /𝒈𝒄", b"generate_code_command")],
            [Button.inline("🚫 /𝒃𝒂𝒏", b"ban_command"), Button.inline("✅ /𝒖𝒏𝒃𝒂𝒏", b"unban_command")],
            [Button.inline("⬇️ /𝒍𝒐𝒐𝒔𝒆𝒓", b"loser_command"), Button.inline("🔐 /𝒈𝒂𝒖𝒕𝒉", b"gauth_command")],
            [Button.inline("❌ /𝒅𝒂𝒖𝒕𝒉", b"dauth_command"), Button.inline("📢 /𝒔𝒆𝒏𝒅𝒂𝒍𝒍", b"sendall_command")],
            [Button.inline("📋 /𝒏𝒐𝒕𝒖𝒔𝒆𝒅", b"notused_command"), Button.inline("🔒 /𝒏𝒐", b"no_command")],
            [Button.inline("⚙️ /𝒐𝒇𝒇", b"off_command"), Button.inline("⚙️ /𝒐𝒏", b"on_command")],
            [Button.inline("🔙 𝑩𝒂𝒄𝒌 𝒕𝒐 𝑴𝒂𝒊𝒏 𝑴𝒆𝒏𝒖 ", b"enter_world")]
        ]
    )

# Callback handler for the "Upgrade" button
@client.on(events.CallbackQuery(data=b"upgrade_command"))
@registered_required
async def upgrade_command(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan == "GOD":
        await event.respond(
            "⬆️ To upgrade a user, use the following command:\n\n"
            "`/upgrade <username or ID>`"
        )
    else:
        await event.respond("🚫 You do not have permission to upgrade users.")

# Command to upgrade a user
@client.on(events.NewMessage(pattern=r'^/upgrade\s|^\.upgrade\s'))
@registered_required
async def upgrade(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to upgrade users.")
        return

    args = event.message.text.split()
    if len(args) < 2:
        await event.respond("ℹ️ Please provide a username or ID to upgrade. Usage: `/upgrade <username or ID>`")
        return

    target = args[1]

    try:
        target_user = await client.get_entity(target)
        target_id = target_user.id
    except Exception as e:
        await event.respond(f"❌ Could not find user: {target}")
        return

    if upgrade_user(target_id, "PLUS"):
        await event.respond(f"✅ Successfully upgraded user {target} to PLUS plan!")
    else:
        await event.respond("❌ Failed to upgrade user.")

# Help command for /upgrade
@client.on(events.NewMessage(pattern=r'^/upgrade$|^\.upgrade$'))
@registered_required
async def upgrade_help(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to upgrade users.")
        return

    await event.respond(
        "⬆️ **How to Upgrade a User**\n\n"
        "`/upgrade <username or ID>`\n\n"
        "📋 **Example:**\n"
        "`/upgrade @username`\n"
        "`/upgrade 123456789`\n\n"
        "✅ This will upgrade the user to PLUS plan."
    )

# Callback handler for the "Banbin" button
@client.on(events.CallbackQuery(data=b"banbin_command"))
@registered_required
async def banbin_command(event):
    if not await check_group_auth(event):
        return
    await event.respond(
        "⛔ To ban a BIN, use the following command:\n\n"
        "`/banbin <6-digit BIN>` or `/banbin <ccnum|mon|year|cvv>`"
    )

# Command to ban a BIN
@client.on(events.NewMessage(pattern=r'^/banbin\s|^\.banbin\s'))
@registered_required
async def banbin(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to ban BINs.")
        return

    args = event.message.text.split()
    if len(args) < 2:
        await event.respond("ℹ️ Please provide a BIN or card details. Usage: `/banbin <6-digit BIN>` or `/banbin <ccnum|mon|year|cvv>`")
        return

    input_data = args[1]

    if '|' in input_data:
        try:
            cc, mes, ano, cvv = input_data.split('|')
            bin_number = cc[:6]
        except ValueError:
            await event.respond("❌ Invalid card format. Please use the format: `/banbin <ccnum|mon|year|cvv>`")
            return
    else:
        if len(input_data) != 6 or not input_data.isdigit():
            await event.respond("❌ Invalid BIN. Please provide a 6-digit BIN.")
            return
        bin_number = input_data

    ban_bin(bin_number)
    await event.respond(f"✅ BIN `{bin_number}` has been banned.")

# Help command for /banbin
@client.on(events.NewMessage(pattern=r'^/banbin$|^\.banbin$'))
@registered_required
async def banbin_help(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to ban BINs.")
        return

    await event.respond(
        "⛔ **How to Ban a BIN**\n\n"
        "`/banbin <6-digit BIN>` or `/banbin <ccnum|mon|year|cvv>`\n\n"
        "📋 **Examples:**\n"
        "`/banbin 123456`\n"
        "`/banbin 411111|12|2025|123`\n\n"
        "✅ This will ban the BIN from being used."
    )

# Callback handler for the "Unbanbin" button
@client.on(events.CallbackQuery(data=b"unbanbin_command"))
@registered_required
async def unbanbin_command(event):
    if not await check_group_auth(event):
        return
    await event.respond(
        "✅ To unban a BIN, use the following command:\n\n"
        "`/unbanbin <6-digit BIN>` or `/unbanbin <ccnum|mon|year|cvv>`"
    )

# Command to unban a BIN
@client.on(events.NewMessage(pattern=r'^/unbanbin\s|^\.unbanbin\s'))
@registered_required
async def unbanbin(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to unban BINs.")
        return

    args = event.message.text.split()
    if len(args) < 2:
        await event.respond("ℹ️ Please provide a BIN or card details. Usage: `/unbanbin <6-digit BIN>` or `/unbanbin <ccnum|mon|year|cvv>`")
        return

    input_data = args[1]

    if '|' in input_data:
        try:
            cc, mes, ano, cvv = input_data.split('|')
            bin_number = cc[:6]
        except ValueError:
            await event.respond("❌ Invalid card format. Please use the format: `/unbanbin <ccnum|mon|year|cvv>`")
            return
    else:
        if len(input_data) != 6 or not input_data.isdigit():
            await event.respond("❌ Invalid BIN. Please provide a 6-digit BIN.")
            return
        bin_number = input_data

    if unban_bin(bin_number):
        await event.respond(f"✅ BIN `{bin_number}` has been unbanned.")
    else:
        await event.respond(f"ℹ️ BIN `{bin_number}` is not banned or could not be unbanned.")

# Help command for /unbanbin
@client.on(events.NewMessage(pattern=r'^/unbanbin$|^\.unbanbin$'))
@registered_required
async def unbanbin_help(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to unban BINs.")
        return

    await event.respond(
        "✅ **How to Unban a BIN**\n\n"
        "`/unbanbin <6-digit BIN>` or `/unbanbin <ccnum|mon|year|cvv>`\n\n"
        "📋 **Examples:**\n"
        "`/unbanbin 123456`\n"
        "`/unbanbin 411111|12|2025|123`\n\n"
        "✅ This will unban the BIN if it was previously banned."
    )

# Callback handler for the "Ban" button
@client.on(events.CallbackQuery(data=b"ban_command"))
@registered_required
async def ban_command(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to ban users.")
        return

    await event.respond(
        "⛔ To ban a user, use the following command:\n\n"
        "`/ban <username or ID>`"
    )

# Command to ban a user
@client.on(events.NewMessage(pattern=r'^/ban\s|^\.ban\s'))
@registered_required
async def ban(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to ban users.")
        return

    args = event.message.text.split()
    if len(args) < 2:
        await event.respond("ℹ️ Please provide a username or ID to ban. Usage: `/ban <username or ID>`")
        return

    target = args[1]

    try:
        target_user = await client.get_entity(target)
        target_id = target_user.id
    except Exception as e:
        await event.respond(f"❌ Could not find user: {target}")
        return

    ban_user(target_id)
    await event.respond(f"✅ User {target} has been banned.")

# Help command for /ban
@client.on(events.NewMessage(pattern=r'^/ban$|^\.ban$'))
@registered_required
async def ban_help(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to ban users.")
        return

    await event.respond(
        "⛔ **How to Ban a User**\n\n"
        "`/ban <username or ID>`\n\n"
        "📋 **Examples:**\n"
        "`/ban @username`\n"
        "`/ban 123456789`\n\n"
        "✅ This will ban the user from using the bot."
    )

# Callback handler for the "Unban" button
@client.on(events.CallbackQuery(data=b"unban_command"))
@registered_required
async def unban_command(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to unban users.")
        return

    await event.respond(
        "✅ To unban a user, use the following command:\n\n"
        "`/unban <username or ID>`"
    )

# Command to unban a user
@client.on(events.NewMessage(pattern=r'^/unban\s|^\.unban\s'))
@registered_required
async def unban(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to unban users.")
        return

    args = event.message.text.split()
    if len(args) < 2:
        await event.respond("ℹ️ Please provide a username or ID to unban. Usage: `/unban <username or ID>`")
        return

    target = args[1]

    try:
        target_user = await client.get_entity(target)
        target_id = target_user.id
    except Exception as e:
        await event.respond(f"❌ Could not find user: {target}")
        return

    if unban_user(target_id):
        await event.respond(f"✅ User {target} has been unbanned.")
    else:
        await event.respond(f"ℹ️ User {target} is not banned or could not be unbanned.")

# Help command for /unban
@client.on(events.NewMessage(pattern=r'^/unban$|^\.unban$'))
@registered_required
async def unban_help(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to unban users.")
        return

    await event.respond(
        "✅ **How to Unban a User**\n\n"
        "`/unban <username or ID>`\n\n"
        "📋 **Examples:**\n"
        "`/unban @username`\n"
        "`/unban 123456789`\n\n"
        "✅ This will unban the user if they were previously banned."
    )

# Callback handler for the "Loser" button
@client.on(events.CallbackQuery(data=b"loser_command"))
@registered_required
async def loser_command(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan != "GOD":
        await event.respond("🚫 You do not have permission to downgrade users.")
        return

    await event.respond(
        "⬇️ To downgrade a user to the FREE plan, use the following command:\n\n"
        "`/looser <username or ID>`"
    )

# Command to downgrade a user to FREE plan
@client.on(events.NewMessage(pattern=r'^/looser\s|^\.looser\s'))
@registered_required
async def loser(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan != "GOD":
        await event.respond("🚫 You do not have permission to downgrade users.")
        return

    args = event.message.text.split()
    if len(args) < 2:
        await event.respond("ℹ️ Please provide a username or ID to downgrade. Usage: `/looser <username or ID>`")
        return

    target = args[1]

    try:
        target_user = await client.get_entity(target)
        target_id = target_user.id
    except Exception as e:
        await event.respond(f"❌ Could not find user: {target}")
        return

    if downgrade_user(target_id):
        await event.respond(f"✅ User {target} has been downgraded to the FREE plan.")
    else:
        await event.respond("❌ Failed to downgrade user.")

# Help command for /looser
@client.on(events.NewMessage(pattern=r'^/looser$|^\.looser$'))
@registered_required
async def loser_help(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan != "GOD":
        await event.respond("🚫 You do not have permission to downgrade users.")
        return

    await event.respond(
        "⬇️ **How to Downgrade a User**\n\n"
        "`/looser <username or ID>`\n\n"
        "📋 **Examples:**\n"
        "`/looser @username`\n"
        "`/looser 123456789`\n\n"
        "✅ This will downgrade the user to FREE plan."
    )

# Callback handler for the "Gates" section
@client.on(events.CallbackQuery(data=b"gates_commands"))
@registered_required
async def gates_commands(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    await event.edit(
        "🔍 **Gates Commands**\n"
        "Choose a gateway type:",
        buttons=[
            [Button.inline("💳 Auth Gates", b"auth_gates_menu"), Button.inline("🔄 Mass Checkers", b"mass_gates_menu")],
            [Button.inline("💰 Charge Gates", b"charge_gates_menu"), Button.inline("🔙 Back to 𝑴𝒂𝒊𝒏 𝑴𝒆𝒏𝒖 ", b"enter_world")]
        ]
    )

# Callback handler for Auth Gates menu
@client.on(events.CallbackQuery(data=b"auth_gates_menu"))
@registered_required
async def auth_gates_menu(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    # Get status for each command
    au_status = "ON ✅" if not is_command_disabled('/au') else "OFF ❌"
    chk_status = "ON ✅" if not is_command_disabled('/chk') else "OFF ❌"

    await event.edit(
        "💳 **Auth Gates**\n\n"
        f"🔥 Stripe Auth\n"
        f"Cmd: /au cc|mm|yy|cvv\n"
        f"Status: {au_status}\n\n"
        f"🔥 Stripe Auth 2\n"
        f"Cmd: /chk cc|mm|yy|cvv\n"
        f"Status: {chk_status}\n\n"
        "🚀 More Auth Gates coming soon... 🔥",
        buttons=[Button.inline("🔙 Back to Gates", b"gates_commands")]
    )

# Callback handler for Mass Gates menu
@client.on(events.CallbackQuery(data=b"mass_gates_menu"))
@registered_required
async def mass_gates_menu(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    # Get status for each command
    mau_status = "ON ✅" if not is_command_disabled('/mau') else "OFF ❌"
    msc_status = "ON ✅" if not is_command_disabled('/msc') else "OFF ❌"

    await event.edit(
        "🔄 **Mass Checkers**\n\n"
        f"🔥 Mass Stripe Auth\n"
        f"Cmd: /mau\n"
        f"Status: {mau_status}\n\n"
        f"🔥 Mass Stripe Charge\n"
        f"Cmd: /msc\n"
        f"Status: {msc_status}\n\n"
        "🚀 More Mass Gates coming soon... 🔥",
        buttons=[Button.inline("🔙 Back to Gates", b"gates_commands")]
    )

# Callback handler for Charge Gates menu
@client.on(events.CallbackQuery(data=b"charge_gates_menu"))
@registered_required
async def charge_gates_menu(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    # Get status for each command
    sc_status = "ON ✅" if not is_command_disabled('/sc') else "OFF ❌"
    sp_status = "ON ✅" if not is_command_disabled('/sp') else "OFF ❌"

    await event.edit(
        "💰 **Charge Gates**\n\n"
        f"🔥 Stripe Charge $10\n"
        f"Cmd: /sc cc|mm|yy|cvv\n"
        f"Status: {sc_status}\n\n"
        f"🔥 Special Charge $5\n"
        f"Cmd: /sp cc|mm|yy|cvv\n"
        f"Status: {sp_status}\n\n"
        "🚀 More Charge Gates coming soon... 🔥",
        buttons=[Button.inline("🔙 Back to Gates", b"gates_commands")]
    )

# Command to broadcast a message to all users (FREE to PLUS plans)
@client.on(events.NewMessage(pattern=r'^/sendall\s|^\.sendall\s'))
@registered_required
async def sendall(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan != "GOD":
        await event.respond("🚫 You do not have permission to use this command.")
        return

    args = event.message.text.split()
    if len(args) < 2:
        await event.respond("📢 **How to use /sendall**\n\n"
                           "Type `/sendall <your message>`\n"
                           "Example: `/sendall Hello everyone!`\n"
                           "This will broadcast your message to all users.")
        return

    message = " ".join(args[1:])

    users = set()
    for plan in ["FREE", "PLUS"]:
        if os.path.exists(PLAN_FILES[plan]):
            with open(PLAN_FILES[plan], 'r') as f:
                users.update(f.read().splitlines())

    for user in users:
        if int(user) != user_id:
            try:
                await client.send_message(int(user), message)
            except Exception as e:
                print(f"Failed to send message to user {user}: {e}")

    await event.respond("📢 Message broadcasted to all users.")

# Help command for /sendall
@client.on(events.NewMessage(pattern=r'^/sendall$|^\.sendall$'))
@registered_required
async def sendall_help(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan != "GOD":
        await event.respond("🚫 You do not have permission to use this command.")
        return

    await event.respond(
        "📢 **How to use /sendall**\n\n"
        "Type `/sendall <your message>`\n"
        "Example: `/sendall Hello everyone!`\n"
        "This will broadcast your message to all users."
    )

# Command to get a list of unused and expired gift codes
@client.on(events.NewMessage(pattern=r'^/notused\s|^\.notused\s'))
@registered_required
async def notused(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan != "GOD":
        await event.respond("🚫 You do not have permission to use this command.")
        return

    if not os.path.exists(GC_FILE):
        await event.respond("ℹ️ No gift codes have been generated yet.")
        return

    with open(GC_FILE, 'r') as f:
        valid_codes = f.read().splitlines()

    unused_codes = []
    expired_codes = []
    for line in valid_codes:
        code, expiration_date = line.split('|')
        expiration_date = datetime.datetime.strptime(expiration_date, "%Y-%m-%d")
        if datetime.datetime.now() > expiration_date:
            expired_codes.append(code)
        else:
            unused_codes.append(code)

    with open(GC_FILE, 'w') as f:
        for line in valid_codes:
            code, expiration_date = line.split('|')
            if code not in expired_codes:
                f.write(f"{line}\n")

    response = "🎁 **Unused and Expired Gift Codes**\n\n"
    if unused_codes:
        response += "✅ **Unused Codes:**\n"
        for code in unused_codes:
            response += f"`{code}`\n"
    else:
        response += "ℹ️ No unused codes found.\n"

    if expired_codes:
        response += "\n❌ **Expired Codes (Removed):**\n"
        for code in expired_codes:
            response += f"`{code}`\n"
    else:
        response += "\nℹ️ No expired codes found.\n"

    await event.respond(response)

# Help command for /notused
@client.on(events.NewMessage(pattern=r'^/notused$|^\.notused$'))
@registered_required
async def notused_help(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan != "GOD":
        await event.respond("🚫 You do not have permission to use this command.")
        return

    await event.respond(
        "📋 **How to Check Unused Gift Codes**\n\n"
        "Simply use:\n\n"
        "`/notused`\n\n"
        "✅ This will show all unused and expired gift codes."
    )

# Callback handler for the "Sendall" button in Admins menu
@client.on(events.CallbackQuery(data=b"sendall_command"))
@registered_required
async def sendall_command(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan != "GOD":
        await event.respond("🚫 You do not have permission to use this command.")
        return

    await event.respond(
        "📢 **How to use /sendall**\n\n"
        "Type `/sendall <your message>`\n"
        "Example: `/sendall Hello everyone!`\n"
        "This will broadcast your message to all users."
    )

# Callback handler for the "Notused" button in Admins menu
@client.on(events.CallbackQuery(data=b"notused_command"))
@registered_required
async def notused_command(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan != "GOD":
        await event.respond("🚫 You do not have permission to use this command.")
        return

    if not os.path.exists(GC_FILE):
        await event.respond("ℹ️ No gift codes have been generated yet.")
        return

    with open(GC_FILE, 'r') as f:
        valid_codes = f.read().splitlines()

    unused_codes = []
    expired_codes = []
    for line in valid_codes:
        code, expiration_date = line.split('|')
        expiration_date = datetime.datetime.strptime(expiration_date, "%Y-%m-%d")
        if datetime.datetime.now() > expiration_date:
            expired_codes.append(code)
        else:
            unused_codes.append(code)

    with open(GC_FILE, 'w') as f:
        for line in valid_codes:
            code, expiration_date = line.split('|')
            if code not in expired_codes:
                f.write(f"{line}\n")

    response = "🎁 **Unused and Expired Gift Codes**\n\n"
    if unused_codes:
        response += "✅ **Unused Codes:**\n"
        for code in unused_codes:
            response += f"`{code}`\n"
    else:
        response += "ℹ️ No unused codes found.\n"

    if expired_codes:
        response += "\n❌ **Expired Codes (Removed):**\n"
        for code in expired_codes:
            response += f"`{code}`\n"
    else:
        response += "\nℹ️ No expired codes found.\n"

    await event.respond(response)

# Command to restrict user commands
@client.on(events.NewMessage(pattern=r'^/no\s|^\.no\s'))
@registered_required
async def no_command(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan != "GOD":
        await event.respond("🚫 You do not have permission to use this command.")
        return

    await restrict_user_command(event)

# Help command for /no
@client.on(events.NewMessage(pattern=r'^/no$|^\.no$'))
@registered_required
async def no_help(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan != "GOD":
        await event.respond("🚫 You do not have permission to use this command.")
        return

    await event.respond(
        "🔒 **How to use /no**\n\n"
        "Restrict a user from using specific commands:\n\n"
        "`/no <command> <user_id>`\n\n"
        "📋 **Examples:**\n"
        "`/no /gate 987654321` - Restrict user from using /gate\n\n"
        "✅ The user will receive a restriction message when trying to use the command."
    )

# Callback handler for /no button - FIXED to show help message
@client.on(events.CallbackQuery(data=b"no_command"))
@registered_required
async def no_command_callback(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan != "GOD":
        await event.respond("🚫 You do not have permission to use this command.")
        return

    await event.respond(
        "🔒 **How to use /no**\n\n"
        "Restrict a user from using specific commands:\n\n"
        "`/no <command> <user_id>`\n\n"
        "📋 **Examples:**\n"
        "`/no /gate 987654321` - Restrict user from using /gate\n\n"
        "✅ The user will receive a restriction message when trying to use the command."
    )

# Command to disable commands globally
@client.on(events.NewMessage(pattern=r'^/off\s|^\.off\s'))
@registered_required
async def off_command(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to use this command.")
        return

    await disable_command_handler(event)  # ✅ CORRECT - calls the async handler

# Help command for /off
@client.on(events.NewMessage(pattern=r'^/off$|^\.off$'))
@registered_required
async def off_help(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to use this command.")
        return

    await event.respond(
        "🚫 **How to use /off**\n\n"
        "Disable a command globally for all users:\n\n"
        "`/off <command>`\n\n"
        "📋 **Examples:**\n"
        "`/off /sc` - Disable /sc command for everyone\n\n"
        "✅ The command will be disabled until re-enabled with /on."
    )

# Callback handler for /off button - FIXED to show help message
@client.on(events.CallbackQuery(data=b"off_command"))
@registered_required
async def off_command_callback(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to use this command.")
        return

    await event.respond(
        "🚫 **How to use /off**\n\n"
        "Disable a command globally for all users:\n\n"
        "`/off <command>`\n\n"
        "📋 **Examples:**\n"
        "`/off /sc` - Disable /sc command for everyone\n\n"
        "✅ The command will be disabled until re-enabled with /on."
    )

# Command to enable commands globally
@client.on(events.NewMessage(pattern=r'^/on\s|^\.on\s'))
@registered_required
async def on_command(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to use this command.")
        return

    await enable_command_handler(event)  # ✅ CORRECT - calls the async handler

# Help command for /on
@client.on(events.NewMessage(pattern=r'^/on$|^\.on$'))
@registered_required
async def on_help(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to use this command.")
        return

    await event.respond(
        "✅ **How to use /on**\n\n"
        "Enable a previously disabled command globally:\n\n"
        "`/on <command>`\n\n"
        "📋 **Examples:**\n"
        "`/on /sc` - Enable /sc command for everyone\n\n"
        "✅ The command will be re-enabled for all users."
    )

# Callback handler for /on button - FIXED to show help message
@client.on(events.CallbackQuery(data=b"on_command"))
@registered_required
async def on_command_callback(event):
    if not await check_group_auth(event):
        return

    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot. Contact @D_A_DYY")
        return

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 You do not have permission to use this command.")
        return

    await event.respond(
        "✅ **How to use /on**\n\n"
        "Enable a previously disabled command globally:\n\n"
        "`/on <command>`\n\n"
        "📋 **Examples:**\n"
        "`/on /sc` - Enable /sc command for everyone\n\n"
        "✅ The command will be re-enabled for all users."
    )

# Create a simple Flask app for health checks
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Telegram Bot is Running"

@app.route('/health')
def health():
    return "OK", 200

def run_flask_app():
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)

# Start Flask in a separate thread
flask_thread = threading.Thread(target=run_flask_app, daemon=True)
flask_thread.start()

print("🤖 Bot Started with Health Check Server...")
try:
    client.run_until_disconnected()
except Exception as e:
    print(f"❌ Bot crashed: {e}")
    for file in os.listdir(SESSIONS_FOLDER):
        if file.startswith('bot_') and file.endswith('.session'):
            try:
                os.remove(os.path.join(SESSIONS_FOLDER, file))
            except:
                pass
    print("🔄 Restarting bot...")
    client = init_client()
    client.start(bot_token=bot_token)
    client.run_until_disconnected()
