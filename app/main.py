from fastapi import FastAPI

from .config import (
    TICKERS,
    MASSIVE_STOCK_TICKERS,
    get_asset_name,
)

from .data import minute_history
from .engine import forecast


app = FastAPI(
    title="Trading Forecast",
    version="10.2",
)


@app.get("/")
async def root():
    return {
        "ok": True,
        "name": "Trading Forecast",
        "version": "10.2",
    }


@app.get("/health")
async def health():
    return {
        "ok": True,
        "version": "10.2",
        "universe": len(TICKERS),
        "stocks_connected": len(
            MASSIVE_STOCK_TICKERS
        ),
        "background_scanner": False,
        "forecast_engine": True,
    }


@app.get("/api/forecast/{symbol}")
async def forecast_symbol(symbol: str):

    symbol = symbol.upper().strip()

    if symbol not in MASSIVE_STOCK_TICKERS:
        return {
            "ok": False,
            "symbol": symbol,
            "message": "המניה אינה ברשימת המניות",
        }

    try:
        rows = await minute_history(
            symbol,
            days=10
        )

        if not rows:
            return {
                "ok": False,
                "symbol": symbol,
                "name": get_asset_name(symbol),
                "message": "לא התקבלו נתוני דקות",
            }

        result = forecast(
            symbol,
            rows
        )

        return {
            "ok": True,
            "symbol": symbol,
            "name": get_asset_name(symbol),
            "data_rows": len(rows),
            "forecast": result,
        }

    except Exception as error:
        return {
            "ok": False,
            "symbol": symbol,
            "name": get_asset_name(symbol),
            "error": str(error),
        }
