import { api, type DashboardOverview } from '../api'
import { useFetch } from '../hooks/useFetch'
import Card from '../components/Card'
import KpiCard from '../components/KpiCard'
import Spinner from '../components/Spinner'
import { fmtNum, fmt2, fmtPct } from '../utils/format'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'

const COLORS = ['#ED7512', '#3b82f6', '#10b981', '#f59e0b']

export default function Dashboard() {
  const { data, loading, error } = useFetch<DashboardOverview>(() => api.overview(), [])

  if (loading) return <Spinner />
  if (error || !data) return <div className="text-red-600 p-4">Error: {error}</div>

  // Prepare forecast chart data
  const forecastChart = (data.forecast ?? []).map((r: Record<string, unknown>) => ({
    branch: (r.branch as string) ?? '',
    forecast: r.demand_index_forecast as number,
    stability: r.forecast_stability_score as number,
  }))

  // Prepare expansion chart data
  const expansionChart = (data.expansion_ranking ?? []).map((r: Record<string, unknown>) => ({
    branch: (r.branch as string ?? r.pk as string ?? '').toString(),
    score: parseFloat(String(r.feasibility_score ?? r.score ?? 0)),
    tier: (r.tier as string) ?? '',
  }))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Operations Overview</h1>
        <p className="text-sm text-gray-500 mt-1">Conut bakery-café chain — executive dashboard</p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard
          label="Branches Tracked"
          value={forecastChart.length}
          sub="demand forecast"
          color="brand"
        />
        <KpiCard
          label="Top Combos"
          value={(data.top_combos ?? []).length}
          sub="product pairs"
          color="purple"
        />
        <KpiCard
          label="Expansion Targets"
          value={expansionChart.length}
          sub="feasibility ranked"
          color="green"
        />
        <KpiCard
          label="Staffing Insights"
          value={(data.staffing_summary ?? []).length}
          sub="branches analyzed"
          color="blue"
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Forecast Bar Chart */}
        <Card title="Demand Forecast" subtitle="1-month ahead (base scenario)">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={forecastChart} margin={{ left: 10, right: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="branch" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={(v: number) => fmtNum(v)} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v: number) => fmtNum(v)} />
                <Bar dataKey="forecast" radius={[6, 6, 0, 0]}>
                  {forecastChart.map((_: unknown, i: number) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Expansion Feasibility */}
        <Card title="Expansion Feasibility" subtitle="Score 0–1 (High > 0.6)">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={expansionChart} layout="vertical" margin={{ left: 10, right: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis type="number" domain={[0, 1]} tick={{ fontSize: 11 }} />
                <YAxis dataKey="branch" type="category" tick={{ fontSize: 11 }} width={70} />
                <Tooltip formatter={(v: number) => fmt2(v)} />
                <Bar dataKey="score" radius={[0, 6, 6, 0]}>
                  {expansionChart.map((d: { score: number }, i: number) => (
                    <Cell key={i} fill={d.score > 0.6 ? '#10b981' : d.score > 0.4 ? '#f59e0b' : '#ef4444'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* Tables Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Combos */}
        <Card title="Top Product Combos" subtitle="Highest-lift item pairs">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b">
                  <th className="pb-2 font-medium">Item A</th>
                  <th className="pb-2 font-medium">Item B</th>
                  <th className="pb-2 font-medium text-right">Lift</th>
                  <th className="pb-2 font-medium text-right">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {(data.top_combos ?? []).slice(0, 8).map((c: Record<string, unknown>, i: number) => (
                  <tr key={i} className="border-b border-gray-50">
                    <td className="py-2">{String(c.item_a ?? c.antecedent ?? '')}</td>
                    <td className="py-2">{String(c.item_b ?? c.consequent ?? '')}</td>
                    <td className="py-2 text-right font-mono">{fmt2(c.lift as number)}</td>
                    <td className="py-2 text-right font-mono">{fmtPct(c.confidence as number)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Staffing Summary */}
        <Card title="Staffing Summary" subtitle="Understaffing indicators per branch">
          <div className="space-y-4">
            {(data.staffing_summary ?? []).map((s: Record<string, unknown>, i: number) => {
              const branch = String(s.branch ?? s.pk ?? '')
              const gapCount = Number(s.understaffed_slots ?? s.gap_count ?? 0)
              return (
                <div key={i} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                  <div>
                    <div className="font-medium text-sm">{branch}</div>
                    <div className="text-xs text-gray-500 mt-0.5">
                      {gapCount} understaffed slot{gapCount !== 1 ? 's' : ''}
                    </div>
                  </div>
                  <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${
                    gapCount > 20 ? 'bg-red-100 text-red-700' :
                    gapCount > 10 ? 'bg-amber-100 text-amber-700' :
                    'bg-green-100 text-green-700'
                  }`}>
                    {gapCount > 20 ? 'Critical' : gapCount > 10 ? 'Moderate' : 'Good'}
                  </span>
                </div>
              )
            })}
          </div>
        </Card>
      </div>

      {/* Growth Summary */}
      <Card title="Growth Potential" subtitle="Coffee & milkshake growth rankings">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {(data.growth_ranking ?? []).map((g: Record<string, unknown>, i: number) => (
            <div key={i} className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-xl p-4 border border-green-200">
              <div className="font-semibold text-green-800 text-sm">
                {String(g.branch ?? g.pk ?? '')}
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                <div>
                  <span className="text-green-600">Potential</span>
                  <div className="font-bold text-green-900 text-lg">
                    {fmt2(g.growth_potential_score as number ?? g.score as number)}
                  </div>
                </div>
                <div>
                  <span className="text-green-600">Tier</span>
                  <div className="font-bold text-green-900 text-lg">
                    {String(g.tier ?? g.growth_tier ?? '—')}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
