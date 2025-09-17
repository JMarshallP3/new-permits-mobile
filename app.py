from flask import Flask, jsonify, render_template, request
import os
from datetime import datetime
import json
import threading
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

app = Flask(__name__, template_folder="templates", static_folder="static")

# Add error handling
@app.errorhandler(500)
def internal_error(error):
    return "Internal Server Error", 500

@app.errorhandler(404)
def not_found(error):
    return "Not Found", 404

# REAL RRC SCRAPING FUNCTIONALITY
scraped_permits = []
last_scrape_time = None
scraping_lock = threading.Lock()

def scrape_rrc_website():
    """Scrape real permits from RRC website like the desktop app"""
    global scraped_permits, last_scrape_time
    
    try:
        print("Starting RRC website scrape...")
        
        # Set up Chrome options for Railway
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--remote-debugging-port=9222")
        
        driver = webdriver.Chrome(options=chrome_options)
        
        try:
            # Navigate to RRC New Permits page
            driver.get("https://webapps.rrc.state.tx.us/DP/initializePublicQueryAction.do")
            
            # Wait for page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Look for the form and submit it to get W-1 permits
            try:
                # Find and click the W-1 permits link or form
                w1_link = driver.find_element(By.PARTIAL_LINK_TEXT, "W-1")
                w1_link.click()
                time.sleep(3)
            except:
                # Try direct URL
                driver.get("https://webapps.rrc.state.tx.us/DP/drillDownQueryAction.do?name%3DW-1%26fromPublicQuery%3DY")
                time.sleep(5)
            
            # Parse the results
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            permits = []
            
            # Look for permit data in tables
            tables = soup.find_all('table')
            print(f"Found {len(tables)} tables on RRC page")
            
            for table in tables:
                rows = table.find_all('tr')
                for row in rows[1:]:  # Skip header row
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 4:
                        try:
                            # Extract permit data (adjust indices based on RRC table structure)
                            county = cells[0].get_text(strip=True).upper() if len(cells) > 0 else ""
                            operator = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                            lease = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                            well = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                            
                            # Look for API number or URL
                            api_link = row.find('a', href=True)
                            url = api_link['href'] if api_link else ""
                            
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
                                    "source": "RRC Website"
                                })
                        except Exception as e:
                            print(f"Error parsing row: {e}")
                            continue
            
            # Update global data
            with scraping_lock:
                scraped_permits = permits
                last_scrape_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            print(f"Scraped {len(permits)} permits from RRC website")
            
        finally:
            driver.quit()
            
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

