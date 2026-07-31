import type {

  ApiEnvelope,

  RegisterResponse,

  TokenResponse,

  UserResponse,

} from "../types/auth";

import type {

  AssessmentQuestion,

  AssessmentSummary,

  CreateAssessmentResponse,

  GenerateQuestionsResponse,

  ParseJdPdfResponse,

} from "../types/assessment";

import type {

  InviteCheckResponse,

  InviteRegisterResponse,

  InviteVerifyIdentityResponse,

} from "../types/invite";

import { InviteFlowError } from "../types/invite";

import type {

  RecruiterAnalyticsResponse,

  RecruiterSessionDetail,

  RecruiterSessionFilters,

  RecruiterSessionSummary,

} from "../types/recruiter";

import type {

  AnswerSubmitResponse,

  AudioTranscribeResponse,

  CurrentQuestionResponse,

  EndInterviewResponse,

  InterviewSessionResponse,

} from "../types/interview";

import type {

  AudioViolationResponse,

  IntegrityReport,

  ProctorAnalyzeResponse,

  VerifyEnvironmentRequest,

  VerifyEnvironmentResponse,

} from "../types/proctor";



const API_BASE = import.meta.env.VITE_API_URL || "";

const REFRESH_STORAGE_KEY = "ss_refresh_token";



let accessToken: string | null = null;

let refreshToken: string | null = null;

let onUnauthorized: (() => void) | null = null;



export function setAccessToken(token: string | null): void {

  accessToken = token;

}



export function getAccessToken(): string | null {

  return accessToken;

}



export function setRefreshToken(token: string | null): void {

  refreshToken = token;

  if (typeof sessionStorage !== "undefined") {

    if (token) {

      sessionStorage.setItem(REFRESH_STORAGE_KEY, token);

    } else {

      sessionStorage.removeItem(REFRESH_STORAGE_KEY);

    }

  }

}



export function loadStoredRefreshToken(): string | null {

  if (typeof sessionStorage === "undefined") return null;

  const stored = sessionStorage.getItem(REFRESH_STORAGE_KEY);

  refreshToken = stored;

  return stored;

}



export function setOnUnauthorized(handler: (() => void) | null): void {

  onUnauthorized = handler;

}



async function blobFromVideoResponse(response: Response): Promise<Blob> {
  const contentType =
    response.headers.get("content-type")?.split(";")[0].trim() || "video/mp4";
  const data = await response.arrayBuffer();
  return new Blob([data], { type: contentType });
}



function parseErrorMessage(body: unknown, status: number): string {

  if (body && typeof body === "object") {

    const record = body as Record<string, unknown>;

    if (typeof record.message === "string" && record.message) {

      return record.message;

    }

    const detail = record.detail;

    if (typeof detail === "string") {

      return detail;

    }

    if (Array.isArray(detail) && detail.length > 0) {

      const first = detail[0] as { msg?: string };

      if (typeof first?.msg === "string") {

        return first.msg;

      }

    }

  }

  if (status === 401) {

    return "Your session expired. Please log in again.";

  }

  if (status === 503) {

    return "Service temporarily unavailable. Please try again.";

  }

  if (status >= 500) {

    return "Something went wrong on the server. Please try again.";

  }

  return `Request failed (${status})`;

}



function authHeaders(extra?: HeadersInit): HeadersInit {

  const headers: Record<string, string> = {};

  if (accessToken) {

    headers.Authorization = `Bearer ${accessToken}`;

  }

  if (extra) {

    const extraRecord =

      extra instanceof Headers

        ? Object.fromEntries(extra.entries())

        : (extra as Record<string, string>);

    Object.assign(headers, extraRecord);

  }

  return headers;

}



async function refreshAccessToken(): Promise<boolean> {

  const token = refreshToken ?? loadStoredRefreshToken();

  if (!token) return false;



  try {

    const response = await fetch(`${API_BASE}/api/v1/auth/refresh`, {

      method: "POST",

      headers: { "Content-Type": "application/json" },

      body: JSON.stringify({ refresh_token: token }),

    });

    if (!response.ok) return false;



    const envelope = (await response.json()) as ApiEnvelope<TokenResponse>;

    setAccessToken(envelope.data.access_token);

    setRefreshToken(envelope.data.refresh_token);

    return true;

  } catch {

    return false;

  }

}



