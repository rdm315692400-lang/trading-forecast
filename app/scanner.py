from .ranking import rank_forecasts, leader

class ForecastScanner:
    """Pure ranking service. It never calls a provider or Firestore itself."""
    def rank(self, forecasts):
        return rank_forecasts(forecasts)
    def leader(self, forecasts):
        return leader(forecasts)

BACKGROUND_SCANNER_ENABLED=False
