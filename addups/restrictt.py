# addups/restrictt.py

import os
import json

RESTRICTED_USERS_FILE = "users/RESTRICTED.txt"

def ensure_file_exists():
    """Ensure the restricted users file exists"""
    os.makedirs("users", exist_ok=True)
    if not os.path.exists(RESTRICTED_USERS_FILE):
        with open(RESTRICTED_USERS_FILE, 'w') as f:
            f.write("")

def is_user_restricted(user_id):
    """Check if a user is restricted from using commands"""
    ensure_file_exists()
    try:
        with open(RESTRICTED_USERS_FILE, 'r') as f:
            restricted_users = [line.strip() for line in f if line.strip()]
            return str(user_id) in restricted_users
    except:
        return False

def restrict_user(user_id):
    """Restrict a user from using commands"""
    ensure_file_exists()
    if not is_user_restricted(user_id):
        with open(RESTRICTED_USERS_FILE, 'a') as f:
            f.write(f"{user_id}\n")
        return True
    return False

def unrestrict_user(user_id):
    """Remove restriction from a user"""
    ensure_file_exists()
    try:
        with open(RESTRICTED_USERS_FILE, 'r') as f:
            restricted_users = [line.strip() for line in f if line.strip()]
        
        if str(user_id) in restricted_users:
            restricted_users.remove(str(user_id))
            with open(RESTRICTED_USERS_FILE, 'w') as f:
                for uid in restricted_users:
                    f.write(f"{uid}\n")
            return True
        return False
    except:
        return False

async def restrict_user_command(event):
    """Command handler to restrict a user"""
    try:
        if event.sender_id not in [int(line.strip()) for line in open("users/ADMIN.txt") if line.strip()]:
            await event.respond("❌ You don't have permission to use this command.")
            return
        
        args = event.message.text.split()
        if len(args) < 2:
            await event.respond("❌ Usage: `/restrict <user_id>`")
            return
        
        target_user_id = args[1].strip()
        if not target_user_id.isdigit():
            await event.respond("❌ Invalid user ID. Must be numeric.")
            return
        
        if restrict_user(target_user_id):
            await event.respond(f"✅ User {target_user_id} has been restricted from using commands.")
        else:
            await event.respond(f"⚠️ User {target_user_id} is already restricted.")
    except Exception as e:
        await event.respond(f"❌ Error: {str(e)}")

async def unrestrict_user_command(event):
    """Command handler to unrestrict a user"""
    try:
        if event.sender_id not in [int(line.strip()) for line in open("users/ADMIN.txt") if line.strip()]:
            await event.respond("❌ You don't have permission to use this command.")
            return
        
        args = event.message.text.split()
        if len(args) < 2:
            await event.respond("❌ Usage: `/unrestrict <user_id>`")
            return
        
        target_user_id = args[1].strip()
        if not target_user_id.isdigit():
            await event.respond("❌ Invalid user ID. Must be numeric.")
            return
        
        if unrestrict_user(target_user_id):
            await event.respond(f"✅ User {target_user_id} has been unrestricted.")
        else:
            await event.respond(f"⚠️ User {target_user_id} was not restricted.")
    except Exception as e:
        await event.respond(f"❌ Error: {str(e)}")
