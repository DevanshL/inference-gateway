import { useState } from "react"
import { api } from "../lib/api"

export function Routing() {
  const [prompt, setPrompt]     = useState("")
  const [taskType, setTaskType] = useState("general")
  const [result, setResult]     = useState(null)
  const [loading, setLoading]   = useState(false)
  const [history, setHistory]   = useState([])

  async function analyze() {
    if (!prompt.trim()) return
    setLoading(true)
    try {
      const res = await api.route([{ role: "user", content: prompt }], taskType)
      setResult(res)
      setHistory(h => [{ prompt, taskType, ...res, ts: new Date() }, ...h.slice(0, 19)])
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  const complexityPct = result ? Math.round(result.complexity_score * 100) : 0

  return (
    <div className="p-4 h-full flex gap-4">
      <div className="w-96 flex-shrink-0 flex flex-col gap-3">
        <div className="text-xs text-muted font-mono">ROUTING ANALYSER</div>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); analyze() }
          }}
          placeholder="Enter prompt to analyze... (Enter to submit, Shift+Enter for new line)" rows={7}
          className="w-full bg-surface border border-border rounded px-3 py-2.5 text-sm font-mono text-text resize-none focus:outline-none focus:border-accent/50 placeholder:text-muted/40" />
        <select value={taskType} onChange={(e) => setTaskType(e.target.value)}
          className="w-full bg-surface border border-border rounded px-3 py-2 text-sm font-mono text-text focus:outline-none">
          {["general","chat","code","reasoning","summarise"].map(t => <option key={t}>{t}</option>)}
        </select>
        <button onClick={analyze} disabled={loading || !prompt.trim()}
          className="w-full py-2.5 rounded font-mono text-sm border transition-all disabled:opacity-40 disabled:cursor-not-allowed enabled:bg-accent/10 enabled:border-accent/40 enabled:text-accent enabled:hover:bg-accent/20">
          {loading ? "Analysing..." : "Analyse Routing"}
        </button>
        <div className="border border-border rounded p-3 text-xs font-mono space-y-2">
          <div className="text-text mb-1">Current Thresholds</div>
          {[["token threshold","≤ 300"],["complexity threshold","< 0.40"],["fast model","mistral:latest"],["quality model","llama3.2:latest"]].map(([k,v]) => (
            <div key={k} className="flex justify-between text-muted"><span>{k}</span><span className="text-accent">{v}</span></div>
          ))}
        </div>
      </div>

      <div className="flex-1 flex flex-col gap-4 overflow-hidden">
        {result && (
          <div className="bg-surface border border-border rounded p-5 animate-fade-in">
            <div className="flex items-center gap-4 mb-4">
              <div className={`text-4xl font-display font-bold ${result.tier === "fast" ? "text-green" : "text-purple"}`}>
                {result.tier === "fast" ? "FAST" : "QUALITY"}
              </div>
              <div>
                <div className="text-bright font-mono text-sm">{result.model}</div>
                <div className="text-muted text-xs font-mono mt-0.5">{result.reason}</div>
              </div>
            </div>
            {[
              { label: "COMPLEXITY SCORE", value: result.complexity_score?.toFixed(3), pct: Math.min(complexityPct * 2.5, 100), threshold: "threshold: 0.40", high: complexityPct >= 40 },
              { label: "ESTIMATED TOKENS", value: result.estimated_tokens, pct: Math.min((result.estimated_tokens / 600) * 100, 100), threshold: "threshold: 300", high: result.estimated_tokens > 300 },
            ].map(({ label, value, pct, threshold, high }) => (
              <div key={label} className="mb-3">
                <div className="flex justify-between text-xs font-mono text-muted mb-1.5">
                  <span>{label}</span>
                  <span className={high ? "text-amber" : "text-green"}>{value}</span>
                </div>
                <div className="h-2 bg-bg rounded-full overflow-hidden border border-border">
                  <div className={`h-full rounded-full transition-all duration-700 ${high ? "bg-amber" : "bg-green"}`} style={{ width: `${pct}%` }} />
                </div>
                <div className="flex justify-between text-xs font-mono text-muted mt-1">
                  <span>low</span><span className="text-muted/50">{threshold}</span><span>high</span>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          <div className="text-xs text-muted font-mono mb-2">HISTORY</div>
          {history.length === 0 ? (
            <div className="text-muted font-mono text-sm">Analyse a prompt to see history</div>
          ) : (
            <div className="space-y-2">
              {history.map((h, i) => (
                <div key={i} className="flex items-center gap-3 py-2 px-3 border border-border rounded bg-surface text-xs font-mono">
                  <span className={`w-14 text-center py-0.5 rounded border ${h.tier === "fast" ? "text-green border-green/30 bg-green/5" : "text-purple border-purple/30 bg-purple/5"}`}>{h.tier}</span>
                  <span className="text-muted flex-1 truncate">{h.prompt?.slice(0, 60)}</span>
                  <span className="text-muted/50">c={h.complexity_score?.toFixed(2)}</span>
                  <span className="text-muted/50">{h.estimated_tokens}t</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
