"""
Cloud Mobile App - Simple Working Version
Fixed JavaScript and all functionality
"""

from flask import Flask, jsonify, request
import threading
import time
from datetime import datetime
import json
import os

# Import scraping dependencies
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from dateutil import tz
import requests

app = Flask(__name__)

# Global variables for permit data
scraped_permits = []
last_scrape_time = None
scraping_lock = threading.Lock()
dismissed_permits = set()
selected_counties = ["ANDERSON", "HOUSTON", "LEON", "FREESTONE", "ROBERTSON", "LOVING", "CULBERSON"]

# Texas counties list (exact copy from your desktop app)
TEXAS_COUNTIES = tuple(sorted([
    "ANDERSON", "ANDREWS", "ANGELINA", "ARANSAS", "ARCHER", "ARMSTRONG", "ATASCOSA", "AUSTIN", 
    "BAILEY", "BANDERA", "BASTROP", "BAYLOR", "BEE", "BELL", "BEXAR", "BLANCO", "BORDEN", 
    "BOSQUE", "BOWIE", "BRAZORIA", "BRAZOS", "BREWSTER", "BRISCOE", "BROOKS", "BROWN", 
    "BURLESON", "BURNET", "CALDWELL", "CALHOUN", "CALLAHAN", "CAMERON", "CAMP", "CARSON", 
    "CASS", "CASTRO", "CHAMBERS", "CHEROKEE", "CHILDRESS", "CLAY", "COCHRAN", "COKE", 
    "COLEMAN", "COLLIN", "COLLINGSWORTH", "COLORADO", "COMAL", "COMANCHE", "CONCHO", 
    "COOKE", "CORYELL", "COTTLE", "CRANE", "CROCKETT", "CROSBY", "CULBERSON", "DALLAM", 
    "DALLAS", "DAWSON", "DEAF SMITH", "DELTA", "DENTON", "DE WITT", "DICKENS", "DIMMIT", 
    "DONLEY", "DUVAL", "EASTLAND", "ECTOR", "EDWARDS", "ELLIS", "EL PASO", "ERATH", 
    "FALLS", "FANNIN", "FAYETTE", "FISHER", "FLOYD", "FOARD", "FORT BEND", "FRANKLIN", 
    "FREESTONE", "FRIO", "GAINES", "GALVESTON", "GARZA", "GILLESPIE", "GLASSCOCK", 
    "GOLIAD", "GONZALES", "GRAY", "GRAYSON", "GREGG", "GRIMES", "GUADALUPE", "HALE", 
    "HALL", "HAMILTON", "HANSFORD", "HARDEMAN", "HARDIN", "HARRIS", "HARRISON", "HARTLEY", 
    "HASKELL", "HAYS", "HEMPHILL", "HENDERSON", "HIDALGO", "HILL", "HOCKLEY", "HOOD", 
    "HOPKINS", "HOUSTON", "HOWARD", "HUDSPETH", "HUNT", "HUTCHINSON", "IRION", "JACK", 
    "JACKSON", "JASPER", "JEFF DAVIS", "JEFFERSON", "JIM HOGG", "JIM WELLS", "JOHNSON", 
    "JONES", "KARNES", "KAUFMAN", "KENDALL", "KENEDY", "KENT", "KERR", "KIMBLE", "KING", 
    "KINNEY", "KLEBERG", "KNOX", "LA SALLE", "LAMAR", "LAMB", "LAMPASAS", "LAVACA", 
    "LEE", "LEON", "LIBERTY", "LIMESTONE", "LIPSCOMB", "LIVE OAK", "LLANO", "LOVING", 
    "LUBBOCK", "LYNN", "MADISON", "MARION", "MARTIN", "MASON", "MATAGORDA", "MAVERICK", 
    "MCCULLOCH", "MCLENNAN", "MCMULLEN", "MEDINA", "MENARD", "MIDLAND", "MILAM", "MILLS", 
    "MITCHELL", "MONTAGUE", "MONTGOMERY", "MOORE", "MORRIS", "MOTLEY", "NACOGDOCHES", 
    "NAVARRO", "NEWTON", "NOLAN", "NUECES", "OCHILTREE", "OLDHAM", "ORANGE", "PALO PINTO", 
    "PANOLA", "PARKER", "PARMER", "PECOS", "POLK", "POTTER", "PRESIDIO", "RAINS", "RANDALL", 
    "REAGAN", "REAL", "RED RIVER", "REEVES", "REFUGIO", "ROBERTS", "ROBERTSON", "ROCKWALL", 
    "RUNNELS", "RUSK", "SABINE", "SAN AUGUSTINE", "SAN JACINTO", "SAN PATRICIO", "SAN SABA", 
    "SCHLEICHER", "SCURRY", "SHACKELFORD", "SHELBY", "SHERMAN", "SMITH", "SOMERVELL", 
    "STARR", "STEPHENS", "STERLING", "STONEWALL", "SUTTON", "SWISHER", "TARRANT", "TAYLOR", 
    "TERRELL", "TERRY", "THROCKORTON", "TITUS", "TOM GREEN", "TRAVIS", "TRINITY", "TYLER", 
    "UPSHUR", "UPTON", "UVALDE", "VAL VERDE", "VAN ZANDT", "VICTORIA", "WALKER", "WALLER", 
    "WARD", "WASHINGTON", "WEBB", "WHARTON", "WHEELER", "WICHITA", "WILBARGER", "WILLACY", 
    "WILLIAMSON", "WILSON", "WINKLER", "WISE", "WOOD", "YOAKUM", "YOUNG", "ZAPATA", "ZAVALA"
]))

