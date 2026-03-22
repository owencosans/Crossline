# CarMax Inventory Flow Strategist — Build Spec (v1)

## 1. Purpose
Build a lightweight Streamlit demo app that shows strategic thinking for a CarMax supply chain strategy role.

The app should feel like a **used-vehicle routing and timing decision engine**, not a generic dashboard.

Core concept:
- Start from a portfolio of used-vehicle inventory cohorts
- Let the user drill into one cohort or representative vehicle
- Show a **Crossover Clock**: when it is still worth holding for retail versus transferring, expediting reconditioning, or liquidating to wholesale
- Show explicit tradeoffs across **margin, speed, capacity pressure, and risk**
- Derive an **Acquisition Confidence** output that answers: “Would we buy more of this type of unit again at this price?”

This is designed to signal:
1. understanding of CarMax’s actual business model
2. analytical rigor without overengineering
3. strategic recommendation framing rather than just reporting metrics

---

## 2. CarMax-specific design principles
The app should speak to CarMax’s business reality:
- CarMax is a large-scale used vehicle retailer with a meaningful wholesale/auction business, not just a dealer website
- Supply chain decisions span **acquisition, reconditioning, movement, retail placement, and wholesale liquidation**
- Inventory is a depreciating asset; time matters
- Reconditioning capacity matters
- Not every car should stay in the retail channel forever
- The app should think in terms of **routing and timing**, not only forecasting

Use CarMax-native framing wherever possible:
- source channel
- retailability state
- recon urgency
- market/store cluster
- days in stage
- retail vs wholesale path
- acquisition confidence

Avoid jargon that sounds too academic or too e-commerce-only.

---

## 3. MVP product statement
**CarMax Inventory Flow Strategist** is a decision-support demo that helps evaluate the best path for used-vehicle inventory over time.

For any selected inventory cohort, the app should recommend one of four actions:
1. **Hold for retail**
2. **Transfer to stronger market**
3. **Expedite recon**
4. **Liquidate to wholesale**

Inside the retail hold path, the user may optionally apply a markdown lever, but **markdown is not a standalone routing action**.

The standout analytical view is the **Crossover Clock**, which visualizes when expected retail economics stop beating the wholesale floor.

---

## 4. Audience and use case
Primary audience:
- supply chain strategy leader
- analytics manager
- cross-functional operator in acquisition / merchandising / logistics / recon / B2B

Primary use case in demo:
- user opens the app and sees portfolio inventory risk
- user selects an aged or at-risk cohort
- app shows the economics over time
- app recommends a route under one of three strategy modes
- app explains the recommendation in plain English
- app computes acquisition confidence to show upstream learning

This should feel credible in a phone interview and tangible enough to show to a CarMax employee for feedback.

---

## 5. Scope boundaries (important)
### Keep in scope
- synthetic cohort data
- simple, defensible economics
- explicit routing logic
- strategy presets
- one clear timing visualization
- acquisition confidence as derived output

### Keep out of scope for v1
- machine learning
- real-time market feeds
- full pricing elasticity model
- auction microstructure
- complex vehicle VIN-level modeling
- detailed recon stage simulation
- multi-objective optimization solver
- polished enterprise authentication / persistence

The demo should look smart because it is **well-scoped**, not because it tries to imitate CarMax’s full data science stack.

---

## 6. Recommended tech stack
- **Python**
- **Streamlit** for the app shell
- **Pandas** for synthetic data and transformations
- **Plotly** for interactive charts
- Optional: **NumPy** for curve math

Keep it easy to run locally.

Expected run command:
```bash
pip install -r requirements.txt
streamlit run app.py
```

Suggested files:
```text
app.py
requirements.txt
README.md
data_generator.py
logic.py
utils.py
```

If the agent wants to keep everything in `app.py` for speed, that is acceptable.

---

## 7. App information architecture
Build a single-page Streamlit app with three main zones.

### A. Portfolio Overview
A top section showing the synthetic inventory portfolio.

Display:
- total cohorts
- total estimated inventory value
- number / percent at risk of crossing into wholesale-favored economics soon
- number / percent stuck in recon-heavy state
- weighted average days since acquisition

Include:
- filters for source channel, retailability state, market cluster, body type, price band
- a table of cohorts with sortable columns

### B. Cohort Drilldown
When a row is selected, show the chosen cohort or representative unit.

Display:
- descriptor summary
- timing summary
- cost summary
- current state
- current recommendation

### C. Crossover Clock + Strategy Panel
This is the hero section.

Display:
- expected retail value path by day
- wholesale floor line
- optional transfer-adjusted retail path
- crossover day marker
- strategy recommendations
- acquisition confidence score and label
- rationale text

---

## 8. User controls
Provide these controls in the sidebar.

