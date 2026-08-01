export interface InviteValidInfo {
  valid: true;
  role_title: string;
  company: string;
  question_count: number;
  difficulty: string;
  duration_minutes?: number | null;
}

export interface InviteInvalidInfo {
  valid: false;
  reason: string;
}

export type InviteCheckResponse = InviteValidInfo | InviteInvalidInfo;

export interface InviteRegisterResponse {
  session_id: string;
  access_token: string;
  refresh_token: string;
}

export class InviteFlowError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "InviteFlowError";
    this.status = status;
  }
}

export interface InviteVerifyIdentityResponse {
  verified: boolean;
  confidence: number;
  message: string;
  low_identity_confidence?: boolean;
  liveness_passed?: boolean;
  liveness_confidence?: number;
  warnings?: string[];
  ocr_name_match?: boolean | null;
  ocr_name_detected?: string | null;
  ocr_document_number?: string | null;
}
