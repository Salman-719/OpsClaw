import { useState } from 'react'
import { api, type DashboardSection } from '../api'
import { useFetch } from '../hooks/useFetch'
import Card from '../components/Card'
import Spinner from '../components/Spinner'
import { fmt2 } from '../utils/format'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
  ReferenceLine,
} from 'recharts'

const BRANCHES = ['', 'Conut - Tyre', 'Conut Jnah', 'Main Street Coffee']

export default function StaffingPage() {
  const [branch, setBranch] = useState('')
  const { data, loading, error } = useFetch<DashboardSection>(
    () => api.staffing(branch || undefined), [branch]
  )

  const payload = data?.data as Record<string, unknown> | null

  // All branches view
  const summary = Array.isArray(payload?.summary) ? payload!.summary as Record<string, unknown>[] : []
  const topGaps = Array.isArray(payload?.top_gaps) ? payload!.top_gaps as Record<string, unknown>[] : []

  // Single branch view
  const findings = payload?.findings as Record<string, unknown> | null
  const worstGaps = Array.isArray(payload?.worst_gaps) ? payload!.worst_gaps as Record<string, unknown>[] : []

  const gapChartData = (branch ? worstGaps : topGaps).slice(0, 20).map(g => ({
    label: `${String(g.branch ?? '').slice(0, 8)} ${String(g.day ?? '').slice(0, 3)} ${String(g.hour ?? '')}`,
    gap: parseFloat(String(g.gap ?? g.staffing_gap ?? 0)),
  }))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Shift Staffing</h1>
          <p className="text-sm text-gray-500 mt-1">Hourly demand vs. staffing analysis</p>
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

      {!loading && !error && (
        <>
          {/* Summary cards */}
          {!branch && summary.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {summary.map((s, i) => {
                const name = String(s.branch ?? s.pk ?? '')
                const gaps = Number(s.understaffed_slots ?? s.gap_count ?? 0)
                return (
                  <div key={i} className={`rounded-xl border p-4 ${
                    gaps > 20 ? 'bg-red-50 border-red-200' :
                    gaps > 10 ? 'bg-amber-50 border-amber-200' :
                    'bg-green-50 border-green-200'
                  }`}>
                    <div className="font-semibold text-sm">{name}</div>
                    <div className="text-2xl font-bold mt-1">{gaps}</div>
                    <div className="text-xs opacity-70">understaffed slots</div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Single branch findings */}
          {branch && findings && (
            <Card title={`${branch} — Findings`}>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {Object.entries(findings).filter(([k]) => !['pk', 'sk', 'branch'].includes(k)).map(([k, v]) => (
                  <div key={k} className="p-3 bg-gray-50 rounded-lg">
                    <div className="text-xs text-gray-500">{k.replace(/_/g, ' ')}</div>
                    <div className="font-bold text-gray-900 mt-1">{typeof v === 'number' ? fmt2(v) : String(v)}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Gaps Chart */}
          <Card title={branch ? `Worst Gaps — ${branch}` : 'Top Staffing Gaps (All Branches)'}
                subtitle="Gap > 0 = understaffed, Gap < 0 = overstaffed">
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={gapChartData} margin={{ left: 10, right: 10, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="label" tick={{ fontSize: 9 }} angle={-35} textAnchor="end" height={60} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => fmt2(v)} />
                  <ReferenceLine y={0} stroke="#6b7280" />
                  <Bar dataKey="gap" name="Staffing Gap" radius={[4, 4, 0, 0]}>
                    {gapChartData.map((d, i: number) => (
                      <Cell key={i} fill={d.gap > 0 ? '#ef4444' : '#10b981'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* Gaps Table */}
          <Card title="Gap Details">
            <div className="overflow-x-auto max-h-80">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-white">
                  <tr className="text-left text-gray-500 border-b">
                    <th className="pb-2 font-medium">Branch</th>
                    <th className="pb-2 font-medium">Day</th>
                    <th className="pb-2 font-medium">Hour</th>
                    <th className="pb-2 font-medium text-right">Gap</th>
                    <th className="pb-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(branch ? worstGaps : topGaps).slice(0, 30).map((g, i) => {
                    const gap = parseFloat(String(g.gap ?? g.staffing_gap ?? 0))
                    return (
                      <tr key={i} className="border-b border-gray-50">
                        <td className="py-2">{String(g.branch ?? '')}</td>
                        <td className="py-2">{String(g.day ?? '')}</td>
                        <td className="py-2">{String(g.hour ?? '')}</td>
                        <td className="py-2 text-right font-mono">{fmt2(gap)}</td>
                        <td className="py-2">
                          <span className={`text-xs px-2 py-0.5 rounded-full ${
                            gap > 0 ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'
                          }`}>
                            {gap > 0 ? 'Understaffed' : 'Overstaffed'}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
