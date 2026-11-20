export type Role = "admin" | "user";
export type Language = "english" | "roman_urdu";
export type Status = "answered" | "clarification" | "no_data" | "refused" | "error";
export type Stage = "understanding" | "retrieving" | "validating" | "responding";

export interface Me {
  id: string;
  username: string;
  full_name: string;
  role: Role;
  can_view_financials: boolean;
  must_change_password: boolean;
}

export interface Table {
  title: string;
  columns: string[];
  rows: (string | number | null)[][];
}

export interface UiPayload {
  filters?: Record<string, string> | null;
  assumptions?: string[];
  table?: Table | null;
  clarification_options?: string[] | null;
  verified?: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  language?: Language | null;
  status?: Status | null;
  ui_payload?: UiPayload;
  rating?: number | null;
  created_at?: string;
  // client-only
  pending?: boolean;
  stage?: Stage;
  errorCode?: string;
  retryText?: string;
  animate?: boolean; // just arrived: reveal word by word
}

export interface ConversationSummary {
  id: string;
  title: string;
  updated_at: string;
}
