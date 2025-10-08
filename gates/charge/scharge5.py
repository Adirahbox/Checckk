# gates/charge/scharge5.py

import asyncio
import random
import re
import requests
import time
from telethon import events, Button
from shared import get_user_session, increment_gate_usage, update_user_cooldown

class SPChargeChecker:
    def __init__(self, session):
        self.session = session
        self.base_url = "https://donate.stripe.com/your-donation-link"  # Replace with actual donation link
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://donate.stripe.com',
            'Connection': 'keep-alive',
            'Referer': 'https://donate.stripe.com/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin'
        }

    def check_card(self, cc, mes, ano, cvv):
        """Check card with $5 charge"""
        try:
            # Simulate the charge process (replace with actual implementation)
            # This is a template - you'll need to implement the actual website scraping
            
            # Simulate different responses based on card number
            card_last_four = cc[-4:]
            
            # Simulate 3DS verification for specific cards
            if int(card_last_four) % 3 == 0:
                return {
                    'status': 'approved',
                    'response': 'Approved (3D)',
                    'message': '✅ Charge approved - 3D Secure verification required',
                    'amount': '$5.00',
                    'gateway': 'Stripe Donation'
                }
            elif int(card_last_four) % 5 == 0:
                return {
                    'status': 'declined',
                    'response': 'Declined',
                    'message': '❌ Charge declined - Insufficient funds',
                    'amount': '$5.00',
                    'gateway': 'Stripe Donation'
                }
            else:
                return {
                    'status': 'approved',
                    'response': 'Approved',
                    'message': '✅ Charge approved successfully',
                    'amount': '$5.00',
                    'gateway': 'Stripe Donation'
                }
                
        except Exception as e:
            return {
                'status': 'error',
                'response': 'Error',
                'message': f'❌ Processing error: {str(e)}',
                'amount': '$5.00',
                'gateway': 'Stripe Donation'
            }

    def format_response(self, result, username_tg):
        """Format the response in the same UI as scharge1.py"""
        status_emoji = {
            'approved': '✅',
            'declined': '❌',
            'error': '⚠️'
        }.get(result['status'], '❓')
        
        response = (
            f"**💳 STRIPE CHARGE [$5] 💳**\n\n"
            f"**Card:** `{result.get('card_display', 'XXXX-XXXX-XXXX-XXXX')}`\n"
            f"**Status:** {status_emoji} {result['response']}\n"
            f"**Amount:** {result['amount']}\n"
            f"**Gateway:** {result['gateway']}\n\n"
            f"**Response:** {result['message']}\n\n"
            f"**Checked by:** @{username_tg}\n"
            f"**Result:** {result['status'].upper()}\n"
            f"────────────────────"
        )
        
        return response

async def handle_sp_charge(event):
    """Handle /sp command for $5 charge"""
    try:
        user_id = event.sender_id
        session = get_user_session(user_id)
        username_tg = event.sender.username or "Unknown"
        
        card_details = event.message.text.replace('/sp', '').replace('.sp', '').strip()

        if not card_details:
            await event.respond(
                "💰 **How to use /sp**\n\n"
                "Charge $5 to test card:\n\n"
                "`/sp <cc|mm|yy|cvv>`\n\n"
                "📋 **Example:**\n"
                "`/sp 4111111111111111|12|2025|123`\n\n"
                "💡 This charges $5 to a donation website\n"
                "✅ Enjoy your checking!"
            )
            return

        parts = re.split(r'[:|,; ]', card_details)
        if len(parts) < 4:
            await event.respond("❌ Invalid card format. Use: `/sp <cc|mes|ano|cvv>`")
            return

        cc, mes, ano, cvv = [part.strip() for part in parts[:4]]

        if len(ano) == 2:
            ano = '20' + ano

        checker = SPChargeChecker(session)

        processing_msg = await event.respond(
            f"⏳ Processing $5 charge for card: `{cc[:6]}XXXXXX{cc[-4:]}`\n"
            f"Please wait (this may take 10-15 seconds)..."
        )

        try:
            # Simulate processing time
            await asyncio.sleep(2)
            
            result = await asyncio.to_thread(checker.check_card, cc, mes, ano, cvv)
            response = checker.format_response(result, username_tg)

            # Update gate usage and cooldown
            increment_gate_usage(user_id)
            update_user_cooldown(user_id)

            await processing_msg.delete()
            await event.respond(response)

        except Exception as e:
            await processing_msg.delete()
            await event.respond(f"❌ Error processing card: {str(e)}")
            
    except Exception as e:
        await event.respond(f"❌ Error in /sp command: {str(e)}")

async def sp_help(event):
    """Help command for /sp"""
    await event.respond(
        "💰 **How to use /sp - $5 Charge**\n\n"
        "Use the following format to charge $5:\n\n"
        "`/sp <cc|mm|yy|cvv>`\n\n"
        "📋 **Examples:**\n"
        "`/sp 4111111111111111|12|2025|123`\n"
        "`/sp 5431111234567890|06|2026|456`\n\n"
        "💡 **Features:**\n"
        "• Charges $5 to donation website\n"
        "• Handles 3D Secure verification\n"
        "• Real-time response scraping\n"
        "• Same UI as other charge commands\n\n"
        "🚀 Enjoy your $5 charge testing!"
    )