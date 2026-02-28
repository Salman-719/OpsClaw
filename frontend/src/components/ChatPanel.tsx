import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { api, type ChatResponse } from '../api'

interface Message {
  role: 'user' | 'assistant'
  content: string
  tools?: ChatResponse['tool_calls']
}

export default function ChatPanel({ onClose }: { onClose: () => void }) {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: "Hi! I'm **OpsClaw**, your Chief of Operations AI. Ask me anything about Conut's branches, forecasts, combos, staffing, expansion, or growth strategy." },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const send = async () => {
    const msg = input.trim()
    if (!msg || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setLoading(true)

    try {
      const res = await api.chat(msg)
      setMessages(prev => [...prev, { role: 'assistant', content: res.answer, tools: res.tool_calls }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err instanceof Error ? err.message : 'Unknown error'}` }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed bottom-24 right-6 z-40 w-[420px] h-[600px] bg-white rounded-2xl shadow-2xl border border-gray-200 flex flex-col overflow-hidden animate-fade-in-up">
      {/* Header */}
      <div className="bg-brand-600 px-4 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-white/20 rounded-full flex items-center justify-center text-white text-xs font-bold">C</div>
          <div>
            <div className="text-white font-semibold text-sm">OpsClaw Agent</div>
            <div className="text-brand-200 text-[10px]">Conut Operations AI</div>
          </div>
        </div>
        <button onClick={onClose} className="text-white/70 hover:text-white">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 chat-scroll">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'} animate-fade-in-up`}>
            <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
              m.role === 'user'
                ? 'bg-brand-600 text-white rounded-br-md'
                : 'bg-gray-100 text-gray-800 rounded-bl-md'
            }`}>
              {m.role === 'assistant' ? (
                <div className="chat-md">
                  <ReactMarkdown>{m.content}</ReactMarkdown>
                </div>
              ) : m.content}

              {m.tools && m.tools.length > 0 && (
                <div className="mt-2 pt-2 border-t border-gray-200/50">
                  <div className="text-[10px] text-gray-500 mb-1">Tools used:</div>
                  <div className="flex flex-wrap gap-1">
                    {m.tools.map((t, j) => (
                      <span key={j} className="inline-block bg-gray-200 text-gray-600 text-[10px] px-1.5 py-0.5 rounded">
                        {t.tool}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start animate-fade-in-up">
            <div className="bg-gray-100 rounded-2xl rounded-bl-md px-4 py-3">
              <div className="flex gap-1.5">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="p-3 border-t border-gray-100 shrink-0">
        <form onSubmit={e => { e.preventDefault(); send() }} className="flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Ask about operations..."
            className="flex-1 bg-gray-100 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white rounded-xl px-4 py-2.5 text-sm font-medium transition-colors"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  )
}
