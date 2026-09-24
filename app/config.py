import os
from dotenv import load_dotenv
load_dotenv()
MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY", "")
MASSIVE_BASE = "https://api.massive.com"
STOCKS = {"AAPL":"אפל","NVDA":"אנבידיה","MSFT":"מיקרוסופט","AMZN":"אמזון","META":"מטא","TSLA":"טסלה","GOOGL":"אלפבית (גוגל)","AMD":"AMD","INTC":"אינטל","AVGO":"ברודקום","NFLX":"נטפליקס","PLTR":"פלנטיר","COIN":"קוינבייס","MSTR":"סטרטג'י","PYPL":"פייפאל","ADBE":"אדובי","CRM":"סיילספורס","ORCL":"אורקל","QCOM":"קוואלקום","MU":"מיקרון","ARM":"ARM","SMCI":"סופר מיקרו קומפיוטר","SHOP":"שופיפיי","UBER":"אובר","ABNB":"איירבנב","JPM":"ג'יי פי מורגן","BAC":"בנק אוף אמריקה","GS":"גולדמן זאקס","V":"ויזה","MA":"מאסטרקארד","WMT":"וולמארט","COST":"קוסטקו","MCD":"מקדונלד'ס","NKE":"נייקי","DIS":"דיסני","BA":"בואינג","CAT":"קטרפילר","XOM":"אקסון מוביל","CVX":"שברון","LLY":"אלי לילי","UNH":"יונייטד הלת'","PFE":"פייזר","JNJ":"ג'ונסון אנד ג'ונסון","KO":"קוקה קולה","CSCO":"סיסקו"}
OTHER = ["SP500","NASDAQ100","DOW30","RUSSELL2000","VIX","DAX40","FTSE100","CAC40","NIKKEI225","HANGSENG","GOLD","SILVER","WTI","BRENT","NATGAS","COPPER","PLATINUM","PALLADIUM","CORN","WHEAT"]
MASSIVE_STOCK_TICKERS = list(STOCKS)
TICKERS = MASSIVE_STOCK_TICKERS + OTHER
def get_asset_name(symbol):
    return STOCKS.get(symbol, symbol)
