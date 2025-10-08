# tooling.py

import datetime
import asyncio
import os
import stripe
import requests
import random
import logging
import cloudscraper
import time
import ssl
import socket
from telethon import events, Button
from shared import (
    is_group_authorized, get_user_plan, authorize_group,
    is_user_banned, is_user_registered, can_user_use_command,
    increment_personal_usage, PLAN_FILES, GC_FILE,
    PLANS, upgrade_user
)
from bs4 import BeautifulSoup
import re
from faker import Faker
from urllib.parse import urlparse, urlunparse, urljoin
import json
import urllib.parse
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Initialize logging
logger = logging.getLogger(__name__)

# Global thread pool for concurrent requests
gate_thread_pool = ThreadPoolExecutor(max_workers=20)

def get_message_text(event):
    """Helper function to get text from both message events and callback queries"""
    if hasattr(event, 'message') and hasattr(event.message, 'text'):
        return event.message.text
    elif hasattr(event, 'text'):
        return event.text
    elif hasattr(event, 'data') and event.data:
        if isinstance(event.data, bytes):
            return event.data.decode()
        return str(event.data)
    return ''

def luhn_checksum(card_number):
    def digits_of(n):
        return [int(d) for d in str(n)]
    digits = digits_of(card_number)
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    checksum = sum(odd_digits)
    for d in even_digits:
        checksum += sum(digits_of(d * 2))
    return checksum % 10

def generate_luhn_compliant_cc(bin):
    cc_number = bin + ''.join(random.choices("0123456789", k=15 - len(bin)))
    check_digit = (10 - luhn_checksum(cc_number + '0')) % 10
    return cc_number + str(check_digit)

def replace_x_with_digits(input_str):
    result = []
    for char in input_str:
        if char == 'x':
            result.append(random.choice("0123456789"))
        else:
            result.append(char)
    return ''.join(result)

def fetch_bin_details(bin):
    url = f"https://binlist.io/lookup/{bin}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        bin_data = response.json()
        return bin_data
    except Exception as e:
        return None

COUNTRY_NAME_TO_CODE = {
    "united states": "en_US",
    "usa": "en_US", 
    "us": "en_US",
    "canada": "en_CA",
    "ca": "en_CA",
    "united kingdom": "en_GB",
    "uk": "en_GB",
    "gb": "en_GB",
    "germany": "de_DE",
    "de": "de_DE",
    "france": "fr_FR",
    "fr": "fr_FR",
    "italy": "it_IT",
    "it": "it_IT",
    "spain": "es_ES",
    "es": "es_ES",
    "australia": "en_AU",
    "au": "en_AU",
    "japan": "ja_JP",
    "jp": "ja_JP",
    "china": "zh_CN",
    "cn": "zh_CN",
    "india": "en_IN",
    "in": "en_IN",
    "brazil": "pt_BR",
    "br": "pt_BR",
    "mexico": "es_MX",
    "mx": "es_MX"
}

CODE_TO_COUNTRY_NAME = {
    "en_US": "United States",
    "en_CA": "Canada",
    "en_GB": "United Kingdom",
    "de_DE": "Germany",
    "fr_FR": "France",
    "it_IT": "Italy",
    "es_ES": "Spain",
    "en_AU": "Australia",
    "ja_JP": "Japan",
    "zh_CN": "China",
    "en_IN": "India",
    "pt_BR": "Brazil",
    "es_MX": "Mexico"
}

def get_country_code(country_input):
    country_input = country_input.lower()
    if country_input in COUNTRY_NAME_TO_CODE:
        return COUNTRY_NAME_TO_CODE[country_input]
    elif country_input in CODE_TO_COUNTRY_NAME:
        return country_input
    else:
        return None

def get_country_name(country_code):
    return CODE_TO_COUNTRY_NAME.get(country_code, "Unknown")

def parse_country_input(input_str):
    match = re.match(r"^\s*(\w+)\s*(?:\(([^)]+)\))?\s*$", input_str, re.IGNORECASE)
    if match:
        code_or_name = match.group(1).strip()
        full_name = match.group(2).strip() if match.group(2) else None
        return code_or_name, full_name
    return None, None

