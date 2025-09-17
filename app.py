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
        
        # Get today's date
        today = date.today()
        
        # Set up session with headers
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # For now, add sample data to test the app
        sample_permits = [
            Permit(
                county="HARRIS",
                operator="EXXON MOBIL CORPORATION",
                lease_name="BAYTOWN REFINERY UNIT",
                well_number="BR-001",
                api_number="42-201-12345",
                date_issued=today,
                rrc_link="https://webapps.rrc.state.tx.us/DP/drillDownQueryAction.do"
            ),
            Permit(
                county="TRAVIS",
                operator="CHEVRON U.S.A. INC.",
                lease_name="AUSTIN CHALK UNIT",
                well_number="AC-002",
                api_number="42-453-67890",
                date_issued=today,
                rrc_link="https://webapps.rrc.state.tx.us/DP/drillDownQueryAction.do"
            ),
            Permit(
                county="MIDLAND",
                operator="PIONEER NATURAL RESOURCES",
                lease_name="PERMIAN BASIN UNIT",
                well_number="PB-003",
                api_number="42-483-11111",
                date_issued=today,
                rrc_link="https://webapps.rrc.state.tx.us/DP/drillDownQueryAction.do"
            )
        ]
        
        # Check which permits are new
        new_permits = []
        for permit in sample_permits:
            existing = Permit.query.filter_by(
                county=permit.county,
                operator=permit.operator,
                lease_name=permit.lease_name,
                well_number=permit.well_number,
                date_issued=permit.date_issued
            ).first()
            
            if not existing:
                new_permits.append(permit)
        
        # Save new permits to database
        if new_permits:
            db.session.add_all(new_permits)
            db.session.commit()
            print(f"Added {len(new_permits)} new permits")
        
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
