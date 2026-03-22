# CROSSLINE — Debug & Polish Spec

## For Claude Code execution. Fix everything below before shipping.

---

## 1. REBRAND: Merchant → Crossline

### Changes
- Page title: "Crossline — Auction Drop Decision Engine"
- Browser tab: "Crossline"
- Header: Display the logo image (see below) + "Crossline" text
- Footer: "Crossline v0.2 — Auction Drop Decision Engine"
- All references to "Merchant" in code, comments, and UI strings → "Crossline"

### Logo
- File: `crossline_logo.png` (included in repo — black basilisk illustration)
- Display in the sidebar or top of page using `st.image("crossline_logo.png", width=200)`
- The image is a black illustration on white/transparent background
- Below the logo, display "CROSSLINE" in clean, spaced caps as a header

---

## 2. FIX: Expected Margin Calculation (CRITICAL)

### The bug
Expected margin is currently calculated WITHOUT accounting for acquisition cost (the auction price). This means every vehicle in the same segment shows roughly the same margin regardless of what it costs to buy.

Evidence: A 2016 Chevy Cruze at $12,500 and a Rolls Royce Phantom both show ~$1,600 margin.

### Current (wrong)
```python
exp_margin = base_retail_by_segment[segment] - recon_estimate - carry_cost
```

### Correct
```python
exp_margin = estimated_retail_price - auction_price - recon_estimate - carry_cost
```

Where:
- `estimated_retail_price` = the model's computed retail value (from base price + year/mileage/condition adjustments)
- `auction_price` = what the user entered as the asking price
- `recon_estimate` = computed from condition grade + notes
- `carry_cost` = avg_days_to_sale[segment] × daily_carry_rate

### Downstream effects
- This fix changes the margin on EVERY vehicle card
- Bid ceiling remains the same (it already accounts for acquisition cost)
- Margin should now equal approximately: `bid_ceiling - auction_price + target_margin`
- If `auction_price > bid_ceiling`, margin at ceiling is negative — that's correct and is why the vehicle is skipped
- The portfolio impact summary "Expected Gross" should sum the corrected margins

### Validation check
After fixing, verify:
- Vehicles where `auction_price < bid_ceiling` show positive margin ✓
- Vehicles where `auction_price > bid_ceiling` show negative margin or are skipped ✓
- No two vehicles in different segments with different auction prices show the same margin ✓
- The Cruze at $12,500 with a $184 ceiling shows deeply negative margin, not $1,600 ✓

---

## 3. FIX: Skip Card Display

### Problem
Skip cards (right panel, margin_insufficient reason) currently show a positive margin alongside a ceiling far below the asking price. This is confusing — the whole reason it's skipped is that the economics don't work.