async function request<T>(

  path: string,

  options?: RequestInit,

  isRetry = false,

): Promise<T> {

  const isFormData = options?.body instanceof FormData;

  const response = await fetch(`${API_BASE}${path}`, {

    ...options,

    headers: isFormData

      ? authHeaders(options?.headers)

      : {

          "Content-Type": "application/json",

          ...authHeaders(options?.headers),

        },

  });



  if (!response.ok) {

    const body = await response.json().catch(() => ({}));



    if (response.status === 401 && !isRetry) {

      const refreshed = await refreshAccessToken();

      if (refreshed) {

        return request<T>(path, options, true);

      }

      onUnauthorized?.();

    }



    throw new Error(parseErrorMessage(body, response.status));

  }



  return response.json() as Promise<T>;

}



export const authApi = {

  login(email: string, password: string) {

    return request<ApiEnvelope<TokenResponse>>("/api/v1/auth/login", {

      method: "POST",

      body: JSON.stringify({ email, password }),

    });

  },



  register(

    full_name: string,

    email: string,

    password: string,

    role: "candidate" | "recruiter",

  ) {

    return request<ApiEnvelope<RegisterResponse>>("/api/v1/auth/register", {

      method: "POST",

      body: JSON.stringify({ full_name, email, password, role }),

    });

  },



  refresh(refresh_token: string) {

    return request<ApiEnvelope<TokenResponse>>("/api/v1/auth/refresh", {

      method: "POST",

      body: JSON.stringify({ refresh_token }),

    });

  },



  me() {

    return request<ApiEnvelope<UserResponse>>("/api/v1/auth/me");

  },



  async verifyEmail(token: string) {

    const response = await fetch(

      `${API_BASE}/api/v1/auth/verify-email?token=${encodeURIComponent(token.trim())}`,

    );

    const body = (await response.json().catch(() => ({}))) as

      | import("../types/auth").VerifyEmailResponse

      | { detail?: string };

    if (!response.ok) {

      throw new Error(parseErrorMessage(body, response.status));

    }

    return body as import("../types/auth").VerifyEmailResponse;

  },



  forgotPassword(email: string) {

    return request<import("../types/auth").MessageResponse>(

      "/api/v1/auth/forgot-password",

      {

        method: "POST",

        body: JSON.stringify({ email }),

      },

    );

  },



  resetPassword(token: string, new_password: string) {

    return request<import("../types/auth").MessageResponse>(

      "/api/v1/auth/reset-password",

      {

        method: "POST",

        body: JSON.stringify({ token, new_password }),

      },

    );

  },



  resendVerification(email: string) {

    return request<import("../types/auth").MessageResponse>(

      "/api/v1/auth/resend-verification",

      {

        method: "POST",

        body: JSON.stringify({ email }),

      },

    );

  },

};



