"""
scoring.py — Auction Drop Scoring Engine
Implements decision logic from MERCHANT_AUCTION_DROP_SPEC_v0.2
Pure Python — no Streamlit imports.
"""
from __future__ import annotations
from typing import Optional
import copy

# ── Segment lookup ─────────────────────────────────────────────────────────────

SEGMENT_BY_MODEL: dict[str, str] = {
    "civic": "compact_sedan", "corolla": "compact_sedan",
    "sentra": "compact_sedan", "jetta": "compact_sedan",
    "elantra": "compact_sedan", "forte": "compact_sedan", "cruze": "compact_sedan",
    "camry": "midsize_sedan", "altima": "midsize_sedan", "accord": "midsize_sedan",
    "malibu": "midsize_sedan", "sonata": "midsize_sedan", "fusion": "midsize_sedan",
    "optima": "midsize_sedan", "passat": "midsize_sedan",
    "avalon": "full_size_sedan", "maxima": "full_size_sedan",
    "impala": "full_size_sedan", "300": "full_size_sedan",
    "cr-v": "compact_suv", "rav4": "compact_suv", "equinox": "compact_suv",
    "tucson": "compact_suv", "rogue": "compact_suv", "escape": "compact_suv",
    "cherokee": "compact_suv", "sportage": "compact_suv", "cx-5": "compact_suv",
    "tiguan": "compact_suv", "trax": "compact_suv",
    "highlander": "midsize_suv", "explorer": "midsize_suv", "pilot": "midsize_suv",
    "santa fe": "midsize_suv", "sorento": "midsize_suv", "traverse": "midsize_suv",
    "pathfinder": "midsize_suv", "murano": "midsize_suv", "edge": "midsize_suv",
    "4runner": "midsize_suv", "durango": "midsize_suv",
    "tahoe": "full_size_suv", "expedition": "full_size_suv", "suburban": "full_size_suv",
    "sequoia": "full_size_suv", "armada": "full_size_suv", "yukon": "full_size_suv",
    "navigator": "full_size_suv", "escalade": "full_size_suv",
    "tacoma": "pickup_midsize", "colorado": "pickup_midsize", "ranger": "pickup_midsize",
    "frontier": "pickup_midsize", "ridgeline": "pickup_midsize", "canyon": "pickup_midsize",
    "f-150": "pickup_full_size", "f150": "pickup_full_size",
    "silverado": "pickup_full_size", "tundra": "pickup_full_size",
    "titan": "pickup_full_size", "sierra": "pickup_full_size", "1500": "pickup_full_size",
    "odyssey": "minivan", "sienna": "minivan", "pacifica": "minivan",
    "grand caravan": "minivan", "carnival": "minivan",
    "mustang": "sports", "camaro": "sports", "challenger": "sports",
    "mx-5": "sports", "miata": "sports", "corvette": "sports",
    "86": "sports", "brz": "sports", "supra": "sports",
}

LUXURY_MAKES: frozenset[str] = frozenset({
    "bmw", "mercedes-benz", "mercedes", "audi", "lexus",
    "cadillac", "lincoln", "genesis", "infiniti", "acura",
    "volvo", "jaguar", "land rover", "porsche", "maserati",
})

RAM_MAKES: frozenset[str] = frozenset({"ram", "dodge ram"})

SEGMENT_LABELS: dict[str, str] = {
    "compact_sedan": "Compact Sedan", "midsize_sedan": "Midsize Sedan",
    "full_size_sedan": "Full-Size Sedan", "compact_suv": "Compact SUV",
    "midsize_suv": "Midsize SUV", "full_size_suv": "Full-Size SUV",
    "pickup_full_size": "Full-Size Pickup", "pickup_midsize": "Midsize Pickup",
    "minivan": "Minivan", "luxury": "Luxury", "sports": "Sports", "other": "Other",
}

SUV_SEGMENTS: frozenset[str] = frozenset({"compact_suv", "midsize_suv", "full_size_suv"})
SEDAN_SEGMENTS: frozenset[str] = frozenset({"compact_sedan", "midsize_sedan", "full_size_sedan"})
TRUCK_SEGMENTS: frozenset[str] = frozenset({"pickup_full_size", "pickup_midsize"})

# ── Recon constants ────────────────────────────────────────────────────────────

RECON_TABLE = [
    {"grade_min": 4.0, "grade_max": 5.0, "base_cost": 300,  "base_days": 2},
    {"grade_min": 3.0, "grade_max": 3.9, "base_cost": 1000, "base_days": 4},
    {"grade_min": 2.0, "grade_max": 2.9, "base_cost": 2500, "base_days": 8},
    {"grade_min": 1.0, "grade_max": 1.9, "base_cost": 4500, "base_days": 12},
]

