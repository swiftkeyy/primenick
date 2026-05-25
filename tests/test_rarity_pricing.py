from decimal import Decimal
from app.services.pricing import PricingEngine, PricingContext
from app.services.rarity import rarity_score


def test_pricing_no_vip_discount():
    engine = PricingEngine()
    quote = engine.quote(PricingContext(username="prime", rarity_score=80))
    assert quote >= Decimal("149.00")
    assert engine.explain(PricingContext(username="prime", rarity_score=80))["vip_discount"] == Decimal("0.00")


def test_rarity_bounds():
    assert 0 <= rarity_score("voidlabs") <= 100
