import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

from data_generator import generate_cohorts
from logic import evaluate_cohort

# ── Page config ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CarMax Inventory Flow Strategist",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .kpi-label { font-size: 0.75rem; color: #666; margin-bottom: 2px; }
  .kpi-value { font-size: 1.6rem; font-weight: 700; color: #1a1a1a; }
  .rec-card {
    border-radius: 8px; padding: 16px; height: 100%;
    border: 1px solid #ddd; background: #fafafa;
  }
  .rec-card-selected {
    border-radius: 8px; padding: 16px; height: 100%;
    border: 2.5px solid #2980b9; background: #eaf4fb;
  }
</style>
""", unsafe_allow_html=True)

# ── Data ──────────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    return generate_cohorts()

df = load_data()

# ── Sidebar ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Controls")

    st.subheader("Portfolio Filters")
    all_opt = ["All"]

    src_opts = all_opt + sorted(df["source_channel"].unique())
    sel_source = st.selectbox("Source Channel", src_opts)

    ret_opts = all_opt + sorted(df["retailability_state"].unique())
    sel_ret = st.selectbox("Retailability State", ret_opts)

    mkt_opts = all_opt + sorted(df["market_cluster"].unique())
    sel_market = st.selectbox("Market Cluster", mkt_opts)

    body_opts = all_opt + sorted(df["body_type"].unique())
    sel_body = st.selectbox("Body Type", body_opts)

    price_opts = all_opt + sorted(df["price_band"].unique())
    sel_price = st.selectbox("Price Band", price_opts)

    age_opts = all_opt + sorted(df["age_band"].unique())
    sel_age = st.selectbox("Age Band", age_opts)

    st.divider()
    st.subheader("Strategy Mode")
    strategy_mode = st.radio(
        "Strategy Mode",
        ["Margin Max", "Balanced", "Turn Max"],
        index=1,
        help=(
            "**Margin Max** — patient, holds longer, stricter wholesale threshold\n\n"
            "**Balanced** — sensible default\n\n"
            "**Turn Max** — values speed; shorter hold window, aggressive exit"
        ),
    )
    hold_horizon = st.slider("Hold Horizon (days)", 7, 45, 30)

    use_markdown = st.toggle("Apply Markdown to Retail Price")
    markdown_pct = 0.0
    if use_markdown:
        markdown_pct = st.slider("Markdown %", 1, 10, 3) / 100

    st.divider()
    st.subheader("Scenario")
    wholesale_shock_pct = st.slider("Wholesale Market Shock (%)", -10, 5, 0)
    wholesale_shock = wholesale_shock_pct / 100

    demand_label = st.select_slider(
        "Retail Demand Strength", options=["Weak", "Base", "Strong"], value="Base"
    )
    demand_mult = {"Weak": 0.85, "Base": 1.0, "Strong": 1.15}[demand_label]

    recon_pressure = st.select_slider(
        "Recon Capacity Pressure", options=["low", "medium", "high"], value="medium"
    )

scenario = {
    "wholesale_shock": wholesale_shock,
    "demand_mult": demand_mult,
    "recon_pressure": recon_pressure,
}

# ── Apply filters ─────────────────────────────────────────────────────────
filt = df.copy()
if sel_source != "All":
    filt = filt[filt["source_channel"] == sel_source]
if sel_ret != "All":
    filt = filt[filt["retailability_state"] == sel_ret]
if sel_market != "All":
    filt = filt[filt["market_cluster"] == sel_market]
if sel_body != "All":
    filt = filt[filt["body_type"] == sel_body]
if sel_price != "All":
    filt = filt[filt["price_band"] == sel_price]
if sel_age != "All":
    filt = filt[filt["age_band"] == sel_age]

# ── Header ────────────────────────────────────────────────────────────────
st.title("CarMax Inventory Flow Strategist")
st.caption("Used-vehicle routing and timing decision engine · Synthetic data demo")

if filt.empty:
    st.warning("No cohorts match the selected filters. Adjust the sidebar controls.")
    st.stop()

# ── Precompute portfolio stats (base scenario for overview) ───────────────
BASE_SCENARIO = {"wholesale_shock": 0.0, "demand_mult": 1.0, "recon_pressure": "medium"}

@st.cache_data
def compute_portfolio_stats(cohort_ids_json):
    """Compute base-scenario EV stats for all cohorts (cached by cohort set)."""
    all_df = load_data()
    results = []
    for _, row in all_df.iterrows():
        r = evaluate_cohort(row, BASE_SCENARIO, "Balanced", 0.0, 30)
        cd = r["crossover_day"]
        results.append({
            "cohort_id": row["cohort_id"],
            "ev_gap": r["best_ev_hold"] - r["ev_wholesale"],
            "at_risk": 1 if (cd is not None and cd <= 10) else 0,
            "crossover_day_base": cd,
        })
    return pd.DataFrame(results)

portfolio_stats = compute_portfolio_stats(
    str(sorted(df["cohort_id"].tolist()))
)

filt_stats = filt.merge(portfolio_stats, on="cohort_id")

# ── Portfolio Overview ────────────────────────────────────────────────────
st.header("Portfolio Overview")

at_risk_n = int(filt_stats["at_risk"].sum())
recon_n = int(filt[filt["retailability_state"].isin(["recon_heavy", "recon_light"])].shape[0])
total_n = len(filt)
total_units = int(filt["cohort_units"].sum())
est_value = float((filt["current_expected_retail_price"] * filt["cohort_units"]).sum())
avg_days = float(filt["days_since_acquisition"].mean())

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Cohorts in View", total_n)
k2.metric("Total Units", f"{total_units:,}")
k3.metric("Est. Portfolio Value", f"${est_value:,.0f}")
k4.metric(
    "At Risk of Crossover ≤ 10 Days",
    f"{at_risk_n}",
    delta=f"{at_risk_n/total_n*100:.0f}% of cohorts",
    delta_color="inverse",
)
k5.metric(
    "Recon-Trapped Cohorts",
    f"{recon_n}",
    delta=f"{recon_n/total_n*100:.0f}% of cohorts",
    delta_color="inverse",
)
st.caption(f"Weighted avg days since acquisition: **{avg_days:.1f}**")

# ── Portfolio charts ──────────────────────────────────────────────────────
STATE_COLORS = {
    "frontline_ready": "#27ae60",
    "recon_light": "#f39c12",
    "recon_heavy": "#e74c3c",
    "borderline_retail": "#e67e22",
    "wholesale_likely": "#c0392b",
}

st.subheader("Portfolio Breakdown")
pc1, pc2 = st.columns(2)

with pc1:
    ret_cnt = (
        filt.groupby("retailability_state")["cohort_id"]
        .count()
        .reset_index()
        .rename(columns={"cohort_id": "Cohorts", "retailability_state": "State"})
    )
    fig_bar = px.bar(
        ret_cnt, x="State", y="Cohorts", color="State",
        color_discrete_map=STATE_COLORS,
        title="Cohorts by Retailability State",
    )
    fig_bar.update_layout(showlegend=False, height=300, margin=dict(t=40, b=30))
    st.plotly_chart(fig_bar, use_container_width=True)

with pc2:
    scatter_df = filt_stats.copy()
    scatter_df["label"] = scatter_df["retailability_state"].str.replace("_", " ").str.title()
    fig_scat = px.scatter(
        scatter_df,
        x="days_since_acquisition",
        y="ev_gap",
        color="retailability_state",
        color_discrete_map=STATE_COLORS,
        hover_data=["cohort_id", "market_cluster", "body_type", "crossover_day_base"],
        title="Days Since Acquisition vs Retail–Wholesale Value Gap",
        labels={
            "days_since_acquisition": "Days Since Acquisition",
            "ev_gap": "Expected Value Gap ($)",
            "retailability_state": "State",
        },
    )
    fig_scat.add_hline(
        y=0, line_dash="dash", line_color="#e74c3c",
        annotation_text="Wholesale Beats Retail", annotation_position="bottom right",
    )
    fig_scat.update_layout(height=300, showlegend=False, margin=dict(t=40, b=30))
    st.plotly_chart(fig_scat, use_container_width=True)

# ── Cohort selection + table ──────────────────────────────────────────────
st.subheader("Cohort Portfolio")

display_df = filt[[
    "cohort_id", "market_cluster", "source_channel", "retailability_state",
    "body_type", "price_band", "age_band", "cohort_units",
    "days_since_acquisition", "current_expected_retail_price", "wholesale_floor_price",
]].copy()

display_df["current_expected_retail_price"] = display_df["current_expected_retail_price"].map("${:,.0f}".format)
display_df["wholesale_floor_price"] = display_df["wholesale_floor_price"].map("${:,.0f}".format)
display_df.columns = [
    "Cohort ID", "Market Cluster", "Source", "Retailability State",
    "Body Type", "Price Band", "Age Band", "Units",
    "Days Since Acq.", "Retail Price", "Wholesale Floor",
]

cohort_ids = filt["cohort_id"].tolist()


def cohort_label(cid):
    row = filt[filt["cohort_id"] == cid].iloc[0]
    return (
        f"{cid}  ·  "
        f"{row['retailability_state'].replace('_',' ').title()}  ·  "
        f"{row['market_cluster']}  ·  "
        f"{row['body_type'].upper()}  ·  "
        f"{row['price_band'].replace('_',' ')}"
    )


sel_id = st.selectbox(
    "Select a cohort to analyze:",
    cohort_ids,
    format_func=cohort_label,
)

st.dataframe(display_df, use_container_width=True, hide_index=True, height=220)

# ── Evaluate selected cohort ──────────────────────────────────────────────
cohort = filt[filt["cohort_id"] == sel_id].iloc[0]
results = evaluate_cohort(cohort, scenario, strategy_mode, markdown_pct, hold_horizon)

# ── Cohort Drilldown ──────────────────────────────────────────────────────
st.divider()
st.header(f"Cohort Drilldown — {sel_id}")

d1, d2, d3 = st.columns(3)

with d1:
    st.markdown("**Descriptor**")
    st.markdown(f"- Body type: **{cohort['body_type'].capitalize()}**")
    st.markdown(f"- Age band: **{cohort['age_band'].replace('_',' ')}**")
    st.markdown(f"- Mileage band: **{cohort['mileage_band'].replace('_',' ')}**")
    st.markdown(f"- Source: **{cohort['source_channel'].replace('_',' ').title()}**")
    st.markdown(f"- Market: **{cohort['market_cluster']}**")
    st.markdown(f"- Units in cohort: **{cohort['cohort_units']}**")
    st.markdown(f"- Price band: **{cohort['price_band'].replace('_',' ')}**")

with d2:
    st.markdown("**Timing**")
    st.markdown(f"- Days since acquisition: **{cohort['days_since_acquisition']}**")
    st.markdown(f"- Days in current stage: **{cohort['days_in_current_stage']}**")
    st.markdown(f"- Days in recon: **{cohort['days_in_recon']}**")
    st.markdown(f"- Days frontline ready: **{cohort['days_frontline_ready']}**")
    st.markdown(f"- Days since listed: **{cohort['days_since_listed']}**")
    st.markdown(
        f"- Retailability state: "
        f"**{cohort['retailability_state'].replace('_',' ').title()}**"
    )

with d3:
    st.markdown("**Economics & Demand**")
    st.markdown(f"- Avg acquisition cost: **${cohort['avg_acquisition_cost']:,.0f}**")
    st.markdown(f"- Expected recon cost: **${cohort['expected_recon_cost']:,.0f}**")
    st.markdown(f"- Daily carry / depreciation: **${cohort['daily_carry_depreciation']:,.0f}**")
    st.markdown(f"- Current retail price: **${cohort['current_expected_retail_price']:,.0f}**")
    st.markdown(f"- Wholesale floor: **${cohort['wholesale_floor_price']:,.0f}**")
    st.markdown(f"- Market demand index: **{cohort['market_demand_index']:.2f}**")
    st.markdown(f"- Transfer uplift: **{cohort['transfer_uplift_pct']*100:.1f}%**")

# ── Crossover Clock ───────────────────────────────────────────────────────
st.divider()
st.header("Crossover Clock")
st.caption(
    "Shows when expected retail economics deteriorate below the wholesale floor. "
    "The sooner the crossover, the more urgent the routing decision."
)

days = results["days"]
ev_hold = results["ev_hold_curve"]
ev_transfer = results["ev_transfer_curve"]
ev_expedite = results["ev_expedite_curve"]
ev_wh = results["ev_wholesale"]
crossover_day = results["crossover_day"]

fig = go.Figure()

fig.add_trace(go.Scatter(
    x=days, y=ev_hold,
    mode="lines", name="Hold for Retail",
    line=dict(color="#2980b9", width=3),
    hovertemplate="Day %{x}: $%{y:,.0f}<extra>Hold for Retail</extra>",
))

fig.add_trace(go.Scatter(
    x=days, y=ev_transfer,
    mode="lines", name="Transfer to Stronger Market",
    line=dict(color="#8e44ad", width=2, dash="dash"),
    hovertemplate="Day %{x}: $%{y:,.0f}<extra>Transfer</extra>",
))

fig.add_trace(go.Scatter(
    x=days, y=ev_expedite,
    mode="lines", name="Expedite Recon",
    line=dict(color="#27ae60", width=2, dash="dot"),
    hovertemplate="Day %{x}: $%{y:,.0f}<extra>Expedite Recon</extra>",
))

fig.add_hline(
    y=ev_wh, line_color="#e74c3c", line_width=2.5, line_dash="longdash",
    annotation_text=f"  Wholesale Floor  ${ev_wh:,.0f}",
    annotation_position="right",
    annotation_font_color="#e74c3c",
)

if crossover_day is not None:
    fig.add_vline(
        x=crossover_day, line_color="#e74c3c", line_width=1.5, line_dash="dot",
        annotation_text=f"  Crossover Day {crossover_day}",
        annotation_position="top right",
        annotation_font_color="#e74c3c",
    )

fig.update_layout(
    title=f"Expected Value by Day — Strategy: {strategy_mode}  |  Demand: {demand_label}  |  Recon Pressure: {recon_pressure}",
    xaxis_title="Days from Today",
    yaxis_title="Expected Value ($)",
    height=420,
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(t=80, r=160),
)
st.plotly_chart(fig, use_container_width=True)

if crossover_day is not None and crossover_day == 0:
    st.error(
        "Retail crossover has already occurred. "
        "Holding further increases downside under the current strategy."
    )
elif crossover_day is not None:
    st.warning(
        f"**Days Left Before Retail Hold Becomes Unfavorable: {crossover_day}** — "
        f"act before the wholesale floor becomes the better option."
    )
else:
    st.success(
        f"No crossover within the {hold_horizon}-day horizon. "
        f"Retail economics remain favorable. Continue monitoring."
    )

# ── Recommendation cards ──────────────────────────────────────────────────
st.subheader("Routing Recommendation")

rec = results["recommended_action"]

actions = {
    "Hold for Retail": {
        "ev": results["best_ev_hold"],
        "speed": "Medium",
        "tradeoff": "Maximizes retail margin but requires patient capital. Carries aging and demand risk.",
        "color": "#2980b9",
    },
    "Transfer to Stronger Market": {
        "ev": results["best_ev_transfer"],
        "speed": "Medium–Slow",
        "tradeoff": "Improves demand fit and retail price. Adds fixed move cost and transit time.",
        "color": "#8e44ad",
    },
    "Expedite Recon": {
        "ev": results["best_ev_expedite"],
        "speed": "Fast",
        "tradeoff": "Speeds time-to-frontline. Best when recon delay is the binding constraint.",
        "color": "#27ae60",
    },
    "Liquidate to Wholesale": {
        "ev": results["ev_wholesale"],
        "speed": "Immediate",
        "tradeoff": "Releases capital now. Right choice when retail upside is exhausted.",
        "color": "#e74c3c",
    },
}

card_cols = st.columns(4)
for col, (action, data) in zip(card_cols, actions.items()):
    is_rec = action == rec
    border = f"2.5px solid {data['color']}" if is_rec else "1px solid #ddd"
    bg = "#f0f8ff" if is_rec else "#fafafa"
    badge = " ★ Recommended" if is_rec else ""
    with col:
        st.markdown(
            f"""<div style="border:{border};border-radius:8px;padding:14px;background:{bg};min-height:190px">
<span style="color:{data['color']};font-weight:700">{action}</span>
<span style="color:{data['color']};font-size:0.78rem">{badge}</span><br><br>
<b>Expected Value:</b> ${data['ev']:,.0f}<br>
<b>Exit Speed:</b> {data['speed']}<br><br>
<span style="font-size:0.82rem;color:#555">{data['tradeoff']}</span>
</div>""",
            unsafe_allow_html=True,
        )

# ── Acquisition Confidence ────────────────────────────────────────────────
st.divider()
st.subheader("Acquisition Confidence")
st.caption("Would We Buy More of This Type of Unit at a Similar Price?")

conf_score = results["acquisition_confidence_score"]
conf_label = results["acquisition_confidence_label"]
conf_color = {"High": "#27ae60", "Medium": "#f39c12", "Low": "#e74c3c"}[conf_label]

ac1, ac2 = st.columns([1, 3])
with ac1:
    st.markdown(
        f"""<div style="text-align:center;padding:24px 16px;border:2px solid {conf_color};
border-radius:10px;background:#fff">
<div style="font-size:52px;font-weight:800;color:{conf_color};line-height:1">{conf_score}</div>
<div style="font-size:22px;font-weight:600;color:{conf_color};margin-top:4px">{conf_label}</div>
<div style="font-size:11px;color:#888;margin-top:8px">Acquisition Confidence</div>
</div>""",
        unsafe_allow_html=True,
    )

with ac2:
    st.markdown("**Decision Rationale**")
    st.info(results["decision_rationale"])

    with st.expander("How is this score calculated?"):
        st.markdown("""
The Acquisition Confidence score (0–100) answers:
**"Would we want to acquire more of this cohort type at a similar price point?"**

| Factor | Adjustment |
|---|---|
| Recommended: Hold for Retail | **+15** |
| Recommended: Transfer to Stronger Market | **+10** |
| Recommended: Expedite Recon | **−10** |
| Recommended: Liquidate to Wholesale | **−20** |
| Crossover day > 14 (or no crossover) | **+10** |
| Days since acquisition > 45 | **−10** |
| Retailability state: Recon Heavy or Wholesale Likely | **−10** |
| Expected value negative across all retail paths | **−10** |

**Labels:** High ≥ 70 · Medium 40–69 · Low < 40

A Low score signals this is a profile to avoid or reprice at acquisition.
A High score suggests this vehicle type is working well in this market cluster.
        """)

# ── Footer ────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "CarMax Inventory Flow Strategist · All data is synthetic · Strategy demo only · "
    f"Strategy: {strategy_mode}  |  Demand: {demand_label}  |  "
    f"Wholesale Shock: {wholesale_shock_pct:+d}%  |  Recon Pressure: {recon_pressure}"
)
