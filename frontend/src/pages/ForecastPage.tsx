import { useState } from 'react'
import { api, type DashboardSection } from '../api'
import { useFetch } from '../hooks/useFetch'
import Card from '../components/Card'
import KpiCard from '../components/KpiCard'
import Spinner from '../components/Spinner'
import { fmtNum } from '../utils/format'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, Legend,
} from 'recharts'

const BRANCHES = ['', 'Conut', 'Conut - Tyre', 'Conut Jnah', 'Main Street Coffee']
const COLORS = ['#ED7512', '#3b82f6', '#10b981', '#f59e0b']

export default function ForecastPage() {
  const [branch, setBranch] = useState('')
  const { data, loading, error } = useFetch<DashboardSection>(
    () => api.forecast(branch || undefined), [branch]
  )

  const rows = Array.isArray(data?.data) ? data!.data as Record<string, unknown>[] : []

  // For all-branches view, show only primary (period 1, base)
  const primaryRows = branch
    ? rows
    : rows.filter(r => (r.is_primary === true || r.is_primary === 1 || r.is_primary === 1.0) && r.scenario === 'base')

  const chartData = primaryRows.map(r => ({
    branch: String(r.branch ?? ''),
    forecast: r.demand_index_forecast as number,
    low: r.relative_band_low as number,
    high: r.relative_band_high as number,
    stability: r.forecast_stability_score as number,
  }))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Demand Forecast</h1>
          <p className="text-sm text-gray-500 mt-1">Revenue demand predictions per branch</p>
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
          {/* KPIs for single branch */}
          {branch && rows.length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {rows.filter(r => r.scenario === 'base').map((r, i) => (
                <KpiCard
                  key={i}
                  label={`Period ${r.forecast_period} (${r.forecast_month})`}
                  value={fmtNum(r.demand_index_forecast as number)}
                  sub={`Stability: ${r.forecast_stability_score}/100`}
                  color={i === 0 ? 'brand' : 'blue'}
                />
              ))}
            </div>
          )}

          {/* Chart */}
          <Card title={branch ? `${branch} — Forecast by Period` : 'All Branches — Primary Forecast'}>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ left: 10, right: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="branch" tick={{ fontSize: 11 }} />
                  <YAxis tickFormatter={(v: number) => fmtNum(v)} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => fmtNum(v)} />
                  <Legend />
                  <Bar dataKey="forecast" name="Forecast" radius={[6, 6, 0, 0]}>
                    {chartData.map((_: unknown, i: number) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* Detail Table */}
          <Card title="Forecast Details">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 border-b">
                    <th className="pb-2 font-medium">Branch</th>
                    <th className="pb-2 font-medium">Scenario</th>
                    <th className="pb-2 font-medium">Period</th>
                    <th className="pb-2 font-medium text-right">Forecast</th>
                    <th className="pb-2 font-medium text-right">Stability</th>
                    <th className="pb-2 font-medium">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 24).map((r, i) => (
                    <tr key={i} className="border-b border-gray-50">
                      <td className="py-2">{String(r.branch)}</td>
                      <td className="py-2 capitalize">{String(r.scenario)}</td>
                      <td className="py-2">{String(r.forecast_period)}</td>
                      <td className="py-2 text-right font-mono">{fmtNum(r.demand_index_forecast as number)}</td>
                      <td className="py-2 text-right">{String(r.forecast_stability_score)}/100</td>
                      <td className="py-2">
                        <span className={`text-xs px-2 py-0.5 rounded-full ${
                          String(r.confidence_level).includes('high') ? 'bg-green-100 text-green-700' :
                          String(r.confidence_level).includes('medium') ? 'bg-amber-100 text-amber-700' :
                          'bg-red-100 text-red-700'
                        }`}>
                          {String(r.confidence_level)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