### Portfolio filters
- source channel
- retailability state
- market cluster
- body type
- price band
- age band

### Strategy controls
- strategy mode: `Margin Max`, `Balanced`, `Turn Max`
- hold horizon in days: slider, e.g. 0 to 30
- markdown toggle: on/off
- markdown percent: slider, e.g. 0% to 10%

### Scenario controls
- wholesale market shock: e.g. `-10%` to `+5%`
- retail demand strength: `weak`, `base`, `strong`
- recon capacity pressure: `low`, `medium`, `high`

Keep the number of controls modest.

---

## 9. Data model
Use **cohort-level synthetic data** as the primary table, but let the app talk as though each cohort is made of similar units.

### Primary entity: `inventory_cohort`
Each row is one cohort.

Suggested fields:

#### Identification
- `cohort_id` (string)
- `market_cluster` (string) — e.g. Richmond, Mid-Atlantic North, Atlanta, Dallas
- `store_count_coverage` (int)

#### Sourcing / business descriptors
- `source_channel` (categorical)
  - `consumer_appraisal`
  - `dealer_purchase`
  - `auction`
- `retailability_state` (categorical)
  - `frontline_ready`
  - `recon_light`
  - `recon_heavy`
  - `borderline_retail`
  - `wholesale_likely`
- `body_type` (categorical)
  - `sedan`
  - `suv`
  - `truck`
  - `cuv`
  - `van`
  - `ev`
- `price_band` (categorical)
  - `under_20k`
  - `20k_30k`
  - `30k_40k`
  - `40k_plus`
- `age_band` (categorical)
  - `0_3_years`
  - `4_6_years`
  - `7_10_years`
  - `10_plus_years`
- `mileage_band` (categorical)
  - `under_30k`
  - `30k_60k`
  - `60k_90k`
  - `90k_plus`
- `cohort_units` (int)

#### Timing / flow-state fields
- `days_since_acquisition` (int)
- `days_in_current_stage` (int)
- `days_in_recon` (int)
- `days_frontline_ready` (int)
- `days_since_listed` (int)

#### Economics
- `avg_acquisition_cost` (float)
- `expected_recon_cost` (float)
- `daily_carry_depreciation` (float)
- `current_expected_retail_price` (float)
- `wholesale_floor_price` (float)
- `embedded_transfer_cost` (float) — may be hidden from the UI and treated as a fixed assumption

#### Operational modifiers
- `recon_priority_score` (0-100)
- `market_demand_index` (0.8-1.2 range)
- `market_supply_pressure_index` (0.8-1.2 range)
- `transfer_uplift_pct` (float) — retail path improvement if sent to a better market
- `sale_probability_decay_rate` (float)
- `retail_price_decay_rate` (float)

#### Derived outputs (computed in app)
- `crossover_day`
- `recommended_action`
- `strategy_mode`
- `expected_value_hold`
- `expected_value_transfer`
- `expected_value_expedite_recon`
- `expected_value_wholesale`
- `acquisition_confidence_score`
- `acquisition_confidence_label`
- `decision_rationale`

---

## 10. Synthetic data generation rules
The synthetic data should be plausible, not random nonsense.

### Suggested cohort count
- 40 to 80 cohorts total

### Pattern guidance
Embed believable differences:
- `auction` cohorts should be somewhat riskier on average than `consumer_appraisal`
- `recon_heavy` and `wholesale_likely` cohorts should have higher aging risk
- older / higher-mileage cohorts should have lower retail upside and lower wholesale floors
- trucks and SUVs can have somewhat higher price bands on average
- strong `market_demand_index` should improve retail value path and delay crossover
- high `days_since_acquisition` plus weak demand should push more cohorts toward wholesale

### Example generation logic
- higher age band -> higher `retail_price_decay_rate`
- higher mileage band -> lower `current_expected_retail_price`
- `recon_heavy` -> higher `expected_recon_cost` and more `days_in_recon`
- `wholesale_likely` -> lower retail sale odds and earlier crossover

The goal is to create data that produces clearly different recommendations.

---

## 11. Core decision logic
This is the heart of the app.

Use a **simple expected value engine**.

### 11.1 Retail hold path
For each future day `d` in a horizon (e.g. 0 to 30 days), estimate:

```text
retail_price_d = current_expected_retail_price * (1 - retail_price_decay_rate)^d
```

Estimate a sale-probability factor:

```text
sale_prob_d = base_sale_prob * exp(-sale_probability_decay_rate * d)
```

Where `base_sale_prob` can be influenced by:
- retailability state
- market demand index
- strategy mode
- optional markdown

Estimated expected retail value on day `d`:

```text
expected_retail_value_d =
  (retail_price_d * sale_prob_d)
  - avg_acquisition_cost
  - expected_recon_cost
  - (daily_carry_depreciation * d)
```

