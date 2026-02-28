import { useState } from 'react'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import ForecastPage from './pages/ForecastPage'
import ComboPage from './pages/ComboPage'
import ExpansionPage from './pages/ExpansionPage'
import StaffingPage from './pages/StaffingPage'
import GrowthPage from './pages/GrowthPage'
import ChatPanel from './components/ChatPanel'

export type Page = 'overview' | 'forecast' | 'combo' | 'expansion' | 'staffing' | 'growth'

export default function App() {
  const [page, setPage] = useState<Page>('overview')
  const [chatOpen, setChatOpen] = useState(false)

  const renderPage = () => {
    switch (page) {
      case 'overview': return <Dashboard />
      case 'forecast': return <ForecastPage />
      case 'combo': return <ComboPage />
      case 'expansion': return <ExpansionPage />
      case 'staffing': return <StaffingPage />
      case 'growth': return <GrowthPage />
    }
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar current={page} onNavigate={setPage} />

      <main className="flex-1 overflow-y-auto p-6 bg-gray-50">
        {renderPage()}
      </main>

      {/* Chat toggle button */}
      <button
        onClick={() => setChatOpen(!chatOpen)}
        className="fixed bottom-6 right-6 z-50 w-14 h-14 bg-brand-600 hover:bg-brand-700 text-white rounded-full shadow-lg flex items-center justify-center transition-transform hover:scale-110"
        title="Chat with OpsClaw"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          {chatOpen ? (
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          ) : (
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          )}
        </svg>
      </button>

      {/* Chat Panel */}
      {chatOpen && <ChatPanel onClose={() => setChatOpen(false)} />}
    </div>
  )
}
