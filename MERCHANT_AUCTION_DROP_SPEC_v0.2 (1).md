# MERCHANT: Auction Drop Decision Engine

## Spec v0.2 — March 2026

---

## What This App Does

A Manheim auction manifest drops. 80+ vehicles available. Your lot has 300+ units — you already know what's in stock because the existing portfolio cohort model tracks it. The model ingests the auction vehicles, scores every one against your current portfolio state, and returns a ranked bid list with ceiling prices and skip reasons.

The user's job is to review, override, and commit. The model's job is to react to those overrides in real time.

---

## Relationship to Existing App

**This is a refactor, not a rebuild.**

The current app already has the hard part:

- Portfolio cohorts with segment data, acquisition costs, days on lot
- Expected value model (retail, wholesale, recon estimates)
- Wholesale floor tracking
- Market context (demand indices, seasonal adjustments)

What changes:

| Current Role | New Role |
|-------------|----------|
| Portfolio cohort view = main screen | Portfolio cohort view = lot state context panel ("what's already in stock") |
| Expected value chart = hero feature | Expected value logic = internal scoring engine for bid ceilings |
| Retailability state = displayed label | Retailability logic = informs portfolio fit scoring (not shown as label) |
| Crossover clock = primary visual | Crossover logic = informs hold confidence behind skip/bid rationale |
| Scenario toggles = standalone feature | Market shocks = live modifiers that re-sort the bid list |

**The existing cohort data becomes the `lot_state` input.** The auction drop becomes the new front door. When a user wants to understand why the model says "you're heavy on SUVs," they click through to the existing portfolio view — that's the evidence layer.

### What Stays

- All existing cohort/portfolio data structures
- Segment definitions and assignment logic
- Recon cost estimation model
- Wholesale floor calculations
- Market demand indices
- Seasonal adjustments

### What Changes

- Landing screen becomes auction input + bid room
- Portfolio view moves to a "Current Lot" tab or side panel
- Expected value formula refactored: no more probability-weighted decay curve on the main display — replaced by bid ceiling math (see Decision Logic)
- Retailability state removed as a displayed field — its logic folds into portfolio fit scoring
- Scenario toggles replaced by market shock modifiers that have visible, immediate effect on bid list

### What's New

- Auction manifest input (CSV upload or manual table entry)
- Bid/skip scoring engine
- Bid room UI with drag-and-drop override
- Override reaction logic (displacement recommendations)
- Portfolio impact summary (live-updating)
- Bid sheet export

---

## Core Loop

```
AUCTION MANIFEST (user input — CSV or manual table)
        ↓
LOT STATE (from existing portfolio cohort data)
        ↓
SCORE EVERY VEHICLE → bid list + skip list
        ↓
USER REVIEWS → overrides (drag skip → bid, adjust ceiling, force-include)
        ↓
MODEL REACTS → recalculates portfolio exposure, recon queue, concentration risk
        ↓
USER COMMITS → final bid sheet exported
```

This is a conversation with the model, not a report from it.

---

## Inputs

### 1. Auction Manifest (User-Entered)

**Design constraint:** A user must be able to type 10–20 vehicles into a Streamlit editable table in under a minute. CSV upload available for larger batches.

#### Required Fields (6 columns)

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `year` | int | 2022 | Model year |
| `make` | string | Toyota | Manufacturer |
| `model` | string | Camry | Model name |
| `mileage` | int | 34000 | Odometer reading |
| `condition` | float | 3.5 | Manheim-style grade (1.0–5.0) |
| `auction_price` | float | 24500 | Expected sale price / your bid-against number |

#### Optional Fields (user can leave blank)

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `trim` | string | SE | Trim level (model uses base trim assumptions if blank) |
| `notes` | string | "paint work, tire wear" | Free text for known issues — model parses for recon adjustments |

**The model fills in everything else:**
- Segment assignment → from make/model lookup
- Recon estimate → from condition grade + parsed notes
- Expected retail price → from year/mileage/segment/regional demand
- Bid ceiling → from retail price minus target margin minus recon minus carry
- Portfolio fit → from current lot state

