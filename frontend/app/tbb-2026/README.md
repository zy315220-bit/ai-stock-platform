# TBB 2026 — Wealth Research Copilot

## Product thesis

The competition prototype is not a generic AI stock picker.

It targets a current Taiwan Business Bank opportunity: high-net-worth / business-owner
wealth management requires more integrated, personalized and auditable research support.

The product is a **research copilot for relationship managers**, not an execution agent.

## User flow

1. Collect only minimal non-PII risk-boundary inputs.
2. Convert them into research constraints.
3. Allow the Research Lab to search only inside those constraints.
4. Require out-of-sample / anti-overfitting evidence.
5. Fail closed if evidence is incomplete or inconsistent.
6. Require human review before any customer-facing summary.
7. Preserve run IDs, dataset fingerprints, lineage and rejection reasons.

## Safety invariants

- No automated order execution.
- No payment or fund-transfer authority.
- No interactive Final Holdout access.
- Unknown suitability fields are rejected.
- The competition POST proxy accepts same-origin JSON only and caps request size.
- Customer-facing recommendations are blocked unless research gates pass.
- Secrets must not be committed to the repository.
- The original production site remains untouched; this work lives on
  `competition/tbb-2026-smart-wealth`.

## Visual direction

Avoid generic AI landing-page conventions such as heavy gradients, glass cards,
oversized icon grids and decorative chatbot imagery.

Use a restrained FinTech / bank-product hierarchy:

- one problem and one answer above the fold;
- a live control panel instead of feature-card clutter;
- a workflow showing where AI stops and human control begins;
- an interactive prototype in the middle of the page;
- a compact audit table for technical and governance evidence.

## Competition framing

The differentiator is not that AI can generate investment ideas. The differentiator is
that an AI research process can be **constrained, statistically challenged, explainable,
human-reviewed and audit-ready** before it is allowed to influence wealth-management
workflows.
