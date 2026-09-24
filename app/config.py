import os
from dotenv import load_dotenv

load_dotenv()
MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY", "")
MASSIVE_BASE = "https://api.massive.com"

STOCKS = {
"AAPL":"אפל","NVDA":"אנבידיה","MSFT":"מיקרוסופט","AMZN":"אמזון","META":"מטא",
"TSLA":"טסלה","GOOGL":"אלפבית (גוגל)","AMD":"AMD","INTC":"אינטל","AVGO":"ברודקום",
"NFLX":"נטפליקס","PLTR":"פלנטיר","COIN":"קוינבייס","MSTR":"סטרטג'י","PYPL":"פייפאל",
"ADBE":"אדובי","CRM":"סיילספורס","ORCL":"אורקל","QCOM":"קוואלקום","MU":"מיקרון",
"ARM":"ARM","SMCI":"סופר מיקרו קומפיוטר","SHOP":"שופיפיי","UBER":"אובר","ABNB":"איירבנב",
"JPM":"ג'יי פי מורגן","BAC":"בנק אוף אמריקה","GS":"גולדמן זאקס","V":"ויזה","MA":"מאסטרקארד",
"WMT":"וולמארט","COST":"קוסטקו","MCD":"מקדונלד'ס","NKE":"נייקי","DIS":"דיסני",
"BA":"בואינג","CAT":"קטרפילר","XOM":"אקסון מוביל","CVX":"שברון","LLY":"אלי לילי",
"UNH":"יונייטד הלת'","PFE":"פייזר","JNJ":"ג'ונסון אנד ג'ונסון","KO":"קוקה קולה","CSCO":"סיסקו"
}

INDICES = {
"SP500":"S&P 500","NASDAQ100":"נאסד״ק 100","DOW30":"דאו ג'ונס 30","RUSSELL2000":"ראסל 2000",
"VIX":"מדד התנודתיות VIX","DAX40":"גרמניה 40","FTSE100":"בריטניה 100","CAC40":"צרפת 40",
"NIKKEI225":"יפן 225","HANGSENG":"הונג קונג 50"
}
COMMODITIES = {
"GOLD":"זהב","SILVER":"כסף","WTI":"נפט","BRENT":"נפט ברנט","NATGAS":"גז טבעי",
"COPPER":"נחושת","PLATINUM":"פלטינה","PALLADIUM":"פלדיום","CORN":"תירס","WHEAT":"חיטה"
}
ALL_ASSETS = {**STOCKS, **INDICES, **COMMODITIES}
MASSIVE_STOCK_TICKERS = list(STOCKS)
TICKERS = list(ALL_ASSETS)

def get_asset_name(symbol):
    return ALL_ASSETS.get(symbol, symbol)
