import numpy as np

# ── Strategy presets ──────────────────────────────────────────────────────
# Each mode shifts a few coefficients; recommendation naturally follows.
STRATEGY_PARAMS = {
    "Margin Max": {
        "base_sale_prob_scale": 1.08,   # more optimistic about retail sale
        "decay_modifier": 0.70,          # slower sale-prob decay → hold longer
        "carry_weight": 0.80,            # lighter carry penalty → hold is cheaper
    },
    "Balanced": {
        "base_sale_prob_scale": 1.00,
        "decay_modifier": 1.00,
        "carry_weight": 1.00,
    },
    "Turn Max": {
        "base_sale_prob_scale": 0.88,    # more pessimistic → exit sooner
        "decay_modifier": 1.35,           # faster effective decay
        "carry_weight": 1.45,             # heavier aging penalty
    },
}

# Base sale probability by retailability state (reflects frontline availability)
BASE_SALE_PROB = {
    "frontline_ready":   0.90,
    "recon_light":       0.78,
    "recon_heavy":       0.45,
    "borderline_retail": 0.58,
    "low_retail_fit":    0.30,
}

TRANSFER_TRANSIT_DAYS = 4   # days vehicle is in transit before it can sell


def _get_base_sale_prob(cohort, params):
    state_prob = BASE_SALE_PROB.get(cohort["retailability_state"], 0.55)
    demand_adj = (cohort["market_demand_index"] - 1.0) * 0.25
    raw = state_prob * params["base_sale_prob_scale"] + demand_adj
    return float(np.clip(raw, 0.05, 0.95))


# ── Path evaluators ───────────────────────────────────────────────────────

def evaluate_hold_path(cohort, scenario, strategy_mode="Balanced",
                       markdown_pct=0.0, horizon=30):
    """Return (days, ev_curve, retail_prices_curve)."""
    params = STRATEGY_PARAMS[strategy_mode]
    days = np.arange(0, horizon + 1)

    base_price = cohort["current_expected_retail_price"] * (1 - markdown_pct)
    retail_prices = base_price * ((1 - cohort["retail_price_decay_rate"]) ** days)

    base_prob = _get_base_sale_prob(cohort, params)
    decay = cohort["sale_probability_decay_rate"] * params["decay_modifier"]
    sale_probs = base_prob * np.exp(-decay * days)
    sale_probs = np.clip(sale_probs, 0.01, 0.98)

    acq   = cohort["avg_acquisition_cost"]
    recon = cohort["expected_recon_cost"]
    carry = cohort["daily_carry_depreciation"] * params["carry_weight"]

    ev = (retail_prices * sale_probs) - acq - recon - (carry * days)
    ev = ev * scenario.get("demand_mult", 1.0)

    return days, ev, retail_prices


def evaluate_wholesale_path(cohort, scenario):
    """Immediate liquidation expected value (net of acquisition cost)."""
    shock = scenario.get("wholesale_shock", 0.0)
    gross = cohort["market_floor_price"] * (1 + shock)
    return float(gross - cohort["avg_acquisition_cost"])


def evaluate_transfer_path(cohort, scenario, strategy_mode="Balanced", horizon=30):
    """Return (days, ev_curve). Transfer = price uplift to stronger market, fixed cost, transit delay."""
    params = STRATEGY_PARAMS[strategy_mode]
    days = np.arange(0, horizon + 1)

    # Price in destination market after transit depreciation
    uplift = cohort["transfer_uplift_pct"]
    price_at_arrival = (
        cohort["current_expected_retail_price"]
        * (1 + uplift)
        * ((1 - cohort["retail_price_decay_rate"]) ** TRANSFER_TRANSIT_DAYS)
    )
    retail_prices = price_at_arrival * ((1 - cohort["retail_price_decay_rate"]) ** days)

    # Sale probability boost is demand-driven: only helps when local market is weak
    local_demand = cohort["market_demand_index"]
    demand_gap = max(0.0, 1.0 - local_demand)          # positive only when demand < average
    transfer_sale_boost = 1.0 + demand_gap * 1.40       # up to ~1.28x when demand = 0.80
    if local_demand > 1.05:                              # strong local market → transfer disrupts
        transfer_sale_boost = max(0.92, 1.0 - (local_demand - 1.05) * 0.6)

    base_prob = _get_base_sale_prob(cohort, params)
    transfer_prob = float(np.clip(base_prob * transfer_sale_boost, 0.05, 0.95))
    decay = cohort["sale_probability_decay_rate"] * params["decay_modifier"]
    sale_probs = transfer_prob * np.exp(-decay * days)
    sale_probs = np.clip(sale_probs, 0.01, 0.98)

    acq           = cohort["avg_acquisition_cost"]
    recon         = cohort["expected_recon_cost"]
    carry         = cohort["daily_carry_depreciation"] * params["carry_weight"]
    transfer_cost = cohort["embedded_transfer_cost"]
    transit_carry = cohort["daily_carry_depreciation"] * TRANSFER_TRANSIT_DAYS

    ev = (retail_prices * sale_probs) - acq - recon - transfer_cost - transit_carry - (carry * days)
    ev = ev * scenario.get("demand_mult", 1.0)

    return days, ev