def fetch_fake_address(country_code):
    try:
        fake = Faker(country_code)
        name = fake.name()

        # Enhanced address generation with proper city-state-postcode matching
        country_configs = {
            'en_US': {
                'street_format': lambda: f"{random.randint(100, 9999)} {random.choice(['Main', 'Oak', 'Pine', 'Elm', 'Maple', 'Cedar', 'Washington', 'Lincoln', 'Park', 'First'])} {random.choice(['St', 'Ave', 'Blvd', 'Dr', 'Rd', 'Ln'])}",
                'state_city_postcode': lambda: random.choice([
                    ('CA', 'Los Angeles', '90001'), ('CA', 'San Francisco', '94102'), ('CA', 'San Diego', '92101'),
                    ('NY', 'New York', '10001'), ('NY', 'Buffalo', '14201'), ('NY', 'Rochester', '14602'),
                    ('TX', 'Houston', '77001'), ('TX', 'Dallas', '75201'), ('TX', 'Austin', '73301'),
                    ('FL', 'Miami', '33101'), ('FL', 'Orlando', '32801'), ('FL', 'Tampa', '33601'),
                    ('IL', 'Chicago', '60601'), ('IL', 'Springfield', '62701'), ('IL', 'Peoria', '61601'),
                    ('PA', 'Philadelphia', '19101'), ('PA', 'Pittsburgh', '15201'), ('PA', 'Harrisburg', '17101'),
                    ('OH', 'Columbus', '43201'), ('OH', 'Cleveland', '44101'), ('OH', 'Cincinnati', '45201'),
                    ('GA', 'Atlanta', '30301'), ('GA', 'Savannah', '31401'), ('GA', 'Augusta', '30901'),
                    ('NC', 'Charlotte', '28201'), ('NC', 'Raleigh', '27601'), ('NC', 'Greensboro', '27401'),
                    ('MI', 'Detroit', '48201'), ('MI', 'Grand Rapids', '49501'), ('MI', 'Lansing', '48901')
                ]),
                'phone': lambda: f"+1 ({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"
            },
            'en_GB': {
                'street_format': lambda: f"{random.randint(1, 999)} {random.choice(['High', 'Station', 'Church', 'Victoria', 'King', 'Queen', 'London', 'Park'])} {random.choice(['Street', 'Road', 'Lane', 'Avenue', 'Close', 'Drive'])}",
                'state_city_postcode': lambda: random.choice([
                    ('England', 'London', 'SW1A 1AA'), ('England', 'Manchester', 'M1 1AA'), ('England', 'Birmingham', 'B1 1AA'),
                    ('England', 'Liverpool', 'L1 1AA'), ('England', 'Leeds', 'LS1 1AA'), ('England', 'Sheffield', 'S1 1AA'),
                    ('Scotland', 'Edinburgh', 'EH1 1AA'), ('Scotland', 'Glasgow', 'G1 1AA'), ('Scotland', 'Aberdeen', 'AB1 1AA'),
                    ('Wales', 'Cardiff', 'CF10 1AA'), ('Wales', 'Swansea', 'SA1 1AA'), ('Wales', 'Newport', 'NP10 1AA'),
                    ('Northern Ireland', 'Belfast', 'BT1 1AA'), ('Northern Ireland', 'Derry', 'BT48 1AA')
                ]),
                'phone': lambda: f"+44 {random.randint(1, 9)} {random.randint(10, 99)} {random.randint(10, 99)} {random.randint(10, 99)}"
            },
            'en_CA': {
                'street_format': lambda: f"{random.randint(100, 9999)} {random.choice(['Main', 'King', 'Queen', 'Yonge', 'Bay', 'College', 'Dundas', 'Bloor'])} {random.choice(['St', 'Ave', 'Rd', 'Blvd', 'Dr'])}",
                'state_city_postcode': lambda: random.choice([
                    ('ON', 'Toronto', 'M5A 1A1'), ('ON', 'Ottawa', 'K1A 0A1'), ('ON', 'Hamilton', 'L8P 1A1'),
                    ('QC', 'Montreal', 'H2X 1A1'), ('QC', 'Quebec City', 'G1R 1A1'), ('QC', 'Laval', 'H7X 1A1'),
                    ('BC', 'Vancouver', 'V6A 1A1'), ('BC', 'Victoria', 'V8W 1A1'), ('BC', 'Surrey', 'V3R 1A1'),
                    ('AB', 'Calgary', 'T2P 1A1'), ('AB', 'Edmonton', 'T5J 1A1'), ('AB', 'Red Deer', 'T4N 1A1'),
                    ('MB', 'Winnipeg', 'R3C 1A1'), ('MB', 'Brandon', 'R7A 1A1')
                ]),
                'phone': lambda: f"+1 ({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"
            },
            'de_DE': {
                'street_format': lambda: f"{random.choice(['Hauptstraße', 'Berliner Straße', 'Münchner Straße', 'Frankfurter Allee', 'Hamburger Straße', 'Kölner Straße'])} {random.randint(1, 999)}",
                'state_city_postcode': lambda: random.choice([
                    ('Berlin', 'Berlin', '10115'), ('Hamburg', 'Hamburg', '20095'), ('Bavaria', 'Munich', '80331'),
                    ('Bavaria', 'Nuremberg', '90402'), ('North Rhine-Westphalia', 'Cologne', '50667'),
                    ('North Rhine-Westphalia', 'Düsseldorf', '40213'), ('Hesse', 'Frankfurt', '60311'),
                    ('Hesse', 'Wiesbaden', '65183'), ('Baden-Württemberg', 'Stuttgart', '70173'),
                    ('Baden-Württemberg', 'Karlsruhe', '76131'), ('Lower Saxony', 'Hanover', '30159')
                ]),
                'phone': lambda: f"+49 {random.randint(30, 89)} {random.randint(1000000, 9999999)}"
            },
            'fr_FR': {
                'street_format': lambda: f"{random.randint(1, 999)} {random.choice(['Rue', 'Avenida', 'Boulevard', 'Impasse', 'Place', 'Quai'])} {random.choice(['de la République', 'Victor Hugo', 'Jean Jaurès', 'de Gaulle', 'Pasteur', 'Gambetta'])}",
                'state_city_postcode': lambda: random.choice([
                    ('Île-de-France', 'Paris', '75001'), ('Île-de-France', 'Versailles', '78000'),
                    ('Provence-Alpes-Côte d\'Azur', 'Marseille', '13001'), ('Provence-Alpes-Côte d\'Azur', 'Nice', '06000'),
                    ('Auvergne-Rhône-Alpes', 'Lyon', '69001'), ('Auvergne-Rhône-Alpes', 'Grenoble', '38000'),
                    ('Occitanie', 'Toulouse', '31000'), ('Occitanie', 'Montpellier', '34000'),
                    ('Nouvelle-Aquitaine', 'Bordeaux', '33000'), ('Nouvelle-Aquitaine', 'Limoges', '87000')
                ]),
                'phone': lambda: f"+33 {random.randint(1, 9)} {random.randint(10, 99)} {random.randint(10, 99)} {random.randint(10, 99)}"
            },
            'it_IT': {
                'street_format': lambda: f"{random.choice(['Via', 'Viale', 'Corso', 'Piazza'])} {random.choice(['Roma', 'Milano', 'Napoli', 'Firenze', 'Venezia', 'Torino'])} {random.randint(1, 999)}",
                'state_city_postcode': lambda: random.choice([
                    ('Lazio', 'Rome', '00100'), ('Lombardy', 'Milan', '20100'), ('Campania', 'Naples', '80100'),
                    ('Tuscany', 'Florence', '50100'), ('Veneto', 'Venice', '30100'), ('Piedmont', 'Turin', '10100'),
                    ('Emilia-Romagna', 'Bologna', '40100'), ('Sicily', 'Palermo', '90100')
                ]),
                'phone': lambda: f"+39 {random.randint(300, 399)} {random.randint(1000000, 9999999)}"
            },
            'es_ES': {
                'street_format': lambda: f"{random.choice(['Calle', 'Avenida', 'Plaza', 'Paseo'])} {random.choice(['Mayor', 'Real', 'San Francisco', 'Gran Vía', 'Alcalá', 'Atocha'])} {random.randint(1, 999)}",
                'state_city_postcode': lambda: random.choice([
                    ('Madrid', 'Madrid', '28001'), ('Catalonia', 'Barcelona', '08001'), ('Andalusia', 'Seville', '41001'),
                    ('Andalusia', 'Malaga', '29001'), ('Valencia', 'Valencia', '46001'), ('Galicia', 'La Coruña', '15001'),
                    ('Basque Country', 'Bilbao', '48001'), ('Canary Islands', 'Las Palmas', '35001')
                ]),
                'phone': lambda: f"+34 {random.randint(600, 699)} {random.randint(100000, 999999)}"
            }
        }

        if country_code in country_configs:
            config = country_configs[country_code]
            street = config['street_format']()
            state, city, postcode = config['state_city_postcode']()
            phone = config['phone']()
        else:
            # Fallback for other countries
            fake = Faker(country_code)
            street = fake.street_address()
            city = fake.city()
            state = fake.state()
            postcode = fake.postcode()
            phone = fake.phone_number()

        country = CODE_TO_COUNTRY_NAME.get(country_code, "Unknown")

        return name, street, city, state, postcode, phone, country
    except Exception as e:
        logger.error(f"Error generating fake address: {e}")
        # Fallback to US address
        fake = Faker('en_US')
        name = fake.name()
        street = f"{random.randint(100,9999)} {random.choice(['Main St', 'Oak Ave', 'First St', 'Park Ave'])}"
        city = fake.city()
        state = fake.state()
        postcode = fake.postcode()
        phone = f"+1 ({random.randint(200,999)}) {random.randint(200,999)}-{random.randint(1000,9999)}"
        country = "United States"
        return name, street, city, state, postcode, phone, country

def normalize_url(url):
    """Normalize URL by removing path and query parameters"""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    parsed = urlparse(url)
    normalized = parsed._replace(path='', params='', query='', fragment='')
    return urlunparse(normalized)

def get_ip_address(domain):
    """Get IP address of domain"""
    try:
        return socket.gethostbyname(domain)
    except:
        return "N/A"

