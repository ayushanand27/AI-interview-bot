import type { AnswerJudgment } from "./interview";
import type { FinalScore } from "./interview";
import type { IntegrityViolation } from "./proctor";

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
}

export interface TranscriptItem {
  index: number;
  question: string;
  answer: string | null;
  judgment: AnswerJudgment | null;
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
  proctoring_summary: {
    total_violations?: number;
    violations?: IntegrityViolation[];
    score_penalty_percent?: number;
    integrity_level?: string;
  } | null;
  low_identity_confidence?: boolean;
  identity_similarity_score?: number | null;
  human_review_flag?: boolean;
  recording_available: boolean;
  recording_filename: string | null;
  transcript: TranscriptItem[];
}
