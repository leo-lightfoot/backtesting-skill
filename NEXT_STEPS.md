# Next Steps

Living tracker for planned improvements. Update status as work progresses.

**Status legend:** `[ ]` not started · `[~]` in progress · `[x]` done

---

## 1. New Strategies

Each strategy needs: `scripts/strategies/<name>.py`, entry in `__init__.py` registry, entry in `api/templates.py`, entry in `references/schema.md`, a reference example schema, and tests.

### 1a. Baseline / Simple Strategies

These are deliberately minimal. They serve as benchmarks to compare against more complex strategies, and as easy entry points for new users.

| # | Strategy | Type | Multi-symbol | Notes |
|---|----------|------|-------------|-------|
| 1.1 | **Buy and Hold** | Baseline | Yes | Buy at start, hold until end. Equal-weight across all symbols. Zero parameters beyond position sizing. The essential baseline every backtest should be compared against. |
| 1.2 | **Periodic Equal-Weight Rebalance** | Baseline | Yes | Hold all symbols in equal weight, rebalance on a schedule (daily/weekly/monthly). Slightly more complex than pure buy-and-hold — shows the cost/benefit of rebalancing. |
| 1.3 | **SMA Trend Filter (Buy and Hold variant)** | Trend filter | Yes | Hold when price > SMA(N), move to cash otherwise. One-parameter extension of buy-and-hold. Good bridge between baseline and full strategies. |

### 1b. Intermediate Strategies

| # | Strategy | Type | Multi-symbol | Notes |
|---|----------|------|-------------|-------|
| 1.4 | **Bollinger Band Mean Reversion** | Mean reversion | No | Enter below lower band, exit at midline. Different flavour from RSI — uses price extremes not momentum. |
| 1.5 | **MACD Signal Crossover** | Trend following | Yes | Enter on MACD line crossing signal line, exit on reverse. Momentum-adjusted vs plain SMA cross. |
| 1.6 | **Dual Momentum / Relative Strength** | Momentum | Yes | Rank symbols by trailing N-month return, hold top K. Classic Antonacci-style. Portfolio-native. |
| 1.7 | **Donchian Channel Breakout** | Breakout | Yes | Enter on N-day high break, exit on M-day low break. Pure trend-following, complements dip-buy. |

**For each new strategy, the checklist is:**
- [ ] `scripts/strategies/<name>.py` — strategy source with `TEMPLATE_NAME`, `HAS_PORTFOLIO_CONTROLS`, `PARAMS_SCHEMA`, `get_defaults()`, `get_source()`
- [ ] `scripts/strategies/__init__.py` — add to `REGISTRY`
- [ ] `api/templates.py` — add template metadata (params with type/min/max/label for UI)
- [ ] `references/schema.md` — add to supported templates + strategy block params
- [ ] `references/example_<name>_schema.json` — working example
- [ ] `tests/test_runner.py` — add algorithm source compilation test + param defaults test
- [ ] `SKILL.md` — add to template mapping rules

---

## 2. Frontend UX / UI

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 2.1 | **Benchmark warning in form** | High | Show inline warning when benchmark field value is not in the symbols list |
| 2.2 | **Real-time job status bar** | High | Show elapsed time + current status (queued/running) during execution. Currently just "Running…" with no feedback. |
| 2.3 | **Inline error display** | High | Show the actual error message from `detail` field when status=error. Currently no error detail shown. |
| 2.4 | **Parameter validation before submit** | Medium | Client-side: warn if `short_ma >= long_ma` for SMA, enforce min/max ranges from template metadata |
| 2.5 | **Export results** | Medium | Button to download the raw JSON result and/or equity curve as CSV |
| 2.6 | **Chart improvements** | Medium | Tooltips on hover, zoom/pan, benchmark overlay line, drawdown subplot |
| 2.7 | **Strategy description tooltip** | Low | Show strategy description text on template hover/select |
| 2.8 | **Mobile-responsive layout** | Low | Two-column collapses to single column on small screens |
| 2.9 | **Run history** | Low | Keep last N results in session storage, allow switching between them |
| 2.10 | **Schema import/export** | Low | Load a JSON schema file into the form; export current form state as JSON |

---

## 3. AI Natural Language Input (Bring Your Own Key)

Allow users to describe a backtest in plain English and have it auto-fill the form. Always visible in the UI — users just need to supply their own Anthropic API key to activate it.

**UX design:**
```
┌─────────────────────────────────────────────────────────────┐
│  ✦ Try AI-assisted setup                                     │
│  Anthropic API key  [sk-ant-...............] [Save]          │
│  Describe your backtest:                                     │
│  [backtest NVDA with RSI 14, oversold 30, from 2018    ]    │
│  [Fill Form with AI →]                                       │
│                                                              │
│  ← form fields auto-populate from AI response               │
│  User reviews and clicks Run as normal                       │
└─────────────────────────────────────────────────────────────┘
```

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 3.1 | **`POST /interpret` endpoint** | High | Accepts `{message, api_key}`. Calls Claude API using the user-supplied key. Returns a valid schema JSON. Never stores the key server-side. |
| 3.2 | **UI panel — always visible** | High | Collapsible "✦ Try AI-assisted setup" section at the top of the form. Shows key input + natural language textarea. Key saved to `localStorage`. Not hidden — framed as a feature to try. |
| 3.3 | **Form auto-fill from response** | High | On success, parsed schema populates all form fields (template, symbols, dates, strategy params). User can edit before running. |
| 3.4 | **Server-side key override** | Low | If `ANTHROPIC_API_KEY` is set as env var, feature works without user entering a key. For self-hosted deployments. |
| 3.5 | **Add `anthropic` to requirements.txt** | High | `anthropic>=0.25.0` |

