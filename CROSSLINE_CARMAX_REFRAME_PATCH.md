# CROSSLINE — CarMax Reframe Patch

## Context
CarMax buys at auction to fill retail inventory gaps, not to wholesale. Wholesale is the failure mode, not a strategy. All language should reflect: every auction dollar is a retail bet. The question is which bets are good ones.

---

## 1. Remove/Rename "Wholesale" Language

### Skip reasons — find and replace:
| Current | New |
|---------|-----|
| `wholesale_softening` | `market_softening` |
| "Wholesale prices dropping in this segment" | "Used vehicle market prices dropping in this segment — retail margins at risk" |
| "Weak exit" (skip tag) | "Soft market" |
| "Underwater" (skip tag referencing wholesale) | "Underwater" (keep tag, but change explanation) |

### Skip card rationale — update templates:
| Current | New |
|---------|-----|
| "Wholesale index dropped X%" | "Market index dropped X% in this segment — if it doesn't sell retail, you're exposed" |
| "Exit risk outweighs hold value" | "Retail margin is thin and market is softening" |
| "Would bid if wholesale firms up" | "Would bid if market prices stabilize in this segment" |

### Anywhere in the codebase:
- `wholesale_index_deltas` → `market_index_deltas` (variable name)
- `wholesale_floor` → remove or rename to `market_floor` 
- Any rationale text mentioning "wholesale exit" or "liquidate to wholesale" → "retail economics don't support this purchase"

---

## 2. Rename Market Shock Toggles

| Current | New |
|---------|-----|
| "Wholesale SUV prices drop 4%" | "Used SUV market prices drop 4%" |
| "Truck wholesale firms up 3%" | "Used truck market prices firm up 3%" |
| "Sedan demand surge (tax refund season)" | No change — this is fine |
| "Recon bay goes offline" | No change — this is fine |

Shock descriptions in any tooltip or explanatory text:
| Current | New |
|---------|-----|
| "Increases risk_buffer for SUV segments" | "SUV retail margins compress — some bids no longer pencil" |
| "Reduces risk_buffer for truck segments" | "Truck retail margins strengthen — can bid more aggressively" |

---

## 3. Update Rationale Text to Retail-First Framing

### Bid rationale — no changes needed
These already read as retail decisions. Just verify none mention wholesale.

### Skip rationale — key updates:

**margin_insufficient:**
> OLD: "Skip. At the asking price of $X, expected margin is -$Y after recon and carry. Would bid if price drops below $ceiling."
> NEW: "Pass. At $X, the retail margin doesn't pencil after recon and carry. Would bid below $ceiling." ✓ (fine as-is, just verify no wholesale mention)

**market_softening (was wholesale_softening):**
> OLD: "Skip. Wholesale prices in [segment] dropped X% this week. If this vehicle doesn't sell retail, your exit floor is lower than usual."
> NEW: "Pass. Market prices in this segment dropped X% this week — retail margins are compressed and the downside is elevated."

---

## 4. Add Footer Note About Pricing Data

In the sidebar or footer area, add a small caption:
```python
st.caption("Demo uses segment-average pricing. Production version would anchor to Edmunds/NADA market data or internal offer models.")
```

---

## 5. Add Buyer Integration Note

In the sidebar under the logo/brand, or as a small expander at the bottom of lot settings:
```python
st.caption("Designed to set portfolio context before auction day. Buyers bring lane-level judgment the model can't replicate.")
```

---

## Testing
- [ ] Search entire codebase for "wholesale" — zero instances in UI-facing text
- [ ] Shock toggles show updated labels
- [ ] Skip card rationale mentions "market" not "wholesale"
- [ ] Footer pricing note visible
- [ ] Buyer integration note visible