def find_payment_gateways_comprehensive(response_text, url):
    """ENHANCED payment gateway detection - More accurate and comprehensive"""
    detected_gateways = set()

    # Convert to lowercase for case-insensitive matching
    text_lower = response_text.lower()

    # COMPREHENSIVE and ACCURATE payment gateway patterns
    gateway_patterns = {
        # Major International Gateways - IMPROVED DETECTION
        "Stripe": [
            r'js\.stripe\.com', r'api\.stripe\.com', r'stripe\.com/v3/', r'Stripe\([^)]',
            r'stripePaymentIntent', r'stripe\.com/elements', r'stripe\.com/checkout',
            r'stripe\.com/payments', r'stripe\.com/connect', r'data-stripe', 
            r'data-stripe-key', r'stripeToken', r'stripeSource', r'stripeCustomerId',
            r'stripe\.com/js', r'stripe-js', r'stripe-card', r'stripe\.com/api',
            r'stripe\.com/v1/tokens', r'stripe\.com/v1/sources', r'stripe\.com/v1/customers',
            r'stripe\.com/v1/charges', r'stripe\.com/v1/payment_intents',
            r'pk_live_', r'pk_test_', r'sk_live_', r'sk_test_'
        ],
        "Stripe 3D": [
            r'stripe\.confirmCardPayment', r'stripe\.handleCardPayment', r'payment_intent',
            r'stripe\.confirmPayment', r'stripe\.handleCardSetup', r'setup_intent',
            r'3d.*secure.*stripe', r'stripe.*3d.*secure', r'stripe\.confirmCardSetup'
        ],
        "PayPal": [
            r'www\.paypal\.com', r'paypalobjects\.com', r'paypal\.com/sdk/js',
            r'paypal\.com/checkoutnow', r'paypal\.com/webapps/hermes', r'paypal\.com/buttons',
            r'braintree\.paypal', r'paypal\.com/digital', r'paypal\.com/checkout',
            r'data-paypal', r'paypal-button', r'paypal\.com/act', r'paypal\.com/smart',
            r'paypal\.com/ipn', r'paypal\.com/cgi-bin/webscr', r'paypal-gateway',
            r'ppcp-gateway', r'paypal-good'
        ],
        "Braintree": [
            r'braintreegateway\.com', r'braintree\.js', r'braintree-client\.js',
            r'Braintree\.Client', r'braintree\.com/web', r'braintree\.com/api',
            r'braintree\.com/sdk', r'data-braintree', r'braintree-hosted-fields',
            r'braintree\.com/payments', r'braintree\.com/dropin', r'braintree.*payment',
            r'braintree.*gateway'
        ],
        "Square": [
            r'squareup\.com', r'sq-payment-form', r'square\.com/payments',
            r'SqPaymentForm', r'square\.com/sdk/js', r'square\.com/online',
            r'square\.com/checkout', r'data-square', r'square\.com/pos',
            r'square\.com/api', r'squareupsandbox\.com'
        ],
        "Authorize.Net": [
            r'authorize\.net', r'accept\.js', r'authorize\.net/Accept\.js',
            r'authorize\.net/v1/Accept\.js', r'Accept\.dispatch', r'authorize\.net/api',
            r'data-authorize', r'authorizenet', r'authorize\.net/xml'
        ],
        "AuthorizeNet": [
            r'authorizenet\.', r'authnet\.', r'authorize-net', r'authorizenet\.com'
        ],
        "2Checkout": [
            r'2checkout', r'2co\.com', r'2checkout\.com', r'2checkout\.com/checkout/api',
            r'2checkout\.com/inline', r'data-2checkout', r'twocheckout', r'2co\.js'
        ],
        "Adyen": [
            r'adyen', r'adyen\.com', r'adyen\.js', r'adyen\.min\.js', r'adyen-component',
            r'adyen-checkout', r'adyen\.com/hpp', r'adyen\.com/pay'
        ],
        "Worldpay": [
            r'worldpay', r'worldpay\.com', r'worldpay\.js', r'worldpay\.min\.js',
            r'worldpay-form', r'worldpay-payment', r'worldpay\.com/gateway'
        ],
        "SagePay": [
            r'sagepay', r'sagepay\.com', r'sagepay\.js', r'sagepay\.min\.js',
            r'sagepay-form', r'sagepay-payment', r'sagepay\.com/gateway'
        ],

        # Digital Wallets
        "Amazon Pay": [
            r'pay\.amazon\.com', r'amazonpay\.js', r'amazonpay\.com', r'amazon\.payments',
            r'amazon\.checkout', r'amazon-pay', r'amazonpayments'
        ],
        "Apple Pay": [
            r'apple-pay', r'ApplePaySession', r'apple\.pay', r'apple\.payment', r'apple-pay-button'
        ],
        "Google Pay": [
            r'gpaysdk', r'googlepay\.js', r'google\.pay', r'pay\.google\.com', r'google-pay-button'
        ],
        "Venmo": [
            r'venmo', r'venmo\.com', r'venmo-button', r'venmo-payment', r'data-venmo'
        ],

        # Bank Gateways
        "Chase": [
            r'chase\.com', r'chasepay', r'chase\.com/payments', r'chase\.pay',
            r'chasepaymentech', r'chase\.com/merchant', r'chase.*payment.*solutions'
        ],
        "NAB": [
            r'nab\.com\.au', r'nabtransact', r'nab\.payments', r'nab\.gateway', r'nab\.com\.au/merchant'
        ],
        "CBA": [
            r'cba', r'commonwealth bank', r'commbank', r'commbank\.com\.au',
            r'cba-payment', r'commbank\.com\.au/merchant'
        ],
        "ANZ": [
            r'anz', r'australia and new zealand banking', r'anz\.com', r'anz\.com\.au',
            r'anz-payment', r'anz\.com/merchant'
        ],

        # Regional Gateways
        "Eway": [
            r'eway', r'eway\.com\.au', r'eway-payment', r'eway-gateway', r'data-eway',
            r'eway\.com\.au/gateway', r'secure\.ewaypayments\.com'
        ],
        "Eway Rapid": [
            r'ewayrapid', r'eway\.com\.au/rapid', r'secure\.ewaypayments\.com',
            r'eway\.com\.au/api', r'eway.*rapid.*api', r'rapid\.eway', r'eway.*checkout'
        ],
        "Epay": [
            r'epay', r'e-pay', r'epay\.com', r'epay\.payment', r'epay\.method', r'epay\.gateway'
        ],
        "XPay": [
            r'xpay', r'x-pay', r'xpay\.com', r'xpay-payment', r'xpay-gateway'
        ],

        # Alternative Payments
        "Cash on Delivery (COD)": [
            r'cash on delivery', r'cod', r'payment_method_cod', r'payment-method-cod',
            r'cod_payment', r'cod\.method', r'cash\.delivery', r'pay\.on\.delivery'
        ],
        "Afterpay": [
            r'afterpay', r'afterpay\.com', r'afterpay\.js', r'afterpay\.min\.js',
            r'afterpay-payment', r'afterpay\.com/checkout'
        ],
        "Klarna": [
            r'klarna', r'klarnapayments\.com', r'klarna\.js', r'klarna\.min\.js',
            r'klarna\.com', r'klarna-widget', r'klarna\.com/payments'
        ],

        # Platform-specific
        "Magento": [
            r'magento', r'/static/version', r'mage', r'Mage\.js', r'var/requirejs',
            r'Magento_', r'mage\.translate', r'data-mage-init'
        ],
        "Shopify": [
            r'shopify', r'cdn\.shopify\.com', r'shopify\.com', r'shopify\.js',
            r'shopify_domain', r'shopify\.checkout', r'Shopify\.Checkout',
            r'window\.Shopify', r'var Shopify', r'shopify\.com/shop',
            r'shopify\.com/cart', r'shopify\.com/account'
        ],
        "WooCommerce": [
            r'woocommerce', r'wc-', r'woocommerce/assets',
            r'wc_add_to_cart_params', r'wc_cart_fragments_params'
        ],

        # Security & Verification
        "AVS": [
            r'avs', r'address.*verification', r'address.*validation', r'avs.*check',
            r'card.*address', r'billing.*address', r'address.*match', r'avs.*code'
        ],
        "CVV": [
            r'cvv', r'card.*verification', r'security.*code', r'card.*code', r'cvc', r'card.*validation'
        ]
    }

    # Check for each gateway with multiple patterns - use ANY match
    for gateway_name, patterns in gateway_patterns.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                detected_gateways.add(gateway_name)
                break  # Move to next gateway after first match

    # Enhanced Stripe detection with API keys
    stripe_key_patterns = [
        r'pk_live_[a-zA-Z0-9]{24,}', r'pk_test_[a-zA-Z0-9]{24,}',
        r'sk_live_[a-zA-Z0-9]{24,}', r'sk_test_[a-zA-Z0-9]{24,}',
        r'rk_live_[a-zA-Z0-9]{24,}', r'rk_test_[a-zA-Z0-9]{24,}'
    ]

    for pattern in stripe_key_patterns:
        if re.search(pattern, response_text):
            detected_gateways.add("Stripe")
            break

    # Enhanced Stripe 3D detection
    stripe_3d_patterns = [
        r'stripe\.confirmCardPayment', r'stripe\.handleCardPayment', r'payment_intent',
        r'stripe\.confirmPayment', r'stripe\.handleCardSetup', r'setup_intent',
        r'3d.*secure.*stripe', r'stripe.*3d.*secure', r'stripe\.confirmCardSetup'
    ]

    stripe_3d_detected = any(re.search(pattern, text_lower, re.IGNORECASE) for pattern in stripe_3d_patterns)

    if stripe_3d_detected and "Stripe" in detected_gateways:
        detected_gateways.discard("Stripe")
        detected_gateways.add("Stripe 3D")

    # Enhanced Eway Rapid detection
    eway_rapid_patterns = [
        r'ewayrapid', r'eway\.com\.au/rapid', r'secure\.ewaypayments\.com',
        r'eway\.com\.au/api', r'eway.*rapid.*api', r'rapid\.eway'
    ]

    eway_rapid_detected = any(re.search(pattern, text_lower, re.IGNORECASE) for pattern in eway_rapid_patterns)

    if eway_rapid_detected and "Eway" in detected_gateways:
        detected_gateways.discard("Eway")
        detected_gateways.add("Eway Rapid")

    # Check for generic payment indicators if no specific gateways found
    if not detected_gateways or (len(detected_gateways) == 1 and "Unknown" in detected_gateways):
        payment_indicators = [
            r'checkout', r'payment', r'pay', r'gateway', r'credit.?card',
            r'debit.?card', r'card.?number', r'expir', r'cvv', r'cvc',
            r'billing', r'purchase', r'buy.?now', r'add.?to.?cart',
            r'shopping.?cart', r'checkout\.js', r'payment\.method'
        ]

        generic_count = sum(1 for indicator in payment_indicators if re.search(indicator, text_lower, re.IGNORECASE))

        if generic_count >= 3:  # Require multiple indicators
            detected_gateways.discard("Unknown")
            detected_gateways.add("Generic Payment System")

    return list(detected_gateways) if detected_gateways else ["Unknown"]

