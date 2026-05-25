from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from math import log1p


@dataclass(frozen=True)
class PricingContext:
    username: str
    rarity_score: int
    demand_index: float = 1.0
    inventory_pressure: float = 1.0
    platform: str = "telegram"


class PricingEngine:
    base_by_length = {4: Decimal("249.00"), 5: Decimal("149.00"), 6: Decimal("89.00"), 7: Decimal("49.00")}
    default_base = Decimal("29.00")

    def quote(self, ctx: PricingContext) -> Decimal:
        length = len(ctx.username)
        base = self.base_by_length.get(length, self.default_base)
        rarity_multiplier = Decimal(str(1 + min(ctx.rarity_score, 100) / 120))
        surge = Decimal(str(max(0.85, min(3.0, ctx.demand_index * ctx.inventory_pressure))))
        platform_multiplier = Decimal("1.15") if ctx.platform == "telegram" else Decimal("1.00")
        price = base * rarity_multiplier * surge * platform_multiplier
        return price.quantize(Decimal("1.00"), rounding=ROUND_HALF_UP)

    def explain(self, ctx: PricingContext) -> dict:
        return {"base_length": len(ctx.username), "rarity_score": ctx.rarity_score, "surge": ctx.demand_index * ctx.inventory_pressure, "vip_discount": Decimal("0.00"), "final_rub": str(self.quote(ctx))}
