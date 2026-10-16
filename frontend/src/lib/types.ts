export type SeverityLevel = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "SUGGESTION";
export type RiskRating = "CRITICAL" | "HIGH" | "MODERATE" | "LOW" | "CLEAN";
export type AgentSource =
  | "bug_detector"
  | "security_scanner"
  | "logic_auditor"
  | "style_checker"
  | "synthesizer";

export interface PRReviewRequest {
  repo_owner: string;
  repo_name: string;
  pr_number: number;
  branch?: string;
}

export interface AgentFinding {
  severity: SeverityLevel;
  file: string;
  line_start: number;
  line_end: number;
  message: string;
  agent_source: AgentSource;
}

export interface SeverityStats {
  critical: number;
  high: number;
  medium: number;
  low: number;
  suggestion: number;
}

export interface PRReviewResponse {
  id?: string;
  repo: string;
  pr_number: number;
  summary: string;
  risk_rating: RiskRating;
  findings: AgentFinding[];
  stats: SeverityStats;
  reviewed_at: string;
}

export interface BenchmarkFinding {
  file: string;
  line_start?: number;
  severity: SeverityLevel | string;
  message: string;
}

export interface HumanComment {
  body?: string;
  file?: string;
  line?: number;
  reviewer?: string;
  created_at?: string;
}

export interface BenchmarkResult {
  pr_number: number;
  precision: number;
  recall: number;
  f1_score: number;
  severity_weighted_score: number;
  human_findings_count: number;
  prism_findings_count: number;
  prism_findings?: BenchmarkFinding[];
  human_comments?: HumanComment[];
}

export interface BenchmarkSummary {
  total_prs: number;
  avg_precision: number;
  avg_recall: number;
  avg_f1: number;
  avg_severity_weighted: number;
  results: BenchmarkResult[];
  run_at: string;
}

export type ReviewEvent =
  | { event: "status"; data: string }
  | { event: "finding"; data: AgentFinding }
  | { event: "agent_done"; data: { agent: string; count: number } }
  | { event: "complete"; data: PRReviewResponse }
  | { event: "saved"; data: { id: string } }
  | { event: "error"; data: { message: string } };