NOTE_ADJUSTMENTS: dict[str, dict] = {
    "paint":      {"cost": 400, "days": 1},
    "mechanical": {"cost": 800, "days": 3},
    "tire":       {"cost": 600, "days": 1},
    "odor":       {"cost": 300, "days": 2},
    "smoke":      {"cost": 300, "days": 2},
    "interior":   {"cost": 500, "days": 2},
}

CONDITION_FAIL_KEYWORDS: list[str] = ["frame damage", "flood", "salvage", "frame"]

# ── Base pricing ───────────────────────────────────────────────────────────────

BASE_PRICES: dict[str, float] = {
    "compact_sedan": 24000, "midsize_sedan": 27000, "full_size_sedan": 25000,
    "compact_suv": 29000, "midsize_suv": 35000, "full_size_suv": 42000,
    "pickup_full_size": 38000, "pickup_midsize": 32000,
    "minivan": 34000, "luxury": 36000, "sports": 30000, "other": 22000,
}

# ── Market context defaults ────────────────────────────────────────────────────

DEFAULT_MARKET_CONTEXT: dict = {
    "season": "spring_tax",
    "seasonal_multipliers": {
        "spring_tax": 1.05, "summer": 0.98, "fall": 0.97, "winter": 0.92,
    },
    # Regional demand indices set to produce spec narrative with sample manifest:
    # Sedans bid strongly (undersupplied), SUVs marginal/skip (oversupplied+softening),
    # Trucks bid (undersupplied+wholesale firming), Odyssey bids (minivan undersupplied).
    "regional_demand_index": {
        "compact_sedan":   1.00,
        "midsize_sedan":   0.97,
        "full_size_sedan": 0.88,
        "compact_suv":     0.95,
        "midsize_suv":     0.88,
        "full_size_suv":   0.82,
        "pickup_full_size": 1.02,
        "pickup_midsize":  1.06,
        "minivan":         0.95,
        "luxury":          0.90,
        "sports":          0.82,
        "other":           0.85,
    },
    "avg_retail_margin_by_segment": {
        "compact_sedan": 1200, "midsize_sedan": 1500, "full_size_sedan": 1300,
        "compact_suv": 1800, "midsize_suv": 2200, "full_size_suv": 2800,
        "pickup_full_size": 2500, "pickup_midsize": 1800,
        "minivan": 1600, "luxury": 2400, "sports": 1800, "other": 1200,
    },
    "avg_days_to_sale_by_segment": {
        "compact_sedan": 18, "midsize_sedan": 22, "full_size_sedan": 30,
        "compact_suv": 20, "midsize_suv": 25, "full_size_suv": 38,
        "pickup_full_size": 28, "pickup_midsize": 30,
        "minivan": 35, "luxury": 42, "sports": 45, "other": 30,
    },
    "daily_carry_rate": 35,
}

# ── Lot state defaults (Richmond demo) ────────────────────────────────────────

DEFAULT_LOT_STATE: dict = {
    "total_units": 340, "capacity": 400,
    "recon_bays_total": 14, "recon_bays_occupied": 11,
    "recon_queue_depth": 6, "avg_days_on_lot": 28.0, "daily_carry_rate": 35.0,
    "segment_counts": {
        "compact_sedan": 38, "midsize_sedan": 55, "full_size_sedan": 5,
        "compact_suv": 72, "midsize_suv": 58, "full_size_suv": 22,
        "pickup_full_size": 35, "pickup_midsize": 18,
        "minivan": 12, "luxury": 20, "sports": 5, "other": 5,
    },
    "segment_targets": {
        "compact_sedan": 50, "midsize_sedan": 55, "full_size_sedan": 10,
        "compact_suv": 65, "midsize_suv": 45, "full_size_suv": 15,
        "pickup_full_size": 40, "pickup_midsize": 20,
        "minivan": 15, "luxury": 20, "sports": 5, "other": 10,
    },
    "recent_velocity_30d": {
        "compact_sedan": 22, "midsize_sedan": 18, "full_size_sedan": 4,
        "compact_suv": 25, "midsize_suv": 15, "full_size_suv": 6,
        "pickup_full_size": 14, "pickup_midsize": 8,
        "minivan": 5, "luxury": 7, "sports": 2, "other": 2,
    },
    "wholesale_index_deltas": {
        "compact_sedan": 0.01, "midsize_sedan": 0.00, "full_size_sedan": 0.00,
        "compact_suv": -0.01, "midsize_suv": -0.02, "full_size_suv": -0.04,
        "pickup_full_size": 0.02, "pickup_midsize": 0.01,
        "minivan": 0.00, "luxury": -0.01, "sports": 0.00, "other": 0.00,
    },
}

