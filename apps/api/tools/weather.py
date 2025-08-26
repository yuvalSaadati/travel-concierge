import requests
from datetime import date as _date

def geocode(city: str):
    r = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1}
    )
    r.raise_for_status()
    js = r.json()
    if not js.get("results"):
        raise ValueError(f"City not found: {city}")
    res = js["results"][0]
    return res["latitude"], res["longitude"], res.get("timezone", "auto")

def _days_between(start: str, end: str) -> int:
    s = _date.fromisoformat(start); e = _date.fromisoformat(end)
    return max((e - s).days + 1, 1)

def get_weather(city: str, start: str, end: str):
    lat, lon, tz = geocode(city)

    base = {
        "latitude": lat,
        "longitude": lon,
        "timezone": tz,
        "start_date": start,
        "end_date": end,
    }

    # 1) Try with precipitation_probability_max (widely supported for daily)
    params = dict(base)
    params["daily"] = "temperature_2m_max,temperature_2m_min,precipitation_probability_max"
    r = requests.get("https://api.open-meteo.com/v1/forecast", params=params)

    # 2) If that fails (HTTP 400 etc.), fall back to precipitation_sum
    if r.status_code >= 400:
        params = dict(base)
        params["daily"] = "temperature_2m_max,temperature_2m_min,precipitation_sum"
        r = requests.get("https://api.open-meteo.com/v1/forecast", params=params)

    r.raise_for_status()
    return r.json()

def weather_brief(js):
    daily = js.get("daily", {}) or {}
    if not daily:
        return "No weather data."

    times = daily.get("time", [])
    days = len(times)
    lines = []
    # Figure out which precip-like key we have
    p_key = None
    for k in (
        "precipitation_probability_max",
        "precipitation_probability_mean",
        "precipitation_sum",
    ):
        if k in daily:
            p_key = k
            break

    for i in range(days):
        t = times[i]
        tmax = daily.get("temperature_2m_max", [None]*days)[i]
        tmin = daily.get("temperature_2m_min", [None]*days)[i]

        if p_key == "precipitation_sum":
            pval = daily[p_key][i]
            ptxt = f"precip {pval} mm"
        elif p_key in ("precipitation_probability_max", "precipitation_probability_mean"):
            pval = daily[p_key][i]
            ptxt = f"rain {pval}%"
        else:
            ptxt = "precip N/A"

        lines.append(f"{t}: {tmin:.0f}–{tmax:.0f}°C, {ptxt}")

    return "Forecast:\n" + "\n".join(lines[:5])