#### CSV Upload Format

Same columns. Header row required. UTF-8 encoding. Example:

```csv
year,make,model,mileage,condition,auction_price,trim,notes
2022,Toyota,Camry,34000,3.5,24500,SE,
2021,Ford,F-150,52000,2.8,31000,XLT,paint work
2023,Honda,CR-V,18000,4.2,27800,EX,
2020,Chevrolet,Equinox,61000,3.0,16500,LT,tire wear
```

#### Streamlit Table Input

- Editable `st.data_editor` with the 6 required columns pre-defined
- Blank rows available to type into
- Paste from Excel/Sheets supported natively by `st.data_editor`
- "Add Row" button
- Validation: flag rows missing required fields, flag condition outside 1.0–5.0, flag auction_price ≤ 0

### 2. Lot State (From Existing Portfolio Data)

**This is not user-entered. It is pulled from the existing cohort/portfolio model.**

The current app already tracks these. Wire them into the scoring engine:

| Field | Source | Description |
|-------|--------|-------------|
| `total_units` | count of active cohorts | Current inventory count |
| `segment_counts` | derived from cohort segments | Units per segment |
| `segment_targets` | configurable / pre-set | Ideal mix by segment |
| `avg_days_on_lot` | from cohort age data | Portfolio average age |
| `recon_bays_total` | configurable (default: 14) | Total recon capacity |
| `recon_bays_occupied` | configurable (default: 80% of total) | Currently in use |
| `recon_queue_depth` | derived from cohorts in recon state | Vehicles waiting |
| `recent_retail_velocity` | from cohort sale data or configurable | Units sold per segment last 30 days |
| `wholesale_index_deltas` | from market context model | Segment-level wholesale price movement |

**For demo purposes:** If the existing app doesn't track all of these yet, make them editable in a "Lot Settings" sidebar so the user can set plausible values. Sensible defaults for a Richmond CarMax-like lot:

```
total_units: 340
capacity: 400
recon_bays_total: 14
recon_bays_occupied: 11
avg_days_on_lot: 28
```

### 3. Market Context (Pre-loaded)

Pulled from existing model. If not yet implemented, use configurable defaults:

| Field | Default | Description |
|-------|---------|-------------|
| `season` | `spring_tax` | Affects demand multiplier |
| `regional_demand_index` | by segment, 0.5–0.9 | Relative local demand |
| `avg_retail_margin_by_segment` | $1,200–$2,800 | Historical avg gross |
| `avg_days_to_sale_by_segment` | 18–42 days | Historical avg time-to-sale |
| `daily_carry_rate` | $35/day | Floorplan + opportunity cost |

---

## Outputs

### Per-Vehicle Score Card

Every vehicle in the manifest gets scored. Two lists: **Bid** and **Skip**.

#### Bid List Vehicle

| Field | Description |
|-------|-------------|
| `rank` | Priority rank within bid list |
| `vehicle` | Year Make Model (e.g. "2022 Toyota Camry SE") |
| `bid_ceiling` | Max recommended bid |
| `expected_margin` | Projected gross at ceiling price |
| `recon_estimate` | Estimated recon cost and days |
| `segment` | Assigned segment |
| `portfolio_fit` | 0.0–1.0 score |
| `rationale` | One plain sentence: why bid, at this price |

#### Skip List Vehicle

| Field | Description |
|-------|-------------|
| `vehicle` | Year Make Model |
| `skip_reason` | Category (see below) |
| `skip_detail` | One plain sentence |
| `would_bid_if` | What would have to change (nullable) |

**Skip reasons:**
- `segment_overexposed` — lot already heavy in this segment
- `margin_insufficient` — expected margin below threshold at auction price
- `recon_risk` — condition/notes suggest high or uncertain recon cost
- `recon_queue_full` — recon backlog can't absorb another unit
- `slow_segment` — retail velocity too low for current inventory depth
- `wholesale_softening` — wholesale index dropping in this segment
- `condition_fail` — notes include disqualifying issues (frame damage, flood, etc.)

