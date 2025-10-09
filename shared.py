# shared.py (fully updated with strict FREE plan enforcement)

import os
import inspect
from datetime import datetime, timedelta
import requests
import threading

# User sessions dictionary with thread safety
user_sessions = {}
session_lock = threading.Lock()

# User cooldown tracking
user_cooldowns = {}
cooldown_lock = threading.Lock()

def get_user_session(user_id):
    """Thread-safe user session management"""
    with session_lock:
        if user_id not in user_sessions:
            user_sessions[user_id] = requests.Session()
        return user_sessions[user_id]

# User plans and limits
PLANS = {
    "FREE": {
        "personal_limit": 3,           # Max 3 uses in private messages (all commands)
        "gate_usage_limit": 20,        # Max 20 gate checks in groups
        "description": "3 personal uses, unlimited tools in groups, 20 gate checks",
        "cooldown": 25                 # 25 second cooldown between gate checks
    },
    "PLUS": {
        "limit": 50,
        "description": "50 CCs total",
        "cooldown": 5
    },
    "ADMIN": {
        "limit": 500,
        "description": "500 CCs total",
        "cooldown": 0
    },
    "GOD": {
        "limit": float('inf'),
        "description": "Unlimited access",
        "cooldown": 0
    }
}

# Folder to store user plan files
USERS_FOLDER = "users"
os.makedirs(USERS_FOLDER, exist_ok=True)

# File paths for user plans
PLAN_FILES = {
    "FREE": os.path.join(USERS_FOLDER, "FREE.txt"),
    "PLUS": os.path.join(USERS_FOLDER, "PLUS.txt"),
    "ADMIN": os.path.join(USERS_FOLDER, "ADMIN.txt"),
    "GOD": os.path.join(USERS_FOLDER, "GOD.txt")
}

# Other data files
BANBIN_FILE = "BANBIN.txt"
GC_FILE = "GC.txt"
BANNEDU_FILE = os.path.join(USERS_FOLDER, "BANNEDU.txt")
AUTHORIZED_GROUPS_FILE = os.path.join(USERS_FOLDER, "AUTHORIZED_GROUPS.txt")
PERSONAL_USAGE_FILE = os.path.join(USERS_FOLDER, "PERSONAL_USAGE.txt")
GATE_USAGE_FILE = os.path.join(USERS_FOLDER, "GATE_USAGE.txt")

# Initialize files if they don't exist
for file in [BANNEDU_FILE, AUTHORIZED_GROUPS_FILE, PERSONAL_USAGE_FILE, GATE_USAGE_FILE]:
    if not os.path.exists(file):
        open(file, 'a').close()

def increment_personal_usage(user_id):
    """Increment personal usage count for FREE users in private chats"""
    counts = {}
    try:
        with open(PERSONAL_USAGE_FILE, 'r') as f:
            for line in f:
                if ':' in line:
                    uid, count = line.strip().split(':')
                    counts[uid] = int(count)
    except FileNotFoundError:
        pass

    counts[str(user_id)] = counts.get(str(user_id), 0) + 1

    with open(PERSONAL_USAGE_FILE, 'w') as f:
        for uid, count in counts.items():
            f.write(f"{uid}:{count}\n")

    return counts[str(user_id)]

def get_personal_usage_count(user_id):
    """Get personal usage count for FREE users"""
    try:
        with open(PERSONAL_USAGE_FILE, 'r') as f:
            for line in f:
                if ':' in line:
                    uid, count = line.strip().split(':')
                    if uid == str(user_id):
                        return int(count)
    except FileNotFoundError:
        pass
    return 0

def increment_gate_usage(user_id):
    """Increment gate usage count for FREE users in groups"""
    counts = {}
    try:
        with open(GATE_USAGE_FILE, 'r') as f:
            for line in f:
                if ':' in line:
                    uid, count = line.strip().split(':')
                    counts[uid] = int(count)
    except FileNotFoundError:
        pass

    counts[str(user_id)] = counts.get(str(user_id), 0) + 1

    with open(GATE_USAGE_FILE, 'w') as f:
        for uid, count in counts.items():
            f.write(f"{uid}:{count}\n")

    return counts[str(user_id)]

def get_gate_usage_count(user_id):
    """Get gate usage count for FREE users in groups"""
    try:
        with open(GATE_USAGE_FILE, 'r') as f:
            for line in f:
                if ':' in line:
                    uid, count = line.strip().split(':')
                    if uid == str(user_id):
                        return int(count)
    except FileNotFoundError:
        pass
    return 0

def get_user_plan(user_id):
    """Get the highest plan a user is subscribed to"""
    user_plan = "FREE"
    for plan, file_name in PLAN_FILES.items():
        if os.path.exists(file_name):
            with open(file_name, 'r') as f:
                if str(user_id) in f.read().splitlines():
                    if PLANS.get(plan, {}).get("limit", 0) > PLANS.get(user_plan, {}).get("limit", 0):
                        user_plan = plan
    return user_plan

