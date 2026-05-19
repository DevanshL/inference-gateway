import { useStore } from "../store"

export function Header() {
  const { health, metrics, dlqEntries, activeTab, setActiveTab } = useStore()
  const isOnline = health?.status === "ready"

  const tabs = [
    { id: "playground", label: "Playground" },
    { id: "dashboard",  label: "Dashboard" },
    { id: "jobs",       label: "Async Jobs" },
    { id: "routing",    label: "Routing" },
    { id: "dlq",        label: "DLQ" },
  ]

  return (
    <header className="border-b border-border bg-surface">
      <div className="flex items-center justify-between px-6 py-3">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-8 h-8 rounded border border-accent/40 flex items-center justify-center bg-accent/5">
              <span className="text-accent text-xs font-mono font-bold">IG</span>
            </div>
            <div className={`absolute -top-1 -right-1 w-2 h-2 rounded-full ${isOnline ? "bg-green animate-pulse" : "bg-red"}`} />
          </div>
          <div>
            <div className="text-bright font-display font-semibold text-sm tracking-wide">Inference Gateway</div>
            <div className="text-muted text-xs font-mono">
              {isOnline ? `${metrics.totalRequests} requests · ${metrics.successRate}% success` : "connecting..."}
            </div>
          </div>
        </div>

        <nav className="flex items-center gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-1.5 text-sm font-mono rounded transition-all ${
                activeTab === tab.id
                  ? "bg-accent/10 text-accent border border-accent/30"
                  : "text-muted hover:text-text hover:bg-white/5"
              }`}
            >
              {tab.label}
              {tab.id === "dlq" && dlqEntries.length > 0 && (
                <span className="ml-2 px-1.5 py-0.5 text-xs bg-red/20 text-red rounded-full">
                  {dlqEntries.length}
                </span>
              )}
            </button>
          ))}
        </nav>

        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="flex items-center gap-2">
            <span className="text-muted">active</span>
            <span className={`font-bold ${metrics.activeRequests > 0 ? "text-amber" : "text-muted"}`}>
              {metrics.activeRequests}
            </span>
          </div>
          <div className="w-px h-4 bg-border" />
          <a href="http://localhost:3000" target="_blank" rel="noreferrer" className="text-muted hover:text-accent transition-colors">Grafana ↗</a>
          <a href="http://localhost:16686" target="_blank" rel="noreferrer" className="text-muted hover:text-accent transition-colors">Jaeger ↗</a>
        </div>
      </div>
    </header>
  )
}