# ── Market shock definitions ───────────────────────────────────────────────────

MARKET_SHOCKS: dict[str, dict] = {
    "wholesale_suv_drop": {
        "label": "Wholesale SUV prices drop 4%",
        "affected_segments": list(SUV_SEGMENTS),
        "risk_buffer_delta": 500, "demand_index_delta": 0.0, "recon_bays_delta": 0,
    },
    "sedan_demand_surge": {
        "label": "Sedan demand surge (tax refund season)",
        "affected_segments": list(SEDAN_SEGMENTS),
        "risk_buffer_delta": 0, "demand_index_delta": 0.10, "recon_bays_delta": 0,
    },
    "recon_bay_offline": {
        "label": "Recon bay goes offline",
        "affected_segments": [],
        "risk_buffer_delta": 0, "demand_index_delta": 0.0, "recon_bays_delta": -2,
    },
    "truck_wholesale_firms": {
        "label": "Truck wholesale firms up 3%",
        "affected_segments": list(TRUCK_SEGMENTS),
        "risk_buffer_delta": -300, "demand_index_delta": 0.0, "recon_bays_delta": 0,
    },
}

# ── Sample manifest ────────────────────────────────────────────────────────────

SAMPLE_MANIFEST: list[dict] = [
    {"year": 2022, "make": "Toyota",  "model": "Camry",      "mileage": 34000, "condition": 3.8, "auction_price": 22500, "trim": "",    "notes": ""},
    {"year": 2021, "make": "Honda",   "model": "CR-V",       "mileage": 41000, "condition": 3.5, "auction_price": 25200, "trim": "",    "notes": ""},
    {"year": 2023, "make": "Honda",   "model": "Civic",      "mileage": 18000, "condition": 4.3, "auction_price": 22800, "trim": "",    "notes": ""},
    {"year": 2022, "make": "Ford",    "model": "Explorer",   "mileage": 38000, "condition": 3.2, "auction_price": 29500, "trim": "",    "notes": ""},
    {"year": 2020, "make": "Chevy",   "model": "Equinox",    "mileage": 62000, "condition": 2.8, "auction_price": 16200, "trim": "",    "notes": "tire wear"},
    {"year": 2021, "make": "Ford",    "model": "F-150",      "mileage": 48000, "condition": 3.4, "auction_price": 32000, "trim": "XLT", "notes": "paint work"},
    {"year": 2022, "make": "Nissan",  "model": "Rogue",      "mileage": 29000, "condition": 3.9, "auction_price": 23100, "trim": "",    "notes": ""},
    {"year": 2023, "make": "Toyota",  "model": "RAV4",       "mileage": 15000, "condition": 4.5, "auction_price": 29800, "trim": "",    "notes": ""},
    {"year": 2019, "make": "Chevy",   "model": "Silverado",  "mileage": 71000, "condition": 2.5, "auction_price": 24500, "trim": "",    "notes": ""},
    {"year": 2022, "make": "Hyundai", "model": "Tucson",     "mileage": 33000, "condition": 3.6, "auction_price": 24000, "trim": "",    "notes": ""},
    {"year": 2021, "make": "Toyota",  "model": "Highlander", "mileage": 44000, "condition": 3.3, "auction_price": 33500, "trim": "",    "notes": ""},
    {"year": 2020, "make": "Chevy",   "model": "Tahoe",      "mileage": 58000, "condition": 2.9, "auction_price": 34000, "trim": "",    "notes": ""},
    {"year": 2022, "make": "Nissan",  "model": "Altima",     "mileage": 36000, "condition": 3.7, "auction_price": 20100, "trim": "",    "notes": ""},
    {"year": 2023, "make": "Honda",   "model": "Odyssey",    "mileage": 21000, "condition": 4.1, "auction_price": 32500, "trim": "",    "notes": ""},
    {"year": 2021, "make": "Toyota",  "model": "Tacoma",     "mileage": 39000, "condition": 3.4, "auction_price": 28500, "trim": "",    "notes": ""},
]

# ── Core functions ─────────────────────────────────────────────────────────────