### Portfolio Impact Summary (Live-Updating)

Displayed as a persistent strip/panel. Updates in real time as user overrides.

| Metric | Description |
|--------|-------------|
| Units to bid | Count of bid list |
| Capital required | Sum of bid ceilings |
| Expected gross | Sum of expected margins |
| Segment mix shift | Before vs. after comparison |
| Recon queue impact | Current → projected queue depth |
| Concentration warnings | Segments exceeding target by >15% |

---

## Decision Logic

### Step 1: Segment Assignment

Hardcoded make/model → segment lookup. Segments:

- `compact_sedan` (Civic, Corolla, Sentra, Jetta)
- `midsize_sedan` (Camry, Altima, Accord, Malibu, Sonata)
- `full_size_sedan` (Avalon, Maxima, Impala)
- `compact_suv` (CR-V, RAV4, Equinox, Tucson, Rogue, Escape)
- `midsize_suv` (Highlander, Explorer, Pilot, Santa Fe, Sorento)
- `full_size_suv` (Tahoe, Expedition, Suburban, Sequoia, Armada)
- `pickup_midsize` (Tacoma, Colorado, Ranger, Frontier)
- `pickup_full_size` (F-150, Silverado, RAM 1500, Tundra)
- `minivan` (Odyssey, Sienna, Pacifica, Grand Caravan)
- `luxury` (BMW 3/5, Mercedes C/E, Audi A4/Q5, Lexus RX/ES)
- `sports` (Mustang, Camaro, Challenger, Miata)
- `other` (anything unmapped)

Unknown make/model → `other` with a UI flag to let user reassign.

### Step 2: Condition Filter

Parse `notes` field for hard-fail keywords:
- "frame damage" or "frame" → hard skip, reason `condition_fail`
- "flood" → hard skip
- "salvage" → hard skip

These are non-overridable.

### Step 3: Recon Estimation

From `condition` grade:

| Condition | Recon Cost | Recon Days |
|-----------|-----------|------------|
| 4.0–5.0 | $300 | 2 |
| 3.0–3.9 | $1,000 | 4 |
| 2.0–2.9 | $2,500 | 8 |
| 1.0–1.9 | $4,500 | 12 |

Additive adjustments parsed from `notes`:
- "paint" → +$400, +1 day
- "mechanical" → +$800, +3 days
- "tire" → +$600, +1 day
- "odor" or "smoke" → +$300, +2 days
- "interior" → +$500, +2 days

### Step 4: Bid Ceiling Calculation

```
expected_retail_price = base_price_lookup(segment, year, mileage)
                      × condition_adjustment(condition)
                      × seasonal_multiplier(season)
                      × regional_demand_index[segment]

bid_ceiling = expected_retail_price
            - target_margin
            - recon_estimate
            - (avg_days_to_sale[segment] × daily_carry_rate)
            - risk_buffer

target_margin = max(avg_retail_margin_by_segment[segment], $800)

risk_buffer = base $200
            + $300 if wholesale_index_delta[segment] < -0.02
            + $200 if condition < 3.0
            + $200 if avg_days_to_sale[segment] > 35
```

**If `bid_ceiling < auction_price`:** skip, reason `margin_insufficient`.
**`would_bid_if`:** "Auction price drops below ${bid_ceiling}" or "Retail demand strengthens in this segment."

### Step 5: Portfolio Fit Scoring

```
portfolio_fit = w1 × segment_need
              + w2 × velocity_score
              + w3 × recon_capacity_score
              - w4 × concentration_penalty

segment_need = clamp((target - current) / target, -1.0, 1.0)
velocity_score = segment_velocity / avg_velocity (normalized 0–1)
recon_capacity_score = 1.0 - (projected_queue / max_acceptable_queue)
concentration_penalty = 0.3 if segment would exceed target by >15%, else 0
```

Weights:
- w1 = 0.35 (segment need)
- w2 = 0.30 (velocity)
- w3 = 0.20 (recon capacity)
- w4 = 0.15 (concentration)

