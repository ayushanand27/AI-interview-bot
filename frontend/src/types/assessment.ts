export type QuestionType = "subjective" | "mcq" | "msq" | "numerical";

export interface AssessmentQuestion {
  text: string;
  type?: QuestionType;
  options?: string[] | null;
  correct_indices?: number[] | null;
  correct_answer?: string | null;
  tolerance?: number | null;
  time_seconds: number;
  marks: number;
}

export interface CreateAssessmentResponse {
  token: string;
  invite_link: string;
  questions_preview: AssessmentQuestion[];
}

export interface GenerateQuestionsResponse {
  questions: AssessmentQuestion[];
  jd_text?: string;
}

export interface AssessmentSummary {
  token: string;
  invite_link: string;
  role_preview: string;
  difficulty: string;
  question_count: number;
  expiry_at: string;
  used_count: number;
  max_uses: number;
  created_at: string;
  is_expired: boolean;
}

export interface ParseJdPdfResponse {
  jd_text: string;
}
