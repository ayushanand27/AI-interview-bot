import type { AnswerJudgment } from "./interview";
import type { FinalScore } from "./interview";
import type { IntegrityViolation } from "./proctor";

export interface RecruiterReviewState {
  human_review_required: boolean;
  review_status: string;
  review_notes: string | null;
  reviewed_at: string | null;
  reviewed_by_user_id: number | null;
}

export interface RecruiterIdentityVerificationMetadata {
  verified?: boolean | null;
  confidence_score?: number | null;
  low_identity_confidence: boolean;
  similarity_score?: number | null;
  liveness_mode?: string | null;
  liveness_confidence?: number | null;
  ocr_name?: string | null;
  ocr_document_number?: string | null;
  ocr_confidence?: number | null;
  ocr_name_match?: boolean | null;
  message?: string | null;
  warnings: string[];
  evidence_metadata?: Record<string, unknown> | null;
  created_at?: string | null;
}

export interface RecruiterProctorEvent extends IntegrityViolation {
  evidence_metadata?: Record<string, unknown> | null;
}

export interface RecruiterSessionSummary {
  session_id: string;
  candidate_name: string;
  role_title: string;
  date: string;
  final_score: number | null;
  recommendation: string | null;
  status: string;
  recording_available: boolean;
  human_review_flag?: boolean;
  review_status: string;
  review_notes?: string | null;
  reviewed_at?: string | null;
  integrity_level?: string | null;
  integrity_event_count: number;
  low_identity_confidence: boolean;
  invite_token?: string | null;
}

export interface RecruiterSessionFilters {
  role_title?: string;
  date_from?: string;
  date_to?: string;
  invite_token?: string;
  score_band?: string;
  integrity_level?: string;
  review_status?: string;
}

export interface InviteFunnelMetrics {
  created: number;
  opened: number;
  registered: number;
  verified: number;
  started: number;
  completed: number;
}

export interface AssessmentPerformanceMetric {
  token: string;
  role_preview: string;
  difficulty: string;
  question_count: number;
  used_count: number;
  started_count: number;
  completed_count: number;
  average_score: number | null;
  integrity_flag_count: number;
  created_at: string;
}

export interface RecruiterAnalyticsResponse {
  generated_at: string;
  invite_count: number;
  completed_session_count: number;
  completion_rate_percent: number;
  average_score: number | null;
  integrity_flag_rate_percent: number;
  review_flagged_count: number;
  funnel: InviteFunnelMetrics;
  score_distribution: Record<string, number>;
  integrity_distribution: Record<string, number>;
  assessments: AssessmentPerformanceMetric[];
}

export interface TranscriptItem {
  index: number;
  question: string;
  answer: string | null;
  judgment: AnswerJudgment | null;
  is_adaptive_follow_up?: boolean;
  adaptive_topic?: string | null;
  adaptive_source?: string | null;
}

export interface AdaptiveInterviewSummary {
  enabled?: boolean;
  prompt_version?: string;
  target_difficulty?: string;
  current_difficulty?: string;
  topics?: string[];
  must_hit_competencies?: string[];
  coverage?: Record<string, number>;
  competency_hits?: Record<string, number>;
  adaptation_count?: number;
  adaptations?: Array<Record<string, unknown>>;
}

export interface RecruiterSessionDetail {
  session_id: string;
  candidate_name: string;
  role_title: string;
  experience_level: string;
  status: string;
  date: string;
  created_at: string;
  duration_minutes: number | null;
  total_questions: number;
  answered_count: number;
  final_score: FinalScore | null;
  original_score: number | null;
  adjusted_score: number | null;
  integrity_penalty_percent: number;
  integrity_level: string | null;
  integrity_event_count: number;
  proctoring_summary: {
    total_violations?: number;
    violations?: IntegrityViolation[];
    score_penalty_percent?: number;
    integrity_level?: string;
  } | null;
  low_identity_confidence?: boolean;
  identity_similarity_score?: number | null;
  human_review_flag?: boolean;
  review_state: RecruiterReviewState;
  identity_verification?: RecruiterIdentityVerificationMetadata | null;
  proctor_events: RecruiterProctorEvent[];
  recording_available: boolean;
  recording_filename: string | null;
  transcript: TranscriptItem[];
  adaptive_interview?: AdaptiveInterviewSummary | null;
}
