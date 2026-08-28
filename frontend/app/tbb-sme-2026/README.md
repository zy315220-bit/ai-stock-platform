# SME Liquidity Radar — TBB 2026 technical evidence

## Problem

The competition prototype answers one operational question for SME relationship managers:

> Which enterprise may face liquidity pressure in the next 30 / 60 / 90 days, why, and what should the RM verify next?

It is **not** a credit score, loan approval engine, default probability model, or automated product-sales system.

## Public demo vs. bank pilot

The public demo cannot access confidential enterprise books. It therefore separates data into two classes:

1. **Official public facts** — company registration, capital, business items, market/public-company identity.
2. **Private cash-flow fields** — current cash, payroll, receivables/payables, etc. Public-demo values are only scenario priors and are visibly labelled as estimates.

A bank pilot should replace scenario priors with consented / bank-held transaction data, scheduled payments, payroll, lending cash flows, and optional ERP/e-invoice feeds.

## Official sources

- MOEA GCIS open data: https://data.gcis.nat.gov.tw/od/
- Taiwan SME identification standard: https://law.moea.gov.tw/LawContent.aspx?id=FL011859
- TWSE listed/public-company OpenAPI: https://openapi.twse.com.tw/
- TPEx OpenAPI: https://www.tpex.org.tw/openapi/
- MOF industry classification / profit standards (reference only; **not treated as company actuals**): https://service.mof.gov.tw/public/Data/statistic/std/zhtw/index.html

The current SME gate recognises the statutory capital criterion of NTD 100 million or less, while explicitly noting the alternative criterion of fewer than 200 regular employees. Paid-in capital and registered capital are kept separate; a zero value is treated as missing, and registered capital is labelled only as a proxy when paid-in capital is unavailable. If the applicable amount exceeds NTD 100 million and employee count is unavailable, the quick mode does not assert non-SME status; it refuses the quick baseline until more evidence is available.

## Authoritative calculation engine

All production demo forecasts are routed to one Python engine:

- engine: `sme-liquidity-monte-carlo-v2.1`
- horizons: 30 / 60 / 90 days
- default simulation count: 2,500 paths
- deterministic seed for reproducibility
- SHA-256 input fingerprint
- non-negative mean/std-calibrated lognormal recurring inflow
- explicit receivable and payable timing
- Day-0 safety-floor breach check
- P10 / P50 / P90 ending cash
- P10 minimum-cash buffer against safety floor
- Wilson 95% interval for breach probability
- stress cases: customer delay, revenue decline, TWD appreciation, combined stress
- common random numbers for scenario comparison
- counterfactual adjustments use the same seed and displayed combined-stress baseline; they are only surfaced when they improve breach probability or 90-day P50 cash

The Next.js API validates and maps inputs but does **not** implement a second Monte Carlo engine.

## Why 0 / 2,500 is not shown as “zero risk”

An observed breach count of zero only means no breach occurred in this finite simulation sample. The UI shows “not observed in this run” and a Wilson 95% upper bound rather than claiming certain zero risk.

Reference: Edwin B. Wilson (1927), *Probable Inference, the Law of Succession, and Statistical Inference*, JASA.

## Scenario-comparison variance control

Base and stress scenarios use common random numbers. This reduces comparison noise: when a scenario changes only one assumption, the reported difference is less contaminated by a different random draw.

Reference background: standard common-random-number / variance-reduction practice in Monte Carlo simulation (e.g. Glasserman, *Monte Carlo Methods in Financial Engineering*).

## AI RM evidence router and upgrade gate

The opt-in RM brief uses Vercel AI Gateway with Gemini and structured output. It receives only de-identified derived indicators: the authoritative contact priority, risk status, probabilities, buffer ratio, stress/driver enums, adjustment code and engine fingerprint. Company name, business number and raw financial amounts are excluded. The model can rank only allowlisted evidence and RM-question IDs; it must echo the server priority, which is enforced again after generation. Server code renders the numerical statements from authoritative engine values. If the Gateway is unavailable, the response is explicitly labelled deterministic fallback rather than AI output.

Before the optional AI layer, the Python engine now emits an authoritative `sme-rm-handoff-v1` contract. It contains a deterministic contact window, the evidence that an RM must verify, completion rules, re-run triggers and explicit decision boundaries. The frontend no longer invents this workflow with static copy. Every work card is bound to the same input fingerprint as the forecast, and the browser-generated audit export carries only de-identified handoff codes, evidence IDs and governance flags.

The handoff does not write to CRM, contact a customer, score credit, approve a loan, suggest an amount or sell a product. It prepares a human-review work card only. A bank pilot can map the stable action/evidence codes to existing CRM tasks after access control, retention, maker-checker and audit-log requirements are agreed.

The numerical baseline remains intentionally simpler and auditable. Candidate sequence models such as:

- DeepAR
- Temporal Fusion Transformer (TFT)
- Chronos

must beat the baseline in rolling out-of-sample validation before promotion. A newer model name is not sufficient evidence to replace the baseline.

## Model boundaries

Quick public mode is **scenario screening**, not calibrated company forecasting.

Known simplifications are disclosed in the site:

- private company financial values may be scenario priors;
- monthly values are mapped to calendar-day approximations;
- no full holiday/seasonality calendar in the current baseline;
- public-market companies are not forced through the SME prior;
- the public prototype does not infer hidden customer default probability when no evidence is supplied;
- exposure ranking is not SHAP or causal attribution;
- output is not a credit decision.

## Privacy and governance

- user-entered profile is not persisted by the prototype;
- private forecast responses are `no-store`;
- AI brief requires separate explicit consent and excludes identity / raw financial amounts;
- AI Gateway requests disallow prompt training; the public demo does not claim enterprise Zero Data Retention;
- AI brief uses JSON-only allowlists, a body-size cap, timeout and best-effort rate limit;
- unused responsible-person names are not returned to the frontend;
- no automated loan approval;
- no automated financial-product sale;
- human review required;
- internal smoke / extreme-case endpoints return 404 in production;
- request size limits and strict JSON validation are applied to the forecast proxy.

## Regression coverage

Python tests cover, among other cases:

- deterministic reproduction;
- quantile ordering;
- Wilson interval ordering;
- zero observed breaches;
- Day-0 breach;
- zero revenue with continuing costs;
- huge near-term payable;
- receivable outside 90-day horizon;
- FX stress;
- combined stress;
- adjustment recommendation guards;
- governance flags;
- input fingerprint stability;
- common-random-number parity when FX exposure is zero.

CI runs:

- Python tests
- npm production dependency audit
- ESLint
- TypeScript typecheck
- Next.js build

The frontend was upgraded to patched Next.js 16.3.3; the refreshed lockfile produced 0 npm vulnerabilities at the security-upgrade checkpoint.

## Fail-closed design

When official data is incomplete, company applicability is unresolved, the authoritative backend is unavailable, or the company is outside the quick-mode boundary, the system does not manufacture a confident percentage. It either requests better data, shows a caution state, or blocks the quick calculation.

## Branch isolation

This competition implementation lives on:

`competition/tbb-2026-sme-liquidity`

It should not be merged into the original production stock-platform branch without a separate review.
