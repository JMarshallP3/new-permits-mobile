from flask import Flask, render_template, request, jsonify, session, send_file, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
import requests
from bs4 import BeautifulSoup
import threading
import time
import os
import csv
import io
import json
import sqlite3
from urllib.parse import urljoin
# Optional push notification imports
try:
    from pywebpush import webpush, WebPushException
    PUSH_NOTIFICATIONS_AVAILABLE = True
    print("✅ pywebpush imported successfully")
except ImportError as e:
    print(f"❌ Warning: pywebpush not available. Push notifications disabled. Error: {e}")
    PUSH_NOTIFICATIONS_AVAILABLE = False
    
    # Fallback: Try to implement basic push functionality without pywebpush
    try:
        import requests
        import json
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        import base64
        import struct
        PUSH_NOTIFICATIONS_AVAILABLE = True
        print("✅ Using fallback push implementation")
    except ImportError as e2:
        print(f"❌ Fallback push implementation also failed: {e2}")
        PUSH_NOTIFICATIONS_AVAILABLE = False
    # Create dummy classes for compatibility
    class WebPushException(Exception):
        pass
    def webpush(*args, **kwargs):
        raise WebPushException("Push notifications not available")

import base64

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///permits.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database model
class Permit(db.Model):
    __tablename__ = 'permits'  # Explicitly set table name
    
    id = db.Column(db.Integer, primary_key=True)
    county = db.Column(db.String(100), nullable=False)
    operator = db.Column(db.String(200), nullable=False)
    lease_name = db.Column(db.String(200), nullable=False)
    well_number = db.Column(db.String(50), nullable=False)
    api_number = db.Column(db.String(50), nullable=False)
    date_issued = db.Column(db.Date, nullable=False)
    rrc_link = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Push notification subscription model
class Subscription(db.Model):
    __tablename__ = 'subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    endpoint = db.Column(db.String(500), nullable=False, unique=True)
    p256dh = db.Column(db.String(200), nullable=False)
    auth = db.Column(db.String(200), nullable=False)
    user_agent = db.Column(db.String(500))
    session_id = db.Column(db.String(100), nullable=False)  # Link to user session
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# User settings model
class UserSettings(db.Model):
    __tablename__ = 'user_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(100), nullable=False, unique=True)
    selected_counties = db.Column(db.Text)  # JSON string
    last_notification_check = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Device-scoped subscription model
class DeviceSubscription(db.Model):
    __tablename__ = 'device_subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(100), nullable=False, index=True)
    endpoint = db.Column(db.String(500), nullable=False, unique=True)
    p256dh = db.Column(db.String(200), nullable=False)
    auth = db.Column(db.String(200), nullable=False)
    prefs_json = db.Column(db.Text)  # JSON string with user preferences
    user_agent = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_error = db.Column(db.String(500))  # Last push error message
    error_count = db.Column(db.Integer, default=0)  # Consecutive error count

# Seen permits table for deduplication
class SeenPermit(db.Model):
    __tablename__ = 'seen_permits'
    
    id = db.Column(db.Integer, primary_key=True)
    permit_no = db.Column(db.String(100), nullable=False, unique=True)  # API number or unique identifier
    first_seen_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)  # TTL for cleanup

# Global scraping status
scraping_status = {
    'is_running': False,
    'last_run': None,
    'last_count': 0,
    'error': None
}

# Push notification configuration
VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY')
VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY')
VAPID_CLAIMS = {
    "sub": os.getenv('VAPID_SUBJECT', 'mailto:admin@rrc-monitor.com')
}

# Check if VAPID keys are properly configured
if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
    print("Warning: VAPID keys not configured. Push notifications will be disabled.")
    print("Set VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY environment variables.")
    PUSH_NOTIFICATIONS_AVAILABLE = False
else:
    # Debug: Check VAPID key format
    print(f"DEBUG: VAPID_PRIVATE_KEY length: {len(VAPID_PRIVATE_KEY)}")
    print(f"DEBUG: VAPID_PUBLIC_KEY length: {len(VAPID_PUBLIC_KEY)}")
    print(f"DEBUG: VAPID_PRIVATE_KEY starts with: {VAPID_PRIVATE_KEY[:50]}...")
    print(f"DEBUG: VAPID_PUBLIC_KEY starts with: {VAPID_PUBLIC_KEY[:50]}...")

def send_push_notification(subscription, title, body, url=None):
    """Send push notification to a subscription"""
    if not PUSH_NOTIFICATIONS_AVAILABLE:
        print("Push notifications not available - skipping notification")
        return False
        
    try:
        # Debug: Print subscription data structure
        print(f"DEBUG: Subscription data: {subscription}")
        
        # Validate subscription data
        if not subscription.get('endpoint'):
            print("ERROR: Missing endpoint in subscription")
            return False
            
        keys = subscription.get('keys', {})
        p256dh = keys.get('p256dh', '')
        auth = keys.get('auth', '')
        
        print(f"DEBUG: p256dh length: {len(p256dh)}, auth length: {len(auth)}")
        
        if not p256dh or not auth:
            print(f"ERROR: Missing or empty keys - p256dh: '{p256dh}', auth: '{auth}'")
            return False
        
        payload = json.dumps({
            "title": title,
            "body": body,
            "url": url or "/",
            "icon": "/static/icon-512.png",
            "badge": "/static/apple-touch-icon.png"
        })
        
        # Try pywebpush first
        if 'webpush' in globals() and callable(webpush):
            print(f"DEBUG: Using pywebpush with subscription: {subscription}")
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS
            )
            print("DEBUG: Push notification sent successfully")
            return True
        else:
            # Fallback: Simple HTTP request to push service
            print("DEBUG: Using fallback push method")
            return send_push_fallback(subscription, payload)
            
    except WebPushException as e:
        print(f"Push notification failed: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error sending push notification: {e}")
        import traceback
        traceback.print_exc()
        return False

def send_push_fallback(subscription, payload):
    """Fallback push notification using direct HTTP requests"""
    try:
        import requests
        
        # Extract endpoint
        endpoint = subscription.get('endpoint')
        
        if not endpoint:
            print("Missing push subscription endpoint")
            return False
        
        # Send HTTP request to push service
        headers = {
            'Content-Type': 'application/json',
            'TTL': '86400'
        }
        
        response = requests.post(endpoint, data=payload, headers=headers, timeout=10)
        
        if response.status_code in [200, 201, 202]:
            print(f"✅ Push notification sent successfully")
            return True
        else:
            print(f"❌ Push notification failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Fallback push notification failed: {e}")
        return False

def send_notifications_for_new_permits(new_permits):
    """Send push notifications for new permits to subscribed users with device-scoped preferences"""
    if not new_permits:
        return
    
    if not PUSH_NOTIFICATIONS_AVAILABLE:
        print("Push notifications not available - skipping notifications")
        return
    
    with app.app_context():
        # Get all active device subscriptions
        subscriptions = DeviceSubscription.query.all()
        
        if not subscriptions:
            print("No active device subscriptions found")
            return
        
        notifications_sent = 0
        pruned_endpoints = 0
        
        for permit in new_permits:
            # Check if we've already sent notification for this permit (deduplication)
            permit_key = f"{permit.api_number}_{permit.lease_name}_{permit.well_number}"
            
            # Check if permit was already seen (with 24h TTL)
            seen_permit = SeenPermit.query.filter_by(permit_no=permit_key).first()
            if seen_permit and seen_permit.expires_at > datetime.utcnow():
                print(f"Skipping duplicate notification for permit {permit_key}")
                continue
            
            # Record this permit as seen (24h TTL)
            if not seen_permit:
                seen_permit = SeenPermit(
                    permit_no=permit_key,
                    expires_at=datetime.utcnow() + timedelta(hours=24)
                )
                db.session.add(seen_permit)
            else:
                seen_permit.expires_at = datetime.utcnow() + timedelta(hours=24)
            
            permit_county = permit.county
            
            # Send notification to devices that want this county
            for subscription in subscriptions:
                try:
                    # Parse user preferences
                    prefs = json.loads(subscription.prefs_json) if subscription.prefs_json else {}
                    
                    # Get preference sets
                    monitor_counties = set(prefs.get('monitorCounties', []))
                    dismissed_counties = set(prefs.get('dismissedCountySet', []))
                    dismissed_permits = set(prefs.get('dismissedPermitSet', []))
                    
                    # Skip if county is dismissed
                    if permit_county in dismissed_counties:
                        continue
                    
                    # Skip if permit is dismissed
                    if str(permit.id) in dismissed_permits:
                        continue
                    
                    # Skip if user has specific counties selected and this isn't one of them
                    if monitor_counties and permit_county not in monitor_counties:
                        continue
                    
                    # Send notification
                    subscription_data = {
                        "endpoint": subscription.endpoint,
                        "keys": {
                            "p256dh": subscription.p256dh,
                            "auth": subscription.auth
                        }
                    }
                    
                    title = f"New Permit in {permit_county}"
                    body = f"{permit.operator} - {permit.lease_name} #{permit.well_number}"
                    url = permit.rrc_link
                    
                    success = send_push_notification(subscription_data, title, body, url)
                    
                    if success:
                        notifications_sent += 1
                        # Reset error count on successful send
                        subscription.error_count = 0
                        subscription.last_error = None
                        print(f"Sent notification to device {subscription.device_id} for {permit_county} permit")
                    else:
                        # Increment error count
                        subscription.error_count += 1
                        subscription.last_error = "Failed to send notification"
                        
                except Exception as e:
                    print(f"Error processing subscription for device {subscription.device_id}: {e}")
                    subscription.error_count += 1
                    subscription.last_error = str(e)
                    continue
            
            # Prune dead endpoints (404/410 errors)
            dead_subscriptions = DeviceSubscription.query.filter(
                DeviceSubscription.error_count >= 3
            ).all()
            
            for dead_sub in dead_subscriptions:
                print(f"Pruning dead subscription for device {dead_sub.device_id}")
                db.session.delete(dead_sub)
                pruned_endpoints += 1
        
        # Commit all changes
        db.session.commit()
        
        print(f"Sent {notifications_sent} push notifications for {len(new_permits)} new permits")
        if pruned_endpoints > 0:
            print(f"Pruned {pruned_endpoints} dead endpoints")

def get_or_create_user_settings(session_id):
    """Get or create user settings for a session"""
    settings = UserSettings.query.filter_by(session_id=session_id).first()
    if not settings:
        settings = UserSettings(
            session_id=session_id,
            selected_counties=json.dumps(list(TEXAS_COUNTIES))
        )
        db.session.add(settings)
        db.session.commit()
    return settings

