import { useState } from 'react'
import { api, type DashboardSection } from '../api'
import { useFetch } from '../hooks/useFetch'
import Card from '../components/Card'
import KpiCard from '../components/KpiCard'
import Spinner from '../components/Spinner'
import { fmt2 } from '../utils/format'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'

const BRANCHES = ['', 'batroun', 'bliss', 'jnah', 'tyre']

interface ExpansionRecommendation {
  explanation?: string
  recommended_region?: string
  best_branch_to_replicate?: string
  feasibility_tier?: string
  overall_feasibility?: number
  candidate_locations?: string
  region_scores?: string
  growth_summary?: string
  pk?: string
  sk?: string
}

export default function ExpansionPage() {
  const [branch, setBranch] = useState('')
  const { data, loading, error } = useFetch<DashboardSection>(
    () => api.expansion(branch || undefined), [branch]
  )

  const payload = data?.data as Record<string, unknown> | null

  // All-branches view
  const ranking = Array.isArray(payload?.ranking) ? payload!.ranking as Record<string, unknown>[] : []
  const recommendation = (payload?.recommendation as ExpansionRecommendation) ?? null

  // Single branch view
  const kpis = payload?.kpis as Record<string, unknown> | null
  const feasibility = payload?.feasibility as Record<string, unknown> | null

  const chartData = ranking.map(r => ({
    branch: String(r.branch ?? r.pk ?? ''),
    score: parseFloat(String(r.feasibility_score ?? r.score ?? 0)),
    tier: String(r.tier ?? ''),
  }))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Expansion Feasibility</h1>
          <p className="text-sm text-gray-500 mt-1">Candidate branch analysis for expansion</p>
        </div>
        <select
          value={branch}
          onChange={e => setBranch(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">All Candidates</option>
          {BRANCHES.filter(Boolean).map(b => <option key={b} value={b}>{b}</option>)}
        </select>
      </div>

      {loading && <Spinner />}
      {error && <div className="text-red-600">Error: {error}</div>}

      {!loading && !error && !branch && (
        <>
          <Card title="Feasibility Rankings" subtitle="Score 0–1 (High > 0.6, Medium 0.4–0.6, Low < 0.4)">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ left: 10, right: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="branch" tick={{ fontSize: 12 }} />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => fmt2(v)} />
                  <Bar dataKey="score" name="Feasibility Score" radius={[6, 6, 0, 0]}>
                    {chartData.map((d, i: number) => (
                      <Cell key={i} fill={d.score > 0.6 ? '#10b981' : d.score > 0.4 ? '#f59e0b' : '#ef4444'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {recommendation && (
            <Card title="Expansion Recommendation">
              <div className="space-y-3">
                {recommendation.explanation && (
                  <p className="text-gray-700">{String(recommendation.explanation)}</p>
                )}
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {recommendation.recommended_region && (
                    <div className="p-3 bg-blue-50 rounded-lg">
                      <div className="text-xs text-blue-600">Recommended Region</div>
                      <div className="font-bold text-blue-900 mt-1">{String(recommendation.recommended_region)}</div>
                    </div>
                  )}
                  {recommendation.best_branch_to_replicate && (
                    <div className="p-3 bg-green-50 rounded-lg">
                      <div className="text-xs text-green-600">Best Branch to Replicate</div>
                      <div className="font-bold text-green-900 mt-1">{String(recommendation.best_branch_to_replicate)}</div>
                    </div>
                  )}
                  {recommendation.feasibility_tier && (
                    <div className="p-3 bg-amber-50 rounded-lg">
                      <div className="text-xs text-amber-600">Feasibility Tier</div>
                      <div className="font-bold text-amber-900 mt-1">{String(recommendation.feasibility_tier)}</div>
                    </div>
                  )}
                  {recommendation.overall_feasibility != null && (
                    <div className="p-3 bg-purple-50 rounded-lg">
                      <div className="text-xs text-purple-600">Overall Score</div>
                      <div className="font-bold text-purple-900 mt-1">{Number(recommendation.overall_feasibility).toFixed(4)}</div>
                    </div>
                  )}
                  {recommendation.candidate_locations && (
                    <div className="p-3 bg-gray-50 rounded-lg col-span-2">
                      <div className="text-xs text-gray-500">Candidate Locations</div>
                      <div className="font-bold text-gray-900 mt-1">{String(recommendation.candidate_locations)}</div>
                    </div>
                  )}
                </div>
              </div>
            </Card>
          )}
        </>
      )}

      {!loading && !error && branch && (
        <>
          {feasibility && (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <KpiCard
                label="Feasibility Score"
                value={fmt2(feasibility.feasibility_score as number ?? feasibility.score as number)}
                sub={`Tier: ${feasibility.tier ?? '—'}`}
                color={(feasibility.feasibility_score as number ?? 0) > 0.6 ? 'green' : 'amber'}
              />
            </div>
          )}

          {kpis && (
            <Card title={`${branch} — Operational KPIs`}>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {Object.entries(kpis).filter(([k]) => !['pk', 'sk', 'branch'].includes(k)).map(([k, v]) => (
                  <div key={k} className="p-3 bg-gray-50 rounded-lg">
                    <div className="text-xs text-gray-500">{k.replace(/_/g, ' ')}</div>
                    <div className="font-bold text-gray-900 mt-1">{typeof v === 'number' ? fmt2(v) : String(v)}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