def assign_segment(make: str, model: str) -> tuple[str, bool]:
    """Return (segment, is_mapped). is_mapped=False → 'other', user should review."""
    make_l = make.strip().lower()
    model_l = model.strip().lower()
    if make_l in LUXURY_MAKES:
        return "luxury", True
    if make_l in RAM_MAKES:
        return "pickup_full_size", True
    if model_l in SEGMENT_BY_MODEL:
        return SEGMENT_BY_MODEL[model_l], True
    for key, seg in SEGMENT_BY_MODEL.items():
        if key in model_l:
            return seg, True
    return "other", False


def check_condition_fail(notes: str) -> tuple[bool, str]:
    """Return (is_hard_fail, triggering_keyword)."""
    if not notes:
        return False, ""
    notes_l = notes.strip().lower()
    for kw in CONDITION_FAIL_KEYWORDS:
        if kw in notes_l:
            return True, kw
    return False, ""


def estimate_recon(condition: float, notes: str) -> tuple[float, int]:
    """Return (recon_cost, recon_days)."""
    cost, days = 4500, 12
    for row in RECON_TABLE:
        if row["grade_min"] <= condition <= row["grade_max"]:
            cost, days = row["base_cost"], row["base_days"]
            break
    notes_l = (notes or "").lower()
    for keyword, adj in NOTE_ADJUSTMENTS.items():
        if keyword in notes_l:
            cost += adj["cost"]
            days += adj["days"]
    return float(cost), days


def _apply_shocks(lot_state: dict, active_shocks: set[str]) -> tuple[dict, dict, dict]:
    """
    Returns (modified_lot_state, demand_deltas_by_segment, risk_deltas_by_segment).
    """
    ls = copy.deepcopy(lot_state)
    demand_deltas: dict[str, float] = {}
    risk_deltas: dict[str, float] = {}
    for shock_key in active_shocks:
        shock = MARKET_SHOCKS.get(shock_key)
        if not shock:
            continue
        for seg in shock.get("affected_segments", []):
            if shock.get("demand_index_delta"):
                demand_deltas[seg] = demand_deltas.get(seg, 0.0) + shock["demand_index_delta"]
            if shock.get("risk_buffer_delta"):
                risk_deltas[seg] = risk_deltas.get(seg, 0.0) + shock["risk_buffer_delta"]
        if shock.get("recon_bays_delta"):
            ls["recon_bays_total"] = max(1, ls["recon_bays_total"] + shock["recon_bays_delta"])
    return ls, demand_deltas, risk_deltas


def estimate_retail_price(
    segment: str, year: int, mileage: int, condition: float,
    demand_delta: float = 0.0,
) -> float:
    """Estimate expected retail price using spec formula."""
    mc = DEFAULT_MARKET_CONTEXT
    base = BASE_PRICES.get(segment, BASE_PRICES["other"])
    year_diff = year - 2022
    base += year_diff * 1500 if year_diff > 0 else year_diff * 2000
    mile_diff = mileage - 35_000
    base -= mile_diff * 0.08 if mile_diff > 0 else -abs(mile_diff) * 0.05
    cond_mult = 1.05 if condition >= 4.0 else (1.00 if condition >= 3.0 else (0.90 if condition >= 2.0 else 0.75))
    base *= cond_mult
    seasonal_mult = mc["seasonal_multipliers"].get(mc["season"], 1.0)
    demand_index = mc["regional_demand_index"].get(segment, 0.75) + demand_delta
    return max(float(base * seasonal_mult * demand_index), 1000.0)


def calculate_bid_ceiling(
    expected_retail: float, recon_cost: float, segment: str,
    lot_state: dict, risk_delta: float = 0.0,
) -> tuple[float, float, float]:
    """Return (bid_ceiling, target_margin, expected_margin_at_ceiling)."""
    mc = DEFAULT_MARKET_CONTEXT
    avg_days_to_sale = mc["avg_days_to_sale_by_segment"].get(segment, 30)
    daily_carry = lot_state.get("daily_carry_rate", mc["daily_carry_rate"])
    carry_cost = avg_days_to_sale * daily_carry
    target_margin = max(mc["avg_retail_margin_by_segment"].get(segment, 1200), 800)
    risk_buffer = 200.0
    w_delta = lot_state.get("wholesale_index_deltas", {}).get(segment, 0.0)
    if w_delta < -0.02:
        risk_buffer += 300
    if recon_cost > 2000:
        risk_buffer += 200
    if avg_days_to_sale > 35:
        risk_buffer += 200
    risk_buffer += risk_delta
    bid_ceiling = expected_retail - target_margin - recon_cost - carry_cost - risk_buffer
    expected_margin_at_ceiling = target_margin + risk_buffer
    return bid_ceiling, target_margin, expected_margin_at_ceiling