export const recruiterApi = {

  buildSessionFilterQuery(filters?: RecruiterSessionFilters): string {
    if (!filters) return "";
    const params = new URLSearchParams();
    if (filters.role_title?.trim()) params.set("role_title", filters.role_title.trim());
    if (filters.date_from) params.set("date_from", filters.date_from);
    if (filters.date_to) params.set("date_to", filters.date_to);
    if (filters.invite_token?.trim()) params.set("invite_token", filters.invite_token.trim());
    if (filters.score_band?.trim()) params.set("score_band", filters.score_band.trim());
    if (filters.integrity_level?.trim()) {
      params.set("integrity_level", filters.integrity_level.trim());
    }
    if (filters.review_status?.trim()) params.set("review_status", filters.review_status.trim());
    const qs = params.toString();
    return qs ? `?${qs}` : "";
  },

  listSessions(filters?: RecruiterSessionFilters) {
    const qs = recruiterApi.buildSessionFilterQuery(filters);
    return request<ApiEnvelope<RecruiterSessionSummary[]>>(
      `/api/v1/recruiter/sessions${qs}`,
    );
  },

  getAnalytics(filters?: RecruiterSessionFilters) {
    const qs = recruiterApi.buildSessionFilterQuery(filters);
    return request<ApiEnvelope<RecruiterAnalyticsResponse>>(
      `/api/v1/recruiter/analytics${qs}`,
    );
  },

  async exportSessionsCsv(filters?: RecruiterSessionFilters): Promise<Blob> {
    const qs = recruiterApi.buildSessionFilterQuery(filters);
    const response = await fetch(
      `${API_BASE}/api/v1/recruiter/sessions/export${qs}`,
      { headers: authHeaders() },
    );
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(parseErrorMessage(body, response.status));
    }
    return response.blob();
  },

  async exportAssessmentsCsv(): Promise<Blob> {
    const response = await fetch(
      `${API_BASE}/api/v1/recruiter/assessments/export`,
      { headers: authHeaders() },
    );
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(parseErrorMessage(body, response.status));
    }
    return response.blob();
  },



  getSession(sessionId: string) {

    return request<ApiEnvelope<RecruiterSessionDetail>>(

      `/api/v1/recruiter/sessions/${sessionId}`,

    );

  },



  async downloadReport(sessionId: string): Promise<Blob> {

    const response = await fetch(

      `${API_BASE}/api/v1/recruiter/sessions/${sessionId}/report`,

      {

        headers: authHeaders(),

      },

    );

    if (!response.ok) {

      const body = await response.json().catch(() => ({}));

      throw new Error(parseErrorMessage(body, response.status));

    }

    return response.blob();

  },



  async getRecording(sessionId: string): Promise<Blob> {

    const response = await fetch(

      `${API_BASE}/api/v1/interviews/sessions/${sessionId}/recording`,

      {

        headers: authHeaders(),

      },

    );

    if (!response.ok) {

      const body = await response.json().catch(() => ({}));

      throw new Error(parseErrorMessage(body, response.status));

    }

    return blobFromVideoResponse(response);

  },



  listAssessments() {

    return request<ApiEnvelope<AssessmentSummary[]>>(

      "/api/v1/recruiter/assessments",

    );

  },



  deleteAssessment(token: string) {

    return request<ApiEnvelope<null>>(

      `/api/v1/recruiter/assessments/${token}`,

      { method: "DELETE" },

    );

  },



  updateAssessmentExpiry(token: string, expiryHours: number) {

    return request<ApiEnvelope<AssessmentSummary>>(

      `/api/v1/recruiter/assessments/${token}`,

      {
        method: "PATCH",
        body: JSON.stringify({ expiry_hours: expiryHours }),
      },

    );

  },

  sendAssessmentInvites(
    token: string,
    payload: { emails: string[]; message?: string },
  ) {
    return request<
      ApiEnvelope<{ sent: number; failed: string[]; invite_link: string }>
    >(`/api/v1/recruiter/assessments/${token}/send-invites`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },



  setHumanReview(sessionId: string, flagged: boolean) {

    return request<ApiEnvelope<RecruiterSessionDetail>>(

      `/api/v1/recruiter/sessions/${sessionId}/human-review`,

      {

        method: "PATCH",

        body: JSON.stringify({ flagged }),

      },

    );

  },



  updateReviewState(
    sessionId: string,
    payload: { review_status: string; review_notes?: string | null },
  ) {

    return request<ApiEnvelope<RecruiterSessionDetail>>(

      `/api/v1/recruiter/sessions/${sessionId}/review`,

      {

        method: "PATCH",

        body: JSON.stringify(payload),

      },

    );

  },



  async generateQuestions(payload: {
    jd_text?: string;
    jd_pdf?: File | null;
    question_count: number;
    difficulty: string;
    question_types?: string[];
  }) {
    const form = new FormData();
    form.append("jd_text", payload.jd_text ?? "");
    form.append("question_count", String(payload.question_count));
    form.append("difficulty", payload.difficulty);
    if (payload.question_types && payload.question_types.length > 0) {
      form.append("question_types", JSON.stringify(payload.question_types));
    }
    if (payload.jd_pdf) {
      form.append("jd_pdf", payload.jd_pdf);
    }

    const response = await fetch(
      `${API_BASE}/api/v1/recruiter/generate-questions`,
      {
        method: "POST",
        headers: authHeaders(),
        body: form,
      },
    );
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(parseErrorMessage(body, response.status));
    }
    return response.json() as Promise<ApiEnvelope<GenerateQuestionsResponse>>;
  },



  async createAssessment(payload: {
    jd_text?: string;
    jd_pdf?: File | null;
    question_count: number;
    difficulty: string;
    expiry_hours: number;
    questions?: AssessmentQuestion[];
  }) {
    const form = new FormData();
    form.append("jd_text", payload.jd_text ?? "");
    form.append("question_count", String(payload.question_count));
    form.append("difficulty", payload.difficulty);
    form.append("expiry_hours", String(payload.expiry_hours));
    if (payload.jd_pdf) {
      form.append("jd_pdf", payload.jd_pdf);
    }
    if (payload.questions && payload.questions.length > 0) {
      form.append("questions", JSON.stringify(payload.questions));
    }

    const response = await fetch(
      `${API_BASE}/api/v1/recruiter/create-assessment`,
      {
        method: "POST",
        headers: authHeaders(),
        body: form,
      },
    );
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(parseErrorMessage(body, response.status));
    }
    return response.json() as Promise<ApiEnvelope<CreateAssessmentResponse>>;
  },



  async parseJdPdf(file: File) {
    const form = new FormData();
    form.append("pdf", file);
    const response = await fetch(`${API_BASE}/api/v1/recruiter/parse-jd-pdf`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(parseErrorMessage(body, response.status));
    }
    return response.json() as Promise<ApiEnvelope<ParseJdPdfResponse>>;
  },

};



