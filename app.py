from flask import Flask, render_template, request, jsonify, session, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import requests
from bs4 import BeautifulSoup
import threading
import time
import os
import csv
import io
from urllib.parse import urljoin

app = Flask(__name__)
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

# Global scraping status
scraping_status = {
    'is_running': False,
    'last_run': None,
    'last_count': 0,
    'error': None
}

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
                        
                        if permits:
                            print(f"✅ Found {len(permits)} permits via Selenium")
                            scraping_status['last_count'] = len(permits)
                            return
                        else:
                            print("No permits found in results")
                            
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
                    # Extract data based on typical RRC table structure
                    # Status Date, Status #, API No., Operator Name/Number, Lease Name, Well #, Dist., County, etc.
                    
                    api_number = cells[2].get_text(strip=True) if len(cells) > 2 else ''
                    operator = cells[3].get_text(strip=True) if len(cells) > 3 else ''
                    lease_name = cells[4].get_text(strip=True) if len(cells) > 4 else ''
                    well_number = cells[5].get_text(strip=True) if len(cells) > 5 else ''
                    
                    # Find county in later columns
                    county = ''
                    for cell in cells[6:]:
                        cell_text = cell.get_text(strip=True)
                        if cell_text and cell_text.upper() in [c.upper() for c in TEXAS_COUNTIES]:
                            county = cell_text.upper()
                            break
                    
                    # Skip header rows or invalid data
                    if not api_number or not operator or 'api' in api_number.lower() or 'status' in api_number.lower():
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
    county_filter = request.args.get('county', '')
    search_term = request.args.get('search', '')
    sort_by = request.args.get('sort', 'newest')
    
    print(f"DEBUG: Filters - county: '{county_filter}', search: '{search_term}', sort: '{sort_by}'")
    
    filtered_permits = permits
    
    if county_filter and county_filter != 'All Counties':
        filtered_permits = [p for p in filtered_permits if p.county.upper() == county_filter.upper()]
    
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
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Texas Railroad Commission Drilling Permits</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #f5f5f5;
                color: #333;
                line-height: 1.6;
            }}
            
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
            }}
            
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px 0;
                text-align: center;
                margin-bottom: 30px;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            }}
            
            .header h1 {{
                font-size: 2.5rem;
                margin-bottom: 10px;
                font-weight: 700;
            }}
            
            .header p {{
                font-size: 1.1rem;
                opacity: 0.9;
            }}
            
            .controls {{
                background: white;
                padding: 25px;
                border-radius: 15px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                margin-bottom: 30px;
            }}
            
            .control-row {{
                display: flex;
                flex-wrap: wrap;
                gap: 15px;
                align-items: center;
                margin-bottom: 20px;
            }}
            
            .control-group {{
                display: flex;
                flex-direction: column;
                min-width: 200px;
            }}
            
            .control-group label {{
                font-weight: 600;
                margin-bottom: 5px;
                color: #555;
            }}
            
            .control-group select,
            .control-group input {{
                padding: 12px;
                border: 2px solid #e1e5e9;
                border-radius: 8px;
                font-size: 16px;
                transition: border-color 0.3s;
            }}
            
            .control-group select:focus,
            .control-group input:focus {{
                outline: none;
                border-color: #667eea;
            }}
            
            .buttons {{
                display: flex;
                flex-wrap: wrap;
                gap: 15px;
                margin-top: 20px;
            }}
            
            .btn {{
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s;
                text-decoration: none;
                display: inline-flex;
                align-items: center;
                gap: 8px;
            }}
            
            .btn-primary {{
                background: #667eea;
                color: white;
            }}
            
            .btn-primary:hover {{
                background: #5a6fd8;
                transform: translateY(-2px);
            }}
            
            .btn-success {{
                background: #28a745;
                color: white;
            }}
            
            .btn-success:hover {{
                background: #218838;
                transform: translateY(-2px);
            }}
            
            .btn-info {{
                background: #17a2b8;
                color: white;
            }}
            
            .btn-info:hover {{
                background: #138496;
                transform: translateY(-2px);
            }}
            
            .btn-warning {{
                background: #ffc107;
                color: #212529;
            }}
            
            .btn-warning:hover {{
                background: #e0a800;
                transform: translateY(-2px);
            }}
            
            .status {{
                background: white;
                padding: 20px;
                border-radius: 15px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                margin-bottom: 30px;
            }}
            
            .status h3 {{
                margin-bottom: 15px;
                color: #333;
            }}
            
            .status-item {{
                display: flex;
                justify-content: space-between;
                padding: 8px 0;
                border-bottom: 1px solid #eee;
            }}
            
            .status-item:last-child {{
                border-bottom: none;
            }}
            
            .status-label {{
                font-weight: 600;
                color: #555;
            }}
            
            .status-value {{
                color: #333;
            }}
            
            .permits-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
                gap: 20px;
                margin-top: 30px;
            }}
            
            .permit-card {{
                background: white;
                border-radius: 15px;
                padding: 25px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                transition: transform 0.3s, box-shadow 0.3s;
            }}
            
            .permit-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 10px 25px rgba(0,0,0,0.15);
            }}
            
            .permit-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
            }}
            
            .permit-county {{
                background: #667eea;
                color: white;
                padding: 6px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
            }}
            
            .permit-date {{
                color: #666;
                font-size: 14px;
            }}
            
            .permit-info {{
                margin-bottom: 20px;
            }}
            
            .permit-info h3 {{
                color: #333;
                margin-bottom: 10px;
                font-size: 1.2rem;
            }}
            
            .permit-detail {{
                margin-bottom: 8px;
                display: flex;
                align-items: center;
            }}
            
            .permit-detail strong {{
                min-width: 80px;
                color: #555;
                font-size: 14px;
            }}
            
            .permit-detail span {{
                color: #333;
                font-size: 14px;
            }}
            
            .permit-actions {{
                display: flex;
                gap: 10px;
            }}
            
            .btn-sm {{
                padding: 8px 16px;
                font-size: 14px;
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
                color: #dc3545;
                border: 2px solid #dc3545;
            }}
            
            .btn-outline-danger:hover {{
                background: #dc3545;
                color: white;
            }}
            
            .no-permits {{
                text-align: center;
                padding: 60px 20px;
                color: #666;
                background: white;
                border-radius: 15px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            }}
            
            .no-permits h3 {{
                margin-bottom: 15px;
                color: #333;
            }}
            
            .loading {{
                text-align: center;
                padding: 40px;
                color: #666;
            }}
            
            .spinner {{
                border: 4px solid #f3f3f3;
                border-top: 4px solid #667eea;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 0 auto 20px;
            }}
            
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            
            .county-selector {{
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0,0,0,0.5);
                z-index: 1000;
                display: none;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            
            .county-modal {{
                background: white;
                border-radius: 15px;
                padding: 30px;
                max-width: 600px;
                width: 100%;
                max-height: 80vh;
                overflow-y: auto;
            }}
            
            .county-modal h3 {{
                margin-bottom: 20px;
                color: #333;
            }}
            
            .county-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
                gap: 10px;
                margin-bottom: 20px;
            }}
            
            .county-item {{
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            
            .county-item input[type="checkbox"] {{
                width: 18px;
                height: 18px;
            }}
            
            .county-item label {{
                font-size: 14px;
                cursor: pointer;
            }}
            
            .modal-actions {{
                display: flex;
                gap: 15px;
                justify-content: flex-end;
                margin-top: 20px;
            }}
            
            @media (max-width: 768px) {{
                .container {{
                    padding: 10px;
                }}
                
                .header h1 {{
                    font-size: 2rem;
                }}
                
                .control-row {{
                    flex-direction: column;
                    align-items: stretch;
                }}
                
                .control-group {{
                    min-width: auto;
                }}
                
                .buttons {{
                    flex-direction: column;
                }}
                
                .permits-grid {{
                    grid-template-columns: 1fr;
                }}
                
                .permit-actions {{
                    flex-direction: column;
                }}
                
                .county-grid {{
                    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🏗️ Texas Railroad Commission</h1>
                <p>Drilling Permits Monitor</p>
            </div>
            
            <div class="controls">
                <div class="control-row">
                    <div class="control-group">
                        <label for="county">County:</label>
                        <select id="county" name="county">
                            <option value="">All Counties</option>
                            {''.join([f'<option value="{county}" {"selected" if county == county_filter else ""}>{county}</option>' for county in counties])}
                        </select>
                    </div>
                    
                    <div class="control-group">
                        <label for="search">Search Operator/Lease:</label>
                        <input type="text" id="search" name="search" placeholder="Enter operator or lease name..." value="{search_term}">
                    </div>
                    
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
                
                <div class="buttons">
                    <button class="btn btn-primary" onclick="applyFilters()">
                        🔍 Search
                    </button>
                    <button class="btn btn-success" onclick="startScraping()">
                        🔄 Scrape New Permits
                    </button>
                    <button class="btn btn-info" onclick="openCountySelector()">
                        📍 Select Counties
                    </button>
                    <button class="btn btn-warning" onclick="exportCSV()">
                        📊 Export CSV
                    </button>
                </div>
            </div>
            
            <div class="status">
                <h3>📊 Status</h3>
                <div class="status-item">
                    <span class="status-label">Scraping Status:</span>
                    <span class="status-value" id="scraping-status">
                        {scraping_status['is_running'] and 'Running...' or 'Completed'}
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
                    <span class="status-label">Total Permits:</span>
                    <span class="status-value">
                        {len(filtered_permits)} permits
                    </span>
                </div>
            </div>
            
            {f'''
            <div class="permits-grid">
                {''.join([f'''
                <div class="permit-card">
                    <div class="permit-header">
                        <span class="permit-county">{permit.county}</span>
                        <span class="permit-date">{permit.date_issued.strftime('%m/%d/%Y')}</span>
                    </div>
                    <div class="permit-info">
                        <h3>{permit.lease_name}</h3>
                        <div class="permit-detail">
                            <strong>Operator:</strong>
                            <span>{permit.operator}</span>
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
                ''' for permit in filtered_permits])}
            </div>
            ''' if filtered_permits else '''
            <div class="no-permits">
                <h3>📋 No permits found</h3>
                <p>Try adjusting your search criteria or scrape for new permits.</p>
            </div>
            '''}
            
            <div class="county-selector" id="county-selector">
                <div class="county-modal">
                    <h3>📍 Select Counties to Monitor</h3>
                    <div class="county-grid">
                        {''.join([f'''
                        <div class="county-item">
                            <input type="checkbox" id="county-{county}" value="{county}" {"checked" if county in selected_counties else ""}>
                            <label for="county-{county}">{county}</label>
                        </div>
                        ''' for county in TEXAS_COUNTIES])}
                    </div>
                    <div class="modal-actions">
                        <button class="btn btn-outline-primary" onclick="selectAll()">Select All</button>
                        <button class="btn btn-outline-primary" onclick="deselectAll()">Deselect All</button>
                        <button class="btn btn-primary" onclick="saveSelectedCounties()">Save Selection</button>
                        <button class="btn btn-outline-danger" onclick="closeCountySelector()">Cancel</button>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            function applyFilters() {{
                const county = document.getElementById('county').value;
                const search = document.getElementById('search').value;
                const sort = document.getElementById('sort').value;
                
                const params = new URLSearchParams();
                if (county) params.append('county', county);
                if (search) params.append('search', search);
                if (sort) params.append('sort', sort);
                
                window.location.href = '?' + params.toString();
            }}
            
            function startScraping() {{
                if (document.getElementById('scraping-status').textContent === 'Running...') {{
                    alert('Scraping is already in progress!');
                    return;
                }}
                
                document.getElementById('scraping-status').textContent = 'Running...';
                
                fetch('/api/scrape', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }}
                }})
                .then(response => response.json())
                .then(data => {{
                    alert('Scraping Started! Check back in 30 seconds.');
                    setTimeout(() => {{
                        location.reload();
                    }}, 35000);
                }})
                .catch(error => {{
                    console.error('Error:', error);
                    alert('Error starting scraping process');
                    document.getElementById('scraping-status').textContent = 'Error';
                }});
            }}
            
            function openCountySelector() {{
                document.getElementById('county-selector').style.display = 'flex';
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
            
            function saveSelectedCounties() {{
                const checkboxes = document.querySelectorAll('#county-selector input[type="checkbox"]:checked');
                const selectedCounties = Array.from(checkboxes).map(cb => cb.value);
                
                fetch('/api/selected-counties', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{counties: selectedCounties}})
                }})
                .then(response => response.json())
                .then(data => {{
                    alert('County selection saved!');
                    closeCountySelector();
                }})
                .catch(error => {{
                    console.error('Error:', error);
                    alert('Error saving county selection');
                }});
            }}
            
            function exportCSV() {{
                window.location.href = '/export/csv';
            }}
            
            function dismissPermit(permitId) {{
                if (confirm('Are you sure you want to dismiss this permit?')) {{
                    fetch(`/api/dismiss/${{permitId}}`, {{
                        method: 'POST'
                    }})
                    .then(response => response.json())
                    .then(data => {{
                        if (data.success) {{
                            location.reload();
                        }} else {{
                            alert('Error dismissing permit');
                        }}
                    }})
                    .catch(error => {{
                        console.error('Error:', error);
                        alert('Error dismissing permit');
                    }});
                }}
            }}
            
            // Auto-refresh status every 10 seconds
            setInterval(() => {{
                fetch('/api/status')
                .then(response => response.json())
                .then(data => {{
                    document.getElementById('scraping-status').textContent = data.is_running ? 'Running...' : 'Completed';
                    document.getElementById('last-run').textContent = data.last_run || 'Never';
                    document.getElementById('last-count').textContent = data.last_count + ' permits';
                }})
                .catch(error => console.error('Error updating status:', error));
            }}, 10000);
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
        return jsonify({'error': 'Scraping already in progress'}), 400
    
    # Start scraping in background thread
    thread = threading.Thread(target=scrape_rrc_permits)
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Scraping started'})

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
        session['selected_counties'] = data.get('counties', [])
        return jsonify({'success': True})
    else:
        return jsonify(session.get('selected_counties', []))

@app.route('/export/csv')
def export_csv():
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
    
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'rrc_permits_{datetime.now().strftime("%Y%m%d")}.csv'
    )

@app.route('/api/dismiss/<int:permit_id>', methods=['POST'])
def dismiss_permit(permit_id):
    permit = Permit.query.get_or_404(permit_id)
    db.session.delete(permit)
    db.session.commit()
    return jsonify({'success': True})

# Initialize database when the module is imported (works with Gunicorn)
with app.app_context():
    try:
        db.create_all()
        print("Database initialized successfully")
        
        # Test database connection
        result = db.session.execute(db.text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = [row[0] for row in result]
        print(f"Database tables: {tables}")
        
    except Exception as e:
        print(f"Database initialization error: {e}")
        import traceback
        traceback.print_exc()

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