# Texas counties list
TEXAS_COUNTIES = (
    'ANDERSON', 'ANDREWS', 'ANGELINA', 'ARANSAS', 'ARCHER', 'ARMSTRONG', 'ATASCOSA', 'AUSTIN',
    'BAILEY', 'BANDERA', 'BASTROP', 'BAYLOR', 'BEE', 'BELL', 'BEXAR', 'BLANCO', 'BORDEN',
    'BOSQUE', 'BOWIE', 'BRAZORIA', 'BRAZOS', 'BREWSTER', 'BRISCOE', 'BROOKS', 'BROWN',
    'BURLESON', 'BURNET', 'CALDWELL', 'CALHOUN', 'CALLAHAN', 'CAMERON', 'CAMP', 'CARSON',
    'CASS', 'CASTRO', 'CHAMBERS', 'CHEROKEE', 'CHILDRESS', 'CLAY', 'COCHRAN', 'COKE',
    'COLEMAN', 'COLLIN', 'COLLINGSWORTH', 'COLORADO', 'COMAL', 'COMANCHE', 'CONCHO',
    'COOKE', 'CORYELL', 'COTTLE', 'CRANE', 'CROCKETT', 'CROSBY', 'CULBERSON', 'DALLAM',
    'DALLAS', 'DAWSON', 'DEAF SMITH', 'DELTA', 'DENTON', 'DEWITT', 'DICKENS', 'DIMMIT',
    'DONLEY', 'DUVAL', 'EASTLAND', 'ECTOR', 'EDWARDS', 'ELLIS', 'EL PASO', 'ERATH',
    'FALLS', 'FANNIN', 'FAYETTE', 'FISHER', 'FLOYD', 'FOARD', 'FORT BEND', 'FRANKLIN',
    'FREESTONE', 'FRIO', 'GAINES', 'GALVESTON', 'GARZA', 'GILLESPIE', 'GLASSCOCK',
    'GOLIAD', 'GONZALES', 'GRAY', 'GRAYSON', 'GREGG', 'GRIMES', 'GUADALUPE', 'HALE',
    'HALL', 'HAMILTON', 'HANSFORD', 'HARDEMAN', 'HARDIN', 'HARRIS', 'HARRISON', 'HARTLEY',
    'HASKELL', 'HAYS', 'HEMPHILL', 'HENDERSON', 'HIDALGO', 'HILL', 'HOCKLEY', 'HOOD',
    'HOPKINS', 'HOUSTON', 'HOWARD', 'HUDSPETH', 'HUNT', 'HUTCHINSON', 'IRION', 'JACK',
    'JACKSON', 'JASPER', 'JEFF DAVIS', 'JEFFERSON', 'JIM HOGG', 'JIM WELLS', 'JOHNSON',
    'JONES', 'KARNES', 'KAUFMAN', 'KENDALL', 'KENEDY', 'KENT', 'KERR', 'KIMBLE',
    'KING', 'KINNEY', 'KLEBERG', 'KNOX', 'LAMAR', 'LAMB', 'LAMPASAS', 'LA SALLE',
    'LAVACA', 'LEE', 'LEON', 'LIBERTY', 'LIMESTONE', 'LIPSCOMB', 'LIVE OAK', 'LLANO',
    'LOVING', 'LUBBOCK', 'LYNN', 'MADISON', 'MARION', 'MARTIN', 'MASON', 'MATAGORDA',
    'MAVERICK', 'MCCULLOCH', 'MCLENNAN', 'MCMULLEN', 'MEDINA', 'MENARD', 'MIDLAND',
    'MILAM', 'MILLS', 'MITCHELL', 'MONTAGUE', 'MONTGOMERY', 'MOORE', 'MORRIS', 'MOTLEY',
    'NACOGDOCHES', 'NAVARRO', 'NEWTON', 'NOLAN', 'NUECES', 'OCHILTREE', 'OLDHAM',
    'ORANGE', 'PALO PINTO', 'PANOLA', 'PARKER', 'PARMER', 'PECOS', 'POLK', 'POTTER',
    'PRESIDIO', 'RAINS', 'RANDALL', 'REAGAN', 'REAL', 'RED RIVER', 'REEVES', 'REFUGIO',
    'ROBERTS', 'ROBERTSON', 'ROCKWALL', 'RUNNELS', 'RUSK', 'SABINE', 'SAN AUGUSTINE',
    'SAN JACINTO', 'SAN PATRICIO', 'SAN SABA', 'SCHLEICHER', 'SCURRY', 'SHACKELFORD',
    'SHELBY', 'SHERMAN', 'SMITH', 'SOMERVELL', 'STARR', 'STEPHENS', 'STERLING',
    'STONEWALL', 'SUTTON', 'SWISHER', 'TARRANT', 'TAYLOR', 'TERRELL', 'TERRY',
    'THROCK MORTON', 'TITUS', 'TOM GREEN', 'TRAVIS', 'TRINITY', 'TYLER', 'UPSHUR',
    'UPTON', 'UVALDE', 'VAL VERDE', 'VAN ZANDT', 'VICTORIA', 'WALKER', 'WALLER',
    'WARD', 'WASHINGTON', 'WEBB', 'WHARTON', 'WHEELER', 'WICHITA', 'WILBARGER',
    'WILLACY', 'WILLIAMSON', 'WILSON', 'WINKLER', 'WISE', 'WOOD', 'YOAKUM', 'YOUNG',
    'ZAPATA', 'ZAVALA'
)

def scrape_rrc_permits():
    """Scrape new permits from RRC website using Selenium for proper form interaction"""
    global scraping_status
    
    scraping_status['is_running'] = True
    scraping_status['error'] = None
    scraping_status['last_run'] = datetime.now()
    
    try:
        print("Starting RRC permit scraping...")
        
        with app.app_context():
            # Get today's date
            today = date.today()
            date_str = today.strftime('%m/%d/%Y')
            
            # Try Selenium approach first for proper form interaction
            try:
                from selenium import webdriver
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.webdriver.chrome.options import Options
                from selenium.webdriver.common.keys import Keys
                from selenium.webdriver.chrome.service import Service
                from webdriver_manager.chrome import ChromeDriverManager
                
                print(f"Using Selenium to scrape RRC for date: {date_str}")
                
                # Set up Chrome options for headless mode and cloud deployment
                chrome_options = Options()
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--disable-web-security')
                chrome_options.add_argument('--disable-features=VizDisplayCompositor')
                chrome_options.add_argument('--window-size=1920,1080')
                chrome_options.add_argument('--disable-extensions')
                chrome_options.add_argument('--disable-plugins')
                chrome_options.add_argument('--disable-images')
                chrome_options.add_argument('--disable-javascript')
                chrome_options.add_argument('--disable-css')
                chrome_options.add_argument('--disable-logging')
                chrome_options.add_argument('--disable-background-timer-throttling')
                chrome_options.add_argument('--disable-backgrounding-occluded-windows')
                chrome_options.add_argument('--disable-renderer-backgrounding')
                chrome_options.add_argument('--disable-features=TranslateUI')
                chrome_options.add_argument('--disable-ipc-flooding-protection')
                chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
                
                # Additional cloud-specific options
                chrome_options.add_argument('--remote-debugging-port=9222')
                chrome_options.add_argument('--disable-background-networking')
                chrome_options.add_argument('--disable-default-apps')
                chrome_options.add_argument('--disable-sync')
                chrome_options.add_argument('--metrics-recording-only')
                chrome_options.add_argument('--no-first-run')
                chrome_options.add_argument('--safebrowsing-disable-auto-update')
                chrome_options.add_argument('--disable-client-side-phishing-detection')
                chrome_options.add_argument('--disable-hang-monitor')
                chrome_options.add_argument('--disable-prompt-on-repost')
                chrome_options.add_argument('--disable-domain-reliability')
                chrome_options.add_argument('--disable-component-extensions-with-background-pages')
                chrome_options.add_argument('--disable-background-timer-throttling')
                chrome_options.add_argument('--disable-renderer-backgrounding')
                chrome_options.add_argument('--disable-backgrounding-occluded-windows')
                chrome_options.add_argument('--disable-features=TranslateUI,BlinkGenPropertyTrees')
                chrome_options.add_argument('--disable-ipc-flooding-protection')
                
                # Set binary location for cloud environments
                if os.path.exists('/usr/bin/google-chrome'):
                    chrome_options.binary_location = '/usr/bin/google-chrome'
                elif os.path.exists('/usr/bin/chromium-browser'):
                    chrome_options.binary_location = '/usr/bin/chromium-browser'
                
                # Try to use webdriver-manager for automatic ChromeDriver management
                try:
                    # Set ChromeDriver path for cloud environments
                    chromedriver_path = None
                    possible_paths = [
                        '/usr/local/bin/chromedriver',
                        '/usr/bin/chromedriver',
                        '/opt/chromedriver',
                        '/app/chromedriver'
                    ]
                    
                    for path in possible_paths:
                        if os.path.exists(path):
                            chromedriver_path = path
                            print(f"✅ Found ChromeDriver at: {path}")
                            break
                    
                    if not chromedriver_path:
                        print("⚠️ ChromeDriver not found in standard locations, will use webdriver-manager")
                    
                    if chromedriver_path:
                        service = Service(chromedriver_path)
                        driver = webdriver.Chrome(service=service, options=chrome_options)
                        print(f"✅ ChromeDriver initialized successfully with system driver at {chromedriver_path}")
                    else:
                        service = Service(ChromeDriverManager().install())
                        driver = webdriver.Chrome(service=service, options=chrome_options)
                        print("✅ ChromeDriver initialized successfully with WebDriverManager")
                except Exception as e:
                    print(f"ChromeDriver initialization failed: {e}")
                    try:
                        # Fallback to system ChromeDriver without service
                        driver = webdriver.Chrome(options=chrome_options)
                        print("✅ ChromeDriver initialized successfully with system driver (no service)")
                    except Exception as e2:
                        print(f"All ChromeDriver attempts failed: {e2}")
                        raise e2
                
                try:
                    # Navigate to the RRC search page
                    search_url = "https://webapps.rrc.state.tx.us/DP/initializePublicQueryAction.do"
                    print(f"Navigating to: {search_url}")
                    driver.get(search_url)
                    
                    # Wait for page to load and check if we're on the right page
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.TAG_NAME, "form"))
                    )
                    
                    print(f"Page loaded successfully. Current URL: {driver.current_url}")
                    print(f"Page title: {driver.title}")
                    
                    # Check if we're on the correct page (should contain "Search for W-1s" or similar)
                    page_source = driver.page_source
                    if "Search for W-1s" in page_source or "Drilling Permit" in page_source:
                        print("✅ Successfully loaded the RRC public query form")
                    else:
                        print("⚠️ Page content doesn't match expected RRC query form")
                        print(f"Page contains: {page_source[:500]}...")
                    
                    # Look for all input fields to debug
                    all_inputs = driver.find_elements(By.TAG_NAME, "input")
                    print(f"Found {len(all_inputs)} input fields on the page")
                    
                    # Find and fill the Submit Start field
                    try:
                        begin_field = driver.find_element(By.NAME, "submitStart")
                        begin_field.clear()
                        begin_field.send_keys(date_str)
                        print(f"✅ Filled Submit Start: {date_str}")
                    except Exception as e:
                        print(f"❌ Could not find submitStart field: {e}")
                        # List all input fields for debugging
                        for inp in all_inputs:
                            if inp.get_attribute('name'):
                                print(f"  Input field: name='{inp.get_attribute('name')}', type='{inp.get_attribute('type')}', placeholder='{inp.get_attribute('placeholder')}'")
                            
                    # Find and fill the Submit End field
                    try:
                        end_field = driver.find_element(By.NAME, "submitEnd")
                        end_field.clear()
                        end_field.send_keys(date_str)
                        print(f"✅ Filled Submit End: {date_str}")
                    except Exception as e:
                        print(f"❌ Could not find submitEnd field: {e}")
                    
                    # Find and click the Submit button
                    try:
                        # Look for all submit buttons to debug
                        submit_buttons = driver.find_elements(By.CSS_SELECTOR, "input[type='submit']")
                        print(f"Found {len(submit_buttons)} submit buttons")
                        
                        # Find the correct submit button (name='submit' with value='Submit')
                        search_button = None
                        for i, button in enumerate(submit_buttons):
                            name = button.get_attribute('name')
                            value = button.get_attribute('value')
                            print(f"Button {i}: name='{name}', value='{value}', text=''")
                            if name == 'submit' and value == 'Submit':
                                search_button = button
                                break
                        
                        if search_button:
                            print("✅ Found Submit button (name='submit', value='Submit'), clicking...")
                            search_button.click()
                        else:
                            raise Exception("Could not find submit button with name='submit' and value='Submit'")
                        
                        # Wait for results page to load
                        WebDriverWait(driver, 20).until(
                            lambda driver: driver.current_url != search_url
                        )
                        
                        print(f"After search, current URL: {driver.current_url}")
                        
                        # Check if we got redirected to login
                        if 'login' in driver.current_url.lower():
                            print("⚠️ Redirected to login page - this shouldn't happen with public form")
                            scraping_status['last_count'] = 0
                            return
                        
                        # Parse the results page
                        soup = BeautifulSoup(driver.page_source, 'html.parser')
                        permits = parse_rrc_results(soup, today)
                        
                        # Check for pagination and scrape additional pages
                        page_count = 1
                        total_permits = permits if permits else []
                        
                        # Look for pagination links
                        pagination_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'pager.offset')]")
                        if pagination_links:
                            print(f"Found {len(pagination_links)} pagination links")
                            
                            # Get unique page URLs
                            page_urls = set()
                            for link in pagination_links:
                                href = link.get_attribute('href')
                                if href and 'pager.offset' in href:
                                    page_urls.add(href)
                            
                            print(f"Found {len(page_urls)} unique page URLs")
                            
                            # Scrape each additional page
                            for page_url in page_urls:
                                try:
                                    page_count += 1
                                    print(f"Scraping page {page_count}: {page_url}")
                                    
                                    driver.get(page_url)
                                    WebDriverWait(driver, 10).until(
                                        lambda driver: driver.current_url == page_url
                                    )
                                    
                                    # Parse this page
                                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                                    page_permits = parse_rrc_results(soup, today)
                                    
                                    if page_permits:
                                        total_permits.extend(page_permits)
                                        print(f"Found {len(page_permits)} permits on page {page_count}")
                                    else:
                                        print(f"No permits found on page {page_count}")
                                        
                                except Exception as e:
                                    print(f"Error scraping page {page_count}: {e}")
                                    continue
                        
                        if total_permits:
                            print(f"✅ Found {len(total_permits)} total permits across {page_count} pages via Selenium")
                            scraping_status['last_count'] = len(total_permits)
                            return
                        else:
                            print("No permits found in any page")
                            
                    except Exception as e:
                        print(f"Error clicking Search button: {e}")
                        # Try alternative button selectors
                        try:
                            submit_buttons = driver.find_elements(By.XPATH, "//input[@type='submit']")
                            print(f"Found {len(submit_buttons)} submit buttons")
                            for i, btn in enumerate(submit_buttons):
                                print(f"Button {i}: name='{btn.get_attribute('name')}', value='{btn.get_attribute('value')}', text='{btn.text}'")
                            
                            # Click the first submit button that's not "Log In"
                            for btn in submit_buttons:
                                if btn.get_attribute('value') and 'log' not in btn.get_attribute('value').lower():
                                    print(f"Clicking button with value: {btn.get_attribute('value')}")
                                    btn.click()
                                    break
                                    
                        except Exception as e2:
                            print(f"Alternative button click failed: {e2}")
                
                finally:
                    driver.quit()
                    
            except ImportError as e:
                print(f"Selenium not available: {e}, falling back to requests...")
            except Exception as selenium_error:
                print(f"Selenium failed: {selenium_error}, falling back to requests...")
                # Log the specific error for debugging
                import traceback
                print(f"Selenium error details: {traceback.format_exc()}")
                
            # Fallback to requests approach
            try:
                print("Using requests fallback for RRC scraping...")
                session = requests.Session()
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Referer': 'https://webapps.rrc.state.tx.us/'
                })
                
                # Try to access the public permit search directly (no login required)
                search_url = "https://webapps.rrc.state.tx.us/DP/initializePublicQueryAction.do"
                print(f"Attempting to access public search: {search_url}")
                
                response = session.get(search_url, timeout=30)
                print(f"Search page status: {response.status_code}")
                print(f"Final URL: {response.url}")
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Check if we're on the correct page (should contain "Search for W-1s")
                    if "Search for W-1s" in response.text or "Drilling Permit" in response.text:
                        print("✅ Successfully loaded the RRC public query form")
                    elif 'login' in response.url.lower() or soup.find('input', {'name': 'userid'}):
                        print("⚠️ Redirected to login page - this shouldn't happen with public form")
                        scraping_status['last_count'] = 0
                        return
                    else:
                        print("⚠️ Page content doesn't match expected RRC query form")
                        print(f"Page contains: {response.text[:500]}...")
                    
                    # Look for the permit search form
                    form = soup.find('form')
                    if form:
                        print("Found permit search form, extracting fields...")
                        
                        # Extract form action and method
                        action = form.get('action', '')
                        method = form.get('method', 'post').lower()
                        
                        # Build form data with today's date
                        form_data = {}
                        for input_field in form.find_all(['input', 'select', 'textarea']):
                            name = input_field.get('name')
                            if name:
                                if name == 'submittedDateFrom' or name == 'submittedDateTo':
                                    form_data[name] = date_str
                                    print(f"Setting {name} to {date_str}")
                                elif input_field.get('type') == 'submit':
                                    form_data[name] = input_field.get('value', 'Submit')
                                elif input_field.get('type') == 'hidden':
                                    form_data[name] = input_field.get('value', '')
                                elif input_field.get('type') == 'text' and not name.startswith('submittedDate'):
                                    form_data[name] = ''
                        
                        # Submit the form
                        if action:
                            submit_url = urljoin(search_url, action)
                            print(f"Submitting form to: {submit_url}")
                            print(f"Form data: {form_data}")
                            
                            submit_response = session.post(submit_url, data=form_data, timeout=30)
                            print(f"Form submission status: {submit_response.status_code}")
                            print(f"Form submission URL: {submit_response.url}")
                            
                            if submit_response.status_code == 200:
                                results_soup = BeautifulSoup(submit_response.content, 'html.parser')
                                permits = parse_rrc_results(results_soup, today)
                                
                                if permits:
                                    print(f"Found {len(permits)} permits via form submission")
                                    scraping_status['last_count'] = len(permits)
                                    return
                                else:
                                    print("No permits found in search results")
                    else:
                        print("No search form found on page")
                else:
                    print(f"Failed to access search page: {response.status_code}")
                    
            except Exception as requests_error:
                print(f"Requests fallback also failed: {requests_error}")
                import traceback
                print(f"Requests error details: {traceback.format_exc()}")
                
            print("No new permits found for today")
            scraping_status['last_count'] = 0
            
    except Exception as e:
        print(f"Error scraping RRC permits: {e}")
        import traceback
        traceback.print_exc()
        scraping_status['error'] = str(e)
    finally:
        scraping_status['is_running'] = False