### Fix
For vehicles where `skip_reason == "margin_insufficient"`:
- Show `exp_margin` as the ACTUAL margin at auction price (will be negative after fix #2)
- Format negative margins in red: e.g., **-$2,400**
- Or alternatively: suppress the margin field entirely and just show:
  - "Bid ceiling: $184"
  - "Ask: $12,500"  
  - "Gap: -$12,316"
  - "Would bid if: Auction price drops below $184"

For vehicles where `skip_reason` is NOT margin_insufficient (e.g., segment_overexposed, recon_queue_full):
- Show the positive margin as-is — these vehicles are economically viable but skipped for portfolio reasons
- This distinction matters: "good vehicle, wrong time" vs "bad economics"

---

## 4. FIX: Low Bid Ceiling Display

### Problem
When bid_ceiling is very low (e.g., $184 on the Cruze), it looks like a bug even though the math is correct.

### Fix
If `bid_ceiling < 2000`:
- Replace the ceiling number with: **"No viable bid"**
- Show the estimated retail price so the user understands why: "Est. retail: $4,680 — too low to cover recon ($2,500) and carry ($700) with margin"
- Skip reason should be `margin_insufficient` automatically

If `bid_ceiling < 0`:
- Display: **"No viable bid"**  
- "This vehicle costs more to prepare and hold than it would sell for"

---

## 5. FIX: Unrecognized Make/Model Handling

### Problem
Vehicles not in the hardcoded segment lookup (Rolls Royce, Rivian, McLaren, etc.) fall to "other" with a $22,000 base price. This produces absurd results for luxury/exotic vehicles.

### Fix
When make/model is NOT found in the lookup table:

1. Assign segment = `"unrecognized"`
2. On the vehicle card, display a yellow warning banner:
   **"⚠ Unrecognized vehicle — retail estimate may be inaccurate"**
3. Use `"other"` base price ($22,000) as a fallback BUT flag it clearly
4. In rationale text: "This vehicle is not in our reference database. Retail estimate of $X is a rough approximation — review manually before bidding."

### Better fix (if time allows)
Add an optional `retail_estimate` column to the manifest input. If the user provides a value, skip the base price lookup entirely and use their number. This handles exotics, rare trims, and anything else the table misses.

In `st.data_editor`, add this as an optional 7th column:
```python
"retail_estimate": st.column_config.NumberColumn(
    "Retail Est. (optional)",
    help="Override the model's retail estimate if you know the vehicle's value",
    min_value=0,
    format="$%.0f"
)
```

---

## 6. FIX: Market Shocks

### Problem
Shocks modify one variable but don't flow through the full calculation chain.

### Shock 1: Sedan demand surge (tax refund season)

**Current behavior:** Increases capital required but expected gross doesn't change.

**Root cause:** Demand index goes up → retail price estimate goes up → bid ceiling goes up → capital goes up. BUT margin uses the old broken formula that ignores auction price, so margin doesn't change.

**Fix:** Once fix #2 (margin calc) is applied, this shock should work correctly automatically:
- Higher demand index → higher retail estimate → higher margin at same auction price → higher expected gross
- Some sedan skips (margin_insufficient) may flip to bid because ceiling now exceeds ask
- Verify: toggling this shock ON increases both capital AND expected gross for sedan vehicles

### Shock 2: Recon bay goes offline

**Current behavior:** Does nothing.

**Root cause:** The recon queue threshold is too generous. Current: `recon_bays_total × 2.5 = 35`. With only ~6 in queue + ~8–10 new vehicles, you never hit 35.

**Fix:** Change the recon constraint to something that actually binds:
```python
# Old (too loose)
max_recon_queue = recon_bays_total * 2.5

# New (realistic) 
max_recon_queue = (recon_bays_total - recon_bays_occupied) * 3 + recon_bays_occupied
# With defaults: (14 - 11) * 3 + 11 = 20
# After shock (lose 2 bays): (12 - 11) * 3 + 11 = 14
```

Or simpler — just use a tighter fixed multiplier:
```python
max_recon_queue = recon_bays_total * 1.2
# Default: 14 * 1.2 = 16.8
# After shock: 12 * 1.2 = 14.4
```

The shock should:
- Reduce `recon_bays_total` by 2
- Recalculate the queue constraint
- Cut the lowest-ranked vehicles with high recon days from the bid list
- Those vehicles move to skip with reason: "Recon queue is full — removing 2 bays means this vehicle can't be processed in time"

**Verify:** Toggling this shock ON removes at least 1-2 high-recon vehicles from the bid list.

### Shock 3: Truck wholesale firms up 3%

**Current behavior:** Reduces margin instead of increasing it. Backwards.

**Root cause:** The shock is probably ADDING to risk_buffer (making bids more conservative) when it should be SUBTRACTING (wholesale firming up = safer exit = bid more aggressively).

**Fix:** When truck wholesale firms up:
```python
# Wholesale firming up means EXIT FLOOR is higher = LESS risk
# So risk_buffer should DECREASE, bid_ceiling should INCREASE

if shock_truck_wholesale_up:
    for vehicle in truck_segments:
        risk_buffer -= 300  # was probably += 300
        # OR: wholesale_index_delta[segment] += 0.03
```

**Verify:**
- Toggling ON increases bid ceilings for trucks
- Expected margin for trucks goes UP (or stays same if ceiling rises but auction price unchanged)
- Capital required for trucks goes UP (willing to pay more)
- Some previously-skipped trucks may flip to bid

### Shock 4: Wholesale SUV prices drop 4%

**Verify this one works correctly:**
- SUV bid ceilings should decrease
- Some SUV bids should flip to skip
- Margin on remaining SUV bids should decrease
- Rationale should mention the wholesale drop

### All shocks — UI behavior
- When a shock is toggled, bid/skip lists must visibly re-sort
- Cards should move between panels (bid → skip or skip → bid) if their status changes
- The portfolio impact strip must update live
- The number of vehicles that changed status should be briefly indicated: "2 vehicles moved to skip" or similar

---

## 7. ADD: Decision Reason Tags

### Purpose
Each bid and skip card should show a visible tag indicating the PRIMARY reason for the recommendation. This makes the app feel like judgment, not arithmetic.

### Bid reason tags (green/teal badges)
- **Fill shortage** — lot is undersupplied in this segment (segment_need_score > 0.15)
- **Fast turn** — this segment sells quickly (velocity_score > 0.7)
- **Safe margin** — strong spread between ceiling and ask (margin > $2,000)
- **Low recon** — condition 4.0+ and no notes, minimal recon cost and time
- **Strategic stretch** — margin is modest but portfolio fit is high (fit > 0.6, margin < $1,200)

### Skip reason tags (red/amber badges)  
- **Overexposed** — segment_overexposed
- **Too much recon** — recon_risk
- **Thin margin** — margin_insufficient (but ceiling is close to ask, within 20%)
- **Underwater** — margin_insufficient (ceiling is far below ask, gap > 20%)
- **Weak exit** — wholesale_softening
- **Queue full** — recon_queue_full
- **Crowds out better buys** — vehicle was viable but cut at Step 6 ranking

### Implementation
- Display as a small colored badge/pill on each card, next to the vehicle name
- Bid tags: teal or green background, dark text
- Skip tags: red or amber background, dark text
- One tag per card (primary reason only — don't stack multiple)

### Logic for selecting bid tag
Priority order (first match wins):
1. If `segment_need_score > 0.3` → "Fill shortage"
2. If `velocity_score > 0.7` AND `segment_need_score > 0` → "Fast turn"
3. If `condition >= 4.0` AND `recon_estimate < 500` → "Low recon"
4. If `exp_margin > 2000` → "Safe margin"
5. Else → "Strategic stretch"

---

## 8. FIX: Rationale Text — No Spec Jargon

### Problem
Rationale text may contain terms from the spec that mean nothing to a business user.

### Replace these terms everywhere they appear in UI text:

| Spec jargon | Plain English |
|-------------|---------------|
| risk_buffer | safety margin |
| portfolio_fit_score | how well this fits your current lot |
| concentration_penalty | you're already heavy in this segment |
| segment_need_score | how undersupplied you are in this segment |
| velocity_score | how fast this segment sells |
| recon_capacity_score | how much recon bandwidth you have |
| margin_insufficient | the math doesn't work at this price |
| wholesale_softening | wholesale prices are dropping in this segment |
| risk buffer shrinks | you can bid more aggressively because exit values firmed up |

### Rationale templates

**Bid rationale:**
> "Bid up to $[ceiling] on this [year] [make] [model]. Richmond is [X] units [above/below] target in [segment], this segment sells in [Y] days, and expected margin at ceiling is $[margin] after $[recon] recon."

**Skip — overexposed:**
> "Skip. Already [X] units over target in [segment]. Adding another [segment] vehicle increases concentration risk without enough margin to justify it."

**Skip — margin insufficient:**
> "Skip. At the asking price of $[ask], expected margin is -$[gap] after recon and carry. Would bid if price drops below $[ceiling]."

**Skip — recon risk:**
> "Skip. Condition [grade] with [notes] drives recon estimate to $[recon] and [days] days. That's too much recon time and cost relative to the expected margin."

**Skip — wholesale softening:**
> "Skip. Wholesale prices in [segment] dropped [X]% this week. If this vehicle doesn't sell retail, your exit floor is lower than usual."

**Skip — recon queue full:**
> "Skip. Recon is at capacity — [X] vehicles in queue with [Y] bays available. This vehicle needs [Z] days of recon and can't be processed in time."

**Override reaction — displacement:**
> "If you take this [make] [model] at $[ceiling], consider dropping the [other make] [other model] from your bid list — you'd be [X] units over target in [segment] and recon can't absorb both this week."

**Override reaction — slot opened:**
> "Removing the [make] [model] freed a recon slot. The [other make] [other model] (rank #[N]) now qualifies — add it?"

---

## 9. ADD: Lot State Justification Lines

### Problem
Segment targets (e.g., "compact_sedan target: 50") feel arbitrary. If the user doesn't understand where 50 came from, every recommendation built on it feels like sand.

### Fix
Next to each segment target in the lot settings display, show a one-line justification:

```python
# Example display in sidebar or lot state panel:
# Compact Sedan: 38 / 50 target
# ↳ Target based on 22 sold last 30d × 45-day turn window, capped at 15% of lot

# Midsize SUV: 58 / 45 target  
# ↳ Target based on 15 sold last 30d × 45-day turn window, capped at 15% of lot
```

### Calculation
```python
segment_target = min(
    velocity_30d[segment] * (45 / 30),  # velocity-based target
    total_capacity * 0.15               # max 15% of lot in any one segment
)
```

This makes the target inspectable and adjustable. The user can see: "The model thinks I should have 50 compact sedans because I sell 22 a month and want 45 days of supply." If they disagree, they can adjust.

### Display
In the sidebar under "Lot Settings", after the segment counts, add an expander:

```python
with st.expander("Segment targets & reasoning"):
    for segment in segments:
        current = segment_counts[segment]
        target = segment_targets[segment]
        velocity = velocity_30d[segment]
        delta = current - target
        status = "over" if delta > 0 else "under"
        st.markdown(f"**{segment}**: {current} / {target} target ({abs(delta)} {status})")
        st.caption(f"Target = {velocity} sold/mo × 1.5mo supply, max 15% of lot")
```

---

## 10. VERIFY: CSV Upload Edge Cases

Test and handle gracefully:
- Blank row in CSV → skip silently, don't crash
- Missing required field (e.g., no mileage) → flag row with red highlight, exclude from scoring, show message: "Row [N] missing required field: mileage"
- Condition value outside 1.0–5.0 → clamp to range with warning: "Condition adjusted to 5.0 (max)"
- Auction price = 0 or negative → flag and exclude
- Non-numeric values in numeric fields → flag and exclude
- Duplicate VINs (if VIN column added later) → warn but allow

---

## Execution Priority

1. **Fix margin calc** (#2) — everything else is less impactful than this
2. **Fix shock logic** (#6) — the demo depends on shocks working visibly
3. **Rebrand to Crossline** (#1) — quick, high visibility
4. **Add decision reason tags** (#7) — biggest UX upgrade for minimal code
5. **Fix skip card display** (#3) — follows naturally from margin fix
6. **Fix low ceiling display** (#4) — small but prevents "is this broken?" moment  
7. **Fix rationale text** (#8) — find-and-replace pass
8. **Add lot state justifications** (#9) — strengthens the foundation
9. **Unrecognized vehicle handling** (#5) — edge case polish
10. **CSV edge cases** (#10) — defensive polish

---

## Testing Checklist (Run Before Shipping)

- [ ] Load sample manifest → bid/skip split looks reasonable
- [ ] Margins vary by vehicle (not same number repeated)
- [ ] Cruze shows negative margin or "no viable bid"
- [ ] Type in a Rolls Royce → warning about unrecognized vehicle
- [ ] Toggle sedan demand surge → expected gross increases, some sedans flip bid
- [ ] Toggle recon bay offline → at least 1 high-recon vehicle moves to skip
- [ ] Toggle truck wholesale up → truck margins increase, truck ceilings increase
- [ ] Toggle wholesale SUV drop → some SUV bids flip to skip
- [ ] Move a vehicle from skip to bid → portfolio impact updates
- [ ] Override triggers displacement recommendation (if applicable)
- [ ] All rationale text is plain English, no spec jargon
- [ ] Every bid card has a decision reason tag
- [ ] Every skip card has a skip reason tag
- [ ] Page title says "Crossline"
- [ ] Logo displays correctly
- [ ] Upload CSV with blank rows → handles gracefully
- [ ] Sidebar shows segment targets with justification text
