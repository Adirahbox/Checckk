# masscharge.py - Mass Stripe Charge Handler for /msc command

import asyncio
import json
import re
import time
import httpx
import os
from datetime import datetime
from telethon import Button, types
from shared import (
    PLANS, get_user_plan, is_user_banned,
    get_user_session, increment_gate_usage,
    can_user_use_command, update_user_cooldown,
    get_gate_usage_count, PLAN_FILES
)
from gates.charge.scharge import StripeChargeChecker

class MassStripeCharge:
    def __init__(self):
        self.max_limits = {
            "GOD": 100,
            "ADMIN": 100,
            "PLUS": 50,
            "FREE": 25
        }

        self.usage_limits = {
            "FREE": {"single": 10, "mass": 5},
            "PLUS": {"single": 50, "mass": 20},
            "ADMIN": {"single": 100, "mass": 50},
            "GOD": {"single": 999, "mass": 999}
        }
        self.active_checks = {}
        self.user_stop_flags = {}

    def get_user_limits(self, user_plan):
        return self.max_limits.get(user_plan, 25)

    def get_usage_limits(self, user_plan):
        return self.usage_limits.get(user_plan, {"single": 10, "mass": 5})

    async def validate_file(self, file_path, user_plan):
        """Validate the uploaded file and return CC list or error"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # Split lines and filter valid CC formats
            lines = content.splitlines()
            ccs = []
            for line in lines:
                line = line.strip()
                if line and '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 4:
                        cc = parts[0].strip()
                        mes = parts[1].strip()
                        ano = parts[2].strip()
                        cvv = parts[3].strip()
                        # Basic validation
                        if (cc.isdigit() and len(cc) >= 15 and len(cc) <= 16 and
                            mes.isdigit() and len(mes) in [1, 2] and
                            ano.isdigit() and len(ano) in [2, 4] and
                            cvv.isdigit() and len(cvv) in [3, 4]):
                            ccs.append(line)

            max_allowed = self.get_user_limits(user_plan)
            if len(ccs) > max_allowed:
                return None, f"❌ Too many cards! Maximum allowed: {max_allowed} for {user_plan} plan"

            if not ccs:
                return None, "❌ No valid credit card formats found in file. Format: cc|mm|yy|cvv"

            return ccs, None

        except Exception as e:
            return None, f"❌ Error reading file: {str(e)}"

    async def update_progress(self, event, msg_id, checked, hits, declines, errors, total, username, user_plan):
        """Update the progress message"""
        progress = f"""
🔄 **Mass Stripe Check in Progress**

👤 User: @{username}
💎 Plan: {user_plan}
📊 Checked: {checked}/{total}
✅ Hits: {hits}
❌ Declines: {declines}
⚠️ Errors: {errors}
⏳ Left: {total - checked}

⚡ Processing... Please wait
"""
        try:
            await event.client.edit_message(event.chat_id, msg_id, progress)
        except:
            pass

    async def process_mass_charge(self, event, ccs, username, user_plan):
        """Process mass charge with detailed results"""
        user_id = event.sender_id
        checker = StripeChargeChecker(get_user_session(user_id))

        # Initialize counters
        checked = 0
        hits = 0
        declines = 0
        errors = 0
        total = len(ccs)

        # Initialize stop flag
        self.user_stop_flags[user_id] = False

        # Send initial progress message (ONLY ONE MESSAGE)
        processing_msg = await event.respond(f"""
🔄 **Mass Stripe Check in Progress**

👤 User: @{username}
💎 Plan: {user_plan}
📊 Checked: 0/{total}
✅ Hits: 0
❌ Declines: 0
⚠️ Errors: 0
⏳ Left: {total}

⚡ Processing... Please wait
""")
        msg_id = processing_msg.id
        self.active_checks[msg_id] = {
            'start_time': time.time(),
            'last_update': 0,
            'user_id': user_id
        }

        hit_results = []  # ONLY STORE HITS

        # Process cards one by one with delay
        for idx, cc_line in enumerate(ccs, 1):
            # Check if user requested stop
            if self.user_stop_flags.get(user_id, False):
                await event.respond(f"🛑 Mass check stopped by user after {checked} cards")
                break

            try:
                # Process single card with 2 second delay between checks
                if idx > 1:
                    await asyncio.sleep(2)

                result = await checker.check_card(cc_line, username, user_plan)
                checked += 1

                if "APPROVED" in result:
                    hits += 1
                    hit_results.append(f"✅ HIT: {cc_line}")  # ONLY ADD HITS
                    # Send instant hit notification
                    await event.respond(f"""
