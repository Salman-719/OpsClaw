import { useState } from 'react'
import { api, type DashboardSection } from '../api'
import { useFetch } from '../hooks/useFetch'
import Card from '../components/Card'
import KpiCard from '../components/KpiCard'
import Spinner from '../components/Spinner'
import { fmt2, fmtPct } from '../utils/format'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'

const BRANCHES = ['', 'Conut - Tyre', 'Conut Jnah', 'Main Street Coffee']

interface BranchAction {
  branch: string
  potential_score: number
  current_attachment_rate: number
  beverage_gap_to_best: number
  recommended_bundle: string
  action: string
}

interface GrowthRecommendation {
  strategy?: string
  objective?: string
  explanation?: string
  key_findings?: string | string[]
  branch_actions?: string | BranchAction[]
  pk?: string
  sk?: string
}

export default function GrowthPage() {
  const [branch, setBranch] = useState('')
  const { data, loading, error } = useFetch<DashboardSection>(
    () => api.growth(branch || undefined), [branch]
  )

  const payload = data?.data as Record<string, unknown> | null

  // All branches
  const ranking = Array.isArray(payload?.ranking) ? payload!.ranking as Record<string, unknown>[] : []
  const recommendation = (payload?.recommendation as GrowthRecommendation) ?? null

  // Single branch
  const kpis = payload?.kpis as Record<string, unknown> | null
  const potential = payload?.potential as Record<string, unknown> | null
  const rules = Array.isArray(payload?.rules) ? payload!.rules as Record<string, unknown>[] : []

  const chartData = ranking.map(r => ({
    branch: String(r.branch ?? r.pk ?? ''),
    score: parseFloat(String(r.growth_potential_score ?? r.score ?? 0)),
    tier: String(r.tier ?? r.growth_tier ?? ''),
  }))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Growth Strategy</h1>
          <p className="text-sm text-gray-500 mt-1">Coffee & milkshake growth opportunities</p>
        </div>
        <select
          value={branch}
          onChange={e => setBranch(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">All Branches</option>
          {BRANCHES.filter(Boolean).map(b => <option key={b} value={b}>{b}</option>)}
        </select>
      </div>

      {loading && <Spinner />}
      {error && <div className="text-red-600">Error: {error}</div>}

      {!loading && !error && !branch && (
        <>
          <Card title="Growth Potential Rankings">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="branch" tick={{ fontSize: 12 }} />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => fmt2(v)} />
                  <Bar dataKey="score" name="Growth Score" radius={[6, 6, 0, 0]}>
                    {chartData.map((d, i: number) => (
                      <Cell key={i} fill={d.score > 0.6 ? '#10b981' : d.score > 0.4 ? '#f59e0b' : '#3b82f6'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {recommendation && (
            <Card title="Growth Strategy Recommendation">
              <div className="space-y-3">
                {recommendation.strategy && (
                  <p className="font-semibold text-gray-900">{String(recommendation.strategy)}</p>
                )}
                {recommendation.objective && (
                  <p className="text-sm text-gray-600">{String(recommendation.objective)}</p>
                )}
                {recommendation.explanation && (
                  <p className="text-gray-700">{String(recommendation.explanation)}</p>
                )}
                {recommendation.key_findings && (() => {
                  const findings = typeof recommendation.key_findings === 'string'
                    ? (() => { try { return JSON.parse(recommendation.key_findings as string) } catch { return [recommendation.key_findings] } })()
                    : Array.isArray(recommendation.key_findings) ? recommendation.key_findings : [];
                  return findings.length > 0 ? (
                    <div>
                      <p className="text-xs font-medium text-gray-500 uppercase mb-1">Key Findings</p>
                      <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
                        {findings.map((f: string, i: number) => <li key={i}>{f}</li>)}
                      </ul>
                    </div>
                  ) : null;
                })()}
                {recommendation.branch_actions && (() => {
                  const actions = typeof recommendation.branch_actions === 'string'
                    ? (() => { try { return JSON.parse(recommendation.branch_actions as string) } catch { return [] } })()
                    : Array.isArray(recommendation.branch_actions) ? recommendation.branch_actions : [];
                  return actions.length > 0 ? (
                    <div>
                      <p className="text-xs font-medium text-gray-500 uppercase mb-1">Branch Actions</p>
                      <div className="space-y-2">
                        {actions.map((a: BranchAction, i: number) => (
                          <div key={i} className="p-3 bg-green-50 rounded-lg">
                            <div className="flex justify-between items-start">
                              <span className="font-medium text-green-900">{String(a.branch ?? '')}</span>
                              {a.potential_score != null && (
                                <span className="text-xs bg-green-200 text-green-800 px-2 py-0.5 rounded-full">Score: {Number(a.potential_score).toFixed(2)}</span>
                              )}
                            </div>
                            <p className="text-sm text-green-800 mt-1">{String(a.action ?? '')}</p>
                            {a.recommended_bundle && (
                              <p className="text-xs text-green-600 mt-1">Bundle: {String(a.recommended_bundle)}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null;
                })()}
              </div>
            </Card>
          )}
        </>
      )}

      {!loading && !error && branch && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {kpis && Object.entries(kpis).filter(([k]) => !['pk', 'sk', 'branch'].includes(k)).slice(0, 4).map(([k, v], i) => (
              <KpiCard
                key={k}
                label={k.replace(/_/g, ' ')}
                value={typeof v === 'number' ? (v < 1 ? fmtPct(v) : fmt2(v)) : String(v)}
                color={['brand', 'green', 'blue', 'purple'][i]}
              />
            ))}
          </div>

          {potential && (
            <Card title={`${branch} — Growth Potential`}>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {Object.entries(potential).filter(([k]) => !['pk', 'sk', 'branch'].includes(k)).map(([k, v]) => (
                  <div key={k} className="p-3 bg-green-50 rounded-lg">
                    <div className="text-xs text-green-600">{k.replace(/_/g, ' ')}</div>
                    <div className="font-bold text-green-900 mt-1">{typeof v === 'number' ? fmt2(v) : String(v)}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {rules.length > 0 && (
            <Card title={`${branch} — Association Rules (Food → Beverage)`}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-gray-500 border-b">
                      <th className="pb-2 font-medium">Food Item</th>
                      <th className="pb-2 font-medium">Beverage</th>
                      <th className="pb-2 font-medium text-right">Lift</th>
                      <th className="pb-2 font-medium text-right">Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rules.slice(0, 15).map((r, i) => (
                      <tr key={i} className="border-b border-gray-50">
                        <td className="py-2">{String(r.antecedent ?? r.item_a ?? '')}</td>
                        <td className="py-2">{String(r.consequent ?? r.item_b ?? '')}</td>
                        <td className="py-2 text-right font-mono">{fmt2(r.lift as number)}</td>
                        <td className="py-2 text-right font-mono">{fmtPct(r.confidence as number)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
