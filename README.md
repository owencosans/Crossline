# CarMax Inventory Flow Strategist

A Streamlit demo for a CarMax-style supply chain strategy use case. The app evaluates used-vehicle inventory cohorts and recommends whether to hold for retail, transfer to a stronger market, expedite reconditioning, or liquidate to wholesale. Its core analytical view — the **Crossover Clock** — shows when expected retail economics deteriorate below the wholesale floor, and adds an **Acquisition Confidence** signal to connect downstream routing decisions back to upstream buying discipline.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

## What it shows

**Portfolio Overview** — 60 synthetic inventory cohorts with at-risk counts, recon-trapped counts, and breakdowns by retailability state and value gap.

**Cohort Drilldown** — descriptor, timing, and economic summary for any selected cohort.

**Crossover Clock** — expected value curves for all four routing paths, a wholesale floor line, and a vertical marker at the crossover day.

**Routing Recommendation** — one of four actions with expected value, exit speed, and tradeoff notes for each.

**Acquisition Confidence** — a 0–100 score with label (High / Medium / Low) answering whether this cohort type should be bought again at a similar price.

## Controls

| Control | What it does |
|---|---|
| Strategy Mode | Margin Max / Balanced / Turn Max — shifts patience, carry penalty, and wholesale threshold |
| Hold Horizon | Days to evaluate (7–45) |
| Markdown | Optional retail price discount inside the hold path |
| Wholesale Market Shock | ±% shift on wholesale floor prices |
| Retail Demand Strength | Weak / Base / Strong — multiplies expected retail value |
| Recon Capacity Pressure | Low / Medium / High — affects expedite cost and days saved |

## Files

```
app.py              Streamlit app
data_generator.py   Synthetic cohort data generation
logic.py            Expected-value engine, crossover, recommendation, confidence scoring
requirements.txt
README.md
```

## Demo narrative

1. "This portfolio view shows where inventory value is most at risk from aging and weak downstream economics."
2. "Let's drill into a cohort that looks vulnerable — high days since acquisition, recon-heavy state."
3. "Here's the Crossover Clock. The retail value path is decaying toward the wholesale floor."
4. "Under Margin Max we can still hold. Under Turn Max we should exit sooner — the recommendation flips."
5. "The app also computes Acquisition Confidence, which tells us whether this is a profile we should keep buying."

---

*All data is synthetic. This is a strategy demo, not a production revenue-management system.*