def normalize_county_name(county_name):
    """Normalize county name to match TEXAS_COUNTIES format"""
    if not county_name:
        return ''
    
    # Remove "County" suffix if present
    county_name = county_name.replace(' COUNTY', '').replace(' County', '').replace(' county', '')
    
    # Convert to uppercase
    county_name = county_name.upper().strip()
    
    # Check if it matches any Texas county
    for texas_county in TEXAS_COUNTIES:
        if county_name == texas_county:
            return texas_county
    
    # If no exact match, return the cleaned name
    return county_name

def parse_rrc_results(soup, today):
    """Parse RRC results page and extract permit data"""
    try:
        # Look for results table
        tables = soup.find_all('table')
        print(f"Found {len(tables)} tables on page")
        
        results_table = None
        max_rows = 0
        
        for i, table in enumerate(tables):
            rows = table.find_all('tr')
            row_count = len(rows)
            print(f"Table {i}: rows={row_count}")
            
            if row_count > 0:
                first_row_cells = [cell.get_text(strip=True) for cell in rows[0].find_all(['td', 'th'])]
                print(f"  First row: {first_row_cells}")
            
            # Look for table with most rows (likely results)
            if row_count > max_rows:
                max_rows = row_count
                results_table = table
        
        if results_table and max_rows > 1:
            print(f"Using table with {max_rows} rows")
            
            rows = results_table.find_all('tr')
            data_rows = rows[1:] if len(rows) > 1 else rows  # Skip header
            
            print(f"Processing {len(data_rows)} data rows")
            
            new_permits = []
            
            for i, row in enumerate(data_rows):
                cells = row.find_all(['td', 'th'])
                if len(cells) < 5:
                    continue
                
                cell_texts = [cell.get_text(strip=True) for cell in cells]
                print(f"Row {i+1}: {cell_texts}")
                
                try:
                    # Extract data based on RRC table structure from logs:
                    # Status Date, Status #, API No., Operator Name/Number, Lease Name, Well #, Dist., County, etc.
                    # From logs: Column 6 = Dist., Column 7 = County
                    
                    api_number = cells[2].get_text(strip=True) if len(cells) > 2 else ''
                    operator = cells[3].get_text(strip=True) if len(cells) > 3 else ''
                    lease_name = cells[4].get_text(strip=True) if len(cells) > 4 else ''
                    well_number = cells[5].get_text(strip=True) if len(cells) > 5 else ''
                    
                    # County is in column 7 (index 7) based on the logs
                    county = ''
                    if len(cells) > 7:
                        county_text = cells[7].get_text(strip=True)
                        print(f"  Column 7 (County): '{county_text}'")
                        if county_text:
                            county = normalize_county_name(county_text)
                            print(f"  Found county: {county}")
                    
                    # If no county found in column 7, try other columns
                    if not county:
                        print(f"  No county found in column 7, checking other columns")
                        for i, cell in enumerate(cells[6:]):
                            cell_text = cell.get_text(strip=True)
                            print(f"  Column {i+6}: '{cell_text}'")
                            if cell_text:
                                normalized_county = normalize_county_name(cell_text)
                                if normalized_county and normalized_county in TEXAS_COUNTIES:
                                    county = normalized_county
                                    print(f"  Found county: {county}")
                                    break
                    
                    # If still no county found, set to UNKNOWN
                    if not county:
                        print(f"  No county found in any column, setting to UNKNOWN")
                        county = 'UNKNOWN'
                    
                    # Skip header rows or invalid data
                    if not operator or 'api' in api_number.lower() or 'status' in api_number.lower():
                        continue
                    
                    # Extract RRC link from the table row
                    rrc_link = ""
                    link_element = row.find('a', href=True)
                    if link_element:
                        href = link_element['href']
                        if href.startswith('/'):
                            rrc_link = f"https://webapps.rrc.state.tx.us{href}"
                        elif href.startswith('http'):
                            rrc_link = href
                        else:
                            rrc_link = f"https://webapps.rrc.state.tx.us/DP/{href}"
                        print(f"Found RRC link: {rrc_link}")
                    else:
                        # Fallback to generic link if no specific link found
                        rrc_link = f"https://webapps.rrc.state.tx.us/DP/drillDownQueryAction.do?name={lease_name.replace(' ', '%20')}&fromPublicQuery=Y"
                        print(f"Using fallback RRC link: {rrc_link}")
                    
                    # Check if permit already exists
                    existing_permit = Permit.query.filter_by(
                        api_number=api_number,
                        lease_name=lease_name,
                        well_number=well_number
                    ).first()
                    
                    if not existing_permit:
                        permit = Permit(
                            county=county,
                            operator=operator,
                            lease_name=lease_name,
                            well_number=well_number,
                            api_number=api_number,
                            date_issued=today,
                            rrc_link=rrc_link
                        )
                        db.session.add(permit)
                        new_permits.append(permit)
                        print(f"Added new permit: {operator} - {lease_name} - {well_number}")
                
                except Exception as e:
                    print(f"Error processing row {i+1}: {e}")
                    continue
            
            # Commit new permits
            if new_permits:
                db.session.commit()
                print(f"Successfully added {len(new_permits)} new permits")
                
                # Send push notifications for new permits
                send_notifications_for_new_permits(new_permits)
                
                # Debug: Check total permits in database
                total_permits = Permit.query.count()
                print(f"Total permits in database: {total_permits}")
                
                return new_permits
            else:
                print("No new permits found")
                return []
        else:
            print("No results table found or table has no data")
            return []
            
    except Exception as e:
        print(f"Error parsing RRC results: {e}")
        import traceback
        traceback.print_exc()
        return []

