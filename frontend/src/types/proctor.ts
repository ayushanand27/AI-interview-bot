export interface ProctorAnalyzeResponse {
  session_id?: string;
  eye_status: string;
  gaze_direction: string;
  confidence: number;
  message: string;
  /** Immediate flash text (e.g. cell phone) even when eye_status is ok */
  alert_message?: string | null;
  current_status: "ok" | "violation" | string;
  violation_type?: string | null;
  total_violations: number;
  score_penalty_percent: number;
  /** @deprecated use total_violations */
  warning_count?: number;
  /** @deprecated always false */
  terminated?: boolean;
  is_currently_violating?: boolean;
}

export interface IntegrityViolation {
  type: string;
  severity: string;
  time: number;
  penalty_percent: number;
  message: string;
}

export interface AudioViolationResponse {
  recorded: boolean;
  session_id?: string;
  message: string;
  current_status: string;
  violation_type?: string | null;
  total_violations: number;
  score_penalty_percent: number;
  integrity_level?: string;
}

export interface IntegrityReport {
  total_violations: number;
  violations: IntegrityViolation[];
  score_penalty_percent: number;
  integrity_level: string;
}

export interface VerifyEnvironmentRequest {
  session_id: string;
  user_agent: string;
  detected_extensions: Array<{ id: string; name: string }>;
  virtual_camera_detected: boolean;
  virtual_camera_uncertain?: boolean;
  screen_sharing_active: boolean;
  screen_sharing_capability?: boolean;
}

export interface VerifyEnvironmentResponse {
  allowed: boolean;
  reason?: string | null;
  warnings: string[];
}