def evaluate_expedite_path(cohort, scenario, strategy_mode="Balanced", horizon=30):
    """Return (days, ev_curve). Expedite = vehicle treated as frontline_ready immediately, minus expedite cost."""
    params = STRATEGY_PARAMS[strategy_mode]
    days = np.arange(0, horizon + 1)

    # Model expedite as: recon state magically becomes frontline_ready right now
    frontline_prob = BASE_SALE_PROB["frontline_ready"]
    demand_adj = (cohort["market_demand_index"] - 1.0) * 0.25
    base_prob = float(np.clip(
        frontline_prob * params["base_sale_prob_scale"] + demand_adj, 0.05, 0.95
    ))

    retail_prices = (
        cohort["current_expected_retail_price"]
        * ((1 - cohort["retail_price_decay_rate"]) ** days)
    )
    decay = cohort["sale_probability_decay_rate"] * params["decay_modifier"]
    sale_probs = base_prob * np.exp(-decay * days)
    sale_probs = np.clip(sale_probs, 0.01, 0.98)

    acq   = cohort["avg_acquisition_cost"]
    recon = cohort["expected_recon_cost"]
    carry = cohort["daily_carry_depreciation"] * params["carry_weight"]

    ev = (retail_prices * sale_probs) - acq - recon - (carry * days)
    ev = ev * scenario.get("demand_mult", 1.0)

    # Expedite cost (higher when recon capacity is tight)
    recon_pressure = scenario.get("recon_pressure", "medium")
    expedite_penalty = {"low": 250, "medium": 450, "high": 700}[recon_pressure]
    ev = ev - expedite_penalty

    # Expedite only makes sense if the vehicle is currently recon-trapped
    if cohort["retailability_state"] not in ("recon_heavy", "recon_light", "borderline_retail"):
        # Already frontline: expedite offers no improvement over hold (small penalty applies)
        days_h, ev_hold, _ = evaluate_hold_path(cohort, scenario, strategy_mode, 0.0, horizon)
        ev = ev_hold - expedite_penalty * 0.5   # minor cost, not useful

    return days, ev


# ── Derived outputs ───────────────────────────────────────────────────────

def compute_crossover_day(ev_hold_curve, ev_wholesale):
    """First day where expected retail hold value drops below the market floor."""
    for d, val in enumerate(ev_hold_curve):
        if val < ev_wholesale:
            return int(d)
    return None


def compute_acquisition_confidence(cohort, results):
    """Return (score 0-100, label str)."""
    score = 50
    rec = results.get("recommended_action", "")

    if rec == "Hold for Retail":
        score += 15
    elif rec == "Transfer to Stronger Market":
        score += 10
    elif rec == "Expedite Recon":
        score -= 10
    elif rec == "Liquidate":
        score -= 20

    crossover_day = results.get("crossover_day")
    if crossover_day is None or crossover_day > 14:
        score += 10

    if cohort["days_since_acquisition"] > 45:
        score -= 10

    if cohort["retailability_state"] in ("recon_heavy", "low_retail_fit"):
        score -= 10

    # All retail paths have negative EV → bad buy signal
    best_retail_ev = max(
        results.get("best_ev_hold", 0),
        results.get("best_ev_transfer", 0),
        results.get("best_ev_expedite", 0),
    )
    if best_retail_ev < 0:
        score -= 10

    score = int(np.clip(score, 0, 100))
    label = "High" if score >= 70 else ("Medium" if score >= 40 else "Low")
    return score, label


