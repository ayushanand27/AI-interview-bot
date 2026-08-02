export type UserRole = "candidate" | "recruiter";

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type?: string;
}

export interface UserResponse {
  id: number;
  full_name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  is_verified: boolean;
}

export interface MessageResponse {
  message: string;
  verification_url?: string | null;
  reset_url?: string | null;
  email_note?: string | null;
}

export interface VerifyEmailResponse {
  success: boolean;
  message: string;
}

export interface RegisterResponse {
  user: UserResponse;
  access_token: string;
  refresh_token: string;
  token_type?: string;
  verification_url?: string | null;
  email_note?: string | null;
}

export interface ApiEnvelope<T> {
  success: boolean;
  message: string;
  data: T;
}
