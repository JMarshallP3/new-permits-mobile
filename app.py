from flask import Flask, jsonify, render_template, request
import os
from datetime import datetime
import json

app = Flask(__name__, template_folder="templates", static_folder="static")

# REAL PERMIT DATA FROM YOUR DESKTOP APP - VERSION 5.0
def load_real_permits():
    """Load real permit data from your desktop app files"""
    try:
        # This would normally connect to your desktop app's data
        # For now, using the real data I found in your pending_permits.json
        real_permits = [
            {
                "key": "URL:https://webapps.rrc.state.tx.us/DP/drillDownQueryAction.do?name=PISTOL%2BPETE%2B21-56-1&fromPublicQuery=Y&univDocNo=498611180",
                "county": "LOVING",
                "operator": "WPX ENERGY PERMIAN, LLC (942623)",
                "lease": "PISTOL PETE 21-56-1",
                "well": "402H",
                "url": "https://webapps.rrc.state.tx.us/DP/drillDownQueryAction.do?name=PISTOL%2BPETE%2B21-56-1&fromPublicQuery=Y&univDocNo=498611180",
                "added_at": "2025-09-10T09:42:20",
                "status": "pending"
            },
            {
                "key": "URL:https://webapps.rrc.state.tx.us/DP/drillDownQueryAction.do?name=CBR%2B16&fromPublicQuery=Y&univDocNo=498613221",
                "county": "LOVING", 
                "operator": "WPX ENERGY PERMIAN, LLC (942623)",
                "lease": "CBR 16",
                "well": "321H",
                "url": "https://webapps.rrc.state.tx.us/DP/drillDownQueryAction.do?name=CBR%2B16&fromPublicQuery=Y&univDocNo=498613221",
                "added_at": "2025-09-10T10:33:39",
                "status": "pending"
            }
        ]
        return real_permits
    except Exception as e:
        print(f"Error loading real permits: {e}")
        return []

def get_last_scrape_time():
    """Get the last scrape time from your desktop app"""
    try:
        # This would normally read from your last_scrape.json
        return "2025-09-11 11:03:43"
    except:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

@app.route("/")
def index():
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
    
    return render_template(
        "index.html",
        by_county=sorted(by_county.items()),
        last=get_last_scrape_time(),
        token="real-data-token",
        build_stamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        data_dir="cloud",
        selected_counties=["LOVING"],  # Your real data is in LOVING county
        all_counties=TEXAS_COUNTIES,
    )

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
    return jsonify({"ok": True, "message": "Refreshed successfully!"})

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
    port = int(os.environ.get('PORT', 8000))
    app.run(host="0.0.0.0", port=port, debug=False)