🎉 **Instant Hit Notification**

{result}

📊 Progress: {checked}/{total} cards
""")
                elif "DECLINED" in result:
                    declines += 1
                    # DON'T add to results - we only care about hits
                else:
                    errors += 1
                    # DON'T add to results - we only care about hits

                # Update progress every card
                await self.update_progress(event, msg_id, checked, hits, declines, errors, total, username, user_plan)

            except Exception as e:
                errors += 1
                # DON'T add to results - we only care about hits
                continue

        # Generate final report if not stopped
        if not self.user_stop_flags.get(user_id, False):
            report = await self.generate_report(hits, declines, errors, username, user_plan, total, hit_results)

            # Update usage
            increment_gate_usage(user_id)
            update_user_cooldown(user_id)

            # Send results
            await event.respond(report)

        # Clean up
        if user_id in self.user_stop_flags:
            del self.user_stop_flags[user_id]
        if msg_id in self.active_checks:
            del self.active_checks[msg_id]
        try:
            await processing_msg.delete()
        except:
            pass

    async def generate_report(self, hits, declines, errors, username, user_plan, total, hit_results):
        """Generate final completion report"""
        report = f"""
🔄 **Mass Stripe Check Completed**

📊 Checked: {total}/{total}
✅ Hits: {hits}
❌ Declines: {declines}
⚠️ Errors: {errors}
⏳ Left: 0
"""

        # Add hits list only if hits are found
        if hit_results:
            report += "\n"
            for i, hit in enumerate(hit_results, 1):
                report += f"{i}. {hit}\n"

        return report

    async def handle_msc_command(self, event):
        """Main handler for /msc command - ONLY called when it's a reply"""
        user_id = event.sender_id

        if is_user_banned(user_id):
            await event.respond("⛔ You have been banned from using this bot.")
            return

        user_plan = get_user_plan(user_id)
        username = event.sender.username or str(user_id)

        # Get the replied message
        replied_msg = await event.get_reply_message()

        if not replied_msg:
            await event.respond("❌ Could not get the replied message. Please try again.")
            return

        # Check authorization for FREE users
        if user_plan == "FREE" and event.is_private:
            await event.respond(
                "🚫 **FREE users must use groups!**\n\n"
                "Join an authorized group to use mass commands.\n"
                "💎 Upgrade to PLUS for private access!"
            )
            return

        # Check usage limits
        usage_limits = self.get_usage_limits(user_plan)
        gate_usage = get_gate_usage_count(user_id)

        if gate_usage >= usage_limits['mass']:
            await event.respond(
                f"📊 **Limit Reached!**\n\n"
                f"Used: {gate_usage}/{usage_limits['mass']} mass checks\n"
                "⏳ Reset: Next cooldown period\n"
                "💎 Upgrade for more checks!"
            )
            return

        # Check cooldown
        can_use, reason = can_user_use_command(user_id, event.is_group, is_gate_command=True)
        if not can_use:
            await event.respond(f"⏳ {reason}")
            return

        # Download and process file
        file_path = None
        try:
            # Try to download the replied message as file
            file_path = await replied_msg.download_media()

            if not file_path or not os.path.exists(file_path):
                # If no file found, check if it's a text message with CCs
                if replied_msg.text:
                    file_path = f"temp_cc_{user_id}_{int(time.time())}.txt"
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(replied_msg.text)
                else:
                    await event.respond("❌ The replied message doesn't contain a file or CC text. Please reply to a text file with CCs.")
                    return

            # Validate file and extract CCs
            ccs, error = await self.validate_file(file_path, user_plan)

            if error:
                await event.respond(error)
                return

            # Process the cards directly without extra starting message
            await self.process_mass_charge(event, ccs, username, user_plan)

        except Exception as e:
            await event.respond(f"❌ Error processing mass charge: {str(e)}")
            print(f"ERROR in handle_msc_command: {str(e)}")
        finally:
            # Clean up downloaded file
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass

# Global instance
mass_charge_handler = MassStripeCharge()

async def handle_mass_stripe_charge(event):
    await mass_charge_handler.handle_msc_command(event)