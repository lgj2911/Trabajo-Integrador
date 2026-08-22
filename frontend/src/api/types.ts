// TypeScript shapes mirroring the frozen backend REST API contract exactly.
// Do not rename fields or add fields the backend does not return.

export type SessionStatus = "queued" | "running" | "completed" | "failed" | "interrupted";
export type SessionSource = "upload" | "portal";

export interface SessionSummary {
  id: string;
  status: SessionStatus;
  source: SessionSource;
  created_at: string; // ISO 8601
  started_at: string | null;
  finished_at: string | null;
  ok_count: number;
  error_message: string | null;
}

export interface SessionDetail extends SessionSummary {
  csv_files_provided: string[];
  concurrency: number;
  delay: number;
  output_size_bytes: number | null;
}

export interface FileEntry {
  session_id: string;
  downloaded_at: string;
  source: string;
  category: string;
  filename: string;
  source_url: string;
  dest_path: string;
}

export interface SessionListResponse {
  items: SessionSummary[];
  total: number;
}

export interface FileListResponse {
  items: FileEntry[];
  total: number;
}

export interface MeResponse {
  authenticated: true;
  username: string;
}

export interface LoginResponse {
  ok: true;
}

export interface LogoutResponse {
  ok: true;
}

export interface HealthResponse {
  status: "ok";
}

export interface ErrorResponse {
  detail: string;
}

export interface LogLineEvent {
  line: string;
  ts: string;
}

export interface LogEndEvent {
  status: string;
}

/** The 10 known file categories, used to populate the Files page category filter. */
export const FILE_CATEGORIES = [
  "boletines",
  "compendios_de_boletines",
  "convenios",
  "declaraciones_concejo_municipal",
  "decreto_ordenanzas",
  "decretos",
  "decretos_concejo_municipal",
  "ordenanzas",
  "resoluciones",
  "resoluciones_concejo_municipal",
] as const;

export type FileCategory = (typeof FILE_CATEGORIES)[number];