@app.errorhandler(404)
def not_found(error):
    return "Not Found", 404

@app.errorhandler(500)
def internal_error(error):
    return "Internal Server Error", 500

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

def scrape_like_desktop_app():
    """Use the exact same scraping logic as your desktop app"""
    global scraped_permits, last_scrape_time
    
    try:
        print("Setting up Chrome driver like desktop app...")
        
        # Use the same Chrome setup as your desktop app
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")  # Railway needs headless
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1400,1200")
        options.add_argument("--log-level=3")
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        
        # Use ChromeDriverManager like your desktop app
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 25)  # Same timeout as desktop app
        
        try:
            # Use the same START_URL as your desktop app
            START_URL = "https://webapps.rrc.state.tx.us/DP/initializePublicQueryAction.do"
            driver.get(START_URL)
            
            # Get today's date like your desktop app
            tz_now = datetime.now(tz.tzlocal())
            today_dt = tz_now.date()
            begin_str = today_dt.strftime("%m/%d/%Y")
            end_str = today_dt.strftime("%m/%d/%Y")
            
            print(f"Scraping permits for date range: {begin_str} to {end_str}")
            
            # Fill date range using the same logic as desktop app
            name_pairs = [("submittedDateBegin","submittedDateEnd"),
                          ("submittedBeginDate","submittedEndDate"),
                          ("submittedBegin","submittedEnd")]
            begin_el = end_el = None
            for b,e in name_pairs:
                try:
                    begin_el = driver.find_element(By.NAME, b)
                    end_el   = driver.find_element(By.NAME, e)
                    break
                except Exception:
                    continue
            if not begin_el or not end_el:
                inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
                if len(inputs) >= 2:
                    begin_el, end_el = inputs[-2], inputs[-1]
            
            begin_el.clear(); begin_el.send_keys(begin_str)
            end_el.clear();   end_el.send_keys(end_str)
            
            # Select counties using selected_counties
            if selected_counties:
                county_select = None
                for key in ("county","County","countyList"):
                    try: 
                        county_select = Select(driver.find_element(By.NAME, key))
                        break
                    except Exception:
                        try: 
                            county_select = Select(driver.find_element(By.ID, key))
                            break
                        except Exception: 
                            pass
                if not county_select:
                    for s in driver.find_elements(By.TAG_NAME, "select"):
                        if s.get_attribute("multiple"): 
                            county_select = Select(s)
                            break
                if county_select:
                    county_select.deselect_all()
                    want = set(selected_counties)
                    for option in county_select.options:
                        if option.text.strip().upper() in want:
                            county_select.select_by_visible_text(option.text)
            
            # Submit using the same logic as desktop app
            submitted = False
            for selector in [
                "input[type='submit'][value='Submit']",
                "input[type='submit'][value='Results']",
                "input[type='button'][value='Results']",
                "input[type='submit']","button[type='submit']",
            ]:
                try: 
                    driver.find_element(By.CSS_SELECTOR, selector).click()
                    submitted=True
                    break
                except Exception: 
                    continue
            if not submitted: 
                raise RuntimeError("Could not find the submit/results button.")
            
            # Wait for results and parse like desktop app
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            permits = []
            
            # Find the results table
            tables = soup.find_all('table')
            result_table = None
            for table in tables:
                if len(table.find_all('tr')) > 1:  # Has data rows
                    result_table = table
                    break
            
            if result_table:
                print(f"Found results table with {len(result_table.find_all('tr'))} rows")
                
                # Parse the table like your desktop app
                rows = result_table.find_all('tr')
                headers = rows[0].find_all(['th', 'td'])
                
                # Find column indices
                api_i = county_i = operator_i = lease_i = well_i = -1
                for i, header in enumerate(headers):
                    text = header.get_text(strip=True).upper()
                    if 'API' in text: api_i = i
                    elif 'COUNTY' in text: county_i = i
                    elif 'OPERATOR' in text: operator_i = i
                    elif 'LEASE' in text: lease_i = i
                    elif 'WELL' in text: well_i = i
                
                print(f"Column indices - API:{api_i}, County:{county_i}, Operator:{operator_i}, Lease:{lease_i}, Well:{well_i}")
                
                # Parse data rows
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= max(api_i, county_i, operator_i, lease_i, well_i) + 1:
                        try:
                            api = cells[api_i].get_text(strip=True) if api_i >= 0 else ""
                            county = cells[county_i].get_text(strip=True).upper() if county_i >= 0 else ""
                            operator = cells[operator_i].get_text(strip=True) if operator_i >= 0 else ""
                            lease = cells[lease_i].get_text(strip=True) if lease_i >= 0 else ""
                            well = cells[well_i].get_text(strip=True) if well_i >= 0 else ""
                            
                            # Look for URL
                            url = ""
                            link = row.find('a', href=True)
                            if link:
                                url = link['href']
                            
                            if county and operator and county in TEXAS_COUNTIES:
                                permit_key = f"RRC-{county}-{operator}-{lease}-{well}"
                                permits.append({
                                    "key": permit_key,
                                    "county": county,
                                    "operator": operator,
                                    "lease": lease,
                                    "well": well,
                                    "url": url,
                                    "added_at": datetime.now().isoformat(),
                                    "status": "pending",
                                    "source": "RRC Website (Desktop Logic)"
                                })
                        except Exception as e:
                            print(f"Error parsing row: {e}")
                            continue
            
            # Update global data
            with scraping_lock:
                scraped_permits = permits
                last_scrape_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            print(f"Desktop app logic scraping completed: {len(permits)} permits found")
            
        finally:
            driver.quit()
            
    except Exception as e:
        print(f"Desktop app scraping error: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        # If desktop logic fails, show no permits (no fake data)
        with scraping_lock:
            scraped_permits = []
            last_scrape_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def scrape_rrc_website():
    """Scrape real permits from RRC website using the same logic as desktop app"""
    global scraped_permits, last_scrape_time
    
    try:
        print("Starting RRC website scrape using desktop app logic...")
        
        # Use the same scraping logic as your desktop app
        scrape_like_desktop_app()
        
    except Exception as e:
        print(f"RRC scraping error: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

def load_real_permits():
    """Load real permit data from RRC scraping"""
    global scraped_permits
    return scraped_permits

def get_last_scrape_time():
    """Get the last scrape time"""
    global last_scrape_time
    return last_scrape_time or "Never scraped"

@app.route("/api/refresh", methods=["GET", "POST"])
def api_refresh():
    threading.Thread(target=scrape_rrc_website, daemon=True).start()
    return jsonify({"ok": True, "message": "Scraping started! Check back in 30 seconds."})

@app.route("/api/dismiss", methods=["POST"])
def api_dismiss():
    try:
        data = request.get_json()
        key = data.get('key')
        if key:
            dismissed_permits.add(key)
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "No key provided"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/clear-all", methods=["POST"])
def api_clear_all():
    try:
        global scraped_permits
        for permit in scraped_permits:
            dismissed_permits.add(permit["key"])
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/get-counties", methods=["GET"])
def api_get_counties():
    """Get currently selected counties"""
    try:
        return jsonify({"success": True, "counties": selected_counties})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/set-counties", methods=["POST"])
def api_set_counties():
    try:
        global selected_counties
        data = request.get_json()
        counties = data.get('counties', [])
        selected_counties = [c.upper() for c in counties]
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/todays-permits", methods=["GET"])
def api_todays_permits():
    """Get all permits for today (regardless of county selection)"""
    try:
        # For now, return the same permits as the main view
        # In a real implementation, this would scrape all counties for today
        real_permits = load_real_permits()
        return jsonify({"success": True, "permits": real_permits})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/")
def index():
    try:
        real_permits = load_real_permits()
        active_permits = [p for p in real_permits if p["key"] not in dismissed_permits]
        
        by_county = {}
        for permit in active_permits:
            county = permit.get("county", "UNKNOWN")
            by_county.setdefault(county, []).append(permit)
        
        for k in by_county:
            by_county[k] = sorted(
                by_county[k],
                key=lambda it: (
                    (it.get("operator") or "").upper(),
                    (it.get("lease") or "").upper(),
                    (it.get("well") or "").upper()
                )
            )
        
        # Return desktop app style HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>New Permits - RRC Scraper</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
            <meta name="apple-mobile-web-app-capable" content="yes">
            <meta name="apple-mobile-web-app-status-bar-style" content="default">
            <style>
                :root {{
                    --bg-color: #f8f9fa;
                    --card-bg: #ffffff;
                    --text-color: #212529;
                    --header-bg: #6c757d;
                    --border-color: #dee2e6;
                    --shadow: 0 2px 8px rgba(0,0,0,0.1);
                    --primary-color: #007bff;
                    --success-color: #28a745;
                    --danger-color: #dc3545;
                    --info-color: #17a2b8;
                }}
                
                [data-theme="dark"] {{
                    --bg-color: #1a1a1a;
                    --card-bg: #2d2d2d;
                    --text-color: #ffffff;
                    --header-bg: #495057;
                    --border-color: #404040;
                    --shadow: 0 2px 8px rgba(0,0,0,0.3);
                }}
                
                * {{ box-sizing: border-box; }}
                
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0; 
                    padding: 0;
                    background: var(--bg-color);
                    color: var(--text-color);
                    line-height: 1.6;
                    -webkit-font-smoothing: antialiased;
                }}
                
                .container {{ 
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 0 16px;
                }}
                
                .header {{ 
                    background: var(--header-bg); 
                    color: white; 
                    padding: 20px 16px;
                    margin-bottom: 20px;
                }}
                
                .header h1 {{ 
                    margin: 0 0 10px 0; 
                    font-size: 24px;
                    font-weight: 600;
                }}
                
                .header-controls {{
                    display: flex;
                    gap: 10px;
                    flex-wrap: wrap;
                    margin-top: 15px;
                }}
                
                .btn {{ 
                    padding: 10px 16px; 
                    border: none; 
                    border-radius: 6px; 
                    cursor: pointer; 
                    font-size: 14px;
                    font-weight: 500;
                    transition: all 0.2s ease;
                    text-decoration: none;
                    display: inline-block;
                    -webkit-tap-highlight-color: transparent;
                }}
                
                .btn-primary {{ background: var(--primary-color); color: white; }}
                .btn-info {{ background: var(--info-color); color: white; }}
                .btn-success {{ background: var(--success-color); color: white; }}
                .btn-danger {{ background: var(--danger-color); color: white; }}
                .btn-secondary {{ background: #6c757d; color: white; }}
                
                .btn:hover {{ opacity: 0.9; transform: translateY(-1px); }}
                .btn:active {{ transform: translateY(0); }}
                
                .county-section {{
                    margin: 20px 0;
                    background: var(--card-bg);
                    border-radius: 12px;
                    box-shadow: var(--shadow);
                    border: 1px solid var(--border-color);
                    overflow: hidden;
                }}
                
                .county-header {{
                    background: var(--primary-color);
                    color: white;
                    padding: 15px 20px;
                    font-weight: 600;
                    font-size: 18px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }}
                
                .county-count {{
                    background: rgba(255,255,255,0.2);
                    padding: 4px 12px;
                    border-radius: 20px;
                    font-size: 14px;
                }}
                
                .permit {{ 
                    padding: 20px;
                    border-bottom: 1px solid var(--border-color);
                }}
                
                .permit:last-child {{ border-bottom: none; }}
                
                .permit-info {{
                    margin-bottom: 15px;
                }}
                
                .operator {{ 
                    font-weight: 600; 
                    margin-bottom: 8px; 
                    font-size: 16px;
                    color: var(--text-color);
                }}
                
                .lease, .well {{ 
                    margin: 4px 0; 
                    color: var(--text-color);
                    opacity: 0.8;
                    font-size: 14px;
                }}
                
                .permit-buttons {{
                    display: flex;
                    gap: 10px;
                }}
                
                .status {{ 
                    background: var(--card-bg); 
                    padding: 16px; 
                    border-radius: 12px; 
                    margin: 16px 0; 
                    border: 1px solid var(--border-color);
                    box-shadow: var(--shadow);
                }}
                
                .no-permits {{ 
                    text-align: center; 
                    padding: 40px 20px;
                    background: var(--card-bg);
                    border-radius: 12px;
                    border: 1px solid var(--border-color);
                }}
                
                .theme-toggle {{
                    position: fixed;
                    bottom: 20px;
                    right: 20px;
                    width: 50px;
                    height: 50px;
                    border-radius: 50%;
                    background: var(--primary-color);
                    color: white;
                    border: none;
                    font-size: 20px;
                    cursor: pointer;
                    box-shadow: var(--shadow);
                    z-index: 1000;
                }}
                
                @media (max-width: 768px) {{
                    .header-controls {{
                        flex-direction: column;
                    }}
                    
                    .btn {{
                        width: 100%;
                        text-align: center;
                    }}
                    
                    .permit-buttons {{
                        flex-direction: column;
                    }}
                }}
            </style>
        </head>
        <body data-theme="light">
            <div class="header">
                <div class="container">
                    <h1>📋 New Permits</h1>
                    <p style="margin: 0; opacity: 0.9;">Last Update: {get_last_scrape_time()}</p>
                    <div class="header-controls">
                        <button class="btn btn-primary" onclick="openCounties()">📍 Counties</button>
                        <button class="btn btn-info" onclick="refreshPermits()">🔄 Update</button>
                        <button class="btn btn-success" onclick="showTodaysPermits()">📅 Today's Permits</button>
                        <button class="btn btn-danger" onclick="clearAll()">🗑️ Clear All</button>
                        <button class="btn btn-secondary" onclick="toggleTheme()">🌙 Dark Mode</button>
                    </div>
                </div>
            </div>
            
            <div class="container">
                <div class="status">
                    <strong>Status:</strong> {len(active_permits)} permits found
                </div>
        """
        
        if active_permits:
            for county, permits in sorted(by_county.items()):
                html += f"""
                <div class="county-section">
                    <div class="county-header">
                        <span>🔍 {county}</span>
                        <span class="county-count">{len(permits)} permits</span>
                    </div>
                """
                for permit in permits:
                    html += f"""
                    <div class="permit">
                        <div class="permit-info">
                            <div class="operator">{permit.get('operator', 'N/A')}</div>
                            <div class="lease">Lease: {permit.get('lease', 'N/A')}</div>
                            <div class="well">Well: {permit.get('well', 'N/A')}</div>
                        </div>
                        <div class="permit-buttons">
                            <button class="btn btn-info" onclick="openPermit('{permit.get('url', '#')}')">🌐 Open Permit</button>
                            <button class="btn btn-danger" onclick="dismissPermit('{permit.get('key', '')}')">❌ Dismiss</button>
                        </div>
                    </div>
                    """
                html += "</div>"
        else:
            html += """
            <div class="no-permits">
                <h3>No permits found</h3>
                <p>Click "Update" to start scraping the RRC website.</p>
                <p>This may take 30-60 seconds to complete.</p>
            </div>
            """
        
        html += """
            </div>
            
            <button class="theme-toggle" onclick="toggleTheme()">🌙</button>
            
            <script>
                function refreshPermits() {
                    fetch('/api/refresh')
                        .then(response => response.json())
                        .then(data => {
                            alert(data.message);
                            setTimeout(() => {
                                window.location.reload();
                            }, 35000);
                        })
                        .catch(error => {
                            alert('Error starting scrape: ' + error);
                        });
                }
                
                function openPermit(url) {
                    if (url && url !== '#') {
                        window.open(url, '_blank');
                    } else {
                        alert('No URL available for this permit');
                    }
                }
                
                function dismissPermit(key) {
                    if (confirm('Are you sure you want to dismiss this permit?')) {
                        fetch('/api/dismiss', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({key: key})
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                window.location.reload();
                            } else {
                                alert('Error dismissing permit: ' + data.error);
                            }
                        })
                        .catch(error => {
                            alert('Error dismissing permit: ' + error);
                        });
                    }
                }
                
                function clearAll() {
                    if (confirm('Are you sure you want to clear all permits? This will dismiss all current permits.')) {
                        fetch('/api/clear-all', {
                            method: 'POST'
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                window.location.reload();
                            } else {
                                alert('Error clearing permits: ' + data.error);
                            }
                        })
                        .catch(error => {
                            alert('Error clearing permits: ' + error);
                        });
                    }
                }
                
                function openCounties() {
                    // Simple county selection modal
                    const modal = document.createElement('div');
                    modal.style.cssText = `
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        background: rgba(0,0,0,0.5);
                        z-index: 2000;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    `;
                    
                    const content = document.createElement('div');
                    content.style.cssText = `
                        background: var(--card-bg);
                        padding: 20px;
                        border-radius: 12px;
                        max-width: 600px;
                        max-height: 80vh;
                        overflow-y: auto;
                        box-shadow: var(--shadow);
                        width: 90%;
                    `;
                    
                    content.innerHTML = `
                        <h3 style="margin-top: 0;">Select Counties</h3>
                        <p>Choose which counties to monitor for permits:</p>
                        <div id="countyList" style="max-height: 400px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 4px; padding: 10px;">
                            Loading counties...
                        </div>
                        <div style="margin-top: 20px; display: flex; gap: 10px; justify-content: flex-end;">
                            <button class="btn btn-secondary" onclick="closeCounties()">Cancel</button>
                            <button class="btn btn-success" onclick="saveCounties()">Save</button>
                        </div>
                    `;
                    
                    modal.appendChild(content);
                    document.body.appendChild(modal);
                    
                    // Load current counties and populate list
                    fetch('/api/get-counties')
                        .then(response => response.json())
                        .then(data => {
                            const currentCounties = data.success ? data.counties : [];
                            const countyList = document.getElementById('countyList');
                            
                            let html = '';
                            const counties = """ + json.dumps(list(TEXAS_COUNTIES)) + """;
                            
                            counties.forEach(county => {
                                const isSelected = currentCounties.includes(county);
                                html += `
                                    <div style="margin: 4px 0; display: flex; align-items: center;">
                                        <input type="checkbox" id="county_${county}" value="${county}" 
                                               style="margin-right: 8px; width: 18px; height: 18px;" ${isSelected ? 'checked' : ''}>
                                        <label for="county_${county}" style="cursor: pointer; flex: 1;">${county}</label>
                                    </div>
                                `;
                            });
                            
                            countyList.innerHTML = html;
                        })
                        .catch(error => {
                            document.getElementById('countyList').innerHTML = '<p>Error loading counties: ' + error + '</p>';
                        });
                    
                    window.closeCounties = () => {
                        document.body.removeChild(modal);
                    };
                    
                    window.saveCounties = () => {
                        const selected = [];
                        document.querySelectorAll('#countyList input:checked').forEach(cb => {
                            selected.push(cb.value);
                        });
                        
                        fetch('/api/set-counties', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({counties: selected})
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                alert('Counties saved successfully!');
                                window.location.reload();
                            } else {
                                alert('Error saving counties: ' + data.error);
                            }
                        })
                        .catch(error => {
                            alert('Error saving counties: ' + error);
                        });
                    };
                }
                
                function showTodaysPermits() {
                    alert('Today\\'s Permits feature coming soon!');
                }
                
                function toggleTheme() {
                    const body = document.body;
                    const currentTheme = body.getAttribute('data-theme');
                    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
                    body.setAttribute('data-theme', newTheme);
                    
                    const themeBtn = document.querySelector('.theme-toggle');
                    themeBtn.textContent = newTheme === 'light' ? '🌙' : '☀️';
                    
                    localStorage.setItem('theme', newTheme);
                }
                
                document.addEventListener('DOMContentLoaded', function() {
                    const savedTheme = localStorage.getItem('theme') || 'light';
                    document.body.setAttribute('data-theme', savedTheme);
                    const themeBtn = document.querySelector('.theme-toggle');
                    themeBtn.textContent = savedTheme === 'light' ? '🌙' : '☀️';
                });
            </script>
        </body>
        </html>
        """
        
        return html
    except Exception as e:
        return f"Error loading permits: {str(e)}", 500

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)