This does not need to be perfect. It needs to be transparent and directionally sensible.

### 11.2 Wholesale path
Wholesale expected value can be treated as immediate liquidation value:

```text
expected_wholesale_value =
  wholesale_floor_price * wholesale_market_shock_factor
  - avg_acquisition_cost
  - sunk_recon_recovery_adjustment
```

This can be simplified further if desired.

### 11.3 Transfer path
Transfer is a modified retail path with an improved demand / price profile and a fixed cost penalty.

```text
transfer_adjusted_retail_price_d = retail_price_d * (1 + transfer_uplift_pct)
expected_transfer_value_d =
  (transfer_adjusted_retail_price_d * transfer_sale_prob_d)
  - avg_acquisition_cost
  - expected_recon_cost
  - embedded_transfer_cost
  - (daily_carry_depreciation * d)
```

### 11.4 Expedite recon path
Expedite recon should reduce time to frontline readiness but increase cost slightly.

Simplified idea:
- reduces effective delay by X days
- adds expedite penalty cost
- improves base sale probability modestly for recon states

```text
expected_expedite_value =
  best_retail_value_after_reduced_delay
  - expedite_cost_penalty
```

### 11.5 Crossover day
The **crossover day** is the first day `d` at which the best retail hold value falls below wholesale.

```text
crossover_day = min(d) where expected_retail_value_d < expected_wholesale_value
```

If no such day occurs in the horizon, show `No crossover in horizon`.

---

## 12. Strategy modes
The app should support three strategy presets.

### Margin Max
Bias:
- more patient
- willing to hold longer
- slower sale probability decay penalty
- stricter threshold before wholesale

### Balanced
Bias:
- middle-of-the-road
- sensible default

### Turn Max
Bias:
- values speed and capital release
- shorter acceptable hold window
- more aggressive wholesale / transfer recommendation
- stronger penalty for aging inventory

Implementation idea:
Each strategy can change a few coefficients:
- acceptable hold horizon
- carry/depreciation penalty weight
- minimum margin threshold
- sale probability assumptions

Do not overcomplicate this. A simple coefficient table is enough.

---

## 13. Acquisition confidence logic
This is a derived, strategic output.

Question being answered:
**“Would we want to acquire more of this type of unit again at a similar price?”**

### Output fields
- `acquisition_confidence_score` (0 to 100)
- `acquisition_confidence_label` (`High`, `Medium`, `Low`)

### Suggested logic
Start at a neutral base, e.g. 50, then adjust:
- + if recommended action is `Hold for retail`
- + if crossover day is far out or absent
- + if market demand index is strong
- - if recommendation is `Liquidate to wholesale`
- - if days since acquisition is already high
- - if retailability state is `wholesale_likely` or `recon_heavy`
- - if expected value is weak under all strategies

Example simple rubric:
```text
score = 50
+ 15 if hold_for_retail
+ 10 if transfer
- 10 if expedite_recon
- 20 if wholesale
+ 10 if crossover_day > 14 or no crossover
- 10 if days_since_acquisition > 45
- 10 if retailability_state in [recon_heavy, wholesale_likely]
clamp to 0..100
```

Labels:
- `High` = 70+
- `Medium` = 40 to 69
- `Low` = under 40

This should be explained in a tooltip or expander so it feels interpretable.

---

## 14. Recommendation engine
For the selected cohort, compute:
- best hold-for-retail expected value within horizon
- best transfer expected value within horizon
- best expedite recon expected value within horizon
- wholesale immediate expected value

Recommended action = action with best expected value **after strategy mode adjustments**.

Also generate a plain-English rationale.

### Example rationale templates
- `Hold for retail: retail economics remain above the wholesale floor for ~12 more days, and this cohort still has healthy demand in its current market.`
- `Transfer to stronger market: current market demand is weak, but a transfer premium offsets the fixed move cost and extends the retail window.`
- `Expedite recon: this cohort is being trapped in recon. Paying a modest expedite premium improves time-to-frontline enough to preserve retail economics.`
- `Liquidate to wholesale: the expected retail value is already below the wholesale floor under the selected strategy, and additional hold time increases downside.`

---

## 15. Visualizations
### 15.1 Portfolio charts
At least two:
1. bar chart: cohort count or units by retailability state
2. scatter plot: days since acquisition vs expected value gap to wholesale

Optional third:
- stacked bar by source channel and recommendation

### 15.2 Crossover Clock chart (required)
One line chart with:
- expected retail value by day
- expected transfer value by day (optional dashed line)
- wholesale floor value (flat line)
- vertical line at crossover day
- annotation for recommended action

This chart should be the visual centerpiece.

### 15.3 Recommendation comparison cards
Show cards for:
- Hold for retail
- Transfer
- Expedite recon
- Wholesale