def score_portfolio_fit(
    segment: str, recon_days: int, lot_state: dict,
    bid_segment_counts: dict[str, int],
) -> float:
    """Compute portfolio_fit score (can be negative)."""
    counts = lot_state["segment_counts"]
    targets = lot_state["segment_targets"]
    velocities = lot_state["recent_velocity_30d"]
    current_count = counts.get(segment, 0) + bid_segment_counts.get(segment, 0)
    target = targets.get(segment, 10)
    segment_need = max(-1.0, min(1.0, (target - current_count) / max(target, 1)))
    seg_velocity = velocities.get(segment, 0)
    avg_velocity = sum(velocities.values()) / max(len(velocities), 1)
    velocity_score = min(1.0, seg_velocity / max(avg_velocity, 0.01))
    recon_total = lot_state["recon_bays_total"]
    recon_queue = lot_state.get("recon_queue_depth", 0)
    max_acceptable = recon_total * 1.5
    projected_queue = recon_queue + sum(bid_segment_counts.values())
    recon_capacity_score = max(0.0, 1.0 - (projected_queue / max(max_acceptable, 1)))
    new_count = current_count + 1
    concentration_penalty = 0.3 if (target > 0 and new_count / target > 1.15) else 0.0
    fit = (0.35 * segment_need + 0.30 * velocity_score
           + 0.20 * recon_capacity_score - 0.15 * concentration_penalty)
    return round(float(fit), 3)


def _get_primary_skip_reason(sv: dict, lot_state: dict) -> tuple[str, str, Optional[str]]:
    """Determine skip_reason, skip_detail, would_bid_if. Returns ("","",None) if should bid."""
    segment = sv["segment"]
    seg_label = SEGMENT_LABELS.get(segment, segment)
    counts = lot_state["segment_counts"]
    targets = lot_state["segment_targets"]
    velocities = lot_state["recent_velocity_30d"]
    current = counts.get(segment, 0)
    target = targets.get(segment, 10)
    seg_velocity = velocities.get(segment, 0)
    avg_velocity = sum(velocities.values()) / max(len(velocities), 1)
    w_delta = lot_state.get("wholesale_index_deltas", {}).get(segment, 0.0)
    if target > 0 and current / target > 1.15:
        over_pct = int((current / target - 1) * 100)
        return (
            "segment_overexposed",
            f"{seg_label} is {current} units vs target {target} — {over_pct}% over target.",
            f"Reduce {seg_label} inventory below {int(target * 1.15)} units.",
        )
    if w_delta < -0.02:
        return (
            "wholesale_softening",
            f"Wholesale index dropped {abs(w_delta)*100:.1f}% in {seg_label} — exit risk elevated.",
            "Wholesale index stabilizes in this segment.",
        )
    # Only penalize slow velocity when we're NOT undersupplied — if we need units, slow velocity is less relevant
    if avg_velocity > 0 and seg_velocity / avg_velocity < 0.50 and current >= target:
        return (
            "slow_segment",
            f"{seg_label} selling {seg_velocity} units/month — below average velocity.",
            "Segment velocity increases or lot depth in this segment decreases.",
        )
    if sv.get("condition", 5.0) < 2.5 or sv.get("recon_cost", 0) > 3000:
        return (
            "recon_risk",
            f"Condition {sv.get('condition', 0):.1f} with ${sv.get('recon_cost', 0):,.0f} estimated recon — high uncertainty.",
            "Condition grade improves or known issues are resolved prior to auction.",
        )
    return "", "", None