TEXAS_COUNTIES = [
    "ANDERSON", "ANDREWS", "ANGELINA", "ARANSAS", "ARCHER", "ARMSTRONG", "ATASCOSA", "AUSTIN",
    "BAILEY", "BANDERA", "BASTROP", "BAYLOR", "BEE", "BELL", "BEXAR", "BLANCO", "BORDEN", "BOSQUE",
    "BOWIE", "BRAZORIA", "BRAZOS", "BREWSTER", "BRISCOE", "BROOKS", "BROWN", "BURLESON", "BURNET",
    "CALDWELL", "CALHOUN", "CALLAHAN", "CAMERON", "CAMP", "CARSON", "CASS", "CASTRO", "CHAMBERS",
    "CHEROKEE", "CHILDRESS", "CLAY", "COCHRAN", "COKE", "COLEMAN", "COLLIN", "COLLINGSWORTH", "COLORADO",
    "COMAL", "COMANCHE", "CONCHO", "COOKE", "CORYELL", "COTTLE", "CRANE", "CROCKETT", "CROSBY", "CULBERSON",
    "DALLAM", "DALLAS", "DAWSON", "DE WITT", "DEAF SMITH", "DELTA", "DENTON", "DICKENS", "DIMMIT", "DONLEY",
    "DUVAL", "EASTLAND", "ECTOR", "EDWARDS", "EL PASO", "ELLIS", "ERATH", "FALLS", "FANNIN", "FAYETTE",
    "FISHER", "FLOYD", "FOARD", "FORT BEND", "FRANKLIN", "FREESTONE", "FRIO", "GAINES", "GALVESTON", "GARZA",
    "GILLESPIE", "GLASSCOCK", "GOLIAD", "GONZALES", "GRAY", "GRAYSON", "GREGG", "GRIMES", "GUADALUPE", "HALE",
    "HALL", "HAMILTON", "HANSFORD", "HARDEMAN", "HARDIN", "HARRIS", "HARRISON", "HARTLEY", "HASKELL", "HAYS",
    "HEMPHILL", "HENDERSON", "HIDALGO", "HILL", "HOCKLEY", "HOOD", "HOPKINS", "HOUSTON", "HOWARD", "HUDSPETH",
    "HUNT", "HUTCHINSON", "IRION", "JACK", "JACKSON", "JASPER", "JEFF DAVIS", "JEFFERSON", "JIM HOGG", "JIM WELLS",
    "JOHNSON", "JONES", "KARNES", "KAUFMAN", "KENDALL", "KENEDY", "KENT", "KERR", "KIMBLE", "KING",
    "KINNEY", "KLEBERG", "KNOX", "LA SALLE", "LAMAR", "LAMB", "LAMPASAS", "LAVACA", "LEE", "LEON",
    "LIBERTY", "LIMESTONE", "LIPSCOMB", "LIVE OAK", "LLANO", "LOVING", "LUBBOCK", "LYNN", "MADISON", "MARION",
    "MARTIN", "MASON", "MATAGORDA", "MAVERICK", "MCCULLOCH", "MCLENNAN", "MCMULLEN", "MEDINA", "MENARD", "MIDLAND",
    "MILAM", "MILLS", "MITCHELL", "MONTAGUE", "MONTGOMERY", "MOORE", "MORRIS", "MOTLEY", "NACOGDOCHES", "NAVARRO",
    "NEWTON", "NOLAN", "NUECES", "OCHILTREE", "OLDHAM", "ORANGE", "PALO PINTO", "PANOLA", "PARKER", "PARMER",
    "PECOS", "POLK", "POTTER", "PRESIDIO", "RAINS", "RANDALL", "REAGAN", "REAL", "RED RIVER", "REEVES",
    "REFUGIO", "ROBERTS", "ROBERTSON", "ROCKWALL", "RUNNELS", "RUSK", "SABINE", "SAN AUGUSTINE", "SAN JACINTO", "SAN PATRICIO",
    "SAN SABA", "SCHLEICHER", "SCURRY", "SHACKELFORD", "SHELBY", "SHERMAN", "SMITH", "SOMERVELL", "STARR", "STEPHENS",
    "STERLING", "STONEWALL", "SUTTON", "SWISHER", "TARRANT", "TAYLOR", "TERRELL", "TERRY", "THROCKMORTON", "TITUS",
    "TOM GREEN", "TRAVIS", "TRINITY", "TYLER", "UPSHUR", "UPTON", "UVALDE", "VAL VERDE", "VAN ZANDT", "VICTORIA",
    "WALKER", "WALLER", "WARD", "WASHINGTON", "WEBB", "WHARTON", "WHEELER", "WICHITA", "WILBARGER", "WILLACY",
    "WILLIAMSON", "WILSON", "WINKLER", "WISE", "WOOD", "YOAKUM", "YOUNG", "ZAPATA", "ZAVALA"
]

# In-memory storage for dismissed permits
dismissed_permits = set()

# Health check route
@app.route("/health")
def health():
    return jsonify({"status": "ok", "message": "App is running"})

# Simple HTML route without templates
@app.route("/simple")
def simple():
    real_permits = load_real_permits()
    active_permits = [p for p in real_permits if p["key"] not in dismissed_permits]
    
    html = f"""
    <html>
    <head><title>New Permits - Real Data</title></head>
    <body>
        <h1>📋 New Permits - Real Data</h1>
        <p>Last Update: {get_last_scrape_time()}</p>
        <h2>Your Real Permits:</h2>
    """
    
    for permit in active_permits:
        html += f"""
        <div style="border: 1px solid #ccc; margin: 10px; padding: 10px;">
            <h3>{permit.get('county', 'UNKNOWN')} County</h3>
            <p><strong>Operator:</strong> {permit.get('operator', 'N/A')}</p>
            <p><strong>Lease:</strong> {permit.get('lease', 'N/A')}</p>
            <p><strong>Well:</strong> {permit.get('well', 'N/A')}</p>
            <p><strong>Added:</strong> {permit.get('added_at', 'N/A')}</p>
            <a href="{permit.get('url', '#')}" target="_blank">Open Permit</a>
        </div>
        """
    
    html += "</body></html>"
    return html