def generate_html():
    """Generate the complete HTML page"""
    # Get permits from database
    permits = Permit.query.order_by(Permit.created_at.desc()).all()
    print(f"DEBUG: Total permits in database: {len(permits)}")
    
    # Get selected counties from session
    selected_counties = session.get('selected_counties', [])
    
    # Apply filters
    search_term = request.args.get('search', '')
    sort_by = request.args.get('sort', 'newest')
    
    print(f"DEBUG: Filters - search: '{search_term}', sort: '{sort_by}'")
    
    filtered_permits = permits
    
    if search_term:
        search_lower = search_term.lower()
        filtered_permits = [p for p in filtered_permits if 
                          search_lower in p.operator.lower() or 
                          search_lower in p.lease_name.lower()]
    
    print(f"DEBUG: After filtering: {len(filtered_permits)} permits")
    
    if sort_by == 'newest':
        filtered_permits.sort(key=lambda x: x.created_at, reverse=True)
    elif sort_by == 'oldest':
        filtered_permits.sort(key=lambda x: x.created_at)
    elif sort_by == 'county':
        filtered_permits.sort(key=lambda x: x.county)
    elif sort_by == 'operator':
        filtered_permits.sort(key=lambda x: x.operator)
    
    # Get unique counties for dropdown
    counties = sorted(list(set([p.county for p in permits if p.county])))
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
        <title>New Permits</title>
        <link rel="manifest" href="/manifest.webmanifest">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
        <meta name="apple-mobile-web-app-title" content="New Permits">
        <meta name="mobile-web-app-capable" content="yes">
        <meta name="theme-color" content="#667eea">
        <link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
        <link rel="apple-touch-icon" sizes="120x120" href="/static/apple-touch-icon-120x120.png">
        <style>
            /* Import premium fonts */
            @import url('https://fonts.googleapis.com/css2?family=SF+Pro+Display:wght@300;400;500;600;700&family=SF+Pro+Text:wght@300;400;500;600&display=swap');
            
            :root {{
                --bg-primary: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
                --bg-secondary: rgba(255, 255, 255, 0.9);
                --bg-card: rgba(255, 255, 255, 0.8);
                --text-primary: #1a202c;
                --text-secondary: #64748b;
                --border-color: rgba(255, 255, 255, 0.3);
                --shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                --shadow-hover: 0 20px 40px rgba(0, 0, 0, 0.15);
            }}
            
            [data-theme="dark"] {{
                --bg-primary: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
                --bg-secondary: rgba(30, 41, 59, 0.9);
                --bg-card: rgba(30, 41, 59, 0.8);
                --text-primary: #f1f5f9;
                --text-secondary: #94a3b8;
                --border-color: rgba(255, 255, 255, 0.1);
                --shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                --shadow-hover: 0 20px 40px rgba(0, 0, 0, 0.4);
            }}
            
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'SF Pro Text', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: var(--bg-primary);
                color: var(--text-primary);
                line-height: 1.6;
                font-size: 16px;
                font-weight: 400;
                -webkit-font-smoothing: antialiased;
                -moz-osx-font-smoothing: grayscale;
                min-height: 100vh;
                transition: all 0.3s ease;
            }}
            
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                padding: 2rem;
            }}
            
            .header {{
                text-align: center;
                margin-bottom: 3rem;
                padding: 2rem 0;
            }}
            
            .header h1 {{
                font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
                font-size: 3.5rem;
                font-weight: 700;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                margin-bottom: 0.5rem;
                letter-spacing: -0.02em;
            }}
            
            .header p {{
                font-size: 1.25rem;
                color: var(--text-secondary);
                font-weight: 400;
                letter-spacing: 0.01em;
            }}
            
            .theme-toggle {{
                position: fixed;
                top: 2rem;
                right: 2rem;
                background: var(--bg-card);
                backdrop-filter: blur(20px);
                border: 1px solid var(--border-color);
                border-radius: 50px;
                padding: 0.75rem;
                cursor: pointer;
                transition: all 0.3s ease;
                box-shadow: var(--shadow);
                z-index: 1000;
            }}
            
            .theme-toggle:hover {{
                transform: scale(1.1);
                box-shadow: var(--shadow-hover);
            }}
            
            .theme-toggle svg {{
                width: 24px;
                height: 24px;
                color: var(--text-primary);
            }}
            
            .controls {{
                background: var(--bg-card);
                backdrop-filter: blur(20px);
                border-radius: 24px;
                padding: 2rem;
                margin-bottom: 2rem;
                box-shadow: var(--shadow);
                border: 1px solid var(--border-color);
            }}
            
            .filters-section {{
                margin: 1.5rem 0;
                padding: 1.5rem;
                background: var(--bg-secondary);
                border-radius: 16px;
                border: 1px solid var(--border-color);
            }}
            
            .filters-heading {{
                font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
                font-size: 1.25rem;
                font-weight: 600;
                color: var(--text-primary);
                margin-bottom: 1rem;
                letter-spacing: -0.01em;
            }}
            
            .filters-actions {{
                display: flex;
                gap: 1rem;
                justify-content: flex-start;
            }}
            
            .controls-spacer {{
                height: 20px;
            }}
            
            .export-notify {{
                display: flex;
                gap: 1rem;
                justify-content: flex-start;
            }}
            
            .control-row {{
                display: flex;
                gap: 1.5rem;
                margin-bottom: 1.5rem;
                align-items: center;
            }}
            
            .control-group {{
                display: flex;
                flex-direction: column;
                gap: 0.5rem;
            }}
            
            .control-group label {{
                font-size: 0.875rem;
                font-weight: 500;
                color: var(--text-secondary);
                letter-spacing: 0.025em;
            }}
            
            .control-group select,
            .control-group input {{
                padding: 0.75rem 1rem;
                border: 2px solid var(--border-color);
                border-radius: 12px;
                font-size: 1rem;
                font-weight: 400;
                background: var(--bg-secondary);
                color: var(--text-primary);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                cursor: pointer;
            }}
            
            .control-group input {{
                cursor: text;
            }}
            
            .control-group select:focus,
            .control-group input:focus {{
                outline: none;
                border-color: #667eea;
                box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            }}
            
            .buttons {{
                display: flex;
                gap: 1rem;
                flex-wrap: wrap;
            }}
            
            .btn {{
                padding: 0.875rem 1.5rem;
                border: none;
                border-radius: 12px;
                font-size: 1rem;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                text-decoration: none;
                display: inline-flex;
                align-items: center;
                gap: 0.5rem;
                letter-spacing: 0.025em;
                position: relative;
                overflow: hidden;
            }}
            
            .btn::before {{
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
                transition: left 0.5s;
            }}
            
            .btn:hover::before {{
                left: 100%;
            }}
            
            .btn-primary {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
            }}
            
            .btn-primary:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
            }}
            
            .btn-success {{
                background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                color: white;
                box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3);
            }}
            
            .btn-success:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(16, 185, 129, 0.4);
            }}
            
            .btn-info {{
                background: linear-gradient(135deg, #06b6d4 0%, #0891b2 100%);
                color: white;
                box-shadow: 0 4px 15px rgba(6, 182, 212, 0.3);
            }}
            
            .btn-info:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(6, 182, 212, 0.4);
            }}
            
            .btn-warning {{
                background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
                color: white;
                box-shadow: 0 4px 15px rgba(245, 158, 11, 0.3);
            }}
            
            .btn-warning:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(245, 158, 11, 0.4);
            }}
            
            .status {{
                background: var(--bg-card);
                backdrop-filter: blur(20px);
                border-radius: 24px;
                padding: 2rem;
                margin-bottom: 2rem;
                box-shadow: var(--shadow);
                border: 1px solid var(--border-color);
            }}
            
            .status h3 {{
                font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
                font-size: 1.5rem;
                font-weight: 600;
                color: var(--text-primary);
                margin-bottom: 1.5rem;
                letter-spacing: -0.01em;
            }}
            
            .status-item {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 1rem 0;
                border-bottom: 1px solid var(--border-color);
            }}
            
            .status-item:last-child {{
                border-bottom: none;
            }}
            
            .status-label {{
                font-size: 1rem;
                font-weight: 500;
                color: var(--text-secondary);
            }}
            
            .status-value {{
                font-size: 1rem;
                font-weight: 600;
                color: var(--text-primary);
            }}
            
            #permits-container {{
                margin-top: 2rem;
            }}
            
            .county-section {{
                margin-bottom: 3rem;
            }}
            
            .county-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 1.5rem;
                padding-bottom: 1rem;
                border-bottom: 2px solid var(--border-color);
            }}
            
            .county-title {{
                font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
                font-size: 1.75rem;
                font-weight: 600;
                color: var(--text-primary);
                margin: 0;
                letter-spacing: -0.01em;
            }}
            
            .county-menu {{
                display: flex;
                gap: 0.5rem;
            }}
            
            .permits-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
                gap: 1.5rem;
            }}
            
            .county-empty-state {{
                text-align: center;
                padding: 3rem 2rem;
                color: var(--text-secondary);
                background: var(--bg-card);
                backdrop-filter: blur(20px);
                border-radius: 20px;
                box-shadow: var(--shadow);
                border: 1px solid var(--border-color);
                margin-top: 1rem;
            }}
            
            .county-empty-state h3 {{
                font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
                font-size: 1.25rem;
                font-weight: 600;
                color: var(--text-primary);
                margin-bottom: 0.5rem;
            }}
            
            .county-empty-state p {{
                font-size: 1rem;
                color: var(--text-secondary);
            }}
            
            .hidden-section {{
                margin-bottom: 2rem;
                padding: 1.5rem;
                background: var(--bg-secondary);
                border-radius: 12px;
                border: 1px solid var(--border-color);
            }}
            
            .hidden-section h4 {{
                font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
                font-size: 1.25rem;
                font-weight: 600;
                color: var(--text-primary);
                margin-bottom: 1rem;
            }}
            
            .hidden-item {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 0.75rem;
                margin-bottom: 0.5rem;
                background: var(--bg-card);
                border-radius: 8px;
                border: 1px solid var(--border-color);
            }}
            
            .hidden-item:last-child {{
                margin-bottom: 0;
            }}
            
            .hidden-item-name {{
                font-weight: 500;
                color: var(--text-primary);
            }}
            
            .hidden-item-actions {{
                display: flex;
                gap: 0.5rem;
            }}
            
            .permit-card {{
                background: var(--bg-card);
                backdrop-filter: blur(20px);
                border-radius: 20px;
                padding: 1.5rem;
                box-shadow: var(--shadow);
                border: 1px solid var(--border-color);
                transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
                position: relative;
                overflow: hidden;
            }}
            
            .permit-card::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 4px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }}
            
            .permit-card:hover {{
                transform: translateY(-8px) scale(1.02);
                box-shadow: var(--shadow-hover);
            }}
            
            .permit-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 1rem;
            }}
            
            .permit-county {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 0.5rem 1rem;
                border-radius: 20px;
                font-size: 0.875rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }}
            
            .permit-date {{
                color: var(--text-secondary);
                font-size: 0.875rem;
                font-weight: 500;
            }}
            
            .permit-info h3 {{
                font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
                font-size: 1.25rem;
                font-weight: 600;
                color: var(--text-primary);
                margin-bottom: 1rem;
                letter-spacing: -0.01em;
            }}
            
            .permit-detail {{
                margin-bottom: 0.75rem;
                display: flex;
                align-items: center;
            }}
            
            .permit-detail strong {{
                min-width: 80px;
                color: var(--text-secondary);
                font-size: 0.875rem;
                font-weight: 500;
            }}
            
            .permit-detail span {{
                color: var(--text-primary);
                font-size: 0.875rem;
                font-weight: 400;
            }}
            
            .permit-actions {{
                display: flex;
                gap: 0.75rem;
                margin-top: 1rem;
            }}
            
            .btn-sm {{
                padding: 0.5rem 1rem;
                font-size: 0.875rem;
            }}
            
            .btn-outline-primary {{
                background: transparent;
                color: #667eea;
                border: 2px solid #667eea;
            }}
            
            .btn-outline-primary:hover {{
                background: #667eea;
                color: white;
            }}
            
            .btn-outline-danger {{
                background: transparent;
                color: #ef4444;
                border: 2px solid #ef4444;
            }}
            
            .btn-outline-danger:hover {{
                background: #ef4444;
                color: white;
            }}
            
            .no-permits {{
                text-align: center;
                padding: 4rem 2rem;
                color: var(--text-secondary);
                background: var(--bg-card);
                backdrop-filter: blur(20px);
                border-radius: 24px;
                box-shadow: var(--shadow);
                border: 1px solid var(--border-color);
            }}
            
            .no-permits h3 {{
                font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
                font-size: 1.5rem;
                font-weight: 600;
                color: var(--text-primary);
                margin-bottom: 0.5rem;
            }}
            
            .no-permits p {{
                font-size: 1rem;
                color: var(--text-secondary);
            }}
            
            /* County Selector Modal */
            .county-selector {{
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                backdrop-filter: blur(10px);
                display: none;
                justify-content: center;
                align-items: center;
                z-index: 1000;
                padding: 2rem;
            }}
            
            .county-modal {{
                background: var(--bg-card);
                backdrop-filter: blur(20px);
                border-radius: 24px;
                padding: 2rem;
                max-width: 600px;
                width: 100%;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: var(--shadow-hover);
                border: 1px solid var(--border-color);
            }}
            
            .county-modal h3 {{
                font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
                font-size: 1.5rem;
                font-weight: 600;
                color: var(--text-primary);
                margin-bottom: 1.5rem;
                text-align: center;
                letter-spacing: -0.01em;
            }}
            
            .county-search-container {{
                margin-bottom: 1.5rem;
            }}
            
            .county-search-input {{
                width: 100%;
                padding: 0.875rem 1rem;
                border: 2px solid var(--border-color);
                border-radius: 12px;
                font-size: 1rem;
                font-weight: 400;
                background: var(--bg-secondary);
                color: var(--text-primary);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }}
            
            .county-search-input:focus {{
                outline: none;
                border-color: #667eea;
                box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            }}
            
            .modal-actions {{
                display: flex;
                gap: 1rem;
                margin-bottom: 1.5rem;
                justify-content: center;
            }}
            
            .county-actions {{
                display: flex;
                gap: 1rem;
                margin-bottom: 1.5rem;
                justify-content: center;
            }}
            
            .county-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
                gap: 0.75rem;
                max-height: 300px;
                overflow-y: auto;
                padding: 1rem;
                background: var(--bg-secondary);
                border-radius: 12px;
            }}
            
            .county-item {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                padding: 0.5rem;
                border-radius: 8px;
                transition: all 0.2s ease;
            }}
            
            .county-item:hover {{
                background: rgba(102, 126, 234, 0.1);
            }}
            
            .county-item input[type="checkbox"] {{
                width: 18px;
                height: 18px;
                accent-color: #667eea;
            }}
            
            .county-item label {{
                font-size: 0.875rem;
                font-weight: 500;
                color: var(--text-primary);
                cursor: pointer;
                flex: 1;
            }}
            
            /* Responsive Design */
            @media (max-width: 768px) {{
                .container {{
                    padding: 1rem;
                }}
                
                .header h1 {{
                    font-size: 2.5rem;
                }}
                
                .controls, .status {{
                    padding: 1.5rem;
                }}
                
                .control-row {{
                    flex-direction: column;
                    gap: 1rem;
                }}
                
                .filters-actions {{
                    flex-direction: column;
                }}
                
                .export-notify {{
                    flex-direction: column;
                }}
                
                .permits-grid {{
                    grid-template-columns: 1fr;
                }}
                
                .county-modal {{
                    margin: 1rem;
                    max-height: 90vh;
                }}
                
                .county-grid {{
                    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
                }}
                
                .theme-toggle {{
                    top: 1rem;
                    right: 1rem;
                }}
            }}
            
            /* Smooth animations */
            @keyframes fadeIn {{
                from {{ opacity: 0; transform: translateY(20px); }}
                to {{ opacity: 1; transform: translateY(0); }}
            }}
            
            .permit-card {{
                animation: fadeIn 0.6s cubic-bezier(0.4, 0, 0.2, 1);
            }}
            
            .controls, .status {{
                animation: fadeIn 0.8s cubic-bezier(0.4, 0, 0.2, 1);
            }}
            
            .header {{
                animation: fadeIn 1s cubic-bezier(0.4, 0, 0.2, 1);
            }}
            
            /* Mobile Compact Layout */
            @media (max-width: 430px) {{
                /* Debug: Add a visible border to confirm CSS is loading */
                body {{
                    border: 2px solid red !important;
                }}
                
                /* Typography scale: keep inputs >=16px to avoid iOS zoom */
                body {{ 
                    font-size: 15px !important; 
                    line-height: 1.35 !important; 
                }}
                h1 {{ 
                    font-size: clamp(18px, 5vw, 22px) !important; 
                    margin: 8px 0 !important; 
                }}
                h2 {{ 
                    font-size: clamp(16px, 4.2vw, 20px) !important; 
                    margin: 6px 0 !important; 
                }}
                h3 {{ 
                    font-size: clamp(15px, 3.8vw, 18px) !important; 
                    margin: 6px 0 !important; 
                }}

                /* Top controls stack: tighten gaps/padding */
                .controls {{
                    gap: 8px !important;
                    padding: 1rem !important;
                }}
                .control-row {{ 
                    margin: 4px 0 !important; 
                }}

                /* Buttons: smaller text/padding but keep 44px target */
                .btn, button, [role="button"] {{
                    font-size: 14px !important;
                    padding: 8px 12px !important;
                    min-height: 44px !important;
                    line-height: 1.1 !important;
                }}

                /* Inputs/selects: keep font-size >= 16px (no zoom on iOS) */
                input, select, textarea {{
                    font-size: 16px !important;
                    padding: 8px 10px !important;
                    min-height: 44px !important;
                }}

                /* Cards: reduce padding, radius, gaps */
                .permit-card, [data-permit-id] {{
                    padding: 10px 12px !important;
                    border-radius: 10px !important;
                    margin: 8px 0 !important;
                }}
                .permit-header {{
                    gap: 6px !important;
                    margin-bottom: 0.75rem !important;
                }}

                /* County sections: tighter header and spacing */
                .county-header {{
                    padding: 8px 4px !important;
                    margin-bottom: 6px !important;
                }}

                /* Badges/chips smaller */
                .permit-county {{
                    padding: 4px 8px !important;
                    font-size: 12px !important;
                }}

                /* Header adjustments */
                .header {{
                    margin-bottom: 1rem !important;
                    padding: 0.5rem 0 !important;
                }}

                /* Status section adjustments */
                .status {{
                    padding: 0.75rem !important;
                    margin-bottom: 0.75rem !important;
                }}

                /* Container adjustments */
                .container {{
                    padding: 1rem !important;
                }}

                /* More aggressive spacing reduction */
                .county-section {{
                    margin-bottom: 1.5rem !important;
                }}

                .permit-info h3 {{
                    margin-bottom: 0.5rem !important;
                }}

                .permit-detail {{
                    margin-bottom: 0.5rem !important;
                }}

                .permit-actions {{
                    margin-top: 0.75rem !important;
                    gap: 0.5rem !important;
                }}

                /* Filters section */
                .filters-section {{
                    margin: 1rem 0 !important;
                    padding: 1rem !important;
                }}

                .filters-heading {{
                    margin-bottom: 0.75rem !important;
                }}

                .filters-actions {{
                    gap: 0.75rem !important;
                }}

                .controls-spacer {{
                    height: 12px !important;
                }}

                .export-notify {{
                    gap: 0.75rem !important;
                }}

                /* Grid adjustments */
                .permits-grid {{
                    gap: 0.75rem !important;
                }}

                /* Theme toggle adjustments */
                .theme-toggle {{
                    top: 1rem !important;
                    right: 1rem !important;
                    padding: 0.5rem !important;
                }}

                /* Avoid accidental horizontal scroll */
                body {{ 
                    overflow-x: hidden !important; 
                }}
            }}

            /* Ultra small devices */
            @media (max-width: 360px) {{
                body {{ 
                    font-size: 14px !important; 
                }}
                .btn, button {{ 
                    padding: 8px 10px !important; 
                }}
                .permit-card, [data-permit-id] {{ 
                    padding: 8px 10px !important; 
                }}
                .controls {{
                    padding: 0.75rem !important;
                }}
                .header {{
                    margin-bottom: 1rem !important;
                    padding: 0.5rem 0 !important;
                }}
                .container {{
                    padding: 0.75rem !important;
                }}
            }}
        </style>
    </head>
    <body>
        <!-- Theme Toggle Button -->
        <div class="theme-toggle" onclick="toggleTheme()">
            <svg id="theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="5"/>
                <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
            </svg>
        </div>
        
        <div class="container">
            <div class="header">
                <h1>New Permits</h1>
                <p>Texas Railroad Commission Monitor</p>
            </div>
            
            <div class="controls">
                <!-- 1) Sort By -->
                <div class="control-row">
                    <div class="control-group">
                        <label for="sort">Sort By:</label>
                        <select id="sort" name="sort">
                            <option value="newest" {"selected" if sort_by == "newest" else ""}>Most Recent</option>
                            <option value="oldest" {"selected" if sort_by == "oldest" else ""}>Oldest First</option>
                            <option value="county" {"selected" if sort_by == "county" else ""}>County</option>
                            <option value="operator" {"selected" if sort_by == "operator" else ""}>Operator</option>
                        </select>
                    </div>
                </div>
                
                <!-- 2) Counties to Monitor (was Select Counties) -->
                <div class="control-row">
                    <button class="btn btn-info" onclick="openCountySelector()">
                        📍 Counties to Monitor
                    </button>
                </div>
                
                <!-- 3) Update Permits -->
                <div class="control-row">
                    <button class="btn btn-success" onclick="startScraping()">
                        🔄 Update Permits
                    </button>
                </div>
                
                <!-- 4) Filters section -->
                <section class="filters-section">
                    <h2 class="filters-heading">Filters</h2>
                    
                    <!-- 5) Filter Counties (was View Counties) -->
                    <div class="control-row">
                        <button class="btn btn-outline-info" onclick="openViewCountiesSelector()">
                            👁️ Filter Counties
                        </button>
                    </div>
                    
                    <!-- 6) Search with label above input -->
                    <div class="control-row">
                        <div class="control-group">
                            <label for="search">Search:</label>
                            <input type="text" id="search" name="search" placeholder="Search operator or lease name..." value="{search_term}">
                        </div>
                    </div>
                    
                    <!-- 7) Apply / Clear under search -->
                    <div class="control-row filters-actions">
                        <button class="btn btn-primary" onclick="applyFilters()">
                            🔍 Apply Filters
                        </button>
                        <button class="btn btn-outline-primary" onclick="clearFilters()">
                            🗑️ Clear Filters
                        </button>
                    </div>
                </section>
                
                <!-- 8) Spacer then Export/Notifications -->
                <div class="controls-spacer"></div>
                <div class="control-row export-notify">
                    <button class="btn btn-warning" onclick="exportCSV()">
                        📊 Export CSV
                    </button>
                    <button class="btn btn-info" onclick="toggleNotifications()" id="notificationBtn">
                        🔔 Enable Notifications
                    </button>
                    <button class="btn btn-outline-secondary" onclick="sendTestNotification()" id="testNotificationBtn" style="display: none;">
                        🧪 Test Notification
                    </button>
                </div>
            </div>
            
            <div class="status">
                <h3>📊 Status</h3>
                <div class="status-item">
                    <span class="status-label">Update Status:</span>
                    <span class="status-value" id="scraping-status">
                        {scraping_status['is_running'] and 'Updating...' or 'Completed'}
                    </span>
                </div>
                <div class="status-item">
                    <span class="status-label">Last Run:</span>
                    <span class="status-value" id="last-run">
                        {scraping_status['last_run'] or 'Never'}
                    </span>
                </div>
                <div class="status-item">
                    <span class="status-label">Last Count:</span>
                    <span class="status-value" id="last-count">
                        {scraping_status['last_count']} permits
                    </span>
                </div>
                <div class="status-item">
                    <span class="status-label">Monitoring:</span>
                    <span class="status-value" id="monitoring-count">
                        <span id="monitoring-count-text">Loading...</span>
                    </span>
                </div>
                <div class="status-item">
                    <span class="status-label">Total Permits:</span>
                    <span class="status-value">
                        {len(filtered_permits)} permits
                    </span>
                </div>
                <div class="status-item">
                    <span class="status-label">Manage Hidden:</span>
                    <span class="status-value">
                        <a href="#" onclick="openManageHidden()" style="color: #667eea; text-decoration: none;">Restore dismissed items</a>
                    </span>
                </div>
            </div>
            
            <div id="permits-container">
                {''.join([
                    f'''
                    <div class="county-section" data-county="{county}">
                        <div class="county-header">
                            <h2 class="county-title">{county}</h2>
                            <div class="county-menu">
                                <button class="btn btn-outline-secondary btn-sm" onclick="dismissCounty('{county}')">
                                    ⋯ Dismiss County
                                </button>
                            </div>
                        </div>
                        <div class="permits-grid">
                            {''.join([
                                f'''
                                <div class="permit-card" data-permit-id="{permit.id}">
                                    <div class="permit-header">
                                        <span class="permit-county">{permit.county}</span>
                                        <span class="permit-date">{permit.date_issued.strftime('%m/%d/%Y')}</span>
                                    </div>
                                    <div class="permit-info">
                                        <h3 class="truncate-2">{permit.lease_name}</h3>
                                        <div class="permit-detail">
                                            <strong>Operator:</strong>
                                            <span class="truncate-1">{permit.operator}</span>
                                        </div>
                                        <div class="permit-detail">
                                            <strong>Well #:</strong>
                                            <span>{permit.well_number}</span>
                                        </div>
                                        <div class="permit-detail">
                                            <strong>API #:</strong>
                                            <span>{permit.api_number}</span>
                                        </div>
                                    </div>
                                    <div class="permit-actions">
                                        <a href="{permit.rrc_link}" target="_blank" class="btn btn-outline-primary btn-sm">
                                            🔗 Open Permit
                                        </a>
                                        <button class="btn btn-outline-danger btn-sm" onclick="dismissPermit({permit.id})">
                                            ❌ Dismiss
                                        </button>
                                    </div>
                                </div>
                                ''' for permit in [p for p in filtered_permits if p.county == county]
                            ])}
                        </div>
                        <div class="county-empty-state" style="display: none;">
                            <h3>📋 No new permits</h3>
                            <p>No new permits in {county}.</p>
                        </div>
                    </div>
                    ''' for county in sorted(set(p.county for p in filtered_permits))
                ])}
            </div>
            
            <!-- County Selector Modal -->
            <div id="county-selector" class="county-selector">
                <div class="county-modal">
                    <h3>Counties to Monitor</h3>
                    <div class="county-search-container">
                        <input type="text" id="countySearch" class="county-search-input" placeholder="Search counties...">
                    </div>
                    <div class="county-actions">
                        <button class="btn btn-outline-primary btn-sm" onclick="selectAll()">Select All</button>
                        <button class="btn btn-outline-secondary btn-sm" onclick="deselectAll()">Deselect All</button>
                    </div>
                    <div class="county-grid">
                        {''.join([f'''
                        <div class="county-item" data-county="{county}">
                            <input type="checkbox" id="county_{county}" value="{county}">
                            <label for="county_{county}">{county}</label>
                        </div>
                        ''' for county in sorted(TEXAS_COUNTIES)])}
                    </div>
                    <div class="modal-actions">
                        <button class="btn btn-primary" onclick="saveSelectedCounties()">Save Selection</button>
                        <button class="btn btn-outline-secondary" onclick="closeCountySelector()">Cancel</button>
                    </div>
                </div>
            </div>
            
            <!-- View Counties Selector Modal -->
            <div id="view-counties-selector" class="county-selector">
                <div class="county-modal">
                    <h3>Filter Counties</h3>
                    <div class="county-search-container">
                        <input type="text" id="viewCountySearch" class="county-search-input" placeholder="Search counties...">
                    </div>
                    <div class="county-actions">
                        <button class="btn btn-outline-primary btn-sm" onclick="selectAllView()">Select All</button>
                        <button class="btn btn-outline-secondary btn-sm" onclick="deselectAllView()">Deselect All</button>
                        <button class="btn btn-outline-warning btn-sm" onclick="clearViewFilter()">Clear Filter</button>
                    </div>
                    <div class="county-grid">
                        {''.join([f'''
                        <div class="county-item" data-county="{county}">
                            <input type="checkbox" id="view_county_{county}" value="{county}">
                            <label for="view_county_{county}">{county}</label>
                        </div>
                        ''' for county in sorted(set(p.county for p in filtered_permits))])}
                    </div>
                    <div class="modal-actions">
                        <button class="btn btn-primary" onclick="saveViewCounties()">Apply Filter</button>
                        <button class="btn btn-outline-secondary" onclick="closeViewCountiesSelector()">Cancel</button>
                    </div>
                </div>
            </div>
            
            <!-- Manage Hidden Modal -->
            <div id="manage-hidden-modal" class="county-selector">
                <div class="county-modal">
                    <h3>Manage Hidden Items</h3>
                    <div class="hidden-section">
                        <h4>Dismissed Counties</h4>
                        <div id="dismissed-counties-list"></div>
                    </div>
                    <div class="hidden-section">
                        <h4>Dismissed Permits</h4>
                        <div id="dismissed-permits-list"></div>
                    </div>
                    <div class="modal-actions">
                        <button class="btn btn-success" onclick="restoreAllDismissed()">Restore All</button>
                        <button class="btn btn-outline-secondary" onclick="closeManageHidden()">Close</button>
                    </div>
                </div>
            </div>
            
            <script>
            // Utility functions for localStorage
            function getSet(key) {{
                try {{
                    const data = localStorage.getItem(key);
                    return data ? new Set(JSON.parse(data)) : new Set();
                }} catch {{
                    return new Set();
                }}
            }}
            
            function saveSet(key, set) {{
                try {{
                    localStorage.setItem(key, JSON.stringify(Array.from(set)));
                }} catch (e) {{
                    console.error('Error saving to localStorage:', e);
                }}
            }}
            
            function toggleArrayValue(key, value) {{
                const set = getSet(key);
                if (set.has(value)) {{
                    set.delete(value);
                }} else {{
                    set.add(value);
                }}
                saveSet(key, set);
            }}
            
            function initializeStorage() {{
                // Initialize default values if not set
                if (!localStorage.getItem('monitorCounties')) {{
                    saveSet('monitorCounties', new Set());
                }}
                if (!localStorage.getItem('dismissedCountySet')) {{
                    saveSet('dismissedCountySet', new Set());
                }}
                if (!localStorage.getItem('dismissedPermitSet')) {{
                    saveSet('dismissedPermitSet', new Set());
                }}
                if (!localStorage.getItem('viewFilterCounties')) {{
                    saveSet('viewFilterCounties', new Set());
                }}
            }}
            
            function applyFilters() {{
                const search = document.getElementById('search').value;
                const sort = document.getElementById('sort').value;
                const url = new URL(window.location);
                url.searchParams.set('search', search);
                url.searchParams.set('sort', sort);
                window.location.href = url.toString();
            }}
            
            function clearFilters() {{
                document.getElementById('search').value = '';
                document.getElementById('sort').value = 'newest';
                applyFilters();
            }}
            
            function openViewCountiesSelector() {{
                document.getElementById('view-counties-selector').style.display = 'flex';
                loadViewCounties();
            }}
            
            function closeViewCountiesSelector() {{
                document.getElementById('view-counties-selector').style.display = 'none';
            }}
            
            function loadViewCounties() {{
                const viewCounties = getSet('viewFilterCounties');
                const checkboxes = document.querySelectorAll('#view-counties-selector input[type="checkbox"]');
                checkboxes.forEach(checkbox => {{
                    checkbox.checked = viewCounties.has(checkbox.value);
                }});
            }}
            
            function saveViewCounties() {{
                const checkboxes = document.querySelectorAll('#view-counties-selector input[type="checkbox"]:checked');
                const selectedCounties = Array.from(checkboxes).map(cb => cb.value);
                saveSet('viewFilterCounties', new Set(selectedCounties));
                applyViewFilters();
                closeViewCountiesSelector();
            }}
            
            function selectAllView() {{
                const checkboxes = document.querySelectorAll('#view-counties-selector input[type="checkbox"]');
                checkboxes.forEach(checkbox => checkbox.checked = true);
            }}
            
            function deselectAllView() {{
                const checkboxes = document.querySelectorAll('#view-counties-selector input[type="checkbox"]');
                checkboxes.forEach(checkbox => checkbox.checked = false);
            }}
            
            function clearViewFilter() {{
                saveSet('viewFilterCounties', new Set());
                applyViewFilters();
                closeViewCountiesSelector();
            }}
            
            function applyViewFilters() {{
                const viewCounties = getSet('viewFilterCounties');
                const dismissedCounties = getSet('dismissedCountySet');
                const dismissedPermits = getSet('dismissedPermitSet');
                
                // Hide/show county sections
                document.querySelectorAll('.county-section').forEach(section => {{
                    const county = section.getAttribute('data-county');
                    const isDismissed = dismissedCounties.has(county);
                    const isFilteredOut = viewCounties.size > 0 && !viewCounties.has(county);
                    
                    if (isDismissed || isFilteredOut) {{
                        section.style.display = 'none';
                    }} else {{
                        section.style.display = 'block';
                    }}
                }});
                
                // Hide dismissed permits
                document.querySelectorAll('.permit-card').forEach(card => {{
                    const permitId = card.getAttribute('data-permit-id');
                    if (dismissedPermits.has(permitId)) {{
                        card.style.display = 'none';
                    }} else {{
                        card.style.display = 'block';
                    }}
                }});
                
                // Show empty states for counties with no visible permits
                document.querySelectorAll('.county-section').forEach(section => {{
                    if (section.style.display !== 'none') {{
                        const visiblePermits = section.querySelectorAll('.permit-card:not([style*="display: none"])');
                        const emptyState = section.querySelector('.county-empty-state');
                        
                        if (visiblePermits.length === 0) {{
                            emptyState.style.display = 'block';
                        }} else {{
                            emptyState.style.display = 'none';
                        }}
                    }}
                }});
            }}
            
            // Dismissal functionality
            function dismissPermit(permitId) {{
                console.log('Dismissing permit:', permitId);
                if (confirm('Are you sure you want to dismiss this permit?')) {{
                    toggleArrayValue('dismissedPermitSet', permitId.toString());
                    document.querySelector(`[data-permit-id="${{permitId}}"]`).style.display = 'none';
                    applyViewFilters();
                    console.log('Permit dismissed, current dismissed permits:', getSet('dismissedPermitSet'));
                    
                    // Sync preferences with server
                    updatePreferencesOnServer();
                }}
            }}
            
            function dismissCounty(county) {{
                console.log('Dismissing county:', county);
                if (confirm(`Are you sure you want to dismiss all permits in ${{county}} county?`)) {{
                    toggleArrayValue('dismissedCountySet', county);
                    document.querySelector(`[data-county="${{county}}"]`).style.display = 'none';
                    console.log('County dismissed, current dismissed counties:', getSet('dismissedCountySet'));
                    
                    // Sync preferences with server
                    updatePreferencesOnServer();
                }}
            }}
            
            // Manage Hidden functionality
            function openManageHidden() {{
                document.getElementById('manage-hidden-modal').style.display = 'flex';
                loadHiddenItems();
            }}
            
            function closeManageHidden() {{
                document.getElementById('manage-hidden-modal').style.display = 'none';
            }}
            
            function loadHiddenItems() {{
                const dismissedCounties = getSet('dismissedCountySet');
                const dismissedPermits = getSet('dismissedPermitSet');
                
                console.log('Dismissed counties:', dismissedCounties);
                console.log('Dismissed permits:', dismissedPermits);
                
                // Load dismissed counties
                const countiesList = document.getElementById('dismissed-counties-list');
                countiesList.innerHTML = '';
                
                if (dismissedCounties.size === 0) {{
                    countiesList.innerHTML = '<p style="color: var(--text-secondary); font-style: italic;">No dismissed counties</p>';
                }} else {{
                    dismissedCounties.forEach(county => {{
                        const item = document.createElement('div');
                        item.className = 'hidden-item';
                        item.innerHTML = `
                            <span class="hidden-item-name">${{county}}</span>
                            <div class="hidden-item-actions">
                                <button class="btn btn-outline-success btn-sm" onclick="restoreCounty('${{county}}')">Restore</button>
                            </div>
                        `;
                        countiesList.appendChild(item);
                    }});
                }}
                
                // Load dismissed permits
                const permitsList = document.getElementById('dismissed-permits-list');
                permitsList.innerHTML = '';
                
                if (dismissedPermits.size === 0) {{
                    permitsList.innerHTML = '<p style="color: var(--text-secondary); font-style: italic;">No dismissed permits</p>';
                }} else {{
                    permitsList.innerHTML = `<p style="color: var(--text-secondary); margin-bottom: 1rem;">${{dismissedPermits.size}} dismissed permits</p>`;
                    permitsList.innerHTML += `<button class="btn btn-outline-success btn-sm" onclick="restoreAllPermits()">Restore All Permits</button>`;
                }}
            }}
            
            function restoreCounty(county) {{
                const dismissedCounties = getSet('dismissedCountySet');
                dismissedCounties.delete(county);
                saveSet('dismissedCountySet', dismissedCounties);
                loadHiddenItems();
                applyViewFilters();
            }}
            
            function restoreAllPermits() {{
                if (confirm('Are you sure you want to restore all dismissed permits?')) {{
                    saveSet('dismissedPermitSet', new Set());
                    loadHiddenItems();
                    applyViewFilters();
                }}
            }}
            
            function restoreAllDismissed() {{
                if (confirm('Are you sure you want to restore all dismissed items?')) {{
                    saveSet('dismissedCountySet', new Set());
                    saveSet('dismissedPermitSet', new Set());
                    loadHiddenItems();
                    applyViewFilters();
                }}
            }}
            
            function startScraping() {{
                if (document.getElementById('scraping-status').textContent === 'Updating...') {{
                    alert('Update is already in progress!');
                    return;
                }}
                
                document.getElementById('scraping-status').textContent = 'Updating...';
                
                fetch('/api/scrape', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }}
                }})
                .then(response => response.json())
                .then(data => {{
                    alert('Update Started! Check back in 30 seconds.');
                    setTimeout(() => {{
                        location.reload();
                    }}, 35000);
                }})
                .catch(error => {{
                    console.error('Error:', error);
                    alert('Error starting update process');
                    document.getElementById('scraping-status').textContent = 'Error';
                }});
            }}
            
            function openCountySelector() {{
                document.getElementById('county-selector').style.display = 'flex';
                loadMonitoringCounties();
            }}
            
            function loadMonitoringCounties() {{
                const monitorCounties = getSet('monitorCounties');
                const checkboxes = document.querySelectorAll('#county-selector input[type="checkbox"]');
                checkboxes.forEach(checkbox => {{
                    checkbox.checked = monitorCounties.has(checkbox.value);
                }});
            }}
            
            function closeCountySelector() {{
                document.getElementById('county-selector').style.display = 'none';
            }}
            
            function selectAll() {{
                const checkboxes = document.querySelectorAll('#county-selector input[type="checkbox"]');
                checkboxes.forEach(checkbox => checkbox.checked = true);
            }}
            
            function deselectAll() {{
                const checkboxes = document.querySelectorAll('#county-selector input[type="checkbox"]');
                checkboxes.forEach(checkbox => checkbox.checked = false);
            }}
            
            // County search functionality
            document.addEventListener('DOMContentLoaded', function() {{
                const searchInput = document.getElementById('countySearch');
                if (searchInput) {{
                    searchInput.addEventListener('input', function() {{
                        const searchTerm = this.value.toLowerCase();
                        const countyItems = document.querySelectorAll('.county-item');
                        
                        countyItems.forEach(item => {{
                            const countyName = item.getAttribute('data-county');
                            if (countyName.includes(searchTerm)) {{
                                item.style.display = 'block';
                            }} else {{
                                item.style.display = 'none';
                            }}
                        }});
                    }});
                }}
            }});
            
            function saveSelectedCounties() {{
                const checkboxes = document.querySelectorAll('#county-selector input[type="checkbox"]:checked');
                const selectedCounties = Array.from(checkboxes).map(cb => cb.value);
                
                // Save to localStorage for monitoring counties
                saveSet('monitorCounties', new Set(selectedCounties));
                updateMonitoringCount();
                
                // Sync preferences with server
                updatePreferencesOnServer();
                
                alert('Monitoring counties saved!');
                closeCountySelector();
            }}
            
            function exportCSV() {{
                const exportVisible = confirm('Export visible permits only? (Cancel for all permits)');
                const url = exportVisible ? '/export/csv?visible=true' : '/export/csv';
                window.location.href = url;
            }}
            
            
            // Auto-refresh status every 10 seconds
            setInterval(() => {{
                fetch('/api/status')
                .then(response => response.json())
                .then(data => {{
                    document.getElementById('scraping-status').textContent = data.is_running ? 'Updating...' : 'Completed';
                    document.getElementById('last-run').textContent = data.last_run || 'Never';
                    document.getElementById('last-count').textContent = data.last_count + ' permits';
                }})
                .catch(error => console.error('Error updating status:', error));
            }}, 10000);
            
            // Theme toggle functionality
            function toggleTheme() {{
                const body = document.body;
                const themeIcon = document.getElementById('theme-icon');
                const currentTheme = body.getAttribute('data-theme');
                
                if (currentTheme === 'dark') {{
                    body.setAttribute('data-theme', 'light');
                    themeIcon.innerHTML = '<circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>';
                    localStorage.setItem('theme', 'light');
                }} else {{
                    body.setAttribute('data-theme', 'dark');
                    themeIcon.innerHTML = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';
                    localStorage.setItem('theme', 'dark');
                }}
            }}
            
            // Load saved theme on page load
            document.addEventListener('DOMContentLoaded', function() {{
                const savedTheme = localStorage.getItem('theme') || 'light';
                const body = document.body;
                const themeIcon = document.getElementById('theme-icon');
                
                body.setAttribute('data-theme', savedTheme);
                
                if (savedTheme === 'dark') {{
                    themeIcon.innerHTML = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';
                }}
                
                // Initialize localStorage
                initializeStorage();
                
                // Update monitoring count display
                updateMonitoringCount();
                
                // Apply view filters on page load
                applyViewFilters();
                
                // Initialize push notifications
                initializePushNotifications();
            }});
            
            function updateMonitoringCount() {{
                const monitorCounties = getSet('monitorCounties');
                const countText = monitorCounties.size === 0 ? 'All counties' : `${{monitorCounties.size}} counties`;
                document.getElementById('monitoring-count-text').textContent = countText;
            }}
            
            // Device management
            function getOrCreateDeviceId() {{
                let deviceId = localStorage.getItem('deviceId');
                if (!deviceId) {{
                    deviceId = 'device_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
                    localStorage.setItem('deviceId', deviceId);
                }}
                return deviceId;
            }}
            
            // iOS detection
            function isIOS() {{
                return /iPad|iPhone|iPod/.test(navigator.userAgent);
            }}
            
            function isStandalone() {{
                return window.navigator.standalone === true;
            }}
            
            function showIOSBanner() {{
                if (isIOS() && !isStandalone()) {{
                    const banner = document.createElement('div');
                    banner.id = 'ios-banner';
                    banner.style.cssText = `
                        position: fixed;
                        top: 0;
                        left: 0;
                        right: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        padding: 12px;
                        text-align: center;
                        font-size: 14px;
                        z-index: 10000;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.2);
                    `;
                    banner.innerHTML = `
                        📱 Add to Home Screen to receive notifications
                        <button onclick="this.parentElement.remove()" style="margin-left: 10px; background: rgba(255,255,255,0.2); border: none; color: white; padding: 4px 8px; border-radius: 4px;">✕</button>
                    `;
                    document.body.appendChild(banner);
                    
                    // Adjust body padding to account for banner
                    document.body.style.paddingTop = '60px';
                }}
            }}
            
            // Push notification functions
            let isSubscribed = false;
            // Service worker registration is handled in subscribeUser()
            
            function urlBase64ToUint8Array(base64String) {{
                const padding = '='.repeat((4 - base64String.length % 4) % 4);
                const base64 = (base64String + padding)
                    .replace(/-/g, '+')
                    .replace(/_/g, '/');
                
                const rawData = window.atob(base64);
                const outputArray = new Uint8Array(rawData.length);
                
                for (let i = 0; i < rawData.length; ++i) {{
                    outputArray[i] = rawData.charCodeAt(i);
                }}
                return outputArray;
            }}
            
            function arrayBufferToBase64(buffer) {{
                const bytes = new Uint8Array(buffer);
                let binary = '';
                for (let i = 0; i < bytes.byteLength; i++) {{
                    binary += String.fromCharCode(bytes[i]);
                }}
                return window.btoa(binary);
            }}
            
            function updateSubscriptionOnServer(subscription, keys) {{
                console.log('Sending subscription to server:', subscription);
                console.log('Keys being sent:', keys);
                
                const deviceId = getOrCreateDeviceId();
                const preferences = {{
                    monitorCounties: Array.from(getSet('monitorCounties')),
                    dismissedCountySet: Array.from(getSet('dismissedCountySet')),
                    dismissedPermitSet: Array.from(getSet('dismissedPermitSet')),
                    viewFilterCounties: Array.from(getSet('viewFilterCounties'))
                }};
                
                const payload = {{
                    deviceId: deviceId,
                    endpoint: subscription.endpoint,
                    keys: keys,
                    preferences: preferences
                }};
                
                console.log('Payload being sent:', payload);
                console.log('Payload keys:', payload.keys);
                
                return fetch('/api/push/subscribe', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify(payload)
                }});
            }}
            
            function updatePreferencesOnServer() {{
                const deviceId = getOrCreateDeviceId();
                const preferences = {{
                    monitorCounties: Array.from(getSet('monitorCounties')),
                    dismissedCountySet: Array.from(getSet('dismissedCountySet')),
                    dismissedPermitSet: Array.from(getSet('dismissedPermitSet')),
                    viewFilterCounties: Array.from(getSet('viewFilterCounties'))
                }};
                
                return fetch('/api/push/prefs', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{
                        deviceId: deviceId,
                        preferences: preferences
                    }})
                }});
            }}
            
            async function unsubscribeUser() {{
                try {{
                    // Get the service worker registration
                    const registration = await navigator.serviceWorker.ready;
                    const subscription = await registration.pushManager.getSubscription();
                    
                    if (subscription) {{
                        await subscription.unsubscribe();
                        
                        // Send unsubscribe request to server
                        await fetch('/api/push/unsubscribe', {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json',
                            }},
                            body: JSON.stringify({{
                                endpoint: subscription.endpoint
                            }})
                        }});
                    }}
                    
                    console.log('User is unsubscribed.');
                    isSubscribed = false;
                    updateBtn();
                    
                }} catch (error) {{
                    console.log('Error unsubscribing', error);
                }}
            }}
            
            async function subscribeUser() {{
                console.log('Attempting to subscribe user...');
                
                try {{
                    // Check if service worker and push are supported
                    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {{
                        alert('Push notifications not supported in this browser');
                        return;
                    }}
                    
                    // 1) Register service worker at root path
                    let reg;
                    try {{
                        reg = await navigator.serviceWorker.register('/sw.js', {{ scope: '/' }});
                        await navigator.serviceWorker.ready; // ensure active
                        console.log('Service worker registered and ready');
                    }} catch (e) {{
                        console.error('SW register failed', e);
                        alert('Could not register service worker.');
                        return;
                    }}
                    
                    // 2) Ask permission
                    const perm = await Notification.requestPermission();
                    if (perm !== 'granted') {{
                        alert('Notifications not allowed');
                        return;
                    }}
                    
                    // 3) Get public key
                    const response = await fetch('/api/vapid-public-key');
                    const data = await response.json();
                    if (!data.publicKey) {{
                        alert('Public key missing on server');
                        return;
                    }}
                    console.log('Received public key from server');
                    
                    // 4) Subscribe using the ready service worker
                    const ready = await navigator.serviceWorker.ready;
                    const subscription = await ready.pushManager.subscribe({{
                        userVisibleOnly: true,
                        applicationServerKey: urlBase64ToUint8Array(data.publicKey)
                    }});
                    
                    console.log('User is subscribed:', subscription);
                    
                    // Extract keys using getKey() method
                    const p256dh = subscription.getKey('p256dh');
                    const auth = subscription.getKey('auth');
                    
                    console.log('p256dh key:', p256dh);
                    console.log('auth key:', auth);
                    
                    // Convert ArrayBuffer to base64 string
                    const p256dhBase64 = p256dh ? arrayBufferToBase64(p256dh) : '';
                    const authBase64 = auth ? arrayBufferToBase64(auth) : '';
                    
                    console.log('p256dh base64:', p256dhBase64);
                    console.log('auth base64:', authBase64);
                    
                    // Create keys object
                    const keys = {{
                        p256dh: p256dhBase64,
                        auth: authBase64
                    }};
                    
                    console.log('Keys object:', keys);
                    
                    // 5) Send subscription to server
                    const serverResponse = await updateSubscriptionOnServer(subscription, keys);
                    console.log('Server response:', serverResponse);
                    
                    if (serverResponse.ok) {{
                        isSubscribed = true;
                        updateBtn();
                        console.log('Successfully subscribed!');
                        alert('Notifications enabled on this device.');
                    }} else {{
                        console.error('Server subscription failed:', serverResponse);
                        throw new Error('Server subscription failed');
                    }}
                    
                }} catch (err) {{
                    console.log('Failed to subscribe the user:', err);
                    alert('Failed to enable notifications. Please try again.');
                }}
            }}
            
            function updateBtn() {{
                const btn = document.getElementById('notificationBtn');
                const testBtn = document.getElementById('testNotificationBtn');
                
                if (isSubscribed) {{
                    btn.textContent = '🔕 Disable Notifications';
                    btn.onclick = unsubscribeUser;
                    // Show test button in debug mode
                    if (testBtn) {{
                        testBtn.style.display = 'inline-flex';
                    }}
                }} else {{
                    btn.textContent = '🔔 Enable Notifications';
                    btn.onclick = subscribeUser;
                    // Hide test button when not subscribed
                    if (testBtn) {{
                        testBtn.style.display = 'none';
                    }}
                }}
            }}
            
            async function toggleNotifications() {{
                if (isSubscribed) {{
                    unsubscribeUser();
                }} else {{
                    await subscribeUser();
                }}
            }}
            
            function sendTestNotification() {{
                const deviceId = getOrCreateDeviceId();
                
                fetch('/api/push/test', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{ deviceId: deviceId }})
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        alert('Test notification sent!');
                    }} else {{
                        alert('Failed to send test notification: ' + data.error);
                    }}
                }})
                .catch(error => {{
                    console.error('Error sending test notification:', error);
                    alert('Error sending test notification');
                }});
            }}
            
            function initializePushNotifications() {{
                // Show iOS banner if needed
                showIOSBanner();
                
                // Always show the notification button initially
                const btn = document.getElementById('notificationBtn');
                if (btn) {{
                    btn.style.display = 'inline-flex';
                    btn.style.visibility = 'visible';
                    console.log('Notification button made visible');
                }} else {{
                    console.error('Notification button not found!');
                }}
                
                // Check if push notifications are available on the server
                fetch('/api/vapid-public-key')
                .then(response => {{
                    if (!response.ok) {{
                        console.warn('Push notifications not available on server, but showing button anyway');
                        // Don't hide the button - let user try anyway
                        return;
                    }}
                    
                    if ('serviceWorker' in navigator && 'PushManager' in window) {{
                        console.log('Service Worker and Push is supported');
                        // Service worker will be registered when user clicks Enable Notifications
                    }} else {{
                        console.warn('Push messaging is not supported, but showing button anyway');
                        // Don't hide the button - let user try anyway
                    }}
                }})
                .catch(function(error) {{
                    console.warn('Failed to check push notification availability, but showing button anyway:', error);
                    // Don't hide the button - let user try anyway
                }});
            }}
        </script>
    </body>
    </html>
    """
    return html

# Routes
@app.route('/')
def index():
    return generate_html()

@app.route('/api/scrape', methods=['POST'])
def api_scrape():
    if scraping_status['is_running']:
        return jsonify({'error': 'Update already in progress'}), 400
    
    # Start scraping in background thread
    thread = threading.Thread(target=scrape_rrc_permits)
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Update started'})

@app.route('/api/status')
def api_status():
    return jsonify(scraping_status)

@app.route('/api/permits')
def api_permits():
    permits = Permit.query.order_by(Permit.created_at.desc()).all()
    return jsonify([{
        'id': p.id,
        'county': p.county,
        'operator': p.operator,
        'lease_name': p.lease_name,
        'well_number': p.well_number,
        'api_number': p.api_number,
        'date_issued': p.date_issued.isoformat(),
        'rrc_link': p.rrc_link,
        'created_at': p.created_at.isoformat()
    } for p in permits])

@app.route('/api/counties')
def api_counties():
    return jsonify(list(TEXAS_COUNTIES))

@app.route('/api/selected-counties', methods=['GET', 'POST'])
def api_selected_counties():
    if request.method == 'POST':
        data = request.get_json()
        counties = data.get('counties', [])
        
        # Store in database for push notifications
        session_id = session.get('session_id', 'default')
        settings = get_or_create_user_settings(session_id)
        settings.selected_counties = json.dumps(counties)
        db.session.commit()
        
        # Also store in session for backward compatibility
        session['selected_counties'] = counties
        return jsonify({'success': True})
    else:
        # Get from database first, fallback to session
        session_id = session.get('session_id', 'default')
        settings = UserSettings.query.filter_by(session_id=session_id).first()
        if settings and settings.selected_counties:
            try:
                return jsonify(json.loads(settings.selected_counties))
            except:
                pass
        return jsonify(session.get('selected_counties', []))

@app.route('/api/push/subscribe', methods=['POST'])
def api_push_subscribe():
    """Subscribe to push notifications with device-scoped preferences"""
    data = request.get_json()
    
    # Debug: Print received data
    print(f"DEBUG: Received subscription data: {data}")
    
    if not data or not data.get('endpoint'):
        return jsonify({'error': 'Missing subscription data'}), 400
    
    if not data.get('deviceId'):
        return jsonify({'error': 'Missing deviceId'}), 400
    
    try:
        device_id = data['deviceId']
        endpoint = data['endpoint']
        prefs_json = json.dumps(data.get('preferences', {}))
        
        # Extract keys with debugging
        keys = data.get('keys', {})
        p256dh = keys.get('p256dh', '')
        auth = keys.get('auth', '')
        
        print(f"DEBUG: Extracted keys - p256dh length: {len(p256dh)}, auth length: {len(auth)}")
        print(f"DEBUG: p256dh: '{p256dh[:50]}...' (first 50 chars)")
        print(f"DEBUG: auth: '{auth[:50]}...' (first 50 chars)")
        
        # Upsert subscription by endpoint
        existing = DeviceSubscription.query.filter_by(endpoint=endpoint).first()
        
        if existing:
            # Update existing subscription
            existing.device_id = device_id
            existing.p256dh = p256dh
            existing.auth = auth
            existing.prefs_json = prefs_json
            existing.user_agent = request.headers.get('User-Agent', '')
            existing.updated_at = datetime.utcnow()
            existing.error_count = 0  # Reset error count on successful subscription
            existing.last_error = None
            print(f"DEBUG: Updated existing subscription with keys")
        else:
            # Create new subscription
            subscription = DeviceSubscription(
                device_id=device_id,
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                prefs_json=prefs_json,
                user_agent=request.headers.get('User-Agent', '')
            )
            db.session.add(subscription)
            print(f"DEBUG: Created new subscription with keys")
        
        db.session.commit()
        
        print(f"Device subscription {'updated' if existing else 'created'} for device {device_id}")
        return jsonify({'success': True, 'message': 'Subscribed to notifications'})
        
    except Exception as e:
        print(f"Error subscribing device: {e}")
        return jsonify({'error': 'Failed to subscribe'}), 500

@app.route('/api/push/unsubscribe', methods=['POST'])
def api_push_unsubscribe():
    """Unsubscribe from push notifications"""
    data = request.get_json()
    
    if not data or not data.get('endpoint'):
        return jsonify({'error': 'Missing endpoint'}), 400
    
    try:
        endpoint = data['endpoint']
        subscription = DeviceSubscription.query.filter_by(endpoint=endpoint).first()
        
        if subscription:
            db.session.delete(subscription)
            db.session.commit()
            print(f"Device unsubscribed: {subscription.device_id}")
            return jsonify({'success': True, 'message': 'Unsubscribed from notifications'})
        else:
            return jsonify({'success': True, 'message': 'Subscription not found'})
            
    except Exception as e:
        print(f"Error unsubscribing: {e}")
        return jsonify({'error': 'Failed to unsubscribe'}), 500

@app.route('/api/push/prefs', methods=['POST'])
def api_push_prefs():
    """Update preferences for a device"""
    data = request.get_json()
    
    if not data or not data.get('deviceId'):
        return jsonify({'error': 'Missing deviceId'}), 400
    
    try:
        device_id = data['deviceId']
        prefs_json = json.dumps(data.get('preferences', {}))
        
        subscription = DeviceSubscription.query.filter_by(device_id=device_id).first()
        
        if subscription:
            subscription.prefs_json = prefs_json
            subscription.updated_at = datetime.utcnow()
            db.session.commit()
            print(f"Updated preferences for device {device_id}")
            return jsonify({'success': True, 'message': 'Preferences updated'})
        else:
            return jsonify({'error': 'Device not found'}), 404
            
    except Exception as e:
        print(f"Error updating preferences: {e}")
        return jsonify({'error': 'Failed to update preferences'}), 500

@app.route('/api/push/test', methods=['POST'])
def api_push_test():
    """Send a test notification"""
    # Allow test notifications in production for debugging
    
    data = request.get_json()
    device_id = data.get('deviceId')
    
    if not device_id:
        return jsonify({'error': 'Missing deviceId'}), 400
    
    try:
        subscription = DeviceSubscription.query.filter_by(device_id=device_id).first()
        
        if not subscription:
            return jsonify({'error': 'Device not found'}), 404
        
        subscription_data = {
            "endpoint": subscription.endpoint,
            "keys": {
                "p256dh": subscription.p256dh,
                "auth": subscription.auth
            }
        }
        
        success = send_push_notification(
            subscription_data,
            "Test Notification",
            "This is a test notification from RRC Monitor",
            "/"
        )
        
        if success:
            return jsonify({'success': True, 'message': 'Test notification sent'})
        else:
            return jsonify({'error': 'Failed to send test notification'}), 500
            
    except Exception as e:
        print(f"Error sending test notification: {e}")
        return jsonify({'error': 'Failed to send test notification'}), 500

# Legacy endpoint for backward compatibility
@app.route('/api/subscribe', methods=['POST'])
def api_subscribe():
    """Legacy subscribe endpoint - redirects to new device-scoped system"""
    return jsonify({'error': 'Please use /api/push/subscribe with deviceId'}), 400

@app.route('/api/unsubscribe', methods=['POST'])
def api_unsubscribe():
    """Unsubscribe from push notifications"""
    data = request.get_json()
    
    if not data or not data.get('endpoint'):
        return jsonify({'error': 'Missing endpoint'}), 400
    
    try:
        Subscription.query.filter_by(endpoint=data['endpoint']).delete()
        db.session.commit()
        return jsonify({'success': True, 'message': 'Unsubscribed from notifications'})
    except Exception as e:
        print(f"Error unsubscribing: {e}")
        return jsonify({'error': 'Failed to unsubscribe'}), 500

@app.route('/api/vapid-public-key')
def api_vapid_public_key():
    """Get VAPID public key for push notifications"""
    # Always return the VAPID public key, even if pywebpush isn't available
    return jsonify({'publicKey': VAPID_PUBLIC_KEY})

@app.route('/static/mobile-compact.css')
def serve_mobile_css():
    """Serve the mobile compact CSS"""
    return send_from_directory('static', 'mobile-compact.css', mimetype='text/css')

@app.route('/static/manifest.webmanifest')
def serve_manifest():
    """Serve the web app manifest"""
    return send_from_directory('static', 'manifest.webmanifest', mimetype='application/manifest+json')

@app.route('/sw.js')
def service_worker():
    """Serve the service worker at root with no cache"""
    print("DEBUG: Serving inline service worker")
    content = """self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {};
  const title = data.title || 'New permit';
  const body  = data.body  || '';
  const opts = {
    body,
    data: data.data || {},
    icon: '/static/icon-512.png',
    badge: '/static/icon-512.png'
  };
  event.waitUntil(self.registration.showNotification(title, opts));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(clients.matchAll({ type:'window', includeUncontrolled:true }).then(list => {
    for (const c of list) {
      if ('focus' in c) { c.navigate(url); return c.focus(); }
    }
    if (clients.openWindow) return clients.openWindow(url);
  }));
});"""
    print(f"DEBUG: Service worker content length: {len(content)}")
    resp = app.response_class(content, mimetype='application/javascript')
    resp.headers['Cache-Control'] = 'no-cache'
    return resp

@app.route('/manifest.webmanifest')
def manifest():
    """Serve the manifest at root with no cache"""
    print("DEBUG: Serving inline manifest")
    content = """{
  "name": "Permit Watch",
  "short_name": "Permits",
  "start_url": "/?source=pwa",
  "display": "standalone",
  "background_color": "#0E1525",
  "theme_color": "#0E1525",
  "icons": [
    { "src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png" },
    { "src": "/static/apple-touch-icon.png", "sizes": "180x180", "type": "image/png" }
  ]
}"""
    print(f"DEBUG: Manifest content length: {len(content)}")
    resp = app.response_class(content, mimetype='application/manifest+json')
    resp.headers['Cache-Control'] = 'no-cache'
    return resp

@app.route('/debug/files')
def debug_files():
    """Debug route to check what files are available"""
    import os
    try:
        files = os.listdir('static')
        return f"Files in static directory: {files}"
    except Exception as e:
        return f"Error listing files: {e}"

@app.route('/debug/sw')
def debug_sw():
    """Debug route to check service worker file"""
    try:
        with open('static/sw.js', 'r') as f:
            content = f.read()
        return f"Service worker content (first 200 chars): {content[:200]}..."
    except Exception as e:
        return f"Error reading service worker: {e}"

@app.route('/static/icon-512.png')
def serve_icon_512():
    """Serve the main app icon"""
    return send_from_directory('static', 'icon-512.png', mimetype='image/png')

@app.route('/static/apple-touch-icon.png')
def serve_apple_touch_icon():
    """Serve the Apple touch icon"""
    return send_from_directory('static', 'apple-touch-icon.png', mimetype='image/png')

@app.route('/static/apple-touch-icon-120x120.png')
def serve_apple_touch_icon_120():
    """Serve the Apple touch icon 120x120"""
    return send_from_directory('static', 'apple-touch-icon-120x120.png', mimetype='image/png')

@app.route('/api/dismiss/<int:permit_id>', methods=['POST'])
def api_dismiss_permit(permit_id):
    """Dismiss a permit by removing it from the database"""
    try:
        permit = Permit.query.get(permit_id)
        if permit:
            db.session.delete(permit)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Permit dismissed successfully'})
        else:
            return jsonify({'success': False, 'error': 'Permit not found'}), 404
    except Exception as e:
        print(f"Error dismissing permit: {e}")
        return jsonify({'success': False, 'error': 'Failed to dismiss permit'}), 500

@app.route('/api/push-status')
def api_push_status():
    """Test endpoint to check push notification setup"""
    return jsonify({
        'pywebpush_available': PUSH_NOTIFICATIONS_AVAILABLE,
        'vapid_configured': bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY),
        'service_worker_exists': True,  # We know this exists
        'status': 'Push notifications should work' if PUSH_NOTIFICATIONS_AVAILABLE else 'Limited functionality - pywebpush not available'
    })

@app.route('/api/debug-push')
def api_debug_push():
    """Debug endpoint for push notification troubleshooting"""
    subscriptions = Subscription.query.all()
    return jsonify({
        'total_subscriptions': len(subscriptions),
        'subscriptions': [{
            'id': s.id,
            'endpoint': s.endpoint[:50] + '...' if len(s.endpoint) > 50 else s.endpoint,
            'session_id': s.session_id,
            'created_at': s.created_at.isoformat()
        } for s in subscriptions],
        'vapid_public_key': VAPID_PUBLIC_KEY[:50] + '...' if len(VAPID_PUBLIC_KEY) > 50 else VAPID_PUBLIC_KEY,
        'pywebpush_available': PUSH_NOTIFICATIONS_AVAILABLE
    })

@app.route('/export/csv')
def export_csv():
    visible_only = request.args.get('visible', 'false').lower() == 'true'
    
    if visible_only:
        # For visible-only export, we need to get the client-side filters
        # This is a simplified version - in a real app you'd pass the filters as parameters
        permits = Permit.query.order_by(Permit.created_at.desc()).all()
        # Note: Full client-side filtering would require passing dismissed IDs as parameters
        # For now, we'll export all permits and let the client handle filtering
    else:
        permits = Permit.query.order_by(Permit.created_at.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['County', 'Operator', 'Lease Name', 'Well Number', 'API Number', 'Date Issued', 'RRC Link'])
    
    for permit in permits:
        writer.writerow([
            permit.county,
            permit.operator,
            permit.lease_name,
            permit.well_number,
            permit.api_number,
            permit.date_issued.strftime('%Y-%m-%d'),
            permit.rrc_link
        ])
    
    output.seek(0)
    
    filename_suffix = '_visible' if visible_only else '_all'
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'rrc_permits_{datetime.now().strftime("%Y%m%d")}{filename_suffix}.csv'
    )

# Automatic scraping scheduler
def start_scraping_scheduler():
    """Start the automatic scraping scheduler"""
    def scrape_periodically():
        while True:
            try:
                print(f"Starting automatic scrape at {datetime.now()}")
                scrape_rrc_permits()
                print(f"Automatic scrape completed at {datetime.now()}")
            except Exception as e:
                print(f"Error in automatic scrape: {e}")
                import traceback
                traceback.print_exc()
            
            # Wait 5 minutes (300 seconds) before next scrape
            time.sleep(300)
    
    # Start the scheduler in a background thread
    scheduler_thread = threading.Thread(target=scrape_periodically)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    print("Automatic scraping scheduler started (every 5 minutes)")

# Initialize database when the module is imported (works with Gunicorn)
with app.app_context():
    try:
        db.create_all()
        print("Database initialized successfully")
        
        # Test database connection
        result = db.session.execute(db.text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = [row[0] for row in result]
        print(f"Database tables: {tables}")
        
        # Start automatic scraping scheduler
        start_scraping_scheduler()
        
    except Exception as e:
        print(f"Database initialization error: {e}")
        import traceback
        traceback.print_exc()

@app.route('/api/push/debug')
def push_debug():
    """Debug endpoint to check push notification dependencies and VAPID keys"""
    import os
    import importlib
    
    def check_module(module_name):
        try:
            importlib.import_module(module_name)
            return True
        except ImportError:
            return False
    
    return jsonify({
        'pywebpush_installed': check_module('pywebpush'),
        'cryptography_installed': check_module('cryptography'),
        'vapid_public_present': bool(os.getenv('VAPID_PUBLIC_KEY')),
        'vapid_private_present': bool(os.getenv('VAPID_PRIVATE_KEY')),
        'vapid_subject_present': bool(os.getenv('VAPID_SUBJECT')),
        'push_notifications_available': PUSH_NOTIFICATIONS_AVAILABLE
    })

if __name__ == '__main__':
    print("🚀 Starting RRC Monitor Application...")
    print(f"📊 Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    # Handle Railway's PORT environment variable properly
    port_str = os.environ.get('PORT', '8080')
    print(f"🔍 Raw PORT environment variable: '{port_str}'")
    
    try:
        port = int(port_str)
    except (ValueError, TypeError):
        print(f"⚠️ Invalid PORT value '{port_str}', using default 8080")
        port = 8080
    
    print(f"🌐 Host: 0.0.0.0")
    print(f"🔌 Port: {port}")
    try:
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
    except Exception as e:
        print(f"❌ Failed to start application: {e}")
        import traceback
        traceback.print_exc()
