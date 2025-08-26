import requests

def convert(amount: float, from_ccy: str, to_ccy: str):
    if from_ccy.upper() == to_ccy.upper():
        return amount, 1.0
    r = requests.get(f"https://api.frankfurter.app/latest", params={"amount": amount, "from": from_ccy, "to": to_ccy})
    r.raise_for_status()
    js = r.json()
    rate = js["rates"][to_ccy.upper()]
    return rate, rate/amount if amount else 0.0