### Step 6: Rank and Cut

1. Score each vehicle: `rank_score = expected_margin × portfolio_fit`
2. Sort descending
3. Walk the list, accumulating recon queue impact
4. Cut when `recon_queue_projected > recon_bays_total × 2.5`
5. Remaining below cutoff → skip, reason `recon_queue_full`

### Step 7: Generate Rationale

**Bid example:**
> "Bid up to $24,100 on this 2022 Camry SE. Richmond is 12 units below target in compact sedans, this segment sells in 18 days, and expected margin at ceiling is $1,650 after $1,000 recon."

**Skip example:**
> "Skip. Already 8 units over target in midsize SUVs. Wholesale index dropped 3% this week — exit risk outweighs hold value."

---

## Override Logic (The Kill Feature)

### Skip → Bid

1. Model accepts the override
2. Recalculates portfolio impact with this unit included
3. Checks for **displacement**: if recon queue or concentration now exceeds threshold, recommends dropping the lowest-ranked current bid vehicle
   - "Taking this Tahoe at $34k means dropping the Traverse (rank #22) — recon can't absorb both and you're now 20% over target in full-size SUVs."
4. Updates all live metrics

### Bid → Skip

1. Model accepts the override
2. Checks if removal opens space for a previously-cut vehicle
   - "Removing the Altima freed a recon slot. The Tucson at rank #26 now qualifies — add it?"
3. Updates all live metrics

### Ceiling Adjustment

1. User edits bid ceiling on any bid vehicle
2. Model recalculates expected margin at new ceiling
3. If margin < $800: amber warning — "Margin is thin at this price"
4. If margin < $0: red warning — "At this price you're buying a wholesale loss"
5. Rank may shift based on new margin

---

## Market Shock Modifier

**Replaces the old abstract scenario toggles.**

Instead of "demand: high/medium/low," the shocks are specific and have visible, immediate effects.

Implemented as toggles or buttons in the UI:

| Shock | What It Does |
|-------|-------------|
| "Wholesale SUV prices drop 4%" | Increases risk_buffer for all SUV segments by $500. Re-scores. Some SUV bids flip to skip. |
| "Sedan demand surge (tax refund season)" | Increases regional_demand_index for sedan segments by 0.10. Raises retail price estimates. Some sedan skips may flip to bid. |
| "Recon bay goes offline" | Reduces recon_bays_total by 2. Tightens queue constraint. Lowest-ranked high-recon vehicles get cut. |
| "Truck wholesale firms up 3%" | Reduces risk_buffer for truck segments. Trucks become safer bids. |

These should visibly re-sort the bid/skip lists when toggled. Cards animate between panels. Rationale text updates.

---

## UI Architecture (Streamlit)

### Tab 1: Auction Drop (New — Primary Screen)

**Top section: Manifest Input**
- `st.data_editor` with 6 required columns, pre-populated with empty rows
- "Upload CSV" button as alternative
- Row count + validation status displayed
- "Score Auction" button

**Main section: Bid Room** (appears after scoring)

Two-column layout:

- **Left column: Bid List**
  - Ranked cards (st.container or custom components)
  - Each card: vehicle name, bid ceiling, expected margin, portfolio fit badge, rationale
  - "Move to Skip" button per card
  - Expandable detail: recon breakdown, segment context, comparable lot vehicles

- **Right column: Skip List**
  - Grouped by skip reason (expanders)
  - Each card: vehicle name, reason, would_bid_if
  - "Move to Bid" button per card

**Bottom section: Portfolio Impact Strip**
- Columns showing: units to bid, capital, expected gross, recon queue
- Segment mix comparison (simple bar chart or table)
- Concentration warnings in red

**Sidebar: Market Shocks**
- Toggle switches for each shock scenario
- When toggled, bid/skip lists refresh

### Tab 2: Current Lot (Existing — Refactored)

