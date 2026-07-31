export type SessionStatus =
  | "created"
  | "questions_ready"
  | "in_progress"
  | "completed"
  | "ended";

export interface InterviewSessionCreate {
  role_title: string;
  experience_level: string;
  topic_focus?: string;
}

export interface InterviewSessionResponse {
  session_id: string;
  status: SessionStatus;
  role_title: string;
  experience_level: string;
  topic_focus?: string | null;
  total_questions: number;
  current_question_index: number;
  created_at: string;
}

export type QuestionType =
  | "subjective"
  | "mcq"
  | "msq"
  | "numerical"
  | "coding";

export interface CodingTestCase {
  stdin: string;
  expected_stdout: string;
}

export interface CurrentQuestionResponse {
  session_id: string;
  status: SessionStatus;
  question_index: number;
  total_questions: number;
  question: string | null;
  is_complete: boolean;
  message: string;
  proctor_warning_count?: number;
  time_seconds?: number | null;
  marks?: number | null;
  question_type?: QuestionType | string | null;
  options?: string[] | null;
  tolerance?: number | null;
  languages?: string[] | null;
  starter_code?: Record<string, string> | null;
  public_tests?: CodingTestCase[] | null;
  time_limit_ms?: number | null;
  memory_limit_mb?: number | null;
  is_adaptive_follow_up?: boolean;
  adaptive_topic?: string | null;
  adaptive_difficulty?: string | null;
}

export interface AudioTranscribeResponse {
  session_id: string;
  transcribed_text: string;
}

export interface AnswerSubmitResponse {
  session_id: string;
  status: SessionStatus;
  answered_question_index: number;
  message: string;
  has_more_questions: boolean;
  is_complete: boolean;
  remaining_questions: number;
}

export interface EndInterviewResponse {
  session_id: string;
  status: SessionStatus;
  total_questions: number;
  answered_count: number;
  unanswered_count: number;
  questions: string[];
  answers: string[];
  answer_judgments?: AnswerJudgment[] | null;
  final_score?: FinalScore | null;
  message: string;
  original_score?: number | null;
  integrity_penalty_percent?: number;
  adjusted_final_score?: number | null;
  integrity_report?: import("./proctor").IntegrityReport | null;
  integrity_level?: string | null;
  candidate_report_email_sent?: boolean;
}

export interface AnswerJudgment {
  weighted_total?: number;
  overall_reasoning?: string;
  reasoning?: string;
  strengths?: string[];
  improvements?: string[];
  criteria_scores?: Record<string, { score?: number; reasoning?: string }>;
  grading_mode?: string;
  run_summary?: {
    passed?: number;
    total?: number;
    error?: string | null;
    cases?: Array<{
      passed?: boolean;
      status?: string;
      stdin_preview?: string;
      stderr_preview?: string;
    }>;
  } | null;
  error?: string;
}

export interface FinalScore {
  final_score?: number;
  candidate_score?: number;
  recommendation?: string;
  per_question_scores?: Array<{
    index: number;
    question: string;
    score: number;
    reasoning?: string;
  }>;
  top_strengths?: string[];
  top_improvements?: string[];
  score_breakdown?: {
    max_possible?: number;
    candidate_score?: number;
    thresholds?: Record<string, number>;
  };
}

export interface ApiError {
  detail: string | { loc: string[]; msg: string; type: string }[];
}
