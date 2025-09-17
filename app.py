"""
New Permits - Mobile Web App
Automatically tracks and displays new oil & gas drilling permits from Texas RRC
"""

from flask import Flask, render_template, request, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import requests
from bs4 import BeautifulSoup
import threading
import os
from sqlalchemy import desc, or_

app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///permits.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

db = SQLAlchemy(app)

# Database Models
class Permit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    county = db.Column(db.String(100), nullable=False)
    operator = db.Column(db.String(200), nullable=False)
    lease_name = db.Column(db.String(200), nullable=False)
    well_number = db.Column(db.String(100), nullable=False)
    api_number = db.Column(db.String(50), nullable=True)
    date_issued = db.Column(db.Date, nullable=False)
    rrc_link = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'county': self.county,
            'operator': self.operator,
            'lease_name': self.lease_name,
            'well_number': self.well_number,
            'api_number': self.api_number,
            'date_issued': self.date_issued.strftime('%Y-%m-%d') if self.date_issued else None,
            'rrc_link': self.rrc_link,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

# Texas counties for filtering
TEXAS_COUNTIES = [
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
]

# Global variables for scraping status
scraping_status = {
    'is_running': False,
    'last_run': None,
    'last_count': 0,
    'error': None
}

def scrape_rrc_permits():
    """Scrape new permits from RRC website"""
    global scraping_status
    
    scraping_status['is_running'] = True
    scraping_status['error'] = None
    
    try:
        print("Starting RRC permit scraping...")
        
        # Create application context for database operations
        with app.app_context():
            # Get today's date
            today = date.today()
            
            # Set up session with headers
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            
            # Real RRC scraping logic - try multiple approaches
            RRC_BASE_URL = "https://webapps.rrc.state.tx.us"
            
            # Try different RRC URLs that might work
            possible_urls = [
                f"{RRC_BASE_URL}/DP/initializePublicQueryAction.do",
                f"{RRC_BASE_URL}/DP/publicQueryAction.do",
                f"{RRC_BASE_URL}/DP/queryAction.do",
                f"{RRC_BASE_URL}/DP/",
                f"{RRC_BASE_URL}/DP/publicQuery.do"
            ]
            
            response = None
            soup = None
            
            # Try each URL until we find one that works
            for url in possible_urls:
                try:
                    print(f"Trying RRC URL: {url}")
                    response = session.get(url, timeout=30)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Check if this is a login page (bad) or search page (good)
                    page_text = soup.get_text().lower()
                    if 'log in' in page_text or 'userid' in page_text or 'password' in page_text:
                        print(f"URL {url} redirected to login page - trying next URL")
                        continue
                    
                    # Check if we found a search form
                    form = soup.find('form')
                    if form and ('submittedDateBegin' in str(form) or 'dateBegin' in str(form) or 'beginDate' in str(form)):
                        print(f"Found working search form at: {url}")
                        break
                    else:
                        print(f"No search form found at {url} - trying next URL")
                        continue
                        
                except Exception as e:
                    print(f"Error with URL {url}: {e}")
                    continue
            
            if not soup or not response:
                raise Exception("Could not access any RRC search page - all URLs failed")
            
            # Step 2: Find and fill the search form
            form = soup.find('form')
            if not form:
                raise Exception("Could not find search form on RRC website")
            
            form_action = form.get('action', '')
            if form_action.startswith('/'):
                form_url = f"{RRC_BASE_URL}{form_action}"
            elif form_action.startswith('http'):
                form_url = form_action
            else:
                form_url = f"{RRC_BASE_URL}/DP/{form_action}"
            
            print(f"Submitting form to: {form_url}")
            
            # Prepare form data
            form_data = {}
            
            # Find all input fields
            for input_field in form.find_all('input'):
                name = input_field.get('name')
                value = input_field.get('value', '')
                if name:
                    form_data[name] = value
            
            # Set date range to today
            date_str = today.strftime('%m/%d/%Y')
            
            # Try different form field names that RRC might use
            possible_date_fields = [
                'submittedDateBegin', 'submittedDateEnd',
                'dateBegin', 'dateEnd',
                'beginDate', 'endDate',
                'fromDate', 'toDate',
                'startDate', 'stopDate',
                'submittedDate', 'queryDate',
                'permitDateBegin', 'permitDateEnd'
            ]
            
            # Set all possible date fields
            for field in possible_date_fields:
                if field in form_data:
                    if 'begin' in field.lower() or 'start' in field.lower() or 'from' in field.lower():
                        form_data[field] = date_str
                    elif 'end' in field.lower() or 'stop' in field.lower() or 'to' in field.lower():
                        form_data[field] = date_str
                    else:
                        form_data[field] = date_str
            
            # Also try setting some common fields that might be required
            form_data['submittedDateBegin'] = date_str
            form_data['submittedDateEnd'] = date_str
            
            print(f"Form data: {form_data}")
            
            # Submit the form
            response = session.post(form_url, data=form_data, timeout=30)
            response.raise_for_status()
            
            # Step 3: Parse the results
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Check if we got redirected to login again
            page_text = soup.get_text().lower()
            if 'log in' in page_text or 'userid' in page_text or 'password' in page_text:
                print("Form submission redirected to login page - trying fallback method")
                # Try a different approach - direct search URL
                try:
                    fallback_url = f"{RRC_BASE_URL}/DP/publicQueryAction.do"
                    fallback_data = {
                        'submittedDateBegin': date_str,
                        'submittedDateEnd': date_str,
                        'queryType': 'drillingPermit',
                        'status': 'active'
                    }
                    print(f"Trying fallback URL: {fallback_url}")
                    response = session.post(fallback_url, data=fallback_data, timeout=30)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'html.parser')
                    print("Fallback method successful")
                except Exception as e:
                    print(f"Fallback method failed: {e}")
                    raise Exception("All scraping methods failed - RRC website may require authentication")
            
            # Find the results table - look for the largest table with data
            all_tables = soup.find_all('table')
            print(f"Found {len(all_tables)} tables on page")
            
            # Debug: print all tables found
            for i, table in enumerate(all_tables):
                rows = table.find_all('tr')
                print(f"Table {i}: classes={table.get('class')}, id={table.get('id')}, rows={len(rows)}")
                if len(rows) > 0:
                    # Print first few cells of first row to identify table type
                    first_row_cells = rows[0].find_all(['td', 'th'])
                    cell_texts = [cell.get_text(strip=True)[:20] for cell in first_row_cells[:5]]
                    print(f"  First row cells: {cell_texts}")
            
            # Find the table with the most rows (likely the main results table)
            results_table = None
            max_rows = 0
            
            for table in all_tables:
                rows = table.find_all('tr')
                if len(rows) > max_rows:
                    max_rows = len(rows)
                    results_table = table
            
            if not results_table or max_rows < 2:
                print("No suitable results table found - no permits for today")
                scraping_status['last_count'] = 0
                scraping_status['last_run'] = datetime.utcnow()
                return
            
            print(f"Using table with {max_rows} rows as results table")
            
            # Parse table rows - skip header row
            rows = results_table.find_all('tr')[1:]  # Skip header row
            new_permits = []
            
            print(f"Found {len(rows)} data rows to process")
            
            for i, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                if len(cells) < 3:  # Need at least 3 columns
                    continue
                
                try:
                    # Debug: print first few rows
                    if i < 3:
                        cell_texts = [cell.get_text(strip=True) for cell in cells]
                        print(f"Row {i}: {cell_texts}")
                    
                    # Extract data based on RRC table structure
                    # RRC table columns: Status Date, Status #, API No., Operator Name/Number, Lease Name, Well #, Dist., County, Wellbore Profile, Filing Purpose, Amend, Total Depth, Stacked Lateral Parent Well DP, Current Queue
                    
                    county = ""
                    operator = ""
                    lease_name = ""
                    well_number = ""
                    api_number = ""
                    
                    # Look for county in any cell (usually column 8 in RRC table)
                    for j, cell in enumerate(cells):
                        text = cell.get_text(strip=True).upper()
                        if any(county_name in text for county_name in TEXAS_COUNTIES):
                            county = text
                            break
                    
                    # Try to extract other fields based on typical RRC column positions
                    if len(cells) >= 9:  # RRC table should have at least 9 columns
                        # API Number (column 3)
                        if len(cells) > 2:
                            api_number = cells[2].get_text(strip=True)
                        
                        # Operator Name (column 4)
                        if len(cells) > 3:
                            operator = cells[3].get_text(strip=True)
                        
                        # Lease Name (column 5)
                        if len(cells) > 4:
                            lease_name = cells[4].get_text(strip=True)
                        
                        # Well Number (column 6)
                        if len(cells) > 5:
                            well_number = cells[5].get_text(strip=True)
                        
                        # County (column 8)
                        if len(cells) > 7:
                            county = cells[7].get_text(strip=True).upper()
                    
                    # Fallback: try to find county in any cell if not found above
                    if not county:
                        for cell in cells:
                            text = cell.get_text(strip=True).upper()
                            if any(county_name in text for county_name in TEXAS_COUNTIES):
                                county = text
                                break
                    
                    # Find RRC link
                    rrc_link = ""
                    link_element = row.find('a', href=True)
                    if link_element:
                        href = link_element['href']
                        if href.startswith('/'):
                            rrc_link = f"{RRC_BASE_URL}{href}"
                        else:
                            rrc_link = href
                    
                    # Validate data - be more flexible
                    if county and (operator or lease_name or well_number):
                        # Check if permit already exists
                        existing = Permit.query.filter_by(
                            county=county,
                            operator=operator or "Unknown",
                            lease_name=lease_name or "Unknown",
                            well_number=well_number or "Unknown",
                            date_issued=today
                        ).first()
                        
                        if not existing:
                            permit = Permit(
                                county=county,
                                operator=operator or "Unknown",
                                lease_name=lease_name or "Unknown",
                                well_number=well_number or "Unknown",
                                api_number=api_number,
                                date_issued=today,
                                rrc_link=rrc_link
                            )
                            new_permits.append(permit)
                            
                except Exception as e:
                    print(f"Error parsing row {i}: {e}")
                    continue
            
            # Save new permits to database
            if new_permits:
                db.session.add_all(new_permits)
                db.session.commit()
                print(f"Added {len(new_permits)} new permits from RRC website")
            else:
                print("No new permits found for today")
            
            scraping_status['last_count'] = len(new_permits)
            scraping_status['last_run'] = datetime.utcnow()
        
    except Exception as e:
        print(f"Scraping error: {e}")
        scraping_status['error'] = str(e)
    
    finally:
        scraping_status['is_running'] = False