def detect_auth_gate_accurately(html_text, url):
    """CORRECTED Auth Gate detection - Only for ADD PAYMENT METHOD pages"""
    text_lower = html_text.lower()
    url_lower = url.lower()

    # STRONG URL indicators for AUTH GATE (payment method addition ONLY)
    auth_url_indicators = [
        r'add.?payment.?method', 
        r'payment.?method',
        r'add.?card',
        r'save.?card',
        r'store.?card',
        r'payment.?details',
        r'card.?details',
        r'my-account.*payment',
        r'account.*payment'
    ]

    # NEGATIVE URL indicators (NOT auth gate)
    negative_url_indicators = [
        r'checkout',
        r'cart',
        r'pay',
        r'purchase',
        r'order',
        r'billing',
        r'shop',
        r'product'
    ]

    url_auth_indicator = any(re.search(pattern, url_lower) for pattern in auth_url_indicators)
    url_negative_indicator = any(re.search(pattern, url_lower) for pattern in negative_url_indicators)

    # Strong indicators of Auth Gate (payment method addition ONLY)
    strong_auth_indicators = [
        r'add.?payment.?method',
        r'payment.?method.?form', 
        r'save.?payment.?method',
        r'store.?payment.?method',
        r'save.?card',
        r'store.?card',
        r'add.?card',
        r'payment-method-form',
        r'save-payment-method',
        r'woocommerce.*add.*payment.*method',
        r'my-account.*add-payment-method'
    ]

    # Form field detection - SPECIFIC to payment method saving
    form_field_patterns = [
        r'<input[^>]*name=[\'"](save.?payment.?method|store.?card|save.?card)[\'"]',
        r'<input[^>]*type=[\'"]checkbox[\'"][^>]*name=[\'"](save.?card|store.?card)[\'"]',
        r'<input[^>]*id=[\'"](save.?card|store.?card)[\'"]',
        r'<form[^>]*add.?payment.?method',
        r'payment_method_'
    ]

    # Count strong indicators
    strong_count = sum(1 for pattern in strong_auth_indicators if re.search(pattern, text_lower))

    # Count form fields
    form_field_count = sum(1 for pattern in form_field_patterns if re.search(pattern, text_lower, re.IGNORECASE))

    # CORRECTED AUTH GATE LOGIC:
    # Auth Gate = TRUE ONLY for pages where users can ADD/SAVE payment methods
    # Checkout pages with payment forms are NOT auth gates

    # If URL clearly indicates checkout/cart/pay, it's NOT an auth gate
    if url_negative_indicator and not url_auth_indicator:
        logger.info(f"AUTH GATE FALSE: Negative URL indicator - {url_lower}")
        return False

    # If URL indicates payment method addition, it's an auth gate
    if url_auth_indicator:
        logger.info(f"AUTH GATE TRUE: URL indicator - {url_lower}")
        return True

    # If we have strong indicators AND form fields for saving payment methods
    if strong_count >= 2 and form_field_count >= 1:
        logger.info(f"AUTH GATE TRUE: Strong indicators - {strong_count}, form fields: {form_field_count}")
        return True

    # Check for WooCommerce payment method form specifically
    if re.search(r'payment_method_', text_lower) and re.search(r'save.*payment', text_lower):
        logger.info("AUTH GATE TRUE: WooCommerce save payment method")
        return True

    logger.info(f"AUTH GATE FALSE: strong:{strong_count}, form:{form_field_count}, url_auth:{url_auth_indicator}")
    return False

def detect_vbv_accurately(html_text, detected_gateways):
    """IMPROVED VBV/3DS detection - Detects both forced and optional 3DS"""
    text_lower = html_text.lower()

    # STRONG VBV indicators (specific to card authentication)
    strong_vbv_patterns = [
        r'\bvbv\b',  # Exact word VBV
        r'verified by visa', 
        r'mastercard securecode',
        r'\b3ds\b',  # Exact word 3DS
        r'3-d secure', 
        r'three d secure',
        r'securecode',
        r'strong.?customer.?authentication',
        r'\bsca\b',  # Exact word SCA
        r'liability.?shift',
        r'card.?authentication',
        r'authentication.*required',
        r'secure.*authentication'
    ]

    # GATEWAY-SPECIFIC 3DS CAPABILITY INDICATORS
    gateway_3ds_indicators = {
        "Braintree": [
            r'braintree.*3d', r'3d.*braintree', r'braintree.*secure', 
            r'braintree.*authentication', r'three.?d.*secure.*braintree'
        ],
        "Stripe": [
            r'stripe.*3d', r'3d.*stripe', r'stripe.*secure',
            r'payment_intent', r'setup_intent', r'stripe\.confirmCardPayment',
            r'stripe\.handleCardPayment'
        ],
        "Stripe 3D": [
            r'stripe.*3d', r'3d.*stripe', r'stripe.*secure',
            r'payment_intent', r'setup_intent', r'stripe\.confirmCardPayment',
            r'stripe\.handleCardPayment'
        ],
        "Adyen": [
            r'adyen.*3d', r'3d.*adyen', r'adyen.*secure',
            r'adyen.*authentication'
        ],
        "Worldpay": [
            r'worldpay.*3d', r'3d.*worldpay', r'worldpay.*secure'
        ],
        "Authorize.Net": [
            r'authorize.*3d', r'3d.*authorize', r'authorize.*secure'
        ],
        "PayPal": [
            r'paypal.*secure', r'secure.*paypal'
        ]
    }

    # Count STRONG indicators
    strong_count = 0
    for pattern in strong_vbv_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            strong_count += 1
            logger.info(f"VBV Strong pattern matched: {pattern}")

    # Check gateway-specific 3DS capabilities
    gateway_3ds_detected = False
    for gateway in detected_gateways:
        if gateway in gateway_3ds_indicators:
            for pattern in gateway_3ds_indicators[gateway]:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    gateway_3ds_detected = True
                    logger.info(f"VBV Gateway 3DS detected: {gateway} - {pattern}")
                    break

    # IMPROVED VBV LOGIC:
    # - Specific VBV/3DS terms indicate VBV
    # - Gateways with 3DS capability indicate potential VBV
    # - Combination of gateway + patterns indicates VBV

    if strong_count >= 1:
        logger.info(f"VBV DETECTED: Strong patterns found: {strong_count}")
        return True  # Specific VBV/3DS terms found

    if gateway_3ds_detected:
        logger.info("VBV DETECTED: Gateway with 3DS capability found")
        return True  # Gateway with 3DS capability detected

    # Check for Braintree specifically (common for optional 3DS)
    if "Braintree" in detected_gateways:
        logger.info("VBV DETECTED: Braintree gateway found (supports optional 3DS)")
        return True

    # Check for Stripe 3D specifically
    if "Stripe 3D" in detected_gateways:
        logger.info("VBV DETECTED: Stripe 3D gateway found")
        return True

    # Check for payment gateways that commonly use 3DS
    three_ds_gateways = ["Stripe", "Adyen", "Worldpay", "Authorize.Net"]
    for gateway in detected_gateways:
        if gateway in three_ds_gateways:
            logger.info(f"VBV POSSIBLE: {gateway} gateway found (commonly uses 3DS)")
            # For these gateways, we'll be more conservative and return True
            return True

    logger.info(f"VBV NOT DETECTED: Strong patterns: {strong_count}, Gateways: {detected_gateways}")
    return False