export const interviewApi = {

  createSession(payload: FormData) {

    return request<InterviewSessionResponse>("/api/v1/interviews/sessions", {

      method: "POST",

      body: payload,

    });

  },



  resetActiveSession() {

    return request<{ message: string }>("/api/v1/interviews/reset-active-session", {

      method: "POST",

    });

  },



  fetchJdUrl(url: string) {

    return request<{ jd_text: string; source: string }>(

      "/api/v1/interviews/fetch-jd-url",

      {

        method: "POST",

        body: JSON.stringify({ url }),

      },

    );

  },



  generateQuestions(sessionId: string, questionCount: number) {

    return request<{ total_questions: number; message: string }>(

      `/api/v1/interviews/sessions/${sessionId}/questions`,

      {

        method: "POST",

        body: JSON.stringify({ question_count: questionCount }),

      },

    );

  },



  getCurrentQuestion(sessionId: string) {

    return request<CurrentQuestionResponse>(

      `/api/v1/interviews/sessions/${sessionId}/current-question`,

    );

  },



  submitAnswer(sessionId: string, answer: string) {

    return request<AnswerSubmitResponse>(

      `/api/v1/interviews/sessions/${sessionId}/answers`,

      {

        method: "POST",

        body: JSON.stringify({ answer }),

      },

    );

  },

  submitCodingAnswer(sessionId: string, language: string, source: string) {
    return request<AnswerSubmitResponse>(
      `/api/v1/interviews/sessions/${sessionId}/coding/answers`,
      {
        method: "POST",
        body: JSON.stringify({ language, source }),
      },
    );
  },

  runCodingPublicTests(sessionId: string, language: string, source: string) {
    return request<{
      session_id: string;
      question_index: number;
      passed: number;
      total: number;
      error?: string | null;
      cases: Array<{
        passed: boolean;
        status: string;
        stdin: string;
        expected_stdout: string;
        actual_stdout: string;
        stderr?: string;
      }>;
    }>(`/api/v1/interviews/sessions/${sessionId}/coding/run-public`, {
      method: "POST",
      body: JSON.stringify({ language, source }),
    });
  },



  transcribeAudio(sessionId: string, audioBlob: Blob, filename = "recording.webm") {

    const form = new FormData();

    form.append("audio", audioBlob, filename);

    form.append("submit", "false");

    return request<AudioTranscribeResponse>(

      `/api/v1/interviews/sessions/${sessionId}/audio-answer`,

      {

        method: "POST",

        body: form,

      },

    );

  },



  endInterview(sessionId: string) {

    return request<EndInterviewResponse>(

      `/api/v1/interviews/sessions/${sessionId}/end`,

      { method: "POST" },

    );

  },



  uploadRecording(sessionId: string, videoBlob: Blob, filename = "session-recording.webm") {

    const form = new FormData();

    form.append("video", videoBlob, filename);

    return request<{ session_id: string; recording_filename: string; message: string }>(

      `/api/v1/interviews/sessions/${sessionId}/recording`,

      {

        method: "POST",

        body: form,

      },

    );

  },



  async getRecording(sessionId: string): Promise<Blob> {

    const response = await fetch(

      `${API_BASE}/api/v1/interviews/sessions/${sessionId}/recording`,

      {

        headers: authHeaders(),

      },

    );

    if (!response.ok) {

      const body = await response.json().catch(() => ({}));

      throw new Error(parseErrorMessage(body, response.status));

    }

    return blobFromVideoResponse(response);

  },



  async getMyRecording(sessionId: string, inviteToken?: string): Promise<Blob> {

    const query = inviteToken

      ? `?token=${encodeURIComponent(inviteToken)}`

      : "";

    const response = await fetch(

      `${API_BASE}/api/v1/interviews/sessions/${sessionId}/my-recording${query}`,

      {

        headers: authHeaders(),

      },

    );

    if (!response.ok) {

      const body = await response.json().catch(() => ({}));

      throw new Error(parseErrorMessage(body, response.status));

    }

    return blobFromVideoResponse(response);

  },



  async downloadMyReport(sessionId: string, inviteToken?: string): Promise<Blob> {

    const query = inviteToken

      ? `?token=${encodeURIComponent(inviteToken)}`

      : "";

    const response = await fetch(

      `${API_BASE}/api/v1/interviews/sessions/${sessionId}/my-report${query}`,

      {

        headers: authHeaders(),

      },

    );

    if (!response.ok) {

      const body = await response.json().catch(() => ({}));

      throw new Error(parseErrorMessage(body, response.status));

    }

    return response.blob();

  },

};