The existing portfolio cohort view, now serving as context:
- Segment breakdown with unit counts vs. targets
- Age distribution
- Recon queue status
- Wholesale floor tracking
- This is where the user goes to understand *why* the auction model scored the way it did

### Tab 3: Export

- Final bid sheet table
- Download as CSV button
- Summary statistics

---

## Demo Flow (For Matt)

1. **Open.** Show the auction input table. "You're a buyer at Richmond. Auction's tomorrow."
2. **Enter 12–15 vehicles** by typing or paste. Mix of sedans, SUVs, trucks. Varying condition and price.
3. **Click "Score Auction."** Bid room populates. "Model says bid on 8, skip 7."
4. **Walk top 3 bids.** Read rationale. Show how segment need + velocity drove ranking.
5. **Show a skip.** "This Explorer looks fine, but you're already heavy on midsize SUVs."
6. **Override.** Move Explorer to bid. Watch portfolio impact update. Model says: "If you take the Explorer, drop the Equinox — can't recon both this week."
7. **Hit a market shock.** Toggle "Wholesale SUV prices drop 4%." Two SUV bids flip to skip. New rationale appears.
8. **Click to Current Lot tab.** "Here's what's already in stock — this is why the model said you're heavy on SUVs."
9. **Export bid sheet.** "This goes to your buyer at 6 AM."

**Total demo: 3–4 minutes.**

---

## Synthetic Data for Demo

### Pre-loaded Lot State (Richmond)

```python
lot_state = {
    "total_units": 340,
    "capacity": 400,
    "recon_bays_total": 14,
    "recon_bays_occupied": 11,
    "recon_queue_depth": 6,
    "avg_days_on_lot": 28,
    "segment_counts": {
        "compact_sedan": 38,    # target: 50  → undersupplied
        "midsize_sedan": 55,    # target: 55  → balanced
        "compact_suv": 72,      # target: 65  → oversupplied
        "midsize_suv": 58,      # target: 45  → oversupplied
        "full_size_suv": 22,    # target: 15  → oversupplied
        "pickup_full_size": 35, # target: 40  → undersupplied
        "pickup_midsize": 18,   # target: 20  → slightly under
        "minivan": 12,          # target: 15  → undersupplied
        "luxury": 20,           # target: 20  → balanced
        "sports": 5,            # target: 5   → balanced
        "other": 5,             # target: 10  → under
    },
    "recent_velocity_30d": {
        "compact_sedan": 22,
        "midsize_sedan": 18,
        "compact_suv": 25,
        "midsize_suv": 15,
        "full_size_suv": 6,
        "pickup_full_size": 14,
        "pickup_midsize": 8,
        "minivan": 5,
        "luxury": 7,
        "sports": 2,
        "other": 2,
    },
    "wholesale_index_deltas": {
        "compact_sedan": +0.01,
        "midsize_sedan": 0.00,
        "compact_suv": -0.01,
        "midsize_suv": -0.02,
        "full_size_suv": -0.04,  # dropping — this is the drama
        "pickup_full_size": +0.02,
        "pickup_midsize": +0.01,
        "minivan": 0.00,
        "luxury": -0.01,
        "sports": 0.00,
    }
}
```

### Sample Auction Manifest (For Quick Demo)

Pre-loaded as a default if user doesn't enter their own:

