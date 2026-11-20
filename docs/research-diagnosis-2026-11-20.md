# Research-to-analysis diagnosis, 2026-11-20

The operational research engine has not yet produced a certified trading model.
Successful scheduled jobs and accumulating parameter trials are not evidence
that the requested multi-perspective AI analyzer has been delivered.

## Observed production evidence

Main commit: `421ae1ecbf015d8c09557d7300ffaf47748a4f78`.
Daily workflow: `44669318065`, finished 2026-11-20 11:56 Asia/Taipei.

| Observation | Result |
| --- | --- |
| Completed stocks | 20/20 |
| New trials this run | 1,280 |
| Cumulative unique trials | 120,216 |
| Lifecycle integrity checks | 17 passed, 0 failed |
| Eligible for Final Holdout | 0 |
| Certified models | 0 |
| Current-round stocks failing CSCV/PBO | 19/20 |
| Current-round stocks failing bull/bear robustness | 11/20 |
| Current-round stocks failing deflated Sharpe | 11/20 |

Sources are `research-data/daily/latest.json`,
`research-data/daily/diagnostics/gate-bottlenecks.json`, and
`research-data/daily/diagnostics/research-system-audit.json`.

## Why waiting has not solved the problem

1. Search explores predefined technical strategy families, score thresholds,
   holding periods, and exposure parameters. It is not training a new general
   stock-prediction model each day. A larger trial count can increase the
   multiple-testing burden without increasing independent evidence.
2. The quarterly campaign freezes its data split to protect Final Holdout.
   For 2026-Q4 the requested history is 2020-01-01 through 2026-09-30;
   Train ends 2024-01-18 and Validation ends 2025-05-25. Daily scheduling
   changes candidates, not these validation observations. Calendar time alone
   therefore does not add fresh validation trades within the campaign.
3. The retained strongest candidate has six completed validation trades and
   still fails bull/bear robustness. Its source return is insufficient evidence
   for a new asset, a different market regime, or a certified production model.
4. The interactive analyzer previously called only Score Engine V2 and its
   generic recommendation rules. It did not load or execute the strongest
   archived research candidate at all. This was a missing product connection,
   separate from statistical certification.

These findings do not justify lowering the promotion thresholds. They identify
limits of the current search design and a concrete delivery gap. Any future
learned-model family or revised research window needs a new, declared research
specification and independent evidence; it must not retroactively relabel an
old candidate as certified.

## Concrete correction

Stock analysis now separately runs the strongest archived candidate's immutable
parameters against the target's latest completed daily candle. Entry predicates
are shared with the historical backtest. This daily research strategy does not
inherit the generic analyzer's extra hourly gate. The UI shows which version
ran, its rule, its source asset's evidence, its failed gates, and the target's
actual signal. A transfer never copies source validation returns into target
validation. Missing or stale input produces an unavailable result.

This inference path never opens Final Holdout, changes a promotion gate, or
feeds validation or inference results back into Train memory.

## Actual 0050 inference

Version: `d40c9014f3e6f4c4416b93c4`, candidate `mut-ba8c6822880a`,
archived from 2882 in 2026-Q3. Its fixed rules use entry score 71,
exit score 2, and a maximum holding period of 20 trading sessions.

Running the unchanged parameters on the official 2026-11-20 0050 close of
NT$84.45 produces score 29 and `NO_ENTRY`. This is an executed rule inference,
not an independent 0050 performance validation or a prediction that price must
fall. The original +55.55% return remains labelled as 2882 validation evidence.

A separate retrospective transfer observation used the unchanged version from
2026-10-01 (after the current campaign's locked period) through 2026-11-20.
The existing execution engine was supplied with the official downloaded frame
and prevented from entering before the observation start; no parameter was
optimized on this window. It completed one trade, buying at 113.00 on October
14 and exiting at 102.85 on November 13 under the fixed holding-period rule.
After the engine's commissions and ETF transaction tax, the strategy returned
-9.33%, versus -25.02% for buying and holding over the observation window.
Maximum strategy drawdown was 18.26%. This short, retrospective, one-trade
observation is not independent certification and is not fed back into Train.
It shows why the source asset's positive return must not be presented as a
0050 result.