def scan_payment_endpoints_comprehensive(base_url):
    """Comprehensive scanning of payment endpoints - FIXED to avoid duplicate results"""
    detected_gateways = set()

    payment_endpoints = [
        "/checkout", "/payment", "/pay", "/cart", "/billing",
        "/api/payment", "/api/checkout", "/gateway", "/process-payment",
        "/checkout/cart", "/checkout/onepage", "/onepagecheckout",
        "/payment/process", "/payment/method", "/payment/gateway",
        "/checkout/#payment", "/checkout/payment", "/checkout/billing",
        "/my-account/add-payment-method", "/add-payment-method",
        "/account/payment-methods", "/payment-methods"
    ]

    def scan_endpoint(endpoint):
        try:
            test_url = urljoin(base_url, endpoint)
            response = requests.get(test_url, timeout=8, verify=False)
            if response.status_code == 200:
                return find_payment_gateways_comprehensive(response.text, test_url)
        except:
            pass
        return []

    # Use thread pool for concurrent endpoint scanning
    with ThreadPoolExecutor(max_workers=4) as executor:  # Reduced workers to avoid conflicts
        futures = [executor.submit(scan_endpoint, endpoint) for endpoint in payment_endpoints[:6]]  # Reduced endpoints
        for future in as_completed(futures):
            try:
                gateways = future.result(timeout=8)
                detected_gateways.update(gateways)
            except:
                continue

    return list(detected_gateways)

def scan_website_enhanced(url):
    """ENHANCED website scanning with improved detection - FIXED duplicate results"""
    try:
        normalized_url = normalize_url(url)
        domain = urlparse(normalized_url).netloc

        # Get IP address concurrently
        ip_future = gate_thread_pool.submit(get_ip_address, domain)

        if not re.match(r'^https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)$', normalized_url):
            return None, None, None, None, None, None, None, None, "Invalid URL", 0, "N/A"

        start_time = time.time()
        all_detected_gateways = set()

        # Enhanced Cloudscraper configuration for difficult sites
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        # Try multiple user agents for better compatibility
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0'
        ]

        response = None
        html_text = ""
        status_code = 0
        server_info = "Unknown"
        final_url = url  # Track the final URL we're scanning

        # Try with different approaches
        for user_agent in user_agents:
            try:
                scraper = cloudscraper.create_scraper(
                    browser={
                        'browser': 'chrome',
                        'platform': 'windows',
                        'mobile': False,
                        'desktop': True
                    },
                    interpreter='nodejs',
                    delay=10,
                    ssl_context=ssl_context
                )

                headers = {
                    'User-Agent': user_agent,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/avif,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none'
                }

                response = scraper.get(url, headers=headers, timeout=20, verify=False)
                status_code = response.status_code
                final_url = response.url  # Get the final URL after redirects

                if response.status_code == 200:
                    html_text = response.text
                    # Use ENHANCED detection for main page
                    initial_gateways = find_payment_gateways_comprehensive(html_text, final_url)
                    all_detected_gateways.update(initial_gateways)
                    server_info = response.headers.get('server', 'Unknown')
                    break  # Success, break the loop
                elif response.status_code in [403, 429]:
                    continue  # Try next user agent

            except Exception as e:
                logger.warning(f"Cloudscraper attempt failed with UA {user_agent[:20]}...: {e}")
                continue

        # If still no success with cloudscraper, try direct requests
        if not html_text:
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                }
                response = requests.get(url, headers=headers, timeout=15, verify=False)
                status_code = response.status_code
                final_url = response.url
                if response.status_code == 200:
                    html_text = response.text
                    initial_gateways = find_payment_gateways_comprehensive(html_text, final_url)
                    all_detected_gateways.update(initial_gateways)
                    server_info = response.headers.get('server', 'Unknown')
            except Exception as e:
                logger.warning(f"Direct request also failed: {e}")

        # STAGE 2: LIMITED endpoint scanning to avoid duplicate results
        if html_text and len(all_detected_gateways) < 3:  # Only scan if we didn't find many gateways
            try:
                # Only scan 2-3 most relevant endpoints to avoid conflicts
                relevant_endpoints = ["/checkout", "/payment", "/cart"]
                endpoint_results = set()

                for endpoint in relevant_endpoints:
                    try:
                        test_url = urljoin(normalized_url, endpoint)
                        endpoint_response = requests.get(test_url, timeout=5, verify=False)
                        if endpoint_response.status_code == 200:
                            endpoint_gateways = find_payment_gateways_comprehensive(endpoint_response.text, test_url)
                            endpoint_results.update(endpoint_gateways)
                    except:
                        continue

                # Only add new unique gateways, avoid duplicates
                for gateway in endpoint_results:
                    if gateway not in all_detected_gateways:
                        all_detected_gateways.add(gateway)
            except:
                pass  # Endpoint scanning is optional

        time_taken = time.time() - start_time

        # Get IP address result
        try:
            ip_address = ip_future.result(timeout=5)
        except:
            ip_address = "N/A"

        # If we still have no content
        if not html_text:
            return None, None, None, None, None, None, None, None, "No content retrieved", status_code, ip_address

        # Process the results using the FINAL URL for accurate detection
        text_lower = html_text.lower()

        # Enhanced platform detection
        platform = "Unknown"
        platform_patterns = {
            "WordPress": [
                r'wp-content', r'wordpress', r'wp-json', r'/wp-includes/', 
                r'wp-admin', r'wp_enqueue_script', r'wp_head', r'wp_footer'
            ],
            "Shopify": [
                r'shopify', r'cdn\.shopify\.com', r'shopify\.com', r'shopify\.js',
                r'shopify_domain', r'shopify\.checkout', r'Shopify\.Checkout',
                r'window\.Shopify', r'var Shopify', r'shopify\.com/shop',
                r'shopify\.com/cart', r'shopify\.com/account'
            ],
            "Magento": [
                r'magento', r'/static/version', r'mage', r'Mage\.js',
                r'var/requirejs', r'Magento_', r'mage\.translate', r'data-mage-init'
            ],
            "WooCommerce": [
                r'woocommerce', r'wc-', r'woocommerce/assets',
                r'wc_add_to_cart_params', r'wc_cart_fragments_params'
            ],
            "BigCommerce": [
                r'bigcommerce', r'bc-', r'bc\.js', r'bigcommerce\.com'
            ]
        }

        for platform_name, patterns in platform_patterns.items():
            if any(re.search(pattern, html_text, re.IGNORECASE) for pattern in patterns):
                platform = platform_name
                break

        # Enhanced captcha detection
        captcha = False
        captcha_type = "N/A"
        captcha_patterns = [
            (r'recaptcha|g-recaptcha|grecaptcha', "reCAPTCHA"),
            (r'hcaptcha', "hCaptcha"),
            (r'cloudflare[\-_]challenge|cf-chl-widget', "Cloudflare Challenge"),
            (r'turnstile|cf-turnstile', "Cloudflare Turnstile"),
            (r'funcaptcha', "FunCaptcha")
        ]

        captcha_types = []
        for pattern, cap_type in captcha_patterns:
            if re.search(pattern, html_text, re.IGNORECASE):
                captcha = True
                captcha_types.append(cap_type)

        if captcha_types:
            captcha_type = ", ".join(captcha_types)

        # Cloudflare detection
        cloudflare = False
        if response:
            cloudflare = (
                "cloudflare" in (response.headers.get('server', '')).lower()
                or "cf-ray" in response.headers
                or "cf-cache-status" in response.headers
                or "cloudflare" in text_lower
                or "challenge" in text_lower
                or "turnstile" in text_lower
            )
        else:
            cloudflare = "cloudflare" in text_lower

        # Final gateway list processing - remove duplicates and sort
        gateways_list = sorted(list(set(all_detected_gateways)))

        # Remove "Unknown" if we found actual gateways
        if len(gateways_list) > 1 and "Unknown" in gateways_list:
            gateways_list.remove("Unknown")

        # If still no gateways found, set to Unknown
        if not gateways_list:
            gateways_list = ["Unknown"]

        # CORRECTED Auth Gate detection - Use FINAL URL for accurate detection
        auth_gate = detect_auth_gate_accurately(html_text, final_url)

        # IMPROVED VBV detection using enhanced logic
        vbv = detect_vbv_accurately(html_text, gateways_list)

        return gateways_list, platform, captcha, captcha_type, cloudflare, auth_gate, vbv, time_taken, server_info, status_code, ip_address

    except Exception as e:
        logger.error(f"Error scanning website {url}: {str(e)}", exc_info=True)
        return None, None, None, None, None, None, None, None, None, f"Error: {str(e)}", "N/A"

