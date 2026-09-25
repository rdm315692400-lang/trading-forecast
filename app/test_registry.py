from .asset_registry import all_assets, provider_verified_assets
def test_universe():
    assert len(all_assets())==65
    assert len(provider_verified_assets())==45
