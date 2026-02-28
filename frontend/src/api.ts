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
};
