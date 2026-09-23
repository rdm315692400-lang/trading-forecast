import os
from dotenv import load_dotenv
load_dotenv()
MASSIVE_API_KEY=os.getenv("MASSIVE_API_KEY","")
MASSIVE_BASE="https://api.massive.com"
TICKERS=["MSTR","META","INTC","AMD","CSCO","COIN","AAPL","NVDA","PYPL","TSLA","MCD","NFLX","PLTR","AMZN","ADBE"]