export const proctorApi = {

  analyze(sessionId: string, frameBase64: string) {

    return request<ProctorAnalyzeResponse>("/proctor/analyze", {

      method: "POST",

      body: JSON.stringify({

        session_id: sessionId,

        frame_base64: frameBase64,

      }),

    });

  },



  reset(sessionId?: string) {

    return request<{ message: string; session_id?: string }>("/proctor/reset", {

      method: "POST",

      body: JSON.stringify(sessionId ? { session_id: sessionId } : {}),

    });

  },



  integrityReport(sessionId?: string) {

    const q = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";

    return request<IntegrityReport>(`/proctor/integrity-report${q}`);

  },



  reportLoudAudio(sessionId: string, message?: string) {

    return this.reportClientViolation(

      sessionId,

      "loud_audio",

      message ?? "Please maintain a quiet environment",

    );

  },



  reportClientViolation(

    sessionId: string,

    violationType: string,

    message: string,

  ) {

    return request<AudioViolationResponse>("/proctor/audio-violation", {

      method: "POST",

      body: JSON.stringify({

        session_id: sessionId,

        violation_type: violationType,

        message,

      }),

    });

  },



  verifyEnvironment(payload: VerifyEnvironmentRequest) {

    return request<VerifyEnvironmentResponse>("/proctor/verify-environment", {

      method: "POST",

      body: JSON.stringify(payload),

    });

  },

};



export const inviteApi = {

  async checkInvite(token: string): Promise<InviteCheckResponse> {

    const response = await fetch(`${API_BASE}/api/v1/invite/${encodeURIComponent(token)}`);

    if (!response.ok) {

      const body = await response.json().catch(() => ({}));

      throw new Error(parseErrorMessage(body, response.status));

    }

    return response.json() as Promise<InviteCheckResponse>;

  },



  register(

    token: string,

    payload: { name: string; email: string; phone: string; password: string },

  ) {

    return request<ApiEnvelope<InviteRegisterResponse>>(

      `/api/v1/invite/${encodeURIComponent(token)}/register`,

      {

        method: "POST",

        body: JSON.stringify(payload),

      },

    );

  },



  async login(

    token: string,

    payload: { email: string; password: string; phone?: string },

  ): Promise<ApiEnvelope<InviteRegisterResponse>> {

    const response = await fetch(

      `${API_BASE}/api/v1/invite/${encodeURIComponent(token)}/login`,

      {

        method: "POST",

        headers: {

          "Content-Type": "application/json",

          ...authHeaders(),

        },

        body: JSON.stringify(payload),

      },

    );

    if (!response.ok) {

      const body = await response.json().catch(() => ({}));

      throw new InviteFlowError(parseErrorMessage(body, response.status), response.status);

    }

    return response.json() as Promise<ApiEnvelope<InviteRegisterResponse>>;

  },



  async registerWithStatus(

    token: string,

    payload: { name: string; email: string; phone: string; password: string },

  ): Promise<ApiEnvelope<InviteRegisterResponse>> {

    const response = await fetch(

      `${API_BASE}/api/v1/invite/${encodeURIComponent(token)}/register`,

      {

        method: "POST",

        headers: {

          "Content-Type": "application/json",

          ...authHeaders(),

        },

        body: JSON.stringify(payload),

      },

    );

    if (!response.ok) {

      const body = await response.json().catch(() => ({}));

      throw new InviteFlowError(parseErrorMessage(body, response.status), response.status);

    }

    return response.json() as Promise<ApiEnvelope<InviteRegisterResponse>>;

  },



  verifyIdentity(

    token: string,

    payload: {

      id_image_base64: string;

      selfie_base64: string;

      selfie_frames_base64?: string[];

      liveness_actions?: string[];

      session_id: string;

    },

  ) {

    return request<ApiEnvelope<InviteVerifyIdentityResponse>>(

      `/api/v1/invite/${encodeURIComponent(token)}/verify-identity`,

      {

        method: "POST",

        body: JSON.stringify(payload),

      },

    );

  },

};