Each card should display:
- expected value
- expected exit speed category
- key tradeoff note

Highlight the selected recommendation.

---

## 16. UX and tone
The UI should feel:
- clean
- executive-friendly
- analytical but not crowded
- strategic rather than academic

Use plain English labels.

Good examples:
- `At Risk of Wholesale Crossover`
- `Days Left Before Retail Hold Becomes Unfavorable`
- `Would We Buy More of This Type?`

Avoid labels like:
- `latent hazard ratio`
- `stochastic inventory utility`

---

## 17. Demo narrative to support the app
The product should support this flow:

1. “This portfolio view shows where inventory value is most at risk from aging and weak downstream economics.”
2. “Let’s drill into one cohort that looks vulnerable.”
3. “Here’s the Crossover Clock. The retail value path is decaying toward the wholesale floor.”
4. “Under a margin-max strategy, we can still hold. Under a turn-max strategy, we should exit sooner.”
5. “Notice the app doesn’t just react to the current unit — it also computes acquisition confidence, which tells us whether this is a profile we should keep buying.”

The demo should make it easy to say:
> “I wanted to show how a supply chain strategy team can make timing and routing choices that connect acquisition, recon, movement, and liquidation — not just report aging inventory.”

---

## 18. Acceptance criteria
The build is successful if:
- the app runs locally with one command
- there is a portfolio table of synthetic cohorts
- selecting a cohort updates the drilldown section
- the Crossover Clock renders and updates based on controls
- the app outputs one of four routing recommendations
- the app outputs acquisition confidence
- the recommendation changes sensibly across at least some scenarios / strategy modes
- the UI is understandable without reading code

Bonus if:
- a selected markdown affects the retail path inside Hold for Retail
- transfer visibly changes the curve
- rationale text updates dynamically

---

## 19. Suggested implementation order for the agent
### Step 1
Create synthetic cohort data generator.

### Step 2
Build sidebar controls and portfolio table.

### Step 3
Implement core expected-value logic for all four actions.

### Step 4
Build Crossover Clock chart.

### Step 5
Add acquisition confidence scoring.

### Step 6
Add recommendation cards and rationale text.

### Step 7
Polish labels and formatting.

Do not start with styling. Start with logic.

---

## 20. Pseudocode skeleton
```python
load_or_generate_data()

render_sidebar_controls()
filtered_df = apply_filters(df, controls)

render_portfolio_summary(filtered_df)
selected_cohort = render_selectable_table(filtered_df)

scenario = build_scenario_from_controls(controls)
results = evaluate_cohort(selected_cohort, scenario)

render_cohort_summary(selected_cohort, results)
render_crossover_clock(results)
render_action_cards(results)
render_acquisition_confidence(results)
render_rationale(results)
```

Core function suggestions:
```python
def evaluate_hold_path(cohort, scenario):
    ...

def evaluate_transfer_path(cohort, scenario):
    ...

def evaluate_expedite_path(cohort, scenario):
    ...

def evaluate_wholesale_path(cohort, scenario):
    ...

def compute_crossover_day(retail_curve, wholesale_value):
    ...

def compute_acquisition_confidence(cohort, results):
    ...

def choose_recommendation(results, strategy_mode):
    ...
```

---

## 21. Nice-to-have stretch ideas (only if time remains)
- compare recommendations under all three strategy modes side by side
- add a portfolio heatmap of cohorts near crossover
- allow a toggle between cohort view and representative unit view
- export one selected cohort as a memo-style recommendation
- add a compact “what changed?” section when the user toggles scenario inputs

Do not do these until the MVP works.

---

## 22. README blurb
Use something like this in the repo README:

> A Streamlit demo for a CarMax-style supply chain strategy use case. The app evaluates used-vehicle inventory cohorts and recommends whether to hold for retail, transfer, expedite reconditioning, or liquidate to wholesale. Its core analytical view, the Crossover Clock, shows when expected retail economics deteriorate below the wholesale floor and adds an acquisition confidence signal to connect downstream routing decisions back to upstream buying discipline.

---

## 23. Final instruction to the coding agent
Build the simplest version that makes the strategic idea obvious.

Priority order:
1. make the logic coherent
2. make the chart compelling
3. make the recommendation explainable
4. make the UI clean

Do **not** overbuild pricing science, forecasting, or optimization.
This is a strategy demo, not a production revenue-management system.

---

## 24. Optional source context for product framing
These points informed the product framing and can be mentioned in README or presentation notes, but do not need to appear in the UI:
- CarMax’s supply chain strategy work spans acquiring, reconditioning, and moving vehicles
- CarMax has both a large retail used-vehicle business and a significant wholesale business
- CarMax publicly highlights risks around access to inventory and failure to expeditiously liquidate inventory

