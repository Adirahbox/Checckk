# addups/notwork.py

import os
import re
import random
from telethon import events, Button
from shared import get_user_plan, is_user_banned, is_user_registered

# File to store disabled commands
DISABLED_COMMANDS_FILE = "users/DISABLED_COMMANDS.txt"

# Initialize file if it doesn't exist
if not os.path.exists(DISABLED_COMMANDS_FILE):
    os.makedirs(os.path.dirname(DISABLED_COMMANDS_FILE), exist_ok=True)
    open(DISABLED_COMMANDS_FILE, 'a').close()

def is_command_disabled(command):
    """Check if a command is disabled globally"""
    try:
        with open(DISABLED_COMMANDS_FILE, 'r') as f:
            disabled_commands = [line.strip() for line in f if line.strip()]
            return command in disabled_commands
    except FileNotFoundError:
        return False

def disable_command(command):
    """Disable a command globally"""
    disabled_commands = set()

    # Read existing disabled commands
    try:
        with open(DISABLED_COMMANDS_FILE, 'r') as f:
            for line in f:
                if line.strip():
                    disabled_commands.add(line.strip())
    except FileNotFoundError:
        pass

    # Add new command
    disabled_commands.add(command)

    # Write back to file
    with open(DISABLED_COMMANDS_FILE, 'w') as f:
        for cmd in disabled_commands:
            f.write(f"{cmd}\n")

    return True

def enable_command(command):
    """Enable a previously disabled command"""
    disabled_commands = set()

    # Read existing disabled commands
    try:
        with open(DISABLED_COMMANDS_FILE, 'r') as f:
            for line in f:
                if line.strip():
                    disabled_commands.add(line.strip())
    except FileNotFoundError:
        return False

    # Remove command
    if command in disabled_commands:
        disabled_commands.remove(command)

        # Write back to file
        with open(DISABLED_COMMANDS_FILE, 'w') as f:
            for cmd in disabled_commands:
                f.write(f"{cmd}\n")
        return True

    return False

