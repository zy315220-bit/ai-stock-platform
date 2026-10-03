import assert from "node:assert/strict";
import test from "node:test";
import { getResearchHealth } from "../lib/researchHealth.ts";

const now = Date.parse("2026-10-03T11:30:00Z");
const snapshot = {
  generated_at_utc: "2026-10-03T11:00:00Z", integrity_status: "PASS",
  completed_symbol_count: 20, universe_size: 20,
};
const audit = { generated_at_utc: "2026-10-03T11:01:00Z", system_ready: true };
const success = { status: "completed", conclusion: "success" };

test("fresh complete results with the matching audit are operational", () => {
  assert.equal(getResearchHealth(snapshot, success, audit, now).state, "OPERATIONAL");
});
test("a failed latest run overrides a previously passing audit", () => {
  assert.equal(getResearchHealth(snapshot, { status: "completed", conclusion: "failure" }, audit, now).state, "DEGRADED");
});
test("old successful results cannot hide a stalled scheduler", () => {
  const old = { ...snapshot, generated_at_utc: "2026-09-30T01:41:00Z" };
  const result = getResearchHealth(old, success, audit, now);
  assert.equal(result.state, "DEGRADED");
  assert.equal(result.snapshot_fresh, false);
});
test("a new snapshot cannot reuse the preceding round's audit", () => {
  assert.equal(getResearchHealth(snapshot, success, { ...audit, generated_at_utc: "2026-10-02T11:01:00Z" }, now).state, "DEGRADED");
});
test("partial, malformed, and unavailable data stay unconfirmed", () => {
  assert.equal(getResearchHealth({ ...snapshot, completed_symbol_count: 19 }, success, audit, now).state, "DEGRADED");
  assert.equal(getResearchHealth({ ...snapshot, generated_at_utc: "bad-date" }, success, audit, now).state, "DEGRADED");
  assert.equal(getResearchHealth(snapshot, null, audit, now).state, "DEGRADED");
});
test("an active recovery run explicitly marks its old result as stale", () => {
  const result = getResearchHealth({ ...snapshot, generated_at_utc: "2026-09-30T01:41:00Z" }, { status: "in_progress" }, audit, now);
  assert.equal(result.state, "RUNNING");
  assert.equal(result.snapshot_fresh, false);
});