def choose_recommendation(ev_hold, ev_transfer, ev_expedite, ev_wholesale, strategy_mode):
    """Pick the highest-EV action after strategy-mode adjustments."""
    params = STRATEGY_PARAMS[strategy_mode]

    # Margin Max: penalize exit slightly (patient; hold longer)
    # Turn Max: bonus to exit (impatient; willing to liquidate)
    # Use carry_weight as a proxy for time preference
    exit_adj = {
        "Margin Max": -200,   # harder to justify liquidation
        "Balanced":    0,
        "Turn Max":  +300,    # easier to justify liquidation
    }[strategy_mode]

    candidates = {
        "Hold for Retail":              ev_hold,
        "Transfer to Stronger Market":  ev_transfer,
        "Expedite Recon":               ev_expedite,
        "Liquidate":                    ev_wholesale + exit_adj,
    }
    return max(candidates, key=candidates.get)


def generate_rationale(cohort, results):
    rec = results["recommended_action"]
    crossover_day = results.get("crossover_day")
    horizon = results.get("horizon", 30)
    days_left = (
        f"~{crossover_day} days" if crossover_day is not None
        else f"beyond the {horizon}-day horizon"
    )

    if rec == "Hold for Retail":
        return (
            f"Retail economics remain strong for {days_left}. "
            f"This cohort still has healthy demand in {cohort['market_cluster']} "
            f"(demand index: {cohort['market_demand_index']:.2f}). "
            f"Continue monitoring for signs of softening. "
            f"A markdown lever is available if sale velocity slows."
        )
    elif rec == "Transfer to Stronger Market":
        return (
            f"Local demand in {cohort['market_cluster']} is below average "
            f"(demand index: {cohort['market_demand_index']:.2f}). "
            f"A transfer uplift of {cohort['transfer_uplift_pct']*100:.1f}% to a stronger market "
            f"offsets the ${cohort['embedded_transfer_cost']:,.0f} move cost and extends the viable retail window. "
            f"Crossover expected at {days_left} if no action is taken."
        )
    elif rec == "Expedite Recon":
        return (
            f"This cohort is currently recon-trapped "
            f"({cohort['days_in_recon']} days in recon, state: "
            f"{cohort['retailability_state'].replace('_', ' ')}). "
            f"Paying an expedite premium compresses time-to-frontline, "
            f"preserving retail economics before the crossover at {days_left}. "
            f"Moving this cohort to frontline immediately captures meaningful retail upside."
        )
    elif rec == "Liquidate":
        if crossover_day == 0:
            timing = "The retail crossover has already occurred."
        elif crossover_day is not None:
            timing = f"Retail crossover expected in {days_left}."
        else:
            timing = "Expected retail value is marginal across all paths."
        return (
            f"{timing} "
            f"Under the selected strategy, additional hold time increases downside. "
            f"Retail economics don't support this purchase at current market prices — "
            f"liquidating at ${cohort['market_floor_price']:,.0f} "
            f"preserves more value than waiting."
        )
    return ""


# ── Main evaluation entry point ───────────────────────────────────────────

def evaluate_cohort(cohort, scenario, strategy_mode="Balanced",
                    markdown_pct=0.0, horizon=30):
    days, ev_hold, retail_prices = evaluate_hold_path(
        cohort, scenario, strategy_mode, markdown_pct, horizon
    )
    _, ev_transfer = evaluate_transfer_path(cohort, scenario, strategy_mode, horizon)
    _, ev_expedite = evaluate_expedite_path(cohort, scenario, strategy_mode, horizon)
    ev_wholesale   = evaluate_wholesale_path(cohort, scenario)

    best_ev_hold     = float(np.max(ev_hold))
    best_ev_transfer = float(np.max(ev_transfer))
    best_ev_expedite = float(np.max(ev_expedite))

    crossover_day = compute_crossover_day(ev_hold, ev_wholesale)

    recommended_action = choose_recommendation(
        best_ev_hold, best_ev_transfer, best_ev_expedite, ev_wholesale, strategy_mode
    )

    results = {
        "days":              days,
        "ev_hold_curve":     ev_hold,
        "ev_transfer_curve": ev_transfer,
        "ev_expedite_curve": ev_expedite,
        "retail_prices":     retail_prices,
        "ev_wholesale":      ev_wholesale,
        "best_ev_hold":      best_ev_hold,
        "best_ev_transfer":  best_ev_transfer,
        "best_ev_expedite":  best_ev_expedite,
        "crossover_day":     crossover_day,
        "recommended_action": recommended_action,
        "strategy_mode":     strategy_mode,
        "horizon":           horizon,
    }

    results["acquisition_confidence_score"], results["acquisition_confidence_label"] = (
        compute_acquisition_confidence(cohort, results)
    )
    results["decision_rationale"] = generate_rationale(cohort, results)

    return results
