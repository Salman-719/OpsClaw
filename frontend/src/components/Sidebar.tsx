import type { Page } from '../App'

const NAV: { key: Page; label: string; icon: string }[] = [
  { key: 'overview',  label: 'Overview',   icon: '📊' },
  { key: 'forecast',  label: 'Forecast',   icon: '📈' },
  { key: 'combo',     label: 'Combos',     icon: '🍩' },
  { key: 'expansion', label: 'Expansion',  icon: '🏗️' },
  { key: 'staffing',  label: 'Staffing',   icon: '👥' },
  { key: 'growth',    label: 'Growth',     icon: '☕' },
  { key: 'upload',    label: 'Upload',     icon: '📁' },
]

interface Props {
  current: Page
  onNavigate: (p: Page) => void
}

export default function Sidebar({ current, onNavigate }: Props) {
  return (
    <aside className="w-56 bg-white border-r border-gray-200 flex flex-col shrink-0">
      {/* Logo */}
      <div className="h-16 flex items-center px-5 border-b border-gray-100">
        <div className="w-8 h-8 bg-brand-500 rounded-lg flex items-center justify-center text-white font-bold text-sm mr-3">C</div>
        <div>
          <div className="font-bold text-sm text-gray-900 leading-tight">OpsClaw</div>
          <div className="text-[10px] text-gray-400 leading-tight">Conut Operations AI</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 px-3 space-y-1">
        {NAV.map(({ key, label, icon }) => (
          <button
            key={key}
            onClick={() => onNavigate(key)}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
              current === key
                ? 'bg-brand-50 text-brand-700'
                : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
            }`}
          >
            <span className="text-base">{icon}</span>
            {label}
          </button>
        ))}
      </nav>

      <div className="p-4 border-t border-gray-100">
        <div className="text-[10px] text-gray-400 text-center">
          Conut AI Hackathon 2026
        </div>
      </div>
    </aside>
  )
}