def _generate_rationale(sv: dict, lot_state: dict) -> str:
    """Generate one plain-English sentence for bid or skip."""
    segment = sv["segment"]
    seg_label = SEGMENT_LABELS.get(segment, segment)
    mc = DEFAULT_MARKET_CONTEXT
    counts = lot_state["segment_counts"]
    targets = lot_state["segment_targets"]
    velocities = lot_state["recent_velocity_30d"]
    current = counts.get(segment, 0)
    target = targets.get(segment, 10)
    need = target - current
    avg_days_to_sale = mc["avg_days_to_sale_by_segment"].get(segment, 30)
    w_delta = lot_state.get("wholesale_index_deltas", {}).get(segment, 0.0)
    velocity = velocities.get(segment, 0)

    if sv["status"] == "bid":
        ceiling = sv.get("bid_ceiling") or 0
        margin = sv.get("expected_margin") or 0
        recon = sv.get("recon_cost") or 0
        need_text = (f"Richmond is {need} units below target in {seg_label}" if need > 0
                     else (f"Richmond is at target in {seg_label}" if need == 0
                           else f"Richmond is {abs(need)} units above target in {seg_label}"))
        return (f"Bid up to ${ceiling:,.0f} on this {sv['label']}. "
                f"{need_text}, this segment sells in {avg_days_to_sale} days, "
                f"and expected margin at ceiling is ${margin:,.0f} after ${recon:,.0f} recon.")

    reason = sv.get("skip_reason", "")
    if reason == "segment_overexposed":
        over = current - target
        if w_delta < -0.02:
            return (f"Skip. Already {over} units over target in {seg_label}. "
                    f"Wholesale index dropped {abs(w_delta)*100:.0f}% this week — exit risk outweighs hold value.")
        return (f"Skip. Already {over} units over target in {seg_label} ({current} vs target {target}). "
                f"Adding more increases concentration risk.")
    if reason == "margin_insufficient":
        ceiling = sv.get('bid_ceiling') or 0
        auction = sv.get('auction_price', 0)
        gap = int(auction - ceiling)
        context = []
        if sv.get("condition", 5.0) < 3.0:
            context.append(f"condition {sv['condition']:.1f} drives up recon to ${sv.get('recon_cost', 0):,.0f}")
        if w_delta < -0.02:
            context.append(f"wholesale index down {abs(w_delta)*100:.1f}% adds risk buffer")
        current = counts.get(segment, 0)
        target_c = targets.get(segment, 10)
        if target_c > 0 and current / target_c > 1.15:
            context.append(f"{seg_label} is {current - target_c} units over target")
        context_str = "; ".join(context)
        suffix = f" ({context_str})" if context_str else ""
        return (f"Skip. Bid ceiling ${ceiling:,.0f} is ${gap:,} below ask{suffix}. "
                f"Would bid if auction price drops to ${ceiling:,.0f}.")
    if reason == "recon_risk":
        return (f"Skip. Condition {sv.get('condition', 0):.1f} with "
                f"${sv.get('recon_cost', 0):,.0f} estimated recon. High cost uncertainty outweighs expected margin.")
    if reason == "recon_queue_full":
        return "Skip. Recon queue can't absorb another unit this week. Come back once current queue clears."
    if reason == "slow_segment":
        return (f"Skip. {seg_label} moving {velocity} units/month — "
                f"too slow for current lot depth.")
    if reason == "wholesale_softening":
        return (f"Skip. Wholesale index dropped {abs(w_delta)*100:.1f}% in {seg_label}. "
                f"Buying into a softening segment increases exit risk.")
    if reason == "condition_fail":
        return sv.get("skip_detail", "Skip. Non-overridable condition issue detected in notes.")
    return sv.get("skip_detail", "Skip.")


def _apply_rank_and_cut(candidates: list[dict], lot_state: dict) -> tuple[list[dict], list[dict]]:
    """Walk sorted candidates, cut when projected recon queue > 2.5× bays."""
    recon_queue = lot_state.get("recon_queue_depth", 0)
    recon_bays = lot_state["recon_bays_total"]
    max_queue = recon_bays * 2.5
    final_bids, recon_cuts = [], []
    accumulated_days = 0.0
    for sv in candidates:
        projected = recon_queue + accumulated_days / max(recon_bays, 1)
        if projected > max_queue:
            sv = {**sv, "status": "skip", "skip_reason": "recon_queue_full",
                  "skip_detail": f"Recon queue ({projected:.0f} projected) exceeds capacity threshold.",
                  "would_bid_if": "A recon slot opens up (remove a bid vehicle or wait for current queue to clear)."}
            recon_cuts.append(sv)
        else:
            final_bids.append(sv)
            accumulated_days += sv.get("recon_days", 4)
    return final_bids, recon_cuts


# ── Master scoring pipeline ────────────────────────────────────────────────────

