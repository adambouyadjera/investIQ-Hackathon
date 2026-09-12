# Risk layer

Steps 3–7 of the AI trading desk guide, implemented and tested. This is the
part the guide says to build before any strategy code, and it is the part that
is pure math with no broker dependency.

```bash
python test_trading.py     # 40 tests
python run_risk_demo.py    # 10 worked scenarios
```

## What's here

| Module | Owns |
|---|---|
| `trading/types.py` | `OrderIntent`, `AccountState`, `CheckResult`, `RiskDecision` |
| `trading/policy.py` | The thresholds, as constants. Breaker evaluation, block file |
| `trading/sizing.py` | Quantity from planned loss, then every cap |
| `trading/protection.py` | Stop/target geometry, the no-widening rule, partial exits |
| `trading/checks.py` | The ordered pre-trade gate |

## The design decision everything rests on

`OrderIntent` has no quantity field.

A strategy proposes a symbol, a direction, an entry, a stop, two targets and
an invalidation. Size is computed by the risk service from the stop distance
and current equity. A strategy that could name its own size could bypass every
limit below it, so the type system simply doesn't let it express one.

`test_trading.py::no_broker_imports_anywhere` scans every module in the package
for broker and network imports and fails if one appears. The isolation is a
test, not a comment.

## The cascade

| Trigger | Action |
|---|---|
| Every trade | Risk at most 1% of current equity |
| Down 2% in a day | Half size |
| Down more than 3% in a day | Flatten, no new entries |
| Down 5% in a week | Half size |
| Down 6% in a week | No new entries |
| Down 10% in a month | No new entries |
| Down 10% from peak | Full stop, write `state/TRADING_BLOCKED` |
| Two or more active | Strictest wins |
| Missing or stale state | Veto |

Note the asymmetry at the daily level: 2% is "at or below", 3% is "strictly
below". Exactly -3.00% halves size; -3.01% flattens. Two tests pin that
boundary, because a cascade that fires a tenth of a percent early or late is
a bug you discover with real money.

`policy.write_block()` has no counterpart. There is no `clear_block()` anywhere
in the package. Removing it is a manual `rm` after a written review — which is
the entire point.

## Sizing

    quantity = floor((equity × 1%) / |entry − stop|)

Then, in order: breaker multiplier, buying power, 50% concentration ceiling,
total open-risk budget, round down, recompute planned loss including costs,
re-check the 1% ceiling. Smallest survivor wins.

Worked example from the guide, which `test_trading.py` asserts exactly:
$2,000 equity, $50 entry, $49 stop → $20 budget → 20 shares → $1,000 position,
which sits exactly at the 50% concentration ceiling. Under a half-size breaker
the same setup returns 9 shares, because the budget is recomputed from the
reduced equity first.

## What is deliberately absent

No broker client. No live credentials. No order submission. No agent roles, no
HMM, no strategies. Those are later steps, and none of them can be built safely
on top of a risk service that hasn't been tested first.

If this ever grows an execution layer, it connects to Alpaca **paper** only,
and the guide's two-week paper requirement applies before anything else is
considered.

---

Educational simulation. Not financial advice. You can lose money.
