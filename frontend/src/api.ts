/**
 * API client — talks to the FastAPI agent backend.
 *
 * In dev mode Vite proxies /api to localhost:8000.
 * In production the API_URL env var should point to the ALB.
 */

const BASE = import.meta.env.VITE_API_URL ?? '';

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

// ── Types ───────────────────────────────────────────────────────────────

export interface ChatResponse {
  answer: string;
  tool_calls: { tool: string; input: Record<string, unknown>; output_preview: string }[];
}

export interface DashboardOverview {
  forecast: Record<string, unknown>[];
  top_combos: Record<string, unknown>[];
  expansion_ranking: Record<string, unknown>[];
  staffing_summary: Record<string, unknown>[];
  growth_ranking: Record<string, unknown>[];
}

export interface DashboardSection {
  feature: string;
  data: unknown;
}

export interface HealthStatus {
  status: string;
  local_mode: boolean;
  model: string;
}

export interface PrepareResponse {
  archived_files: number;
  cleared_tables: Record<string, number>;
  archive_path: string;
}

export interface PresignResponse {
  upload_url: string;
  s3_key: string;
  bucket: string;
  expires_in: number;
}

export interface TriggerResponse {
  execution_arn: string;
  status: string;
  started_at: string;
}

export interface PipelineStatus {
  execution_arn: string;
  status: string;
  started_at: string | null;
  stopped_at: string | null;
}

// ── Endpoints ───────────────────────────────────────────────────────────

export const api = {
  health: () => fetchJSON<HealthStatus>('/api/health'),

  chat: (message: string) =>
    fetchJSON<ChatResponse>('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    }),

  overview: () => fetchJSON<DashboardOverview>('/api/dashboard/overview'),

  forecast: (branch?: string) =>
    fetchJSON<DashboardSection>(branch ? `/api/dashboard/forecast/${encodeURIComponent(branch)}` : '/api/dashboard/forecast'),

  combo: (branch?: string) =>
    fetchJSON<DashboardSection>(branch ? `/api/dashboard/combo/${encodeURIComponent(branch)}` : '/api/dashboard/combo'),

  expansion: (branch?: string) =>
    fetchJSON<DashboardSection>(branch ? `/api/dashboard/expansion/${encodeURIComponent(branch)}` : '/api/dashboard/expansion'),

  staffing: (branch?: string) =>
    fetchJSON<DashboardSection>(branch ? `/api/dashboard/staffing/${encodeURIComponent(branch)}` : '/api/dashboard/staffing'),

  growth: (branch?: string) =>
    fetchJSON<DashboardSection>(branch ? `/api/dashboard/growth/${encodeURIComponent(branch)}` : '/api/dashboard/growth'),

  // Upload + Pipeline
  prepareForUpload: () =>
    fetchJSON<PrepareResponse>('/api/upload/prepare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }),

  presignUpload: (filename: string) =>
    fetchJSON<PresignResponse>('/api/upload/presign', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename }),
    }),

  uploadFileToS3: async (presignedUrl: string, file: File) => {
    const res = await fetch(presignedUrl, {
      method: 'PUT',
      headers: { 'Content-Type': 'text/csv' },
      body: file,
    });
    if (!res.ok) throw new Error(`S3 upload failed: ${res.status}`);
  },

  triggerPipeline: (s3Key?: string) =>
    fetchJSON<TriggerResponse>('/api/upload/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ s3_key: s3Key ?? '' }),
    }),

  pipelineStatus: (executionArn: string) =>
    fetchJSON<PipelineStatus>('/api/upload/status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ execution_arn: executionArn }),
    }),
};
