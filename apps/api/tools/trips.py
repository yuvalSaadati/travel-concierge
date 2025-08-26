# apps/api/tools/trips_wiki.py
import requests
from .weather import geocode  # reuse your geocoder

def list_poi(city: str, radius_m=3000, limit=20):
    lat, lon, _tz = geocode(city)
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "geosearch",
        "gscoord": f"{lat}|{lon}",
        "gsradius": radius_m,        # meters (max 10,000)
        "gslimit": min(limit, 50),
        "format": "json"
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    js = r.json().get("query", {}).get("geosearch", [])
    # Return simple names; you can fetch extracts later with prop=extracts
    return [item["title"] for item in js]
