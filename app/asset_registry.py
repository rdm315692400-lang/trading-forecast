from dataclasses import dataclass
from typing import Dict, Optional

@dataclass(frozen=True)
class AssetProfile:
    asset_id: str
    name_he: str
    provider_symbol: str | None
    asset_type: str
    market_timezone: str
    session_open: str
    session_close: str
    provider_verified: bool

_STOCKS = [
("AAPL","אפל"),("NVDA","אנבידיה"),("MSFT","מיקרוסופט"),("AMZN","אמזון"),
("META","מטא"),("TSLA","טסלה"),("GOOGL","אלפבית"),("AMD","AMD"),
("INTC","אינטל"),("AVGO","ברודקום"),("NFLX","נטפליקס"),("PLTR","פלנטיר"),
("COIN","קוינבייס"),("MSTR","מיקרוסטרטג'י"),("PYPL","פייפאל"),("ADBE","אדובי"),
("CRM","סיילספורס"),("ORCL","אורקל"),("QCOM","קוואלקום"),("MU","מיקרון"),
("ARM","ARM"),("SMCI","סופר מיקרו"),("SHOP","שופיפיי"),("UBER","אובר"),
("ABNB","Airbnb"),("JPM","JPMorgan"),("BAC","בנק אוף אמריקה"),("GS","גולדמן זאקס"),
("V","ויזה"),("MA","מאסטרקארד"),("WMT","וולמארט"),("COST","קוסטקו"),
("MCD","מקדונלד'ס"),("NKE","נייקי"),("DIS","דיסני"),("BA","בואינג"),
("CAT","קטרפילר"),("XOM","אקסון מוביל"),("CVX","שברון"),("LLY","אלי לילי"),
("UNH","יונייטד הלת'"),("PFE","פייזר"),("JNJ","ג'ונסון אנד ג'ונסון"),
("KO","קוקה קולה"),("CSCO","סיסקו"),
]
_PLACEHOLDERS = [
("SP500","S&P 500","index"),("NASDAQ100","Nasdaq 100","index"),
("DOW30","Dow 30","index"),("RUSSELL2000","Russell 2000","index"),
("VIX","VIX","index"),("DAX40","DAX 40","index"),("FTSE100","FTSE 100","index"),
("CAC40","CAC 40","index"),("NIKKEI225","Nikkei 225","index"),
("HANGSENG","Hang Seng","index"),("GOLD","זהב","commodity"),
("SILVER","כסף","commodity"),("WTI","נפט WTI","commodity"),
("BRENT","נפט Brent","commodity"),("NATGAS","גז טבעי","commodity"),
("COPPER","נחושת","commodity"),("PLATINUM","פלטינה","commodity"),
("PALLADIUM","פלדיום","commodity"),("CORN","תירס","commodity"),
("WHEAT","חיטה","commodity"),
]

ASSETS: Dict[str, AssetProfile] = {}
for symbol, name in _STOCKS:
    ASSETS[symbol] = AssetProfile(
        symbol, name, symbol, "stock", "America/New_York", "09:30", "16:00", True
    )
for asset_id, name, kind in _PLACEHOLDERS:
    ASSETS[asset_id] = AssetProfile(
        asset_id, name, None, kind, "UTC", "00:00", "23:59", False
    )

def get_asset(asset_id: str) -> Optional[AssetProfile]:
    return ASSETS.get(asset_id.upper().strip())

def all_assets():
    return list(ASSETS.values())

def provider_verified_assets():
    return [a for a in ASSETS.values() if a.provider_verified]