def generate_html(permits, county_filter, operator_search, sort_newest):
    """Generate HTML directly without templates"""
    
    # Generate county options
    county_options = ""
    for county in TEXAS_COUNTIES:
        selected = 'selected' if county == county_filter else ''
        county_options += f'<option value="{county}" {selected}>{county}</option>'
    
    # Generate permit cards
    permit_cards = ""
    if permits:
        for permit in permits:
            permit_cards += f'''
            <div class="permit-card">
                <div class="permit-header">
                    <span class="permit-county">{permit.county}</span>
                    <span class="permit-date">{permit.date_issued.strftime('%m/%d/%Y')}</span>
                </div>
                <div class="permit-operator">{permit.operator}</div>
                <div class="permit-details">
                    <div class="permit-detail"><strong>Lease:</strong> {permit.lease_name}</div>
                    <div class="permit-detail"><strong>Well:</strong> {permit.well_number}</div>
                    {f'<div class="permit-detail"><strong>API:</strong> {permit.api_number}</div>' if permit.api_number else ''}
                </div>
                <div class="permit-actions">
                    {f'<a href="{permit.rrc_link}" target="_blank" class="btn btn-primary btn-small">🌐 View on RRC</a>' if permit.rrc_link else ''}
                </div>
            </div>
            '''
    else:
        permit_cards = '''
        <div class="no-permits">
            <h3>No permits found</h3>
            <p>Try adjusting your search criteria or scrape for new permits.</p>
        </div>
        '''
    
    # Status indicators
    status_text = ""
    if scraping_status['is_running']:
        status_text = '<span class="status-running">🔄 Running...</span>'
    elif scraping_status['error']:
        status_text = f'<span class="status-error">❌ Error: {scraping_status["error"]}</span>'
    elif scraping_status['last_run']:
        status_text = '<span class="status-success">✅ Completed</span>'
    else:
        status_text = '<span>⏸️ Not Started</span>'
    
    last_run_text = scraping_status['last_run'].strftime('%Y-%m-%d %H:%M:%S') if scraping_status['last_run'] else 'Never'
    
    html = f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>New Permits - Texas RRC</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #f5f5f5;
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
            margin-bottom: 30px;
            border-radius: 10px;
            text-align: center;
        }}

        .header h1 {{
            font-size: 2.5rem;
            margin-bottom: 10px;
        }}

        .header p {{
            font-size: 1.1rem;
            opacity: 0.9;
        }}

        .controls {{
            background: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }}

        .controls h3 {{
            margin-bottom: 20px;
            color: #333;
        }}

        .form-row {{
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}

        .form-group {{
            flex: 1;
            min-width: 200px;
        }}

        .form-group label {{
            display: block;
            margin-bottom: 5px;
            font-weight: 600;
            color: #555;
        }}

        .form-group select,
        .form-group input {{
            width: 100%;
            padding: 12px;
            border: 2px solid #e1e5e9;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }}

        .form-group select:focus,
        .form-group input:focus {{
            outline: none;
            border-color: #667eea;
        }}

        .button-group {{
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
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
            display: inline-block;
            text-align: center;
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

        .btn:disabled {{
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }}

        .status {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }}

        .status-item {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            padding: 10px 0;
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

        .status-running {{
            color: #ffc107;
            font-weight: 600;
        }}

        .status-success {{
            color: #28a745;
            font-weight: 600;
        }}

        .status-error {{
            color: #dc3545;
            font-weight: 600;
        }}

        .permits-grid {{
            display: grid;
            gap: 20px;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
        }}

        .permit-card {{
            background: white;
            border-radius: 10px;
            padding: 25px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            transition: transform 0.3s, box-shadow 0.3s;
        }}

        .permit-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 5px 20px rgba(0,0,0,0.15);
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
            font-size: 14px;
            font-weight: 600;
        }}

        .permit-date {{
            color: #666;
            font-size: 14px;
        }}

        .permit-operator {{
            font-size: 18px;
            font-weight: 700;
            color: #333;
            margin-bottom: 10px;
        }}

        .permit-details {{
            margin-bottom: 20px;
        }}

        .permit-detail {{
            margin-bottom: 8px;
            color: #555;
        }}

        .permit-detail strong {{
            color: #333;
        }}

        .permit-actions {{
            display: flex;
            gap: 10px;
        }}

        .btn-small {{
            padding: 8px 16px;
            font-size: 14px;
        }}

        .no-permits {{
            text-align: center;
            padding: 60px 20px;
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}

        .no-permits h3 {{
            color: #666;
            margin-bottom: 10px;
        }}

        .no-permits p {{
            color: #888;
        }}

        @media (max-width: 768px) {{
            .container {{
                padding: 10px;
            }}

            .header h1 {{
                font-size: 2rem;
            }}

            .form-row {{
                flex-direction: column;
            }}

            .button-group {{
                flex-direction: column;
            }}

            .permits-grid {{
                grid-template-columns: 1fr;
            }}

            .permit-actions {{
                flex-direction: column;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛢️ New Permits</h1>
            <p>Texas Railroad Commission Drilling Permits</p>
        </div>

        <div class="controls">
            <h3>🔍 Search & Filter</h3>
            <form method="GET" action="/">
                <div class="form-row">
                    <div class="form-group">
                        <label for="county">County</label>
                        <select name="county" id="county">
                            <option value="">All Counties</option>
                            {county_options}
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="search">Search Operator/Lease</label>
                        <input type="text" name="search" id="search" placeholder="Enter operator or lease name..." value="{operator_search}">
                    </div>
                    <div class="form-group">
                        <label for="sort">Sort By</label>
                        <select name="sort" id="sort">
                            <option value="">Most Recent</option>
                            <option value="newest" {'selected' if sort_newest else ''}>Newest Permits First</option>
                        </select>
                    </div>
                </div>
                <div class="button-group">
                    <button type="submit" class="btn btn-primary">🔍 Search</button>
                    <button type="button" class="btn btn-success" onclick="startScraping()" id="scrapeBtn">🔄 Scrape New Permits</button>
                    <button type="button" class="btn btn-info" onclick="openCountySelector()">📍 Select Counties</button>
                    <a href="/export/csv" class="btn btn-info">📊 Export CSV</a>
                </div>
            </form>
        </div>

        <div class="status">
            <h3>📊 Status</h3>
            <div class="status-item">
                <span class="status-label">Scraping Status:</span>
                <span class="status-value" id="scrapingStatus">{status_text}</span>
            </div>
            <div class="status-item">
                <span class="status-label">Last Run:</span>
                <span class="status-value">{last_run_text}</span>
            </div>
            <div class="status-item">
                <span class="status-label">Last Count:</span>
                <span class="status-value">{scraping_status['last_count']} permits</span>
            </div>
            <div class="status-item">
                <span class="status-label">Total Permits:</span>
                <span class="status-value">{len(permits)} permits</span>
            </div>
        </div>

        <div class="permits-grid">
            {permit_cards}
        </div>
    </div>

    <script>
        function startScraping() {{
            const btn = document.getElementById('scrapeBtn');
            const status = document.getElementById('scrapingStatus');
            
            btn.disabled = true;
            btn.textContent = '🔄 Scraping...';
            status.innerHTML = '<span class="status-running">🔄 Running...</span>';
            
            fetch('/api/scrape', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }}
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.error) {{
                    alert('Error: ' + data.error);
                    btn.disabled = false;
                    btn.textContent = '🔄 Scrape New Permits';
                    status.innerHTML = '<span class="status-error">❌ Error: ' + data.error + '</span>';
                }} else {{
                    alert('Scraping started! The page will refresh in 30 seconds to show new results.');
                    setTimeout(() => {{
                        window.location.reload();
                    }}, 30000);
                }}
            }})
            .catch(error => {{
                alert('Error starting scrape: ' + error);
                btn.disabled = false;
                btn.textContent = '🔄 Scrape New Permits';
                status.innerHTML = '<span class="status-error">❌ Error: ' + error + '</span>';
            }});
        }}

        // Auto-refresh status every 5 seconds when scraping
        setInterval(() => {{
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {{
                    const status = document.getElementById('scrapingStatus');
                    const btn = document.getElementById('scrapeBtn');
                    
                    if (data.is_running) {{
                        status.innerHTML = '<span class="status-running">🔄 Running...</span>';
                        btn.disabled = true;
                        btn.textContent = '🔄 Scraping...';
                    }} else {{
                        btn.disabled = false;
                        btn.textContent = '🔄 Scrape New Permits';
                        
                        if (data.error) {{
                            status.innerHTML = '<span class="status-error">❌ Error: ' + data.error + '</span>';
                        }} else if (data.last_run) {{
                            status.innerHTML = '<span class="status-success">✅ Completed</span>';
                        }}
                    }}
                }})
                .catch(error => console.error('Status check failed:', error));
        }}, 5000);
        
        function openCountySelector() {{
            // Create modal
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
                background: white;
                padding: 30px;
                border-radius: 12px;
                max-width: 800px;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: 0 5px 20px rgba(0,0,0,0.3);
                width: 90%;
            `;
            
            content.innerHTML = `
                <h3 style="margin-top: 0; margin-bottom: 20px;">📍 Select Counties to Monitor</h3>
                <p style="margin-bottom: 20px; color: #666;">Choose which counties you want to track for new permits:</p>
                
                <div style="margin-bottom: 20px;">
                    <input type="text" id="countySearch" placeholder="Search counties..." 
                           style="width: 100%; padding: 10px; border: 2px solid #e1e5e9; border-radius: 8px; font-size: 16px;">
                </div>
                
                <div style="margin-bottom: 20px; display: flex; gap: 10px;">
                    <button onclick="selectAllFiltered()" class="btn btn-primary btn-small">Select All (Filtered)</button>
                    <button onclick="deselectAllFiltered()" class="btn btn-secondary btn-small">Deselect All (Filtered)</button>
                    <button onclick="selectAll()" class="btn btn-success btn-small">Select ALL</button>
                    <button onclick="deselectAll()" class="btn btn-danger btn-small">Deselect ALL</button>
                </div>
                
                <div id="countyList" style="max-height: 400px; overflow-y: auto; border: 1px solid #e1e5e9; border-radius: 8px; padding: 15px;">
                    Loading counties...
                </div>
                
                <div style="margin-top: 20px; display: flex; gap: 10px; justify-content: flex-end;">
                    <button class="btn btn-secondary" onclick="closeCountySelector()">Cancel</button>
                    <button class="btn btn-success" onclick="saveSelectedCounties()">Save Selection</button>
                </div>
            `;
            
            modal.appendChild(content);
            document.body.appendChild(modal);
            
            // Load counties and current selection
            Promise.all([
                fetch('/api/counties').then(r => r.json()),
                fetch('/api/selected-counties').then(r => r.json())
            ]).then(([counties, selectionData]) => {{
                const selectedCounties = selectionData.counties || [];
                const countyList = document.getElementById('countyList');
                
                let html = '';
                counties.forEach(county => {{
                    const isSelected = selectedCounties.includes(county);
                    html += `
                        <div class="county-item" style="margin: 8px 0; display: flex; align-items: center;">
                            <input type="checkbox" id="county_${{county}}" value="${{county}}"
                                   style="margin-right: 12px; width: 18px; height: 18px;" ${{isSelected ? 'checked' : ''}}>
                            <label for="county_${{county}}" style="cursor: pointer; flex: 1; font-size: 16px;">${{county}}</label>
                        </div>
                    `;
                }});
                
                countyList.innerHTML = html;
                
                // Add search functionality
                document.getElementById('countySearch').addEventListener('input', function() {{
                    const searchTerm = this.value.toLowerCase();
                    const items = countyList.querySelectorAll('.county-item');
                    
                    items.forEach(item => {{
                        const label = item.querySelector('label');
                        const countyName = label.textContent.toLowerCase();
                        item.style.display = countyName.includes(searchTerm) ? 'flex' : 'none';
                    }});
                }});
            }}).catch(error => {{
                document.getElementById('countyList').innerHTML = '<p style="color: red;">Error loading counties: ' + error + '</p>';
            }});
            
            // Store modal reference
            window.countyModal = modal;
        }}
        
        function closeCountySelector() {{
            if (window.countyModal) {{
                document.body.removeChild(window.countyModal);
                window.countyModal = null;
            }}
        }}
        
        function selectAll() {{
            document.querySelectorAll('#countyList input[type="checkbox"]').forEach(cb => cb.checked = true);
        }}
        
        function deselectAll() {{
            document.querySelectorAll('#countyList input[type="checkbox"]').forEach(cb => cb.checked = false);
        }}
        
        function selectAllFiltered() {{
            document.querySelectorAll('#countyList .county-item[style*="flex"] input[type="checkbox"]').forEach(cb => cb.checked = true);
        }}
        
        function deselectAllFiltered() {{
            document.querySelectorAll('#countyList .county-item[style*="flex"] input[type="checkbox"]').forEach(cb => cb.checked = false);
        }}
        
        function saveSelectedCounties() {{
            const selected = [];
            document.querySelectorAll('#countyList input:checked').forEach(cb => {{
                selected.push(cb.value);
            }});
            
            fetch('/api/selected-counties', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{counties: selected}})
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    alert(`Saved ${{selected.length}} counties for monitoring!`);
                    closeCountySelector();
                    // Update the county dropdown to show selected counties
                    updateCountyDropdown(selected);
                }} else {{
                    alert('Error saving counties: ' + data.error);
                }}
            }})
            .catch(error => {{
                alert('Error saving counties: ' + error);
            }});
        }}
        
        function updateCountyDropdown(selectedCounties) {{
            const countySelect = document.getElementById('county');
            // Add selected counties as options if they're not already there
            selectedCounties.forEach(county => {{
                if (!countySelect.querySelector(`option[value="${{county}}"]`)) {{
                    const option = document.createElement('option');
                    option.value = county;
                    option.textContent = county;
                    countySelect.appendChild(option);
                }}
            }});
        }}
    </script>
</body>
</html>
    '''
    
    return html

# Routes
@app.route('/')
def index():
    """Main page showing permits"""
    # Get filter parameters
    county_filter = request.args.get('county', '')
    operator_search = request.args.get('search', '')
    sort_newest = request.args.get('sort') == 'newest'
    
    # Build query
    query = Permit.query
    
    if county_filter:
        query = query.filter(Permit.county == county_filter)
    
    if operator_search:
        query = query.filter(
            or_(
                Permit.operator.contains(operator_search),
                Permit.lease_name.contains(operator_search)
            )
        )
    
    if sort_newest:
        query = query.order_by(desc(Permit.date_issued), desc(Permit.created_at))
    else:
        query = query.order_by(desc(Permit.created_at))
    
    permits = query.limit(100).all()  # Limit to 100 most recent
    
    # Generate HTML directly instead of using templates
    html = generate_html(permits, county_filter, operator_search, sort_newest)
    return html

@app.route('/api/scrape', methods=['POST'])
def api_scrape():
    """API endpoint to start scraping"""
    if scraping_status['is_running']:
        return jsonify({'error': 'Scraping already in progress'}), 400
    
    # Start scraping in background thread
    thread = threading.Thread(target=scrape_rrc_permits)
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Scraping started successfully'})

@app.route('/api/status')
def api_status():
    """API endpoint to get scraping status"""
    return jsonify(scraping_status)

@app.route('/api/permits')
def api_permits():
    """API endpoint to get permits as JSON"""
    permits = Permit.query.order_by(desc(Permit.created_at)).limit(50).all()
    return jsonify([permit.to_dict() for permit in permits])

@app.route('/api/counties')
def api_counties():
    """API endpoint to get all Texas counties"""
    return jsonify(TEXAS_COUNTIES)

@app.route('/api/selected-counties', methods=['GET', 'POST'])
def api_selected_counties():
    """API endpoint to get/set selected counties"""
    if request.method == 'POST':
        data = request.get_json()
        selected_counties = data.get('counties', [])
        
        # Store in session or database (using session for now)
        from flask import session
        session['selected_counties'] = selected_counties
        
        return jsonify({'success': True, 'counties': selected_counties})
    else:
        # Get from session
        from flask import session
        selected_counties = session.get('selected_counties', [])
        return jsonify({'success': True, 'counties': selected_counties})

@app.route('/export/csv')
def export_csv():
    """Export permits to CSV"""
    permits = Permit.query.order_by(desc(Permit.created_at)).all()
    
    csv_data = "County,Operator,Lease Name,Well Number,API Number,Date Issued,RRC Link\n"
    for permit in permits:
        csv_data += f'"{permit.county}","{permit.operator}","{permit.lease_name}","{permit.well_number}","{permit.api_number or ""}","{permit.date_issued}","{permit.rrc_link or ""}"\n'
    
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=permits.csv'}
    )

# Initialize database
with app.app_context():
    db.create_all()
    print("Database initialized")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