```python
sample_manifest = [
    {"year": 2022, "make": "Toyota",    "model": "Camry",     "mileage": 34000, "condition": 3.8, "auction_price": 22500},
    {"year": 2021, "make": "Honda",     "model": "CR-V",      "mileage": 41000, "condition": 3.5, "auction_price": 25200},
    {"year": 2023, "make": "Honda",     "model": "Civic",     "mileage": 18000, "condition": 4.3, "auction_price": 22800},
    {"year": 2022, "make": "Ford",      "model": "Explorer",  "mileage": 38000, "condition": 3.2, "auction_price": 29500},
    {"year": 2020, "make": "Chevy",     "model": "Equinox",   "mileage": 62000, "condition": 2.8, "auction_price": 16200},
    {"year": 2021, "make": "Ford",      "model": "F-150",     "mileage": 48000, "condition": 3.4, "auction_price": 32000},
    {"year": 2022, "make": "Nissan",    "model": "Rogue",     "mileage": 29000, "condition": 3.9, "auction_price": 23100},
    {"year": 2023, "make": "Toyota",    "model": "RAV4",      "mileage": 15000, "condition": 4.5, "auction_price": 29800},
    {"year": 2019, "make": "Chevy",     "model": "Silverado", "mileage": 71000, "condition": 2.5, "auction_price": 24500},
    {"year": 2022, "make": "Hyundai",   "model": "Tucson",    "mileage": 33000, "condition": 3.6, "auction_price": 24000},
    {"year": 2021, "make": "Toyota",    "model": "Highlander","mileage": 44000, "condition": 3.3, "auction_price": 33500},
    {"year": 2020, "make": "Chevy",     "model": "Tahoe",     "mileage": 58000, "condition": 2.9, "auction_price": 34000},
    {"year": 2022, "make": "Nissan",    "model": "Altima",    "mileage": 36000, "condition": 3.7, "auction_price": 20100},
    {"year": 2023, "make": "Honda",     "model": "Odyssey",   "mileage": 21000, "condition": 4.1, "auction_price": 32500},
    {"year": 2021, "make": "Toyota",    "model": "Tacoma",    "mileage": 39000, "condition": 3.4, "auction_price": 28500},
]
```

This manifest is designed to tell a story:
- Camry + Civic = strong bids (lot is undersupplied in sedans, good velocity)
- CR-V + Rogue + RAV4 = marginal (compact SUV already oversupplied)
- Explorer + Highlander + Tahoe = likely skips (midsize/full-size SUV way over target, wholesale softening)
- F-150 + Tacoma + Silverado = interesting (trucks undersupplied, but Silverado condition is rough)
- Odyssey = good fit (minivans undersupplied)
- Equinox = recon risk at condition 2.8 + already oversupplied segment

---

## Base Price Lookup (Simplified)

For MVP, use a static lookup table. Not trying to be Kelley Blue Book — just needs to be directionally correct.

```python
# base_retail_price by segment (for a 2022, 35k miles, condition 3.5)
base_prices = {
    "compact_sedan": 24000,
    "midsize_sedan": 27000,
    "compact_suv": 29000,
    "midsize_suv": 35000,
    "full_size_suv": 42000,
    "pickup_full_size": 38000,
    "pickup_midsize": 32000,
    "minivan": 34000,
    "luxury": 36000,
    "sports": 30000,
    "other": 22000,
}

# Adjustments:
# Year: +$1,500 per year newer than 2022, -$2,000 per year older
# Mileage: -$0.08 per mile above 35,000; +$0.05 per mile below 35,000
# Condition: ×1.05 for 4.0+; ×1.00 for 3.0–3.9; ×0.90 for 2.0–2.9; ×0.75 for <2.0
```

---

## Implementation Notes

- **Framework:** Streamlit (consistent with existing app)
- **Scoring logic:** All client-side Python, deterministic given inputs
- **No backend/API needed** — computation runs in the Streamlit process
- **Drag-and-drop alternative:** Since Streamlit doesn't natively support drag-and-drop between panels, use "Move to Bid" / "Move to Skip" buttons on each card. Functional equivalent, simpler to build.
- **Live updates:** Use `st.session_state` to track bid/skip assignments and override history. Recompute portfolio impact on every state change.
- **Charts:** Plotly or Altair for segment mix comparison and recon queue visualization

---

## What This Is Not

- Not a real auction integration (no Manheim API)
- Not a production pricing model (simplified economics)
- Not a multi-lot optimizer (single lot for MVP)
- Not a forecasting tool (no time-series prediction)

It is a **decision simulator** that demonstrates how a model can ingest real-world supply chain inputs and recommend actions that respond to user judgment in real time.

---

## Success Criteria

Matt opens it and within 10 seconds understands:
1. What decision he's making
2. What the model recommends
3. Why
4. What happens when he disagrees