**Key design decisions:**
- User's API key flows per-request in the request body — never persisted server-side
- `localStorage` stores the key in the browser for convenience across sessions; user can clear it
- Feature is always visible and clearly labelled as "bring your own key" — not hidden or gated
- If no key is entered and no server env var is set, the "Fill Form" button is disabled with a tooltip: *"Enter your Anthropic API key above to use this feature"*
- The AI only fills the form — the user still reviews and clicks Run. Backtest itself costs no tokens.

---

## 5. SKILL.md Improvements

| # | Item | Notes |
|---|------|-------|
| 3.1 | Update template mapping rules as new strategies are added | Do this with each new strategy in §1 |
| 3.2 | Add inline schema snippets per template | Quick copy-paste for agents, avoids having to read the full schema.md |
| 3.3 | Add example output interpretation guide | How to read stability_diagnostics, practical_assessment flags |
| 3.4 | Add common parameter starting points | Sensible defaults per template for different asset classes (large-cap equity, ETFs, etc.) |

---

## 6. Hosting

To let people test the UI without running locally.

| # | Item | Notes |
|---|------|-------|
| 4.1 | **Dockerfile** | Single-stage Python 3.13 image. Copies venv or installs from requirements.txt. Exposes port 8000. |
| 4.2 | **docker-compose.yml** | Convenience wrapper for local Docker testing before cloud deploy |
| 4.3 | **Choose a platform** | See options below |
| 4.4 | **Persistent job store** | In-memory store resets on restart — swap to SQLite-backed store before hosting |
| 4.5 | **Rate limiting** | Add `slowapi` rate limit on `POST /backtest` to prevent abuse on public instance |
| 4.6 | **Optional: basic auth** | Simple password protection for public demo instance |

**Platform options:**

| Platform | Free tier | Persistent disk | Notes |
|----------|-----------|----------------|-------|
| **Render** | Yes (spins down after inactivity) | No (free) / Yes (paid) | Simple `render.yaml` deploy. Good for demos. |
| **Railway** | $5/mo credit | Yes | Faster cold starts than Render. Easy GitHub integration. |
| **Fly.io** | Yes (3 shared VMs) | Yes (volumes) | Best for always-on. More config required. |
| **Hugging Face Spaces** | Yes | No | Good visibility in AI community. Needs Docker Space. |

**Recommended path:** Docker → Railway (fastest path to shareable URL with persistent storage).

---

## 7. Other Suggestions

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 5.1 | **Persistent job store** | High (prerequisite for hosting) | Replace in-memory dict with SQLite-backed store. Jobs survive server restarts. Results browseable. |
| 5.2 | **Multi-benchmark support** | Medium | Allow `"benchmarks": ["SPY", "QQQ"]` and report alpha/beta vs each. Discussed previously. |
| 5.3 | **WebSocket job updates** | Medium | Replace 2s polling with `ws://…/jobs/{id}/stream` for real-time status push |
| 5.4 | **GitHub Actions CI** | Medium | Run `pytest` on every push to `master`. Badge in README. |
| 5.5 | **Result comparison view** | Low | Side-by-side metrics for two runs (e.g. different param sets or strategies) |
| 5.6 | **PDF / HTML report export** | Low | Generate a printable one-page backtest report with chart + metrics table |
| 5.7 | **Schema builder UI** | Low | Visual form that generates the raw JSON schema (for agent or CLI use) |

---

## Suggested Order of Attack

1. **§2.1–2.3** (benchmark warning, status bar, error display) — quick wins, high impact on UX
2. **§1.1–1.2** (Buy and Hold, Periodic Rebalance) — simplest strategies, establish the pattern, immediately useful as baselines
3. **§1.3** (SMA Trend Filter) — one-parameter bridge between baseline and full strategies
4. **§3.1–3.3** (AI natural language input) — visible BYOK feature, adds a compelling demo hook before hosting
5. **§6.1–6.2** (Dockerfile + compose) — unblocks hosting
6. **§7.1** (persistent job store) — prerequisite for a useful hosted demo
7. **§1.4** (Bollinger Band) — first intermediate strategy
8. **§6.3** (deploy to Railway or Render) — get a shareable URL
9. **§1.5–1.7** (MACD, Dual Momentum, Donchian) — expand the template library
10. **§2.4–2.10** (remaining UI polish) — iterative improvement
11. **§7.2–7.7** (longer-horizon features) — based on user feedback after hosting