def get_disabled_commands():
    """Get list of all disabled commands"""
    try:
        with open(DISABLED_COMMANDS_FILE, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def get_command_offline_message(command):
    """Get a creative offline message for disabled commands"""
    messages = [
        f"🔧 **SYSTEM MAINTENANCE** 🔧\n\n⚡ *Bot Under Construction* ⚡\n\n🚫 Command `{command}` is temporarily disabled!\n🛠️ Our team is working on improvements\n\n⚙️ *Check back later* ⚙️",

        f"🚫 **COMMAND OFFLINE** 🚫\n\n💤 *Taking a Quick Nap* 💤\n\n😴 `{command}` is currently sleeping!\n⏰ Will be back soon with upgrades\n\n🌙 *Sweet dreams, command!* 🌙",

        f"⚡ **TEMPORARY OUTAGE** ⚡\n\n🔌 *Powered Down for Updates* 🔌\n\n📴 Command `{command}` is offline!\n🔄 System upgrades in progress\n\n🚀 *Coming back better than ever!* 🚀",

        f"🛑 **SERVICE INTERRUPTION** 🛑\n\n🎭 *Command on Vacation* 🎭\n\n🏖️ `{command}` is taking a break!\n☀️ Enjoying some downtime\n\n📅 *Back soon, refreshed and ready!* 📅",

        f"🔒 **COMMAND LOCKED** 🔒\n\n⚡ *Undergoing Enhancements* ⚡\n\n🚷 `{command}` is currently unavailable!\n🌟 Getting a major upgrade\n\n💎 *Good things take time!* 💎"
    ]

    return random.choice(messages)

def get_command_online_message(command):
    """Get a creative online message for re-enabled commands"""
    messages = [
        f"🎉 **COMMAND RESTORED!** 🎉\n\n⚡ *Back in Action* ⚡\n\n✅ `{command}` is now available!\n🚀 Better than ever before\n\n🌟 *Let's get to work!* 🌟",

        f"🔓 **SERVICE RESUMED** 🔓\n\n💫 *Fully Operational* 💫\n\n👍 `{command}` is back online!\n⚡ Ready to serve you\n\n🎯 *Locked and loaded!* 🎯",

        f"✅ **COMMAND ACTIVATED** ✅\n\n🚀 *Systems Go!* 🚀\n\n🌅 `{command}` is live again!\n💪 Powered up and ready\n\n⚡ *Let the magic happen!* ⚡",

        f"🎊 **WELCOME BACK!** 🎊\n\n🌈 *Better Than Ever* 🌈\n\n😎 `{command}` is now enabled!\n🎯 Fully operational status\n\n🚀 *Back in business!* 🚀",

        f"⚡ **COMMAND REACTIVATED** ⚡\n\n💎 *Enhanced and Ready* 💎\n\n🚀 `{command}` is now live!\n🎯 Improved performance\n\n🌟 *Experience the upgrade!* 🌟"
    ]

    return random.choice(messages)

async def disable_command_handler(event):
    """Handle /off command to disable commands globally"""
    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 Only GOD and ADMIN users can disable commands.")
        return

    args = event.message.text.split()
    if len(args) < 2:
        disabled_commands = get_disabled_commands()
        response = (
            "🚫 **How to use /off**\n\n"
            "Disable a command globally for all users:\n\n"
            "`/off <command>`\n\n"
            "📋 **Examples:**\n"
            "`/off /gate` - Disable /gate command for everyone\n"
            "`/off /sc` - Disable /sc command for everyone\n"
            "`/off /gen` - Disable /gen command for everyone\n\n"
            "⚠️ **Note:** The command will be completely disabled until re-enabled with /on\n\n"
        )

        if disabled_commands:
            response += "📊 **Currently Disabled Commands:**\n" + "\n".join([f"• `{cmd}`" for cmd in disabled_commands])
        else:
            response += "✅ **No commands are currently disabled**"

        await event.respond(response)
        return

    command = args[1]

    # Validate command format
    if not command.startswith('/'):
        await event.respond("❌ Command must start with '/' (e.g., /gate, /sc)")
        return

    # Check if command exists in known commands
    known_commands = ['/gate', '/sc', '/sp', '/au', '/auth', '/mau', '/msc', '/gen', '/fake', '/bin', '/sk', '/status', '/redeem']
    if command not in known_commands:
        await event.respond(f"❌ Unknown command: `{command}`\n\nKnown commands: {', '.join(known_commands)}")
        return

    # Disable the command
    if disable_command(command):
        offline_message = get_command_offline_message(command)

        await event.respond(
            f"✅ **Command Disabled Successfully!**\n\n"
            f"🚫 `{command}` is now disabled for all users\n\n"
            f"⚡ Users will receive this creative message:\n\n"
            f"_{offline_message}_\n\n"
            f"🔓 Use `/on {command}` to re-enable it later."
        )
    else:
        await event.respond("❌ Failed to disable command. Please try again.")

async def enable_command_handler(event):
    """Handle /on command to enable commands globally"""
    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 Only GOD and ADMIN users can enable commands.")
        return

    args = event.message.text.split()
    if len(args) < 2:
        disabled_commands = get_disabled_commands()
        response = (
            "✅ **How to use /on**\n\n"
            "Enable a previously disabled command globally:\n\n"
            "`/on <command>`\n\n"
            "📋 **Examples:**\n"
            "`/on /gate` - Enable /gate command for everyone\n"
            "`/on /sc` - Enable /sc command for everyone\n"
            "`/on /gen` - Enable /gen command for everyone\n\n"
        )

        if disabled_commands:
            response += "📊 **Currently Disabled Commands:**\n" + "\n".join([f"• `{cmd}`" for cmd in disabled_commands])
        else:
            response += "✅ **No commands are currently disabled**"

        await event.respond(response)
        return

    command = args[1]

    # Validate command format
    if not command.startswith('/'):
        await event.respond("❌ Command must start with '/' (e.g., /gate, /sc)")
        return

    # Enable the command
    if enable_command(command):
        online_message = get_command_online_message(command)

        await event.respond(
            f"✅ **Command Enabled Successfully!**\n\n"
            f"🔓 `{command}` is now enabled for all users\n\n"
            f"⚡ Users will receive this creative message:\n\n"
            f"_{online_message}_\n\n"
            f"🎉 Command is back online!"
        )
    else:
        await event.respond(f"❌ Command `{command}` is not currently disabled or could not be enabled.")

async def show_disabled_commands(event):
    """Show all currently disabled commands"""
    user_id = event.sender_id
    user_plan = get_user_plan(user_id)

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("🚫 Only GOD and ADMIN users can view disabled commands.")
        return

    disabled_commands = get_disabled_commands()

    if disabled_commands:
        response = "🚫 **Currently Disabled Commands**\n\n"
        for cmd in disabled_commands:
            response += f"• `{cmd}`\n"

        response += "\n🔓 Use `/on <command>` to enable any command"

        buttons = [
            [Button.inline("🔄 Refresh List", b"refresh_disabled_commands")],
            [Button.inline("🔙 Back to Admin", b"admin_commands")]
        ]

        await event.respond(response, buttons=buttons)
    else:
        response = "✅ **No commands are currently disabled**\n\n⚡ All commands are available for use."
        await event.respond(response)

# Callback handler for refresh button
async def handle_refresh_disabled_commands(event):
    """Handle refresh button for disabled commands list"""
    await show_disabled_commands(event)