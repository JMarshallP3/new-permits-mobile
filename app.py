from flask import Flask, jsonify, request
import os
from datetime import datetime

app = Flask(__name__, template_folder="templates", static_folder="static")

# REAL PERMIT DATA FROM YOUR DESKTOP APP - VERSION 5.0
def load_real_permits():
    try:
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
    try:
        return "2025-09-11 11:03:43"
    except:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

TEXAS_COUNTIES = ["ANDERSON", "ANDREWS", "ANGELINA", "ARANSAS", "ARCHER", "ARMSTRONG", "ATASCOSA", "AUSTIN",
    # … (rest unchanged, keep your big list here)
    "ZAPATA", "ZAVALA"]

dismissed_permits = set()

# -------------------------------
# TEST ROUTES (no templates yet)
# -------------------------------
@app.route("/")
def index():
    return "✅ App is running on Railway", 200

@app.route("/health")
def health():
    return "ok", 200

# -------------------------------
# KEEP your APIs
# -------------------------------
@app.route("/api/permits")
def api_permits():
    real_permits = load_real_permits()
    active_permits = [p for p in real_permits if p["key"] not in dismissed_permits]
    by_county = {}
    for permit in active_permits:
        county = permit.get("county", "UNKNOWN")
        by_county.setdefault(county, []).append(permit)
    return jsonify({
        "permits": active_permits,
        "by_county": by_county,
        "last_update": get_last_scrape_time(),
        "selected_counties": ["LOVING"]
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

# -------------------------------
# ENTRYPOINT
# -------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

