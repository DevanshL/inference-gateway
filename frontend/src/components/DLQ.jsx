import { useState, useEffect } from "react"
import { api } from "../lib/api"

export function DLQ() {
  const [entries, setEntries] = useState([])
  const [total, setTotal]     = useState(0)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try {
      const res = await api.dlq()
      setEntries(res.entries || [])
      setTotal(res.total || 0)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-xs text-muted font-mono">DEAD LETTER QUEUE</div>
          <div className="text-sm font-mono mt-0.5">
            <span className={total > 0 ? "text-red" : "text-green"}>{total} entries</span>
            <span className="text-muted ml-2">— failed / timed-out jobs</span>
          </div>
        </div>
        <button onClick={load} className="px-3 py-1.5 text-xs font-mono border border-border rounded text-muted hover:text-text hover:border-accent/30 transition-all">Refresh</button>
      </div>
      {loading ? (
        <div className="flex items-center justify-center flex-1 text-muted font-mono text-sm">Loading...</div>
      ) : entries.length === 0 ? (
        <div className="flex flex-col items-center justify-center flex-1 gap-3">
          <div className="text-4xl">✓</div>
          <div className="text-green font-mono text-sm">DLQ is empty — all jobs succeeded</div>
          <div className="text-muted font-mono text-xs">Failed or timed-out jobs appear here for inspection</div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-3">
          {entries.map((entry, i) => (
            <div key={i} className="bg-surface border border-red/20 rounded p-4 animate-fade-in">
              <div className="flex items-start justify-between mb-2">
                <span className="px-2 py-0.5 rounded border text-xs font-mono text-red border-red/30 bg-red/5">{entry.error_type}</span>
                <span className="text-xs font-mono text-muted">{entry.failed_at?.slice(11, 19)}</span>
              </div>
              <div className="text-sm font-mono text-red/80 mb-2">{entry.error}</div>
              {entry.payload?.messages?.[0]?.content && (
                <div className="text-xs font-mono text-muted bg-bg rounded p-2 truncate">{entry.payload.messages[0].content}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
