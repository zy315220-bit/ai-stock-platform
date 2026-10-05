export type ResearchCandidate = {
  stock_code?: string;
  candidate_id?: string;
  robot_version_id?: string;
  strategy_family?: string;
  decision?: "DISCARD" | "KEEP" | "HOLDOUT_READY";
  research_score?: number;
  confirmation_gate_pass_count?: number;
  confirmation_gate_total?: number;
  eligible_for_one_shot_holdout?: boolean;
  regime_robust?: boolean;
  walk_forward_sample_sufficient?: boolean;
  walk_forward_positive_slice_ratio?: number;
  validation?: {
    wilson_lower_percent?: number;
    total_return_percent?: number;
    alpha_percent?: number;
    max_drawdown_percent?: number;
    deflated_sharpe_probability_percent?: number;
    deflated_sharpe_pass?: boolean;
  };
  model_selection?: {
    cscv_pbo_pass?: boolean;
    hansen_spa_pass?: boolean;
  };
};

export type AllTimeIncumbent = {
  scope: "ALL_TIME";
  campaign_id: string;
  candidate: ResearchCandidate;
  source_snapshot_as_of_date?: string;
  selection: {
    observation_only: true;
    grants_current_promotion_eligibility: false;
  };
};

type HistorySnapshot = {
  campaign_id?: string;
  round_top_candidate?: ResearchCandidate | null;
  candidates?: ResearchCandidate[];
  all_time_incumbent?: AllTimeIncumbent | null;
};

export function candidateIdentity(candidate?: ResearchCandidate | null): string {
  if (!candidate) return "";
  return candidate.robot_version_id || `${candidate.stock_code ?? ""}:${candidate.candidate_id ?? ""}`;
}

export function getHistoricalStrongest(
  durableArchive: AllTimeIncumbent | null | undefined,
  snapshot: HistorySnapshot | null | undefined,
) {
  const archive = durableArchive ?? snapshot?.all_time_incumbent;
  if (
    !archive || archive.scope !== "ALL_TIME" || !archive.campaign_id ||
    !archive.candidate || !archive.candidate.candidate_id ||
    archive.selection?.observation_only !== true ||
    archive.selection.grants_current_promotion_eligibility !== false
  ) return null;

  // A retained incumbent alone does not prove that this round revalidated it.
  const currentEvidence = archive.campaign_id === snapshot?.campaign_id
    ? [snapshot.round_top_candidate, ...(snapshot.candidates ?? [])].find(
      (candidate) => candidate && candidateIdentity(candidate) === candidateIdentity(archive.candidate),
    ) ?? null
    : null;
  return { archive, currentEvidence };
}
