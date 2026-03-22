import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from collections import defaultdict

from data_generator import generate_cohorts
from logic import evaluate_cohort
from scoring import (
    score_manifest, compute_portfolio_impact, check_displacement,
    DEFAULT_LOT_STATE, DEFAULT_MARKET_CONTEXT, MARKET_SHOCKS, SAMPLE_MANIFEST,
    SEGMENT_LABELS,
)

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Merchant — Auction Drop",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .kpi-label { font-size: 0.75rem; color: #666; margin-bottom: 2px; }
  .kpi-value { font-size: 1.6rem; font-weight: 700; color: #1a1a1a; }
</style>
""", unsafe_allow_html=True)

# ── Portfolio data (for Tab 2) ─────────────────────────────────────────────────
@st.cache_data
def load_data():
    return generate_cohorts()

df = load_data()

# ── Session state init ─────────────────────────────────────────────────────────
for key, val in {
    "scored_flag": False, "scored": [], "bid_status": {},
    "ceiling_overrides": {}, "manual_overrides": set(),
    "displacement_msg": None, "last_scored_shocks": frozenset(),
    "last_manifest_records": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

if "manifest_input_df" not in st.session_state:
    st.session_state["manifest_input_df"] = pd.DataFrame(SAMPLE_MANIFEST)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Merchant")

    st.subheader("Lot Settings")
    ls = DEFAULT_LOT_STATE
    total_units    = st.number_input("Total Units",         value=ls["total_units"],         min_value=0, step=1,   key="ls_total")
    capacity       = st.number_input("Lot Capacity",        value=ls["capacity"],            min_value=0, step=1,   key="ls_cap")
    recon_bays     = st.number_input("Recon Bays (Total)",  value=ls["recon_bays_total"],    min_value=1, step=1,   key="ls_bays")
    recon_occ      = st.number_input("Recon Bays Occupied", value=ls["recon_bays_occupied"], min_value=0, step=1,   key="ls_occ")
    recon_queue    = st.number_input("Recon Queue Depth",   value=ls["recon_queue_depth"],   min_value=0, step=1,   key="ls_queue")
    avg_days       = st.number_input("Avg Days on Lot",     value=float(ls["avg_days_on_lot"]), min_value=0.0, step=1.0, key="ls_days")
    daily_carry    = st.number_input("Daily Carry Rate ($)", value=float(ls["daily_carry_rate"]), min_value=0.0, step=5.0, key="ls_carry")

    lot_state = {
        **DEFAULT_LOT_STATE,
        "total_units": int(total_units), "capacity": int(capacity),
        "recon_bays_total": int(recon_bays), "recon_bays_occupied": int(recon_occ),
        "recon_queue_depth": int(recon_queue), "avg_days_on_lot": float(avg_days),
        "daily_carry_rate": float(daily_carry),
    }

    st.divider()
    st.subheader("Market Shocks")
    active_shocks: set[str] = set()
    for shock_key, shock_def in MARKET_SHOCKS.items():
        if st.toggle(shock_def["label"], value=False, key=f"shock_{shock_key}"):
            active_shocks.add(shock_key)

    st.divider()
    with st.expander("Portfolio Analysis Settings"):
        st.markdown("**Filters**")
        all_opt = ["All"]
        sel_source = st.selectbox("Source",         all_opt + sorted(df["source_channel"].unique()),    key="pf_src")
        sel_ret    = st.selectbox("Retailability",  all_opt + sorted(df["retailability_state"].unique()), key="pf_ret")
        sel_market = st.selectbox("Market Cluster", all_opt + sorted(df["market_cluster"].unique()),    key="pf_mkt")
        sel_body   = st.selectbox("Body Type",      all_opt + sorted(df["body_type"].unique()),         key="pf_body")
        sel_price  = st.selectbox("Price Band",     all_opt + sorted(df["price_band"].unique()),        key="pf_price")
        sel_age    = st.selectbox("Age Band",       all_opt + sorted(df["age_band"].unique()),          key="pf_age")

        st.markdown("**Strategy**")
        strategy_mode = st.radio("Strategy Mode", ["Margin Max", "Balanced", "Turn Max"], index=1, key="strat_mode")
        hold_horizon  = st.slider("Hold Horizon (days)", 7, 45, 30, key="strat_horizon")
        use_markdown  = st.toggle("Apply Markdown", key="strat_mkd")
        markdown_pct  = st.slider("Markdown %", 1, 10, 3, key="strat_mkd_pct") / 100 if use_markdown else 0.0

        st.markdown("**Scenario**")
        ws_shock_pct  = st.slider("Wholesale Shock (%)", -10, 5, 0, key="scen_ws")
        demand_label  = st.select_slider("Demand Strength", ["Weak", "Base", "Strong"], value="Base", key="scen_demand")
        recon_pressure = st.select_slider("Recon Pressure", ["low", "medium", "high"], value="medium", key="scen_recon")

portfolio_scenario = {
    "wholesale_shock": ws_shock_pct / 100,
    "demand_mult": {"Weak": 0.85, "Base": 1.0, "Strong": 1.15}[demand_label],
    "recon_pressure": recon_pressure,
}

# ── Auto re-score on shock change ──────────────────────────────────────────────
def _rescore_preserving_overrides():
    records = st.session_state.last_manifest_records
    if not records:
        return
    new_scored = score_manifest(records, lot_state, active_shocks)
    new_status = {sv["vid"]: sv["status"] for sv in new_scored}
    for vid in st.session_state.manual_overrides:
        if vid in st.session_state.bid_status:
            sv = next((s for s in new_scored if s["vid"] == vid), None)
            if sv and not sv.get("is_condition_fail", False):
                new_status[vid] = st.session_state.bid_status[vid]
    st.session_state.scored = new_scored
    st.session_state.bid_status = new_status
    st.session_state.displacement_msg = None
    st.session_state.last_scored_shocks = frozenset(active_shocks)

if st.session_state.scored_flag and frozenset(active_shocks) != st.session_state.last_scored_shocks:
    _rescore_preserving_overrides()

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Auction Drop", "Current Lot", "Export"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — AUCTION DROP
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Auction Drop")
    st.caption("Score today's auction manifest against your current lot. Get a ranked bid list with ceiling prices and skip reasons.")

    # ── Manifest Input ─────────────────────────────────────────────────────────
    st.subheader("Manifest Input")

    uploaded = st.file_uploader("Upload CSV (year,make,model,mileage,condition,auction_price,trim,notes)",
                                type=["csv"], key="csv_upload")
    if uploaded:
        try:
            upload_df = pd.read_csv(uploaded)
            required_cols = {"year", "make", "model", "mileage", "condition", "auction_price"}
            if required_cols.issubset(set(upload_df.columns)):
                for col in ["trim", "notes"]:
                    if col not in upload_df.columns:
                        upload_df[col] = ""
                upload_df = upload_df.fillna({"trim": "", "notes": ""})
                st.session_state["manifest_input_df"] = upload_df[list(required_cols) + ["trim", "notes"]]
                st.success(f"Loaded {len(upload_df)} vehicles from CSV.")
            else:
                st.error(f"CSV missing columns: {required_cols - set(upload_df.columns)}")
        except Exception as e:
            st.error(f"CSV parse error: {e}")

    manifest_df = st.data_editor(
        st.session_state["manifest_input_df"],
        num_rows="dynamic",
        column_config={
            "year":          st.column_config.NumberColumn("Year",           min_value=2000, max_value=2030, step=1),
            "make":          st.column_config.TextColumn("Make"),
            "model":         st.column_config.TextColumn("Model"),
            "mileage":       st.column_config.NumberColumn("Mileage",        min_value=0, step=1000),
            "condition":     st.column_config.NumberColumn("Condition (1–5)", min_value=1.0, max_value=5.0, step=0.1),
            "auction_price": st.column_config.NumberColumn("Auction Price ($)", min_value=1, step=100),
            "trim":          st.column_config.TextColumn("Trim (optional)"),
            "notes":         st.column_config.TextColumn("Notes (optional)"),
        },
        use_container_width=True,
        key="manifest_editor",
        height=320,
    )
    st.session_state["manifest_input_df"] = manifest_df

    # Validation
    required_cols = ["year", "make", "model", "mileage", "condition", "auction_price"]
    valid_rows = manifest_df.dropna(subset=required_cols)
    errors = []
    if len(manifest_df) - len(valid_rows) > 0:
        errors.append(f"{len(manifest_df) - len(valid_rows)} row(s) missing required fields.")
    bad_cond = valid_rows[~valid_rows["condition"].between(1.0, 5.0)]
    if len(bad_cond):
        errors.append(f"{len(bad_cond)} row(s) have condition outside 1.0–5.0.")
    bad_price = valid_rows[valid_rows["auction_price"] <= 0]
    if len(bad_price):
        errors.append(f"{len(bad_price)} row(s) have auction price ≤ $0.")

    vc1, vc2 = st.columns([4, 1])
    with vc1:
        if errors:
            st.warning("  |  ".join(errors))
        else:
            st.caption(f"{len(valid_rows)} vehicle(s) ready to score.")
    with vc2:
        score_clicked = st.button("Score Auction", type="primary",
                                  disabled=bool(errors) or len(valid_rows) == 0,
                                  use_container_width=True)

    if score_clicked:
        records = []
        for i, (_, row) in enumerate(valid_rows.iterrows()):
            records.append({
                "vid": f"V-{i+1:03d}",
                "year": int(row["year"]), "make": str(row["make"]).strip(),
                "model": str(row["model"]).strip(), "mileage": int(row["mileage"]),
                "condition": float(row["condition"]), "auction_price": float(row["auction_price"]),
                "trim": str(row.get("trim", "") or "").strip(),
                "notes": str(row.get("notes", "") or "").strip(),
            })
        scored = score_manifest(records, lot_state, active_shocks)
        st.session_state.scored = scored
        st.session_state.bid_status = {sv["vid"]: sv["status"] for sv in scored}
        st.session_state.ceiling_overrides = {}
        st.session_state.manual_overrides = set()
        st.session_state.displacement_msg = None
        st.session_state.scored_flag = True
        st.session_state.last_scored_shocks = frozenset(active_shocks)
        st.session_state.last_manifest_records = records
        for k in [k for k in st.session_state.keys() if k.startswith("ceiling_")]:
            del st.session_state[k]
        st.rerun()

    # ── Bid Room ───────────────────────────────────────────────────────────────
    if not (st.session_state.scored_flag and st.session_state.scored):
        st.stop()

    st.divider()

    # Portfolio Impact Strip
    impact = compute_portfolio_impact(
        st.session_state.scored, st.session_state.bid_status,
        st.session_state.ceiling_overrides, lot_state,
    )
    st.subheader("Portfolio Impact")
    pi1, pi2, pi3, pi4, pi5 = st.columns(5)
    pi1.metric("Units to Bid",        impact["units_to_bid"])
    pi2.metric("Capital Required",    f"${impact['capital_required']:,.0f}")
    pi3.metric("Expected Gross",      f"${impact['expected_gross']:,.0f}")
    pi4.metric("Recon Queue",         f"{impact['projected_queue']:.1f} / {impact['recon_bays']} bays")
    pi5.metric("Concentration Alerts", len(impact["concentration_warnings"]))

    if impact["concentration_warnings"]:
        st.error("Concentration risk:  " + "  |  ".join(impact["concentration_warnings"]))

    # Segment mix chart
    seg_adds = impact["segment_adds"]
    if seg_adds:
        seg_keys = list(seg_adds.keys())
        seg_labels_list = [SEGMENT_LABELS.get(s, s) for s in seg_keys]
        with st.expander("Segment Mix Impact", expanded=False):
            fig_mix = go.Figure()
            fig_mix.add_bar(name="Current", y=seg_labels_list,
                            x=[lot_state["segment_counts"].get(s, 0) for s in seg_keys],
                            orientation="h", marker_color="#95a5a6", opacity=0.9)
            fig_mix.add_bar(name="After Bids", y=seg_labels_list,
                            x=[lot_state["segment_counts"].get(s, 0) + seg_adds.get(s, 0) for s in seg_keys],
                            orientation="h", marker_color="#27ae60", opacity=0.6)
            fig_mix.add_bar(name="Target", y=seg_labels_list,
                            x=[lot_state["segment_targets"].get(s, 10) for s in seg_keys],
                            orientation="h", marker_color="#e74c3c",
                            opacity=0.3, marker_pattern_shape="/")
            fig_mix.update_layout(barmode="overlay", height=max(180, len(seg_keys)*38),
                                  margin=dict(t=10, b=10), legend=dict(orientation="h", y=1.02),
                                  xaxis_title="Units")
            st.plotly_chart(fig_mix, use_container_width=True)

    # Displacement / Promotion Alert
    if st.session_state.displacement_msg:
        msg = st.session_state.displacement_msg
        if msg["type"] == "displacement":
            st.warning(
                f"**Override note:** Taking **{msg['added_label']}** means you might want to drop "
                f"**{msg['displaced_label']}** — {msg['reason']}."
            )
            da1, da2 = st.columns(2)
            if da1.button(f"Drop {msg['displaced_label']}", key="drop_displaced"):
                st.session_state.bid_status[msg["displaced_vid"]] = "skip"
                st.session_state.displacement_msg = None
                st.rerun()
            if da2.button("Keep both anyway", key="keep_both"):
                st.session_state.displacement_msg = None
                st.rerun()
        elif msg["type"] == "promotion":
            st.info(
                f"Removing **{msg['removed_label']}** freed a recon slot. "
                f"**{msg['promoted_label']}** now qualifies — add it?"
            )
            pa1, pa2 = st.columns(2)
            if pa1.button(f"Add {msg['promoted_label']}", key="add_promoted"):
                st.session_state.bid_status[msg["promoted_vid"]] = "bid"
                st.session_state.manual_overrides.add(msg["promoted_vid"])
                st.session_state.displacement_msg = None
                st.rerun()
            if pa2.button("No thanks", key="dismiss_promo"):
                st.session_state.displacement_msg = None
                st.rerun()

    # ── Two-column Bid Room ────────────────────────────────────────────────────
    st.subheader("Bid Room")
    bid_col, skip_col = st.columns(2)

    bid_vehicles   = [sv for sv in st.session_state.scored if st.session_state.bid_status.get(sv["vid"], sv["status"]) == "bid"]
    skip_vehicles  = [sv for sv in st.session_state.scored if st.session_state.bid_status.get(sv["vid"], sv["status"]) == "skip"]
    bid_sorted     = sorted(bid_vehicles, key=lambda x: x.get("rank_score") or 0, reverse=True)

    mc_ctx = DEFAULT_MARKET_CONTEXT

    # LEFT: Bid List
    with bid_col:
        st.markdown(f"### Bid List &nbsp; `{len(bid_sorted)}`", unsafe_allow_html=True)
        if not bid_sorted:
            st.info("No vehicles in bid list.")

        for rank_idx, sv in enumerate(bid_sorted, 1):
            vid = sv["vid"]
            fit = sv.get("portfolio_fit") or 0.0
            fit_color = "#27ae60" if fit >= 0.5 else ("#f39c12" if fit >= 0.2 else "#e74c3c")

            with st.container(border=True):
                hc, bc = st.columns([5, 1])
                hc.markdown(f"**#{rank_idx} — {sv['label']}**")
                hc.caption(f"{SEGMENT_LABELS.get(sv['segment'], sv['segment'])}  ·  "
                           f"Cond {sv['condition']:.1f}  ·  {sv['mileage']:,} mi")
                if bc.button("Skip →", key=f"skip_{vid}", use_container_width=True):
                    st.session_state.bid_status[vid] = "skip"
                    st.session_state.manual_overrides.add(vid)
                    disp = check_displacement(vid, "skip", st.session_state.scored,
                                              st.session_state.bid_status, lot_state)
                    st.session_state.displacement_msg = disp
                    st.rerun()

                mc1, mc2, mc3 = st.columns(3)
                current_ceiling = float(st.session_state.ceiling_overrides.get(vid, sv.get("bid_ceiling") or 0))
                new_ceiling = mc1.number_input("Bid Ceiling ($)", value=current_ceiling,
                                               min_value=0.0, step=100.0, key=f"ceiling_{vid}")
                if new_ceiling != sv.get("bid_ceiling"):
                    st.session_state.ceiling_overrides[vid] = new_ceiling
                mc2.metric("Exp. Margin", f"${sv.get('expected_margin') or 0:,.0f}")
                mc3.markdown(f"<div style='margin-top:8px'><b>Fit</b>: "
                             f"<span style='color:{fit_color}'><b>{fit:.2f}</b></span></div>",
                             unsafe_allow_html=True)

                # Ceiling warning
                avg_days_sale = mc_ctx["avg_days_to_sale_by_segment"].get(sv["segment"], 30)
                carry_cost = avg_days_sale * lot_state.get("daily_carry_rate", 35)
                eff_margin = (sv.get("expected_retail") or 0) - new_ceiling - (sv.get("recon_cost") or 0) - carry_cost
                if new_ceiling > 0 and eff_margin < 0:
                    st.error("At this price you're buying a wholesale loss.")
                elif new_ceiling > 0 and eff_margin < 800:
                    st.warning("Margin is thin at this price.")

                st.caption(f"_{sv.get('rationale', '')}_")

                with st.expander("Details"):
                    dc1, dc2 = st.columns(2)
                    dc1.write(f"**Expected Retail:** ${sv.get('expected_retail') or 0:,.0f}")
                    dc1.write(f"**Auction Price:** ${sv.get('auction_price', 0):,.0f}")
                    dc1.write(f"**Bid Ceiling:** ${sv.get('bid_ceiling') or 0:,.0f}")
                    dc2.write(f"**Recon:** ${sv.get('recon_cost') or 0:,.0f} / {sv.get('recon_days', 0)} days")
                    dc2.write(f"**Portfolio Fit:** {fit:.3f}")
                    dc2.write(f"**Rank Score:** {sv.get('rank_score') or 0:.0f}")
                    if not sv.get("segment_is_mapped", True):
                        st.warning("Segment unmapped — verify manually.")

    # RIGHT: Skip List
    with skip_col:
        st.markdown(f"### Skip List &nbsp; `{len(skip_vehicles)}`", unsafe_allow_html=True)
        if not skip_vehicles:
            st.success("All vehicles are in the bid list.")

        reason_labels = {
            "condition_fail":     "⛔ Condition Fail (Non-Overridable)",
            "margin_insufficient": "💸 Margin Insufficient",
            "segment_overexposed": "📦 Segment Overexposed",
            "wholesale_softening": "📉 Wholesale Softening",
            "slow_segment":       "🐢 Slow Segment",
            "recon_risk":         "🔧 Recon Risk",
            "recon_queue_full":   "🚧 Recon Queue Full",
        }
        skips_by_reason: dict = defaultdict(list)
        for sv in skip_vehicles:
            skips_by_reason[sv.get("skip_reason", "other")].append(sv)

        for reason_key, reason_label in reason_labels.items():
            group = skips_by_reason.get(reason_key, [])
            if not group:
                continue
            with st.expander(f"{reason_label} ({len(group)})", expanded=True):
                for sv in group:
                    vid = sv["vid"]
                    with st.container(border=True):
                        sc1, sc2 = st.columns([5, 1])
                        sc1.markdown(f"**{sv['label']}**")
                        sc1.caption(f"{SEGMENT_LABELS.get(sv['segment'], sv['segment'])}  ·  "
                                    f"Cond {sv['condition']:.1f}  ·  Ask: ${sv.get('auction_price', 0):,.0f}")
                        if not sv.get("is_condition_fail", False):
                            if sc2.button("← Bid", key=f"bid_{vid}", use_container_width=True):
                                st.session_state.bid_status[vid] = "bid"
                                st.session_state.manual_overrides.add(vid)
                                disp = check_displacement(vid, "bid", st.session_state.scored,
                                                          st.session_state.bid_status, lot_state)
                                st.session_state.displacement_msg = disp
                                st.rerun()
                        st.caption(sv.get("skip_detail", ""))
                        if sv.get("would_bid_if"):
                            st.caption(f"Would bid if: _{sv['would_bid_if']}_")
                        if sv.get("bid_ceiling") is not None:
                            st.caption(f"Model ceiling: ${sv['bid_ceiling']:,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CURRENT LOT
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Current Lot")
    st.caption("Existing portfolio — the lot state context the auction model scores against.")

    # Apply filters
    filt = df.copy()
    if sel_source != "All": filt = filt[filt["source_channel"] == sel_source]
    if sel_ret    != "All": filt = filt[filt["retailability_state"] == sel_ret]
    if sel_market != "All": filt = filt[filt["market_cluster"] == sel_market]
    if sel_body   != "All": filt = filt[filt["body_type"] == sel_body]
    if sel_price  != "All": filt = filt[filt["price_band"] == sel_price]
    if sel_age    != "All": filt = filt[filt["age_band"] == sel_age]

    if filt.empty:
        st.warning("No cohorts match the selected filters. Adjust Portfolio Analysis Settings in the sidebar.")
    else:
        # Segment overview
        st.subheader("Segment Overview (Lot State)")
        sc1, sc2 = st.columns(2)
        with sc1:
            seg_counts  = lot_state["segment_counts"]
            seg_targets = lot_state["segment_targets"]
            seg_names   = [SEGMENT_LABELS.get(s, s) for s in seg_counts]
            fig_seg = go.Figure()
            fig_seg.add_bar(name="Current", x=seg_names, y=list(seg_counts.values()),
                            marker_color="#2980b9", opacity=0.85)
            fig_seg.add_scatter(name="Target", x=seg_names, y=list(seg_targets.values()),
                                mode="markers", marker=dict(color="#e74c3c", size=10, symbol="diamond"))
            fig_seg.update_layout(title="Segment Counts vs Targets", height=300,
                                  margin=dict(t=40, b=60), xaxis_tickangle=-45)
            st.plotly_chart(fig_seg, use_container_width=True)

        with sc2:
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Recon Bays",    lot_state["recon_bays_total"])
            r2.metric("Occupied",      lot_state["recon_bays_occupied"])
            r3.metric("Queue Depth",   lot_state["recon_queue_depth"])
            r4.metric("Avg Days",      f"{lot_state['avg_days_on_lot']:.0f}")

            wi_data = lot_state["wholesale_index_deltas"]
            wi_rows = [{"Segment": SEGMENT_LABELS.get(s, s), "Delta": f"{v*100:+.1f}%"}
                       for s, v in wi_data.items() if v != 0.0]
            if wi_rows:
                st.markdown("**Wholesale Index Movement**")
                st.dataframe(pd.DataFrame(wi_rows), hide_index=True, use_container_width=True, height=220)

        st.divider()
        st.subheader("Cohort Portfolio")

        BASE_SCENARIO = {"wholesale_shock": 0.0, "demand_mult": 1.0, "recon_pressure": "medium"}

        @st.cache_data
        def compute_portfolio_stats(cohort_ids_json):
            all_df = load_data()
            results = []
            for _, row in all_df.iterrows():
                r  = evaluate_cohort(row, BASE_SCENARIO, "Balanced", 0.0, 30)
                cd = r["crossover_day"]
                results.append({
                    "cohort_id": row["cohort_id"],
                    "ev_gap": r["best_ev_hold"] - r["ev_wholesale"],
                    "at_risk": 1 if (cd is not None and cd <= 10) else 0,
                    "crossover_day_base": cd,
                })
            return pd.DataFrame(results)

        portfolio_stats = compute_portfolio_stats(str(sorted(df["cohort_id"].tolist())))
        filt_stats      = filt.merge(portfolio_stats, on="cohort_id")

        at_risk_n  = int(filt_stats["at_risk"].sum())
        recon_n    = int(filt[filt["retailability_state"].isin(["recon_heavy", "recon_light"])].shape[0])
        total_n    = len(filt)
        total_u    = int(filt["cohort_units"].sum())
        est_val    = float((filt["current_expected_retail_price"] * filt["cohort_units"]).sum())
        avg_d      = float(filt["days_since_acquisition"].mean())

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Cohorts",             total_n)
        k2.metric("Total Units",         f"{total_u:,}")
        k3.metric("Est. Portfolio Value", f"${est_val:,.0f}")
        k4.metric("At Risk (≤10d)",      f"{at_risk_n}", delta=f"{at_risk_n/total_n*100:.0f}%", delta_color="inverse")
        k5.metric("Recon Trapped",       f"{recon_n}",   delta=f"{recon_n/total_n*100:.0f}%",   delta_color="inverse")
        st.caption(f"Avg days since acquisition: **{avg_d:.1f}**")

        STATE_COLORS = {
            "frontline_ready": "#27ae60", "recon_light": "#f39c12",
            "recon_heavy": "#e74c3c",     "borderline_retail": "#e67e22",
            "wholesale_likely": "#c0392b",
        }

        pc1, pc2 = st.columns(2)
        with pc1:
            ret_cnt = (filt.groupby("retailability_state")["cohort_id"].count().reset_index()
                       .rename(columns={"cohort_id": "Cohorts", "retailability_state": "State"}))
            fig_bar = px.bar(ret_cnt, x="State", y="Cohorts", color="State",
                             color_discrete_map=STATE_COLORS, title="Cohorts by Retailability State")
            fig_bar.update_layout(showlegend=False, height=300, margin=dict(t=40, b=30))
            st.plotly_chart(fig_bar, use_container_width=True)

        with pc2:
            fig_scat = px.scatter(
                filt_stats, x="days_since_acquisition", y="ev_gap",
                color="retailability_state", color_discrete_map=STATE_COLORS,
                hover_data=["cohort_id", "market_cluster", "body_type", "crossover_day_base"],
                title="Days Since Acquisition vs EV Gap",
                labels={"days_since_acquisition": "Days Since Acq.", "ev_gap": "EV Gap ($)", "retailability_state": "State"},
            )
            fig_scat.add_hline(y=0, line_dash="dash", line_color="#e74c3c",
                               annotation_text="Wholesale Beats Retail", annotation_position="bottom right")
            fig_scat.update_layout(height=300, showlegend=False, margin=dict(t=40, b=30))
            st.plotly_chart(fig_scat, use_container_width=True)

        # Cohort Drilldown
        st.divider()
        st.subheader("Cohort Drilldown")
        cohort_ids = filt["cohort_id"].tolist()

        def cohort_label(cid):
            row = filt[filt["cohort_id"] == cid].iloc[0]
            return (f"{cid}  ·  {row['retailability_state'].replace('_',' ').title()}  ·  "
                    f"{row['market_cluster']}  ·  {row['body_type'].upper()}")

        sel_id = st.selectbox("Select a cohort:", cohort_ids, format_func=cohort_label, key="cohort_sel")

        display_df = filt[[
            "cohort_id", "market_cluster", "source_channel", "retailability_state",
            "body_type", "price_band", "age_band", "cohort_units",
            "days_since_acquisition", "current_expected_retail_price", "wholesale_floor_price",
        ]].copy()
        display_df["current_expected_retail_price"] = display_df["current_expected_retail_price"].map("${:,.0f}".format)
        display_df["wholesale_floor_price"]          = display_df["wholesale_floor_price"].map("${:,.0f}".format)
        display_df.columns = ["Cohort ID", "Market", "Source", "Retailability",
                               "Body", "Price Band", "Age Band", "Units",
                               "Days Acq.", "Retail Price", "Wholesale Floor"]
        st.dataframe(display_df, use_container_width=True, hide_index=True, height=220)

        cohort  = filt[filt["cohort_id"] == sel_id].iloc[0]
        results = evaluate_cohort(cohort, portfolio_scenario, strategy_mode, markdown_pct, hold_horizon)

        d1, d2, d3 = st.columns(3)
        with d1:
            st.markdown("**Descriptor**")
            for lbl, val in [("Body", cohort["body_type"].capitalize()),
                              ("Age Band", cohort["age_band"].replace("_", " ")),
                              ("Mileage Band", cohort["mileage_band"].replace("_", " ")),
                              ("Source", cohort["source_channel"].replace("_", " ").title()),
                              ("Market", cohort["market_cluster"]),
                              ("Units", cohort["cohort_units"])]:
                st.markdown(f"- {lbl}: **{val}**")
        with d2:
            st.markdown("**Timing**")
            for lbl, val in [("Days Since Acq.", cohort["days_since_acquisition"]),
                              ("Days in Recon", cohort["days_in_recon"]),
                              ("Retailability", cohort["retailability_state"].replace("_", " ").title())]:
                st.markdown(f"- {lbl}: **{val}**")
        with d3:
            st.markdown("**Economics**")
            for lbl, val in [("Acquisition Cost", f"${cohort['avg_acquisition_cost']:,.0f}"),
                              ("Expected Recon", f"${cohort['expected_recon_cost']:,.0f}"),
                              ("Retail Price", f"${cohort['current_expected_retail_price']:,.0f}"),
                              ("Wholesale Floor", f"${cohort['wholesale_floor_price']:,.0f}"),
                              ("Market Demand", f"{cohort['market_demand_index']:.2f}")]:
                st.markdown(f"- {lbl}: **{val}**")

        # Crossover Clock
        st.divider()
        st.subheader("Crossover Clock")
        days = results["days"]
        ev_wh = results["ev_wholesale"]
        crossover_day = results["crossover_day"]

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=days, y=results["ev_hold_curve"], mode="lines",
                                 name="Hold for Retail", line=dict(color="#2980b9", width=3)))
        fig.add_trace(go.Scatter(x=days, y=results["ev_transfer_curve"], mode="lines",
                                 name="Transfer", line=dict(color="#8e44ad", width=2, dash="dash")))
        fig.add_trace(go.Scatter(x=days, y=results["ev_expedite_curve"], mode="lines",
                                 name="Expedite Recon", line=dict(color="#27ae60", width=2, dash="dot")))
        fig.add_hline(y=ev_wh, line_color="#e74c3c", line_width=2.5, line_dash="longdash",
                      annotation_text=f"  Wholesale Floor  ${ev_wh:,.0f}",
                      annotation_position="right", annotation_font_color="#e74c3c")
        if crossover_day is not None:
            fig.add_vline(x=crossover_day, line_color="#e74c3c", line_width=1.5, line_dash="dot",
                          annotation_text=f"  Crossover Day {crossover_day}",
                          annotation_position="top right", annotation_font_color="#e74c3c")
        fig.update_layout(
            title=f"Expected Value — {strategy_mode}  |  Demand: {demand_label}  |  Recon: {recon_pressure}",
            xaxis_title="Days from Today", yaxis_title="Expected Value ($)",
            height=400, hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=80, r=160),
        )
        st.plotly_chart(fig, use_container_width=True)

        if crossover_day == 0:
            st.error("Retail crossover has already occurred.")
        elif crossover_day is not None:
            st.warning(f"**{crossover_day} days** before retail hold becomes unfavorable.")
        else:
            st.success(f"No crossover within {hold_horizon}-day horizon. Retail economics remain favorable.")

        # Recommendation Cards
        st.subheader("Routing Recommendation")
        rec = results["recommended_action"]
        actions = {
            "Hold for Retail":             {"ev": results["best_ev_hold"],     "speed": "Medium",      "color": "#2980b9"},
            "Transfer to Stronger Market": {"ev": results["best_ev_transfer"], "speed": "Medium–Slow", "color": "#8e44ad"},
            "Expedite Recon":              {"ev": results["best_ev_expedite"], "speed": "Fast",        "color": "#27ae60"},
            "Liquidate to Wholesale":      {"ev": results["ev_wholesale"],     "speed": "Immediate",   "color": "#e74c3c"},
        }
        card_cols = st.columns(4)
        for col, (action, data) in zip(card_cols, actions.items()):
            is_rec = action == rec
            border = f"2.5px solid {data['color']}" if is_rec else "1px solid #ddd"
            bg     = "#f0f8ff" if is_rec else "#fafafa"
            badge  = " ★ Recommended" if is_rec else ""
            with col:
                st.markdown(
                    f'<div style="border:{border};border-radius:8px;padding:14px;background:{bg};min-height:100px">'
                    f'<span style="color:{data["color"]};font-weight:700">{action}</span>'
                    f'<span style="color:{data["color"]};font-size:0.78rem">{badge}</span><br><br>'
                    f'<b>EV:</b> ${data["ev"]:,.0f}<br>'
                    f'<b>Speed:</b> {data["speed"]}</div>',
                    unsafe_allow_html=True,
                )

        # Acquisition Confidence
        st.divider()
        st.subheader("Acquisition Confidence")
        conf_score = results["acquisition_confidence_score"]
        conf_label = results["acquisition_confidence_label"]
        conf_color = {"High": "#27ae60", "Medium": "#f39c12", "Low": "#e74c3c"}[conf_label]
        ac1, ac2 = st.columns([1, 3])
        with ac1:
            st.markdown(
                f'<div style="text-align:center;padding:24px 16px;border:2px solid {conf_color};border-radius:10px">'
                f'<div style="font-size:52px;font-weight:800;color:{conf_color}">{conf_score}</div>'
                f'<div style="font-size:22px;font-weight:600;color:{conf_color}">{conf_label}</div>'
                f'<div style="font-size:11px;color:#888;margin-top:8px">Acquisition Confidence</div></div>',
                unsafe_allow_html=True,
            )
        with ac2:
            st.markdown("**Decision Rationale**")
            st.info(results["decision_rationale"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — EXPORT
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("Export Bid Sheet")

    if not st.session_state.scored_flag or not st.session_state.scored:
        st.info("Score an auction manifest in the Auction Drop tab to generate a bid sheet.")
    else:
        impact = compute_portfolio_impact(
            st.session_state.scored, st.session_state.bid_status,
            st.session_state.ceiling_overrides, lot_state,
        )
        e1, e2, e3 = st.columns(3)
        e1.metric("Units to Bid",         impact["units_to_bid"])
        e2.metric("Capital Required",     f"${impact['capital_required']:,.0f}")
        e3.metric("Expected Gross",       f"${impact['expected_gross']:,.0f}")

        st.divider()
        active_bids = [sv for sv in st.session_state.scored
                       if st.session_state.bid_status.get(sv["vid"], sv["status"]) == "bid"]
        active_bids_sorted = sorted(active_bids, key=lambda x: x.get("rank_score") or 0, reverse=True)

        bid_rows = []
        for rank_idx, sv in enumerate(active_bids_sorted, 1):
            effective_ceiling = st.session_state.ceiling_overrides.get(sv["vid"], sv.get("bid_ceiling") or 0)
            bid_rows.append({
                "Rank":               rank_idx,
                "Vehicle":            sv["label"],
                "Segment":            SEGMENT_LABELS.get(sv["segment"], sv["segment"]),
                "Bid Ceiling ($)":    int(effective_ceiling),
                "Auction Price ($)":  int(sv.get("auction_price", 0)),
                "Expected Margin ($)": int(sv.get("expected_margin") or 0),
                "Recon Est. ($)":     int(sv.get("recon_cost") or 0),
                "Recon Days":         sv.get("recon_days", 0),
                "Portfolio Fit":      round(sv.get("portfolio_fit") or 0, 2),
                "Rationale":          sv.get("rationale", ""),
            })

        if bid_rows:
            bid_df = pd.DataFrame(bid_rows)
            st.dataframe(bid_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download Bid Sheet (CSV)",
                data=bid_df.to_csv(index=False).encode("utf-8"),
                file_name="bid_sheet.csv",
                mime="text/csv",
                type="primary",
            )
        else:
            st.info("No vehicles in bid list. Move vehicles from Skip to build your list.")

        if impact["concentration_warnings"]:
            st.divider()
            st.warning("**Concentration Warnings:**\n" +
                       "\n".join(f"- {w}" for w in impact["concentration_warnings"]))

# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.caption("Merchant — Auction Drop Decision Engine  ·  Synthetic data demo  ·  v0.2")
