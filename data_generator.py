import numpy as np
import pandas as pd


def generate_cohorts(seed=42, n=60):
    rng = np.random.default_rng(seed)

    market_clusters = [
        "Richmond", "Mid-Atlantic North", "Atlanta",
        "Dallas", "Southeast", "Midwest Central",
    ]
    source_channels = ["consumer_appraisal", "dealer_purchase", "auction"]
    retailability_states = [
        "frontline_ready", "recon_light", "recon_heavy",
        "borderline_retail", "wholesale_likely",
    ]
    body_types = ["sedan", "suv", "truck", "cuv", "van", "ev"]
    price_bands = ["under_20k", "20k_30k", "30k_40k", "40k_plus"]
    age_bands = ["0_3_years", "4_6_years", "7_10_years", "10_plus_years"]
    mileage_bands = ["under_30k", "30k_60k", "60k_90k", "90k_plus"]

    rows = []
    for i in range(n):
        cohort_id = f"COH-{1000 + i}"
        market_cluster = rng.choice(market_clusters)
        store_count = int(rng.integers(3, 15))

        # Auction cohorts are riskier on average
        source_channel = rng.choice(source_channels, p=[0.45, 0.30, 0.25])

        if source_channel == "auction":
            ret_probs = [0.10, 0.20, 0.25, 0.25, 0.20]
        elif source_channel == "dealer_purchase":
            ret_probs = [0.20, 0.30, 0.20, 0.20, 0.10]
        else:
            ret_probs = [0.35, 0.30, 0.15, 0.15, 0.05]
        retailability_state = rng.choice(retailability_states, p=ret_probs)

        body_type = rng.choice(body_types, p=[0.18, 0.25, 0.15, 0.22, 0.05, 0.15])
        age_band = rng.choice(age_bands, p=[0.30, 0.30, 0.25, 0.15])
        mileage_band = rng.choice(mileage_bands, p=[0.20, 0.35, 0.30, 0.15])

        # Trucks/SUVs skew toward higher price bands
        if body_type in ["truck", "suv"]:
            pb_probs = [0.05, 0.20, 0.40, 0.35]
        elif body_type == "ev":
            pb_probs = [0.03, 0.12, 0.35, 0.50]
        elif age_band == "10_plus_years":
            pb_probs = [0.55, 0.30, 0.10, 0.05]
        elif age_band == "7_10_years":
            pb_probs = [0.35, 0.35, 0.20, 0.10]
        else:
            pb_probs = [0.15, 0.35, 0.30, 0.20]
        price_band = rng.choice(price_bands, p=pb_probs)

        cohort_units = int(rng.integers(5, 40))

        # Timing — aged / at-risk cohorts have more days
        if retailability_state in ["wholesale_likely", "recon_heavy"]:
            days_since_acq = int(rng.integers(20, 80))
        elif retailability_state == "borderline_retail":
            days_since_acq = int(rng.integers(10, 55))
        else:
            days_since_acq = int(rng.integers(0, 35))

        if retailability_state == "recon_heavy":
            days_in_recon = int(rng.integers(10, 30))
        elif retailability_state == "recon_light":
            days_in_recon = int(rng.integers(3, 12))
        else:
            days_in_recon = int(rng.integers(0, 4))

        days_frontline_ready = (
            int(rng.integers(1, max(2, days_since_acq - days_in_recon + 1)))
            if retailability_state == "frontline_ready"
            else 0
        )
        days_in_current_stage = int(rng.integers(1, max(2, days_since_acq // 2 + 1)))
        days_since_listed = int(rng.integers(0, max(1, days_since_acq - days_in_recon)))

        # Economics — base price from price band
        price_lo_hi = {
            "under_20k": (10_000, 18_000),
            "20k_30k": (18_000, 28_000),
            "30k_40k": (27_000, 38_000),
            "40k_plus": (37_000, 65_000),
        }
        lo, hi = price_lo_hi[price_band]
        avg_acquisition_cost = float(rng.uniform(lo, hi))

        if retailability_state == "wholesale_likely":
            retail_markup = rng.uniform(0.92, 1.04)
        elif retailability_state in ["recon_heavy", "borderline_retail"]:
            retail_markup = rng.uniform(1.04, 1.14)
        else:
            retail_markup = rng.uniform(1.12, 1.28)
        current_expected_retail_price = avg_acquisition_cost * retail_markup

        if retailability_state == "recon_heavy":
            expected_recon_cost = float(rng.uniform(1_500, 4_000))
        elif retailability_state in ["recon_light", "borderline_retail"]:
            expected_recon_cost = float(rng.uniform(400, 1_500))
        else:
            expected_recon_cost = float(rng.uniform(50, 400))

        if retailability_state == "wholesale_likely":
            wholesale_fraction = rng.uniform(0.80, 0.96)
        else:
            wholesale_fraction = rng.uniform(0.68, 0.88)
        wholesale_floor_price = avg_acquisition_cost * wholesale_fraction

        daily_carry_depreciation = float(
            current_expected_retail_price * rng.uniform(0.0008, 0.0020)
        )
        embedded_transfer_cost = float(rng.uniform(300, 850))

        # Operational modifiers
        recon_priority_score = int(rng.integers(10, 96))
        market_demand_index = float(rng.uniform(0.80, 1.20))
        market_supply_pressure_index = float(rng.uniform(0.80, 1.20))
        transfer_uplift_pct = float(rng.uniform(0.02, 0.10))

        # Decay rates — older / higher-mileage vehicles decay faster
        age_base_decay = {
            "0_3_years": 0.0015,
            "4_6_years": 0.0035,
            "7_10_years": 0.0060,
            "10_plus_years": 0.0110,
        }[age_band]
        retail_price_decay_rate = float(
            rng.uniform(age_base_decay * 0.7, age_base_decay * 1.5)
        )

        if retailability_state == "wholesale_likely":
            sale_prob_decay = float(rng.uniform(0.040, 0.080))
        elif retailability_state in ["recon_heavy", "borderline_retail"]:
            sale_prob_decay = float(rng.uniform(0.020, 0.050))
        else:
            sale_prob_decay = float(rng.uniform(0.008, 0.028))

        rows.append({
            "cohort_id": cohort_id,
            "market_cluster": market_cluster,
            "store_count_coverage": store_count,
            "source_channel": source_channel,
            "retailability_state": retailability_state,
            "body_type": body_type,
            "price_band": price_band,
            "age_band": age_band,
            "mileage_band": mileage_band,
            "cohort_units": cohort_units,
            "days_since_acquisition": days_since_acq,
            "days_in_current_stage": days_in_current_stage,
            "days_in_recon": days_in_recon,
            "days_frontline_ready": days_frontline_ready,
            "days_since_listed": days_since_listed,
            "avg_acquisition_cost": round(avg_acquisition_cost, 2),
            "expected_recon_cost": round(expected_recon_cost, 2),
            "daily_carry_depreciation": round(daily_carry_depreciation, 2),
            "current_expected_retail_price": round(current_expected_retail_price, 2),
            "wholesale_floor_price": round(wholesale_floor_price, 2),
            "embedded_transfer_cost": round(embedded_transfer_cost, 2),
            "recon_priority_score": recon_priority_score,
            "market_demand_index": round(market_demand_index, 3),
            "market_supply_pressure_index": round(market_supply_pressure_index, 3),
            "transfer_uplift_pct": round(transfer_uplift_pct, 3),
            "sale_probability_decay_rate": round(sale_prob_decay, 5),
            "retail_price_decay_rate": round(retail_price_decay_rate, 6),
        })

    return pd.DataFrame(rows)
