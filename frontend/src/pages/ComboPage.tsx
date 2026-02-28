import { useState } from 'react'
import { api, type DashboardSection } from '../api'
import { useFetch } from '../hooks/useFetch'
import Card from '../components/Card'
import Spinner from '../components/Spinner'
import { fmt2, fmtPct } from '../utils/format'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'

const BRANCHES = ['', 'Conut', 'Conut - Tyre', 'Conut Jnah', 'Main Street Coffee']

export default function ComboPage() {
  const [branch, setBranch] = useState('')
  const { data, loading, error } = useFetch<DashboardSection>(
    () => api.combo(branch || undefined), [branch]
  )

  const rows = Array.isArray(data?.data) ? data!.data as Record<string, unknown>[] : []

  const chartData = rows.slice(0, 15).map(r => ({
    pair: `${String(r.item_a ?? r.antecedent ?? '').slice(0, 12)}+${String(r.item_b ?? r.consequent ?? '').slice(0, 12)}`,
    lift: parseFloat(String(r.lift ?? 0)),
  }))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Product Combos</h1>
          <p className="text-sm text-gray-500 mt-1">Association rules — items frequently purchased together</p>
        </div>
        <select
          value={branch}
          onChange={e => setBranch(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">All (Top Overall)</option>
          {BRANCHES.filter(Boolean).map(b => <option key={b} value={b}>{b}</option>)}
        </select>
      </div>

      {loading && <Spinner />}
      {error && <div className="text-red-600">Error: {error}</div>}

      {!loading && !error && (
        <>
          <Card title="Top Combos by Lift" subtitle="Lift > 3 = strong, > 5 = very strong">
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} layout="vertical" margin={{ left: 20, right: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis dataKey="pair" type="category" tick={{ fontSize: 10 }} width={140} />
                  <Tooltip formatter={(v: number) => fmt2(v)} />
                  <Bar dataKey="lift" radius={[0, 6, 6, 0]}>
                    {chartData.map((_: unknown, i: number) => (
                      <Cell key={i} fill={chartData[i].lift > 5 ? '#10b981' : chartData[i].lift > 3 ? '#f59e0b' : '#3b82f6'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="Combo Details">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 border-b">
                    <th className="pb-2 font-medium">#</th>
                    <th className="pb-2 font-medium">Item A</th>
                    <th className="pb-2 font-medium">Item B</th>
                    <th className="pb-2 font-medium text-right">Support</th>
                    <th className="pb-2 font-medium text-right">Confidence</th>
                    <th className="pb-2 font-medium text-right">Lift</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i} className="border-b border-gray-50">
                      <td className="py-2 text-gray-400">{i + 1}</td>
                      <td className="py-2">{String(r.item_a ?? r.antecedent ?? '')}</td>
                      <td className="py-2">{String(r.item_b ?? r.consequent ?? '')}</td>
                      <td className="py-2 text-right font-mono">{fmtPct(r.support as number)}</td>
                      <td className="py-2 text-right font-mono">{fmtPct(r.confidence as number)}</td>
                      <td className="py-2 text-right">
                        <span className={`font-mono font-medium px-2 py-0.5 rounded ${
                          (r.lift as number) > 5 ? 'bg-green-100 text-green-700' :
                          (r.lift as number) > 3 ? 'bg-amber-100 text-amber-700' :
                          'bg-gray-100 text-gray-600'
                        }`}>
                          {fmt2(r.lift as number)}
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