# ... [Rest of the functions remain exactly the same - gauth_command, fake_command, gen_command, status_command, redeem_command, sk_command, bin_command, gate_command, tools_commands] ...

async def gauth_command(event):
    user_id = event.sender_id

    if not is_user_registered(user_id):
        await event.respond("🔒 You need to register first! Use /register command.")
        return

    user_plan = get_user_plan(user_id)

    if user_plan not in ["GOD", "ADMIN"]:
        await event.respond("⛔ You do not have permission to authorize groups.")
        return

    if hasattr(event, 'data') and event.data == b'gauth_command':
        await event.delete()
        await event.respond(
            "🔓 **Group Authorization Command**\n\n"
            "To authorize a group:\n"
            "1. Add me to the group\n"
            "2. Use `/gauth` command in that group\n"
            "3. I'll add the group to authorized list\n\n"
            "🔒 Only ADMIN/GOD plan users can use this command\n"
            "🔒 Requires admin privileges in the group",
            buttons=[Button.inline("Back to Admin", b"admin_commands")]
        )
        return

    if not event.is_group and not event.is_channel:
        await event.respond("❌ This command can only be used in groups/channels.")
        return

    chat = await event.get_chat()
    if is_group_authorized(chat.id):
        await event.respond(f"ℹ️ Group {chat.title} (ID: {chat.id}) is already authorized!")
    else:
        authorize_group(chat.id)
        await event.respond(f"✅ Group {chat.title} (ID: {chat.id}) has been authorized!")

async def fake_command(event):
    user_id = event.sender_id

    can_use, reason = can_user_use_command(user_id, event.is_group)
    if not can_use:
        await event.respond(reason)
        return

    text = get_message_text(event)
    args = text.split()
    if len(args) < 2:
        await event.respond(
            "📋 **How to use /fake**\n\n"
            "Please input the correct format:\n"
            "`/fake {country_code or country_name}`\n\n"
            "✨ **Example:** `/fake us`\n"
            "✨ **Example:** `/fake United States`\n"
            "✨ **Example:** `/fake gb(united kingdom)`\n"
            "✨ **Example:** `/fake uk`\n"
        )
        return

    country_input = ' '.join(args[1:]).strip()
    code_or_name, full_name = parse_country_input(country_input)

    if full_name:
        country_code = get_country_code(full_name)
    else:
        country_code = get_country_code(code_or_name)

    if not country_code:
        await event.respond(f"❌ Invalid country: {country_input}. Please provide a valid country code or name.")
        return

    name, street, city, state, postcode, phone, country = fetch_fake_address(country_code)

    if name and street:
        response = (
            "**Random Address Generator**\n\n"
            f"- Name: `{name}`\n"
            f"- Street Address: `{street}`\n"
            f"- City: `{city}`\n"
            f"- State/Province: `{state}`\n"
            f"- Postal Code: `{postcode}`\n"
            f"- Phone Number: `{phone}`\n"
            f"- Country: `{country}`\n"
        )
        await event.respond(response, parse_mode='markdown')
    else:
        await event.respond(f"❌ Failed to generate a valid address for the country: {country_input}. Please try again later.")

async def gen_command(event):
    user_id = event.sender_id

    can_use, reason = can_user_use_command(user_id, event.is_group)
    if not can_use:
        await event.respond(reason)
        return

    if not event.is_group:
        increment_personal_usage(user_id)

    text = get_message_text(event)
    args = text.split()

    if len(args) < 2 or args[0].lower() in ['/gen', '.gen'] and len(args) == 1:
        await event.respond(
            "📋 **How to use /gen**\n\n"
            "Generate valid credit card numbers:\n\n"
            "`/gen {bin} {amount}` - Generate cards from BIN\n"
            "`/gen {cc|mm|yy|cvv} {amount}` - Generate full cards\n\n"
            "✨ **Examples:**\n"
            "`/gen 411111 10` - Generate 10 Visa cards\n"
            "`/gen 411111|12|2025|123 5` - Generate 5 cards with details\n\n"
            "🔒 Max 500 cards at once\n"
            "💳 BIN must be at least 6 digits",
            buttons=[Button.inline("Back to Tools", b"tools_commands")]
        )
        return

    input_data = args[1]
    amount = 10
    if len(args) > 2:
        try:
            amount = int(args[2])
            if amount < 1:
                await event.respond("❌ Amount must be greater than 0.")
                return
            if amount > 500:
                await event.respond("❌ Maximum amount is 500.")
                return
        except ValueError:
            await event.respond("❌ Invalid amount. Please provide a valid number.")
            return

    if '|' in input_data:
        parts = input_data.split('|')
        cc = parts[0]
        mes = parts[1]
        ano = parts[2]
        cvv = parts[3]
    else:
        cc = input_data
        mes = 'x'
        ano = 'x'
        cvv = 'x'

    if 'x' in cc:
        await event.respond(
            "❌ Invalid format. 'x' is not allowed in the CC number.\n\n"
            "📋 **Correct Format:**\n"
            "`/gen {cc|mon|year|cvv} {amount}`\n\n"
            "✨ **Example:** `/gen 123456|12|2025|123 10`\n"
            "✨ **Example:** `/gen 123456 5`\n\n"
            "✨ **Example with BIN:** `/gen 123456 5`\n"
            "✨ **Example with CC number:** `/gen 4115081234567890 5`\n"
        )
        return

    if not cc[:5].isdigit():
        await event.respond("❌ The CC number must start with at least 5 digits.")
        return

    try:
        ccs = []
        for _ in range(amount):
            if cc.isdigit() and len(cc) >= 5:
                ccgen = generate_luhn_compliant_cc(cc[:6])
            else:
                ccgen = generate_luhn_compliant_cc(''.join(random.choices("0123456789", k=6)))

            mesgen = f"{random.randint(1, 12):02d}" if mes in ('x', 'xx') else mes
            anogen = random.randint(2025, 2035) if ano in ('x', 'xxxx') else ano
            cvvgen = f"{random.randint(100, 999):03d}" if cvv in ('x', 'xxx') else cvv
            ccs.append(f"{ccgen}|{mesgen}|{anogen}|{cvvgen}")

        bin_details = None
        if cc.isdigit() and len(cc) >= 6:
            bin_number = cc[:6]
            bin_details = fetch_bin_details(bin_number)

        if amount > 10:
            file_name = f"ccs_{user_id}.txt"
            with open(file_name, 'w') as f:
                for cc in ccs:
                    f.write(cc + "\n")

            await event.respond("✅ CCs generated successfully! Sending them in a text file...")
            await event.client.send_file(event.chat_id, file_name, caption=f"Here are your {amount} generated CCs.")
            os.remove(file_name)
        else:
            response = f"💳 Generated CCs: ✅\n"
            if cc.isdigit() and len(cc) >= 6:
                response += f"💳 BIN: {cc[:6]}\n\n"

            for cc in ccs:
                response += f"<code>{cc}</code>\n"

            if bin_details and "scheme" in bin_details:
                scheme = bin_details.get("scheme", "Unknown")
                type = bin_details.get("type", "Unknown")
                brand = bin_details.get("brand", "Unknown")
                bank = bin_details.get("bank", {}).get("name", "Unknown")
                country = bin_details.get("country", {}).get("name", "Unknown")
                emoji = bin_details.get("country", {}).get("emoji", "")

                response += (
                    f"\n💳 Card: {scheme} - {type} - {brand}\n"
                    f"🏦 Bank: {bank}\n"
                    f"🌍 Country: {country} {emoji}"
                )

            await event.respond(response, parse_mode='html')

    except Exception as e:
        await event.respond(f"❌ Failed to generate CCs. Error: {str(e)}")