def score_manifest(manifest: list[dict], lot_state: dict, active_shocks: set[str]) -> list[dict]:
    """
    Score all vehicles. Returns list sorted: bids (ranked) first, then skips.
    Each item is a scored vehicle dict.
    """
    modified_lot, demand_deltas, risk_deltas = _apply_shocks(lot_state, active_shocks)

    hard_fails, margin_skips, other_skips, candidates = [], [], [], []

    for v in manifest:
        make = str(v.get("make", "")).strip()
        model = str(v.get("model", "")).strip()
        year = int(v.get("year", 2020))
        mileage = int(v.get("mileage", 50_000))
        condition = float(v.get("condition", 3.0))
        auction_price = float(v.get("auction_price", 20_000))
        trim = str(v.get("trim", "") or "").strip()
        notes = str(v.get("notes", "") or "").strip()
        vid = str(v.get("vid", f"{year}-{make}-{model}"))
        label = f"{year} {make} {model}" + (f" {trim}" if trim else "")

        segment, is_mapped = assign_segment(make, model)

        # Step 2: Hard fail
        is_fail, fail_kw = check_condition_fail(notes)
        if is_fail:
            sv = dict(
                vid=vid, label=label, year=year, make=make, model=model,
                mileage=mileage, condition=condition, auction_price=auction_price,
                trim=trim, notes=notes, segment=segment, segment_is_mapped=is_mapped,
                recon_cost=0.0, recon_days=0, expected_retail=0.0,
                bid_ceiling=None, expected_margin=None, portfolio_fit=None,
                rank_score=0.0, status="skip", skip_reason="condition_fail",
                skip_detail=f"Notes contain '{fail_kw}' — non-overridable skip.",
                would_bid_if=None, is_condition_fail=True, rationale="", rank=None,
            )
            sv["rationale"] = _generate_rationale(sv, modified_lot)
            hard_fails.append(sv)
            continue

        # Step 3: Recon
        recon_cost, recon_days = estimate_recon(condition, notes)

        # Step 4: Bid ceiling
        demand_delta = demand_deltas.get(segment, 0.0)
        risk_delta = risk_deltas.get(segment, 0.0)
        expected_retail = estimate_retail_price(segment, year, mileage, condition, demand_delta)
        bid_ceiling, target_margin, expected_margin = calculate_bid_ceiling(
            expected_retail, recon_cost, segment, modified_lot, risk_delta
        )

        sv = dict(
            vid=vid, label=label, year=year, make=make, model=model,
            mileage=mileage, condition=condition, auction_price=auction_price,
            trim=trim, notes=notes, segment=segment, segment_is_mapped=is_mapped,
            recon_cost=round(recon_cost, 0), recon_days=recon_days,
            expected_retail=round(expected_retail, 0),
            bid_ceiling=round(bid_ceiling, 0),
            expected_margin=round(expected_margin, 0),
            portfolio_fit=0.0, rank_score=0.0,
            status="bid", skip_reason="", skip_detail="", would_bid_if="",
            is_condition_fail=False, rationale="", rank=None,
        )

        if bid_ceiling < auction_price:
            sv["status"] = "skip"
            sv["skip_reason"] = "margin_insufficient"
            sv["skip_detail"] = f"Bid ceiling ${bid_ceiling:,.0f} is below auction price ${auction_price:,.0f}."
            sv["would_bid_if"] = (f"Auction price drops below ${bid_ceiling:,.0f}, "
                                   f"or retail demand strengthens in this segment.")
            margin_skips.append(sv)
            continue

        reason, detail, wbi = _get_primary_skip_reason(sv, modified_lot)
        if reason:
            sv["status"] = "skip"
            sv["skip_reason"] = reason
            sv["skip_detail"] = detail
            sv["would_bid_if"] = wbi or ""
            other_skips.append(sv)
            continue

        candidates.append(sv)

    # Pass 2: Initial sort by segment_need × margin, then compute portfolio_fit sequentially
    for sv in candidates:
        counts = modified_lot["segment_counts"]
        targets = modified_lot["segment_targets"]
        seg = sv["segment"]
        need = max(-1.0, min(1.0, (targets.get(seg, 10) - counts.get(seg, 0)) / max(targets.get(seg, 10), 1)))
        sv["_initial"] = sv["expected_margin"] * max(need, 0.1)
    candidates.sort(key=lambda x: x["_initial"], reverse=True)

    bid_segment_counts: dict[str, int] = {}
    for sv in candidates:
        seg = sv["segment"]
        sv["portfolio_fit"] = score_portfolio_fit(seg, sv["recon_days"], modified_lot, bid_segment_counts)
        sv["rank_score"] = sv["expected_margin"] * sv["portfolio_fit"]
        bid_segment_counts[seg] = bid_segment_counts.get(seg, 0) + 1

    candidates.sort(key=lambda x: x["rank_score"], reverse=True)

    final_bids, recon_cuts = _apply_rank_and_cut(candidates, modified_lot)
    for i, sv in enumerate(final_bids):
        sv["rank"] = i + 1

    all_vehicles = final_bids + recon_cuts + other_skips + margin_skips + hard_fails
    for sv in all_vehicles:
        sv["rationale"] = _generate_rationale(sv, modified_lot)
        sv.pop("_initial", None)

    return all_vehicles


# ── Portfolio impact ───────────────────────────────────────────────────────────

