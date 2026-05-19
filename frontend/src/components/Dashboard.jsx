import { LineChart, Line, AreaChart, Area, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts"
import { useStore } from "../store"

function StatCard({ label, value, unit = "", color = "text-accent" }) {
  return (
    <div className="bg-surface border border-border rounded p-4">
      <div className="text-xs text-muted font-mono mb-1">{label}</div>
      <div className={`text-3xl font-display font-bold ${color}`}>
        {value}<span className="text-lg ml-1 text-muted">{unit}</span>
      </div>
    </div>
  )
}

const TOOLTIP = { contentStyle: { background: "#0d1117", border: "1px solid #1e2631", borderRadius: 6, fontFamily: "JetBrains Mono", fontSize: 12 }, labelStyle: { color: "#c9d5e0" } }
const GRID = { strokeDasharray: "3 3", stroke: "#1e2631" }
const TICK = { fill: "#3d4f63", fontSize: 10, fontFamily: "JetBrains Mono" }

const TIER_COLORS_MAP = {
  fast:    "text-green  bg-green/10",
  quality: "text-purple bg-purple/10",
  code:    "text-accent bg-accent/10",
  vision:  "text-amber  bg-amber/10",
}

export function Dashboard() {
  const { metrics, latencyHistory, requestHistory } = useStore()

  const tierData = [
    { name: "fast",    value: metrics.fastTierCount || 0, color: "#00ff94" },
    { name: "quality", value: metrics.qualityTierCount || 0, color: "#9d4edd" },
    { name: "code",    value: metrics.codeTierCount || 0, color: "#00d4ff" },
    { name: "vision",  value: metrics.visionTierCount || 0, color: "#f59e0b" },
  ].filter(t => t.value > 0)

  const rateData = requestHistory.slice(0, 20).reverse().map((r, i) => ({ i, ms: r.total_ms }))

  return (
    <div className="p-4 overflow-y-auto h-full">
      <div className="grid grid-cols-6 gap-3 mb-4">
        <StatCard label="TOTAL REQUESTS" value={metrics.totalRequests} color="text-accent" />
        <StatCard label="SUCCESS RATE" value={metrics.successRate} unit="%" color={metrics.successRate >= 98 ? "text-green" : "text-amber"} />
        <StatCard label="ACTIVE" value={metrics.activeRequests} color={metrics.activeRequests > 0 ? "text-amber" : "text-muted"} />
        <StatCard label="ERRORS" value={metrics.errorCount} color={metrics.errorCount > 0 ? "text-red" : "text-green"} />
        <StatCard label="FAST / QUALITY" value={`${metrics.fastTierCount} / ${metrics.qualityTierCount}`} color="text-purple" />
        <StatCard label="CODE / VISION" value={`${metrics.codeTierCount} / ${metrics.visionTierCount}`} color="text-amber" />
      </div>

      <div className="grid grid-cols-3 gap-3 mb-3">
        <div className="col-span-2 bg-surface border border-border rounded p-4">
          <div className="text-xs text-muted font-mono mb-3">ACTIVE REQUESTS OVER TIME</div>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={latencyHistory}>
              <defs>
                <linearGradient id="activeGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#00d4ff" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#00d4ff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="time" tick={TICK} />
              <YAxis tick={TICK} />
              <Tooltip {...TOOLTIP} />
              <Area type="monotone" dataKey="active" stroke="#00d4ff" fill="url(#activeGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-surface border border-border rounded p-4">
          <div className="text-xs text-muted font-mono mb-3">ROUTING SPLIT</div>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={tierData} cx="50%" cy="50%" innerRadius={50} outerRadius={75} dataKey="value" paddingAngle={3}>
                {tierData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip {...TOOLTIP} />
              <Legend formatter={(v) => <span style={{ color: "#c9d5e0", fontFamily: "JetBrains Mono", fontSize: 11 }}>{v}</span>} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="bg-surface border border-border rounded p-4 mb-3">
        <div className="text-xs text-muted font-mono mb-3">RECENT REQUEST LATENCY (ms)</div>
        {rateData.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-muted text-sm font-mono">No requests yet — send a prompt in Playground</div>
        ) : (
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={rateData}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="i" hide />
              <YAxis tick={TICK} unit="ms" />
              <Tooltip {...TOOLTIP} formatter={(v) => [`${v?.toFixed(0)}ms`, "latency"]} />
              <Line type="monotone" dataKey="ms" stroke="#00d4ff" strokeWidth={2} dot={{ fill: "#00d4ff", r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="bg-surface border border-border rounded p-4">
        <div className="text-xs text-muted font-mono mb-3">RECENT REQUESTS</div>
        {requestHistory.length === 0 ? (
          <div className="text-muted text-sm font-mono">No requests yet</div>
        ) : (
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="text-muted border-b border-border">
                {["TIME","PROMPT","MODEL","TIER","LATENCY","STATUS"].map(h => <th key={h} className="text-left pb-2 pr-4">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {requestHistory.slice(0, 10).map((r, i) => (
                <tr key={i} className="border-b border-border/50 hover:bg-white/2 transition-colors">
                  <td className="py-2 pr-4 text-muted">{r.ts?.toLocaleTimeString()}</td>
                  <td className="py-2 pr-4 text-text max-w-xs truncate">{r.prompt?.slice(0, 50)}</td>
                  <td className="py-2 pr-4 text-accent">{r.model?.split(":")[0]}</td>
                  <td className="py-2 pr-4"><span className={`px-1.5 py-0.5 rounded text-xs border border-transparent ${TIER_COLORS_MAP[r.tier] || "text-muted bg-muted/10"}`}>{r.tier}</span></td>
                  <td className="py-2 pr-4 text-amber">{r.total_ms?.toFixed(0)}ms</td>
                  <td className="py-2"><span className={r.status === "success" ? "text-green" : "text-red"}>{r.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
