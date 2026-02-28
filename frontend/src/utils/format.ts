/** Format a large number for display (e.g. 1351165728 → "1.35B") */
export function fmtNum(n: number | string | null | undefined): string {
  if (n == null) return '—'
  const v = typeof n === 'string' ? parseFloat(n) : n
  if (isNaN(v)) return '—'
  if (Math.abs(v) >= 1e9) return (v / 1e9).toFixed(2) + 'B'
  if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2) + 'M'
  if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(1) + 'K'
  return v.toFixed(2)
}

/** Format a number as a percentage string */
export function fmtPct(n: number | string | null | undefined): string {
  if (n == null) return '—'
  const v = typeof n === 'string' ? parseFloat(n) : n
  if (isNaN(v)) return '—'
  return (v * 100).toFixed(1) + '%'
}

/** Format number with 2 decimal places */
export function fmt2(n: number | string | null | undefined): string {
  if (n == null) return '—'
  const v = typeof n === 'string' ? parseFloat(n) : n
  if (isNaN(v)) return '—'
  return v.toFixed(2)
}