def compute_portfolio_impact(
    scored: list[dict],
    bid_status: dict[str, str],
    ceiling_overrides: dict[str, float],
    lot_state: dict,
) -> dict:
    """Compute live portfolio impact for current bid/skip assignments."""
    active_bids = [sv for sv in scored if bid_status.get(sv["vid"], sv["status"]) == "bid"]
    units_to_bid = len(active_bids)
    capital_required = sum(ceiling_overrides.get(sv["vid"], sv.get("bid_ceiling") or 0) for sv in active_bids)
    expected_gross = sum(sv.get("expected_margin") or 0 for sv in active_bids)
    recon_days_total = sum(sv.get("recon_days") or 0 for sv in active_bids)
    segment_adds: dict[str, int] = {}
    for sv in active_bids:
        seg = sv["segment"]
        segment_adds[seg] = segment_adds.get(seg, 0) + 1
    current_queue = lot_state.get("recon_queue_depth", 0)
    recon_bays = lot_state["recon_bays_total"]
    projected_queue = current_queue + recon_days_total / max(recon_bays, 1)
    counts = lot_state["segment_counts"]
    targets = lot_state["segment_targets"]
    warnings = []
    for seg, adds in segment_adds.items():
        new_count = counts.get(seg, 0) + adds
        target = targets.get(seg, 10)
        if target > 0 and new_count / target > 1.15:
            warnings.append(f"{SEGMENT_LABELS.get(seg, seg)}: {new_count} units ({int((new_count/target-1)*100)}% over target)")
    return {
        "units_to_bid": units_to_bid, "capital_required": capital_required,
        "expected_gross": expected_gross, "segment_adds": segment_adds,
        "recon_days_total": recon_days_total, "current_queue": current_queue,
        "projected_queue": round(projected_queue, 1), "recon_bays": recon_bays,
        "concentration_warnings": warnings,
    }


# ── Displacement check ────────────────────────────────────────────────────────

def check_displacement(
    changed_vid: str, new_status: str,
    scored: list[dict], bid_status: dict[str, str], lot_state: dict,
) -> Optional[dict]:
    """Return displacement/promotion suggestion dict, or None."""
    if new_status == "bid":
        changed = next((sv for sv in scored if sv["vid"] == changed_vid), None)
        if not changed:
            return None
        segment = changed["segment"]
        counts = lot_state["segment_counts"]
        targets = lot_state["segment_targets"]
        active_bids = [sv for sv in scored if bid_status.get(sv["vid"], sv["status"]) == "bid"]
        seg_in_bids = sum(1 for sv in active_bids if sv["segment"] == segment)
        new_seg_count = counts.get(segment, 0) + seg_in_bids
        target = targets.get(segment, 10)
        over_threshold = target > 0 and new_seg_count / target > 1.20
        recon_total = sum(sv.get("recon_days") or 0 for sv in active_bids)
        projected_queue = lot_state.get("recon_queue_depth", 0) + recon_total / max(lot_state["recon_bays_total"], 1)
        recon_over = projected_queue > lot_state["recon_bays_total"] * 2.5
        if over_threshold or recon_over:
            sorted_bids = sorted(active_bids, key=lambda x: x.get("rank_score") or 0)
            candidate = None
            if over_threshold:
                same_seg = [sv for sv in sorted_bids if sv["segment"] == segment]
                candidate = same_seg[0] if same_seg else (sorted_bids[0] if sorted_bids else None)
            else:
                by_recon = sorted(active_bids, key=lambda x: x.get("recon_days") or 0, reverse=True)
                candidate = by_recon[0] if by_recon else None
            if candidate:
                parts = []
                if over_threshold:
                    parts.append(f"{SEGMENT_LABELS.get(segment, segment)} would be {new_seg_count - target} over target")
                if recon_over:
                    parts.append("recon can't absorb both this week")
                return {"type": "displacement", "added_vid": changed_vid,
                        "added_label": changed["label"], "displaced_vid": candidate["vid"],
                        "displaced_label": candidate["label"], "reason": " and ".join(parts)}
    elif new_status == "skip":
        recon_cut_skips = [
            sv for sv in scored
            if sv.get("skip_reason") == "recon_queue_full"
            and bid_status.get(sv["vid"], sv["status"]) == "skip"
        ]
        if recon_cut_skips:
            best = max(recon_cut_skips, key=lambda x: x.get("rank_score") or 0)
            removed_label = next((sv["label"] for sv in scored if sv["vid"] == changed_vid), changed_vid)
            return {"type": "promotion", "removed_vid": changed_vid,
                    "removed_label": removed_label, "promoted_vid": best["vid"],
                    "promoted_label": best["label"], "promoted_rank": best.get("rank", "—")}
    return None
