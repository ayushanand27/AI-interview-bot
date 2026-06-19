export interface InviteValidInfo {
  valid: true;
  role_title: string;
  company: string;
  question_count: number;
  difficulty: string;
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
}
