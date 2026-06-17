export interface CreateAssessmentResponse {
  token: string;
  invite_link: string;
  questions_preview: string[];
}

export interface ParseJdPdfResponse {
  jd_text: string;
}