@app.route("/")
def index():
    try:
        # Load REAL permit data from your desktop app
        real_permits = load_real_permits()
        
        # Filter out dismissed permits
        active_permits = [p for p in real_permits if p["key"] not in dismissed_permits]
        
        # Group permits by county
        by_county = {}
        for permit in active_permits:
            county = permit.get("county", "UNKNOWN")
            by_county.setdefault(county, []).append(permit)
        
        # Sort counties
        for k in by_county:
            by_county[k] = sorted(
                by_county[k],
                key=lambda it: (
                    (it.get("operator") or "").upper(),
                    (it.get("lease") or "").upper(),
                    (it.get("well") or "").upper()
                )
            )
        
        # Return mobile-friendly HTML directly (no templates needed)
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>New Permits - RRC Scraper</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
                .header {{ background: #007bff; color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }}
                .permit {{ background: white; margin: 10px 0; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .county {{ font-weight: bold; color: #007bff; font-size: 18px; }}
                .operator {{ font-weight: bold; margin: 5px 0; }}
                .lease, .well {{ margin: 3px 0; color: #666; }}
                .url {{ margin-top: 10px; }}
                .url a {{ background: #007bff; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; }}
                .refresh {{ background: #28a745; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 10px 0; }}
                .status {{ background: #e9ecef; padding: 10px; border-radius: 5px; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📋 New Permits - RRC Scraper</h1>
                <p>Last Update: {get_last_scrape_time()}</p>
                <button class="refresh" onclick="window.location.href='/api/refresh'">🔄 Refresh/Scrape RRC</button>
            </div>
            
            <div class="status">
                <strong>Status:</strong> {len(active_permits)} permits found
            </div>
        """
        
        if active_permits:
            for county, permits in sorted(by_county.items()):
                html += f'<h2 class="county">{county} County ({len(permits)} permits)</h2>'
                for permit in permits:
                    html += f"""
                    <div class="permit">
                        <div class="operator">{permit.get('operator', 'N/A')}</div>
                        <div class="lease">Lease: {permit.get('lease', 'N/A')}</div>
                        <div class="well">Well: {permit.get('well', 'N/A')}</div>
                        <div class="url">
                            <a href="{permit.get('url', '#')}" target="_blank">Open RRC Permit</a>
                        </div>
                    </div>
                    """
        else:
            html += """
            <div class="permit">
                <h3>No permits found</h3>
                <p>Click "Refresh/Scrape RRC" to start scraping the RRC website.</p>
                <p>This may take 30-60 seconds to complete.</p>
            </div>
            """
        
        html += """
        </body>
        </html>
        """
        
        return html
    except Exception as e:
        return f"Error loading permits: {str(e)}", 500

@app.route("/api/permits")
def api_permits():
    # Load REAL permit data from your desktop app
    real_permits = load_real_permits()
    
    # Filter out dismissed permits
    active_permits = [p for p in real_permits if p["key"] not in dismissed_permits]
    
    # Group permits by county
    by_county = {}
    for permit in active_permits:
        county = permit.get("county", "UNKNOWN")
        by_county.setdefault(county, []).append(permit)
    
    return jsonify({
        "permits": active_permits,
        "by_county": by_county,
        "last_update": get_last_scrape_time(),
        "selected_counties": ["LOVING"]  # Your real data is in LOVING county
    })

@app.route("/api/counties")
def api_counties():
    return jsonify(TEXAS_COUNTIES)

@app.route("/api/counties", methods=["POST"])
def api_update_counties():
    return jsonify({"ok": True, "message": "Counties updated"})

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    # Start scraping in background thread
    threading.Thread(target=scrape_rrc_website, daemon=True).start()
    return jsonify({"ok": True, "message": "Scraping started! Check back in 30 seconds."})

@app.route("/api/dismiss", methods=["POST"])
def api_dismiss():
    data = request.get_json() or {}
    key = data.get("key")
    if key:
        dismissed_permits.add(key)
        return jsonify({"ok": True, "message": "Permit dismissed!"})
    return jsonify({"ok": False, "message": "No key provided"})

@app.route("/api/undismiss", methods=["POST"])
def api_undismiss():
    data = request.get_json() or {}
    key = data.get("key")
    if key:
        dismissed_permits.discard(key)
        return jsonify({"ok": True, "message": "Permit undismissed!"})
    return jsonify({"ok": False, "message": "No key provided"})

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8000))  # Railway auto-detect will set the correct port
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)