async def status_command(event):
    user_id = event.sender_id

    if not is_user_registered(user_id):
        await event.respond("🔒 You need to register first! Use /register command.")
        return

    user_plan = get_user_plan(user_id)
    plan_info = PLANS.get(user_plan, {"limit": 0, "description": "Unknown"})

    if is_user_banned(user_id):
        await event.respond("You have been banned from using this bot. Contact @D_A_DYY")
        return

    username = event.sender.username or "None"
    join_date = datetime.datetime.now().strftime("%d-%m-%Y")

    if hasattr(event, 'is_reply') and event.is_reply:
        try:
            replied_msg = await event.get_reply_message()
            if replied_msg:
                replied_user = replied_msg.sender
                replied_user_id = replied_user.id
                replied_username = replied_user.username or "None"
                replied_plan = get_user_plan(replied_user_id)
                replied_plan_info = PLANS.get(replied_plan, {"limit": 0, "description": "Unknown"})

                response = (
                    "┌───────*.·:·.☯ ⚜ ☯.·:·.*───────┐\n"
                    "       Replied User Information\n"
                    "├───────*.·:·.☯ ⚜ ☯.·:·.*───────┤\n\n"
                    f"👤 ID: `{replied_user_id}`\n"
                    f"👤 Username: @{replied_username}\n"
                    f"💎 Plan: {replied_plan}\n"
                    f"📅 Joined At: {join_date}\n\n"
                    "┌───────*.·:·.☯ ⚜ ☯.·:·.*───────┐\n"
                    "       Plan Information\n"
                    "├───────*.·:·.☯ ⚜ ☯.·:·.*───────┤\n\n"
                    f"• Limit: {replied_plan_info['limit']} CCs\n"
                    f"• Description: {replied_plan_info['description']}"
                )
                await event.respond(response)
                return
        except Exception as e:
            logger.error(f"Error getting replied message info: {str(e)}")

    response = (
        "┌───────*.·:·.☯ ⚜ ☯.·:·.*───────┐\n"
        "       User Information\n"
        "├───────*.·:·.☯ ⚜ ☯.·:·.*───────┤\n\n"
        f"👤 ID: `{user_id}`\n"
        f"👤 Username: @{username}\n"
        f"💎 Plan: {user_plan}\n"
        f"📅 Joined At: {join_date}\n\n"
        "┌───────*.·:·.☯ ⚜ ☯.·:·.*───────┐\n"
        "       Plan Information\n"
        "├───────*.·:·.☯ ⚜ ☯.·:·.*───────┤\n\n"
        f"• Limit: {plan_info['limit']} CCs\n"
        f"• Description: {plan_info['description']}"
    )

    await event.respond(response)

async def redeem_command(event):
    user_id = event.sender_id

    can_use, reason = can_user_use_command(user_id, event.is_group)
    if not can_use:
        await event.respond(reason)
        return

    text = get_message_text(event)
    args = text.split()
    if len(args) < 2:
        await event.respond(
            "🎁 **How to Redeem Your Code:**\n\n"
            "✨ Use the following format to redeem your gift code:\n\n"
            "`/redeem <your_code>`\n\n"
            "Example: `/redeem WAYNE-DAD-ABCD-1234`\n"
            "✨ Enjoy your upgraded plan! 💎"
        )
        return

    gift_code = args[1]

    if not os.path.exists(GC_FILE):
        await event.respond("❌ No gift codes have been generated yet.")
        return

    with open(GC_FILE, 'r') as f:
        valid_codes = f.read().splitlines()

    code_found = False
    for line in valid_codes:
        code, expiration_date = line.split('|')
        if gift_code == code:
            code_found = True
            expiration_date = datetime.datetime.strptime(expiration_date, "%Y-%m-%d")
            if datetime.datetime.now() > expiration_date:
                await event.respond("❌ This gift code has expired.")
                return

            if upgrade_user(user_id, "PLUS"):
                await event.respond(
                    f"🎉 **Code Redeemed Successfully!**\n\n"
                    f"✨ You have been upgraded to the **PLUS plan**!\n"
                    f"🔑 **Code:** `{gift_code}`\n"
                    f"📅 **Expiration Date:** `{expiration_date.strftime('%Y-%m-%d')}`\n\n"
                    f"Enjoy your new privileges! 💎"
                )
                return
            else:
                await event.respond("❌ Failed to upgrade your plan. Please contact support.")
                return

    if not code_found:
        await event.respond("❌ Invalid gift code. Please check the code and try again.")

async def sk_command(event):
    user_id = event.sender_id

    can_use, reason = can_user_use_command(user_id, event.is_group)
    if not can_use:
        await event.respond(reason)
        return

    text = get_message_text(event)
    sk_key = text.replace('/sk', '').replace('.sk', '').strip()

    if not sk_key:
        await event.respond(
            "🔑 **How to Check Stripe Secret Key** 🔑\n\n"
            "✨ Use the following format to check your Stripe secret key:\n\n"
            "`/sk <your_sk_key>` or `.sk <your_sk_key>`\n\n"
            "🔑 **Example:** `/sk sk_live_1234567890abcdef`\n\n"
            "💎 Enjoy your key checking! ❤️"
        )
        return

    try:
        stripe.api_key = sk_key
        account = stripe.Account.retrieve()
        balance = stripe.Balance.retrieve()

        country = account.get("country", "N/A")
        currency = account.get("default_currency", "N/A")
        display_name = account.get("settings", {}).get("dashboard", {}).get("display_name", "N/A")
        email = account.get("email", "N/A")
        phone = account.get("business_profile", {}).get("phone", "N/A")
        url = account.get("business_profile", {}).get("url", "N/A")
        card_payments = account.get("capabilities", {}).get("card_payments", "N/A")
        charges_enabled = account.get("charges_enabled", "N/A")
        available_balance = balance.get("available", [{}])[0].get("amount", 0)
        pending_balance = balance.get("pending", [{}])[0].get("amount", 0)

        response = f"""
> ℹ️ Stripe Key Check
────────────────────

> Status: Live ✅

> Key: <code>{sk_key}</code>

> Country: {country}
> Currency: {currency}

> Dashboard Name: {display_name}
> Email: {email}
> Phone: {phone}
> URL: {url}
> Card Payments: {card_payments}
> Charges Enabled: {charges_enabled}

> Balance Information
=================
> Available Balance: {available_balance} {currency}
> Pending Balance: {pending_balance} {currency}
=================

Checked By @{event.sender.username or 'Unknown'}
User Plan => [{get_user_plan(user_id)}]
"""
        await event.respond(response, parse_mode='html')

    except stripe.error.AuthenticationError:
        response = f"""
> 🏦 Stripe Key Check
────────────────────

> Status: Dead ❌

> Key: <code>{sk_key}</code>

> Response: 401

────────────────────
Checked By @{event.sender.username or 'Unknown'}
User Plan => [{get_user_plan(user_id)}]
"""
        await event.respond(response, parse_mode='html')
    except Exception as e:
        await event.respond(f"❌ **Failed to validate Stripe Key**\n\n**Error:** `{str(e)}`")

async def bin_command(event):
    user_id = event.sender_id

    can_use, reason = can_user_use_command(user_id, event.is_group)
    if not can_use:
        await event.respond(reason)
        return

    text = get_message_text(event)
    bin_input = text.replace('/bin', '').replace('.bin', '').strip()

    if not bin_input:
        await event.respond(
            "💳 **How to Check BIN** 💳\n\n"
            "✨ Use the following format to check your BIN:\n\n"
            "`/bin <your_bin>` or `.bin <your_bin>`\n\n"
            "🔑 **Example:** `/bin 123456` or `.bin 123456|12|2025|123`\n\n"
            "💎 Enjoy your BIN checking! ❤️"
        )
        return

    try:
        if '|' in bin_input:
            bin_number = bin_input.split('|')[0][:6]
        else:
            bin_number = bin_input[:6]

        if len(bin_number) != 6 or not bin_number.isdigit():
            await event.respond("❌ Invalid BIN. Please provide a 6-digit BIN or card details.")
            return

        url = f"https://binlist.io/lookup/{bin_number}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        bin_data = response.json()

        if not bin_data or "scheme" not in bin_data:
            await event.respond(f"❌ No information found for BIN: {bin_number}")
            return

        scheme = bin_data.get("scheme", "None")
        type = bin_data.get("type", "None")
        brand = bin_data.get("brand", "None")
        country = bin_data.get("country", {}).get("name", "None")
        emoji = bin_data.get("country", {}).get("emoji", "None")
        bank = bin_data.get("bank", {}).get("name", "None")
        bank_url = bin_data.get("bank", {}).get("url", "None")
        bank_phone = bin_data.get("bank", {}).get("phone", "None")

        response_message = f"""
BIN INFO
BIN: <code>{bin_number}</code>
Brand: {scheme} ({brand})
Type: {type}
Bank Name: {bank}
Bank Url: {bank_url}
Bank Phone: {bank_phone}
Country: {country} {emoji}
────────────────────
"""
        await event.respond(response_message, parse_mode='html')
    except requests.exceptions.RequestException as e:
        await event.respond(f"❌ Failed to fetch BIN details. Error: {str(e)}")
    except ValueError as e:
        await event.respond(f"❌ Failed to parse BIN details. Error: {str(e)}")

async def gate_command(event):
    user_id = event.sender_id

    can_use, reason = can_user_use_command(user_id, event.is_group, is_gate_command=True)
    if not can_use:
        await event.respond(reason)
        return

    text = get_message_text(event)
    args = text.split()
    if len(args) < 2:
        await event.respond(
            "🌐 **How to use /gate**\n\n"
            "Scan a website for payment gateways and security features:\n\n"
            "`/gate <website_url>`\n\n"
            "✨ Examples:\n"
            "`/gate example.com`\n"
            "`/gate https://shop.example.com`\n\n"
            "⚡ **Enhanced scanning** - Better error handling and Shopify support\n"
            "🔧 **Multiple methods** - Advanced detection techniques\n"
            "🔍 **Accurate detection** - Improved VBV and Auth Gate logic",
            buttons=[Button.inline("Back to Tools", b"tools_commands")]
        )
        return

    url = args[1].strip()
    processing_msg = await event.respond(f"🌐 Scanning {url}... ⚡ Enhanced scan in progress (15-30 seconds)")

    try:
        # Use thread pool for enhanced scanning
        scan_results = await asyncio.get_event_loop().run_in_executor(
            gate_thread_pool, scan_website_enhanced, url
        )

        if len(scan_results) == 11:
            gateways, platform, captcha, captcha_type, cloudflare, auth_gate, vbv, time_taken, server_info, status_code, ip_address = scan_results
        else:
            await processing_msg.edit("❌ Failed to scan website. Invalid response format.")
            return

        if gateways is None and platform is None:
            error_msg = status_code if isinstance(status_code, str) else "Unknown error"
            await processing_msg.edit(
                f"❌ Failed to scan {url}\n"
                f"Error: {error_msg}\n\n"
                f"💡 **Tips:**\n"
                f"• The site might be blocking our requests\n"
                f"• Try a different URL or check if the site is accessible\n"
                f"• Some sites require JavaScript which we can't fully execute"
            )
            return

        username = event.sender.username or "Unknown"

        # Format the response
        response = (
                "━━━━━━━ 𝓢𝓲𝓽𝓮 𝓢𝓽𝓪𝓽𝓾𝓼 ━━━━━━━\n"
                f"𝘐𝘗 𝘈𝘥𝘥𝘳𝘦𝘴𝘴 : `{ip_address}`\n"
                f"𝘚𝘪𝘵𝘦       : `{url}`\n"
                f"𝘏𝘛𝘛𝘗 𝘚𝘵𝘢𝘵𝘶𝘴 : `{status_code} {'(𝙊𝙆)' if status_code == 200 else ''}`\n"
                "─────────┈∘◦┄┄┄┄┄∘◦┈────────\n"
                f"𝙋𝙖𝙮𝙢𝙚𝙣𝙩 𝙈𝙚𝙩𝙝𝙤𝙙𝙨: `{', '.join(gateways) if gateways else 'None detected'}`\n\n"
                f"𝘾𝙖𝙥𝙩𝙘𝙝𝙖     : `{'𝙏𝙧𝙪𝙚 ✅' if captcha else '𝙁𝙖𝙡𝙨𝙚 ❌'}`\n"
                f"𝘾𝙖𝙥𝙩𝙘𝙝𝙖 𝙏𝙮𝙥𝙚 : `{captcha_type or 'N/A'}`\n"
                f"𝘾𝙡𝙤𝙪𝙙𝙛𝙡𝙖𝙧𝙚  : `{'𝙏𝙧𝙪𝙚 ✅' if cloudflare else '𝙁𝙖𝙡𝙨𝙚 ❌'}`\n"
                "─────────┈∘◦┄┄┄┄┄∘◦┈────────\n"
                f"𝙋𝙡𝙖𝙩𝙛𝙤𝙧𝙢    : `{platform or 'Unknown'}`\n"
                f"𝙎𝙚𝙧𝙫𝙚𝙧 𝐈𝐧𝐟𝐨 : `{server_info or 'Unknown'}`\n\n"
                f"𝘼𝘂𝘵𝘩 𝙂𝘢𝘵𝘦   : `{'𝙏𝙧𝙪𝙚 ✅' if auth_gate else '𝙁𝙖𝙡𝙨𝙚 ❌'}`\n"
                f"𝙑𝘽𝙑         : `{'𝙏𝙧𝙪𝙚 ✅' if vbv else '𝙁𝙖𝙡𝙨𝙚 ❌'}`\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"𝙏𝙞𝙢𝙚 𝙏𝙖𝙠𝙚𝙣  : {time_taken:.2f} 𝙨𝙚𝙘𝙤𝙣𝙙𝙨\n"
                f"🔍 𝙀𝙉𝙃𝘼𝙉𝘾𝙀𝘿 𝙎𝘾𝘼𝙉 𝙈𝙊𝘿𝙀"
            )

        await processing_msg.edit(response.strip())

    except Exception as e:
        error_msg = str(e) if str(e) else "Unknown error"
        await processing_msg.edit(f"❌ Unexpected error scanning website: {error_msg}")

async def tools_commands(event):
    if not await check_group_auth(event):
        return

    if is_user_banned(event.sender_id):
        await event.respond("🚫 You have been banned from using this bot 🚫\nContact @D_A_DYY")
        return

    user_plan = get_user_plan(event.sender_id)
    buttons = [
        [Button.inline("/status 📋", b"status_command"), Button.inline("/redeem 🎁", b"redeem_command")],
        [Button.inline("/bin 💳", b"bin_command"), Button.inline("/fake 🏠", b"fake_command")],
        [Button.inline("/gen 💳", b"gen_command"), Button.inline("/gate 🌐", b"gate_command")],
        [Button.inline("Exit ↩️", b"exit_command")]
    ]

    await event.edit(
        "🛠️ **Tools Commands**\n"
        "Here are the tools commands:",
        buttons=buttons
    )