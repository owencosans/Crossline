# CROSSLINE — Final Patch (Pre-Ship)

## 1. FIX: Raw HTML/Markdown Leaking in Skip Cards

### Problem
The skip panel is rendering raw markup as literal text instead of formatted output. Visible on screen:

- `**Ask:**` showing as literal asterisks instead of bold
- `<span style='color:red'>` and `</span>` showing as literal text
- `**Margin at ask:** <span style='color:red'>` fully visible as a string

### Cause
The skip card text is being built with markdown/HTML syntax but rendered in a Streamlit element that doesn't interpret it. Likely using `st.text()` or plain string interpolation where it should use `st.markdown()`.

### Fix
Ensure all skip card content uses `st.markdown()` with `unsafe_allow_html=True` for any inline HTML styling (like red text for negative values).

Or better — drop the inline HTML entirely and use Streamlit-native formatting:
```python
# Instead of building HTML strings like:
# f"**Margin at ask:** <span style='color:red'>{margin}</span>"

# Use st.markdown with simpler formatting:
st.markdown(f"**Margin at ask:** :red[{margin}]")

# Or use st.metric for the numbers:
st.metric(label="Margin at ask", value=f"${margin:,.0f}", delta=None)
```

Check every text element in the skip card template and make sure it's rendered through `st.markdown()`, not `st.text()` or `st.write()` with raw HTML.

---

## 2. FIX: "No Viable Bid" Text Runs Together

### Problem
The Cruze card shows:
```
No viable bid
Est. retail: 4,914—toolowtocoverrecon(2,500) and carry ($630) with margin
```

Should read:
```
No viable bid
Est. retail: $4,914 — too low to cover recon ($2,500) and carry ($630) with margin.
```

### Cause
String concatenation is missing spaces around the em dash and the words "too low to cover recon" are concatenated without spaces. Likely an f-string with no whitespace between variables.

### Fix
Find the string template that generates this line. It probably looks something like:
```python
f"Est. retail: {retail}—toolowtocoverrecon({recon}) and carry (${carry}) with margin"
```

Replace with:
```python
f"Est. retail: ${retail:,.0f} — too low to cover recon (${recon:,.0f}) and carry (${carry:,.0f}) with margin."
```

Also ensure the dollar sign and comma formatting are applied to all currency values.

---

## 3. FIX: Current Lot Tab Accessible Before Scoring

### Problem
The "Current Lot" tab is empty or inaccessible until the user clicks "Score Auction." But the lot state data exists independently of the auction scoring — it's the baseline portfolio that doesn't depend on auction input.

### Cause
The Current Lot tab content is probably inside a conditional block like:
```python
if st.session_state.get("scored"):
    # render current lot tab
```

### Fix
The Current Lot tab should render unconditionally. It shows the existing portfolio state which is always available:
- Segment breakdown with unit counts vs. targets
- Recon queue status
- Market conditions / wholesale index deltas

Move the Current Lot tab content outside any scoring-dependent conditional. It should be visible and populated from the moment the app loads.

The only thing that should be gated behind "Score Auction" is the bid/skip results in the Auction Drop tab.

```python
tab_auction, tab_lot, tab_export = st.tabs(["Auction Drop", "Current Lot", "Export"])

with tab_lot:
    # This renders ALWAYS, no conditional
    render_lot_state(lot_state)

with tab_auction:
    # Input section always visible
    render_manifest_input()
    
    if st.session_state.get("scored"):
        # Bid/skip results only after scoring
        render_bid_skip_results()

with tab_export:
    if st.session_state.get("scored"):
        render_export()
```

---

## Testing After Patch

- [ ] Skip cards show bold text and colored numbers properly (no raw `**` or `<span>` tags visible)
- [ ] Cruze "No viable bid" text reads as clean English with proper spacing
- [ ] All currency values in skip cards show `$` prefix and comma formatting
- [ ] Current Lot tab shows segment data immediately on app load (before scoring)
- [ ] Scoring still works correctly after viewing Current Lot first