def is_user_registered(user_id):
    """Check if user is registered in any plan"""
    for plan, file_name in PLAN_FILES.items():
        if os.path.exists(file_name):
            with open(file_name, 'r') as f:
                if str(user_id) in f.read().splitlines():
                    return True
    return False

def register_user(user_id):
    """Register a new FREE user"""
    if is_user_registered(user_id):
        return False

    with open(PLAN_FILES["FREE"], 'a') as f:
        f.write(f"{user_id}\n")
    return True

def is_user_banned(user_id):
    """Check if user is banned"""
    try:
        with open(BANNEDU_FILE, 'r') as f:
            return str(user_id) in f.read().splitlines()
    except FileNotFoundError:
        return False

def is_user_in_cooldown(user_id, is_group=False):
    """Check if user is in cooldown period"""
    user_plan = get_user_plan(user_id)
    if user_plan in ["GOD", "ADMIN"]:
        return False

    current_time = datetime.now()
    with cooldown_lock:
        last_check_time = user_cooldowns.get(user_id)

    if last_check_time:
        cooldown_seconds = PLANS[user_plan]["cooldown"]
        return current_time - last_check_time < timedelta(seconds=cooldown_seconds)
    return False

def update_user_cooldown(user_id):
    """Update user's last command timestamp"""
    with cooldown_lock:
        user_cooldowns[user_id] = datetime.now()

def upgrade_user(user_id, plan):
    """Upgrade user to specified plan"""
    if plan not in PLAN_FILES:
        return False

    # Remove from all plans
    for file_name in PLAN_FILES.values():
        if os.path.exists(file_name):
            with open(file_name, 'r') as f:
                lines = f.readlines()
            with open(file_name, 'w') as f:
                for line in lines:
                    if line.strip() != str(user_id):
                        f.write(line)

    # Add to new plan
    with open(PLAN_FILES[plan], 'a') as f:
        f.write(f"{user_id}\n")
    return True

def is_group_authorized(group_id):
    """Check if group is authorized"""
    try:
        with open(AUTHORIZED_GROUPS_FILE, 'r') as f:
            return str(group_id) in f.read().splitlines()
    except FileNotFoundError:
        return False

def authorize_group(group_id):
    """Authorize a group to use the bot"""
    if is_group_authorized(group_id):
        return False

    with open(AUTHORIZED_GROUPS_FILE, 'a') as f:
        f.write(f"{group_id}\n")
    return True

def deauthorize_group(group_id):
    """Deauthorize a group"""
    if not os.path.exists(AUTHORIZED_GROUPS_FILE):
        return False

    with open(AUTHORIZED_GROUPS_FILE, 'r') as f:
        groups = f.read().splitlines()

    if str(group_id) not in groups:
        return False

    with open(AUTHORIZED_GROUPS_FILE, 'w') as f:
        for g in groups:
            if g != str(group_id):
                f.write(f"{g}\n")
    return True

def can_user_use_command(user_id, is_group=False, is_gate_command=False):
    """Check if user can use a command with current limits"""
    if not is_user_registered(user_id):
        return False, "⚠️ You need to register first! Use /register command."

    if is_user_banned(user_id):
        return False, "⛔️ You have been banned from using this bot."

    user_plan = get_user_plan(user_id)

    # Always allow redeem command
    if is_gate_command and "redeem" in inspect.stack()[1].function:
        return True, ""

    # FREE user restrictions
    if user_plan == "FREE":
        # Private message limit (3 total uses) - exclude redeem command
        if not is_group and not ("redeem" in inspect.stack()[1].function):
            usage_count = get_personal_usage_count(user_id)
            if usage_count >= PLANS["FREE"]["personal_limit"]:
                return False, (
                    f"⚠️ You've reached your FREE plan limit ({PLANS['FREE']['personal_limit']} personal uses).\n"
                    "Upgrade to PLUS for unlimited access or use in authorized groups."
                )

        # Group gate command limit (20 checks)
        if is_group and is_gate_command:
            gate_usage = get_gate_usage_count(user_id)
            if gate_usage >= PLANS["FREE"]["gate_usage_limit"]:
                return False, (
                    f"⚠️ You've reached your group gate check limit ({PLANS['FREE']['gate_usage_limit']}).\n"
                    "Upgrade to PLUS for higher limits."
                )

    # Cooldown check for gate commands (exclude redeem)
    # Only check cooldown if user has previously used commands and is not a premium user
    if (is_gate_command and not ("redeem" in inspect.stack()[1].function) and
        user_id in user_cooldowns and is_user_in_cooldown(user_id, is_group)):
        cooldown = PLANS[user_plan]["cooldown"]
        remaining = (user_cooldowns[user_id] + timedelta(seconds=cooldown)) - datetime.now()
        return False, f"⏳ Please wait {int(remaining.total_seconds())} seconds before next gate check."

    return True, ""
