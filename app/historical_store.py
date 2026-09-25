from collections import defaultdict

class HistoricalStore:
    def __init__(self):
        self._bars = defaultdict(list)

    def extend(self, bars):
        for bar in bars:
            self._bars[bar.asset_id.upper()].append(bar)
        for asset_id in self._bars:
            dedup = {}
            for bar in self._bars[asset_id]:
                dedup[bar.timestamp_utc] = bar
            self._bars[asset_id] = sorted(
                dedup.values(), key=lambda b: (b.timestamp_utc, b.received_at_utc)
            )

    def all_bars(self, asset_id):
        return list(self._bars.get(asset_id.upper(), []))
