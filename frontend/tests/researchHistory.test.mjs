import assert from "node:assert/strict";
import test from "node:test";
import { getHistoricalStrongest } from "../lib/researchHistory.ts";

const candidate = {
  stock_code: "2882", candidate_id: "old", robot_version_id: "old-version",
  confirmation_gate_pass_count: 5, confirmation_gate_total: 6,
};
const archive = {
  scope: "ALL_TIME", campaign_id: "2026-Q3", candidate,
  source_snapshot_as_of_date: "2026-09-30",
  selection: { observation_only: true, grants_current_promotion_eligibility: false },
};

test("quarter rollover and replacement of latest.json keep historical 5/6 visible", () => {
  const snapshot = {
    campaign_id: "2026-Q4",
    round_top_candidate: { ...candidate, robot_version_id: "new-version", confirmation_gate_pass_count: 3 },
  };
  const result = getHistoricalStrongest(archive, snapshot);
  assert.equal(result.archive.candidate.confirmation_gate_pass_count, 5);
  assert.equal(result.archive.campaign_id, "2026-Q3");
  assert.equal(result.currentEvidence, null);
});

test("current evidence belongs to exact robot version and campaign", () => {
  assert.equal(getHistoricalStrongest(archive, {
    campaign_id: "2026-Q4", candidates: [candidate],
  }).currentEvidence, null);
  assert.equal(getHistoricalStrongest(archive, {
    campaign_id: "2026-Q3", candidates: [{ ...candidate, robot_version_id: "different" }],
  }).currentEvidence, null);
  const current = { ...candidate, confirmation_gate_pass_count: 2 };
  const result = getHistoricalStrongest(archive, { campaign_id: "2026-Q3", candidates: [current] });
  assert.equal(result.currentEvidence.confirmation_gate_pass_count, 2);
  assert.equal(result.archive.candidate.confirmation_gate_pass_count, 5);
});

test("retained incumbent does not count as a fresh revalidation", () => {
  const result = getHistoricalStrongest(archive, { campaign_id: "2026-Q3", incumbent_candidate: candidate });
  assert.equal(result.currentEvidence, null);
});

test("embedded archive survives temporary failure to read durable file", () => {
  assert.equal(getHistoricalStrongest(null, { all_time_incumbent: archive }).archive, archive);
  assert.equal(getHistoricalStrongest(archive, null).archive, archive);
});

test("ordinary incumbents and malformed archives are not mislabeled all-time records", () => {
  assert.equal(getHistoricalStrongest({ campaign_id: "2026-Q3", candidate }, null), null);
  assert.equal(getHistoricalStrongest({ ...archive, selection: { observation_only: true } }, null), null);
});
