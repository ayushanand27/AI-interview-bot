export type QuestionType =
  | "subjective"
  | "mcq"
  | "msq"
  | "numerical"
  | "coding";

export type CodingLanguage =
  | "c"
  | "cpp"
  | "python"
  | "perl"
  | "java"
  | "javascript";

export interface CodingTestCase {
  stdin: string;
  expected_stdout: string;
}

export interface AssessmentQuestion {
  text: string;
  type?: QuestionType;
  options?: string[] | null;
  correct_indices?: number[] | null;
  correct_answer?: string | null;
  tolerance?: number | null;
  languages?: CodingLanguage[] | string[] | null;
  starter_code?: Record<string, string> | null;
  public_tests?: CodingTestCase[] | null;
  hidden_tests?: CodingTestCase[] | null;
  time_limit_ms?: number | null;
  memory_limit_mb?: number | null;
  rubric_notes?: string | null;
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
