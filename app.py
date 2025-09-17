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
    
    return render_template('index.html', 
                         permits=permits,
                         counties=TEXAS_COUNTIES,
                         county_filter=county_filter,
                         operator_search=operator_search,
                         sort_newest=sort_newest,
                         scraping_status=scraping_status)

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
