export type FileState = "parsing" | "ready" | "scan" | "error";
export type ItemState = "pending" | "running" | "success" | "failed" | "cancelled";

export interface ParsedResume {
  id: string;
  fileName: string;
  relativePath: string;
  size: number;
  pages: number;
  chars: number;
  text: string;
  state: FileState;
  error?: string;
}

export interface DimensionScores {
  skill_match: number;
  experience_relevance: number;
  project_relevance: number;
  overall_quality: number;
}

export interface Evidence {
  skill_match: string[];
  experience_relevance: string[];
  project_relevance: string[];
  overall_quality: string[];
}

export interface EvaluationResult {
  candidate_name: string;
  match_score: number;
  dimension_scores: DimensionScores;
  recommendation: "interview" | "manual_review" | "supplement" | "reject";
  matched_skills: string[];
  missing_information: string[];
  risk_flags: string[];
  evidence: Evidence;
  recommended_interview_questions: string[];
  human_review_note: string;
}

export interface BatchItem {
  item_id: string;
  client_id: string;
  file_name: string;
  status: ItemState;
  result: EvaluationResult | null;
  error: string | null;
  attempts: number;
}

export interface BatchTask {
  task_id: string;
  status: "pending" | "running" | "completed" | "cancelled";
  items: BatchItem[];
  created_at: string;
  updated_at: string;
  cancelled: boolean;
  summary: Record<ItemState, number>;
  quota?: QuotaStatus;
}

export interface QuotaStatus {
  date: string;
  per_ip_limit: number;
  per_ip_used: number;
  per_ip_remaining: number;
  global_limit: number;
  global_used: number;
  global_remaining: number;
}

export interface SessionStatus {
  authenticated: boolean;
  auth_required: boolean;
  auth_methods: {
    feishu: boolean;
    access_code: boolean;
  };
  auth_provider: "feishu" | "access_code" | null;
  display_name: string | null;
  expires_at: number;
  quota: QuotaStatus;
}
