import { useState, useEffect, useRef } from "react"
import { api } from "../lib/api"
import { useStore } from "../store"

const STATUS_COLOR = {
  queued:     "text-amber border-amber/30 bg-amber/5",
  processing: "text-accent border-accent/30 bg-accent/5",
  success:    "text-green border-green/30 bg-green/5",
  failed:     "text-red border-red/30 bg-red/5",
  timeout:    "text-red border-red/30 bg-red/5",
}

function JobCard({ job }) {
  const isTerminal = ["success", "failed", "timeout"].includes(job.status)
  return (
    <div className="bg-surface border border-border rounded p-4 animate-slide-up">
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded border text-xs font-mono ${STATUS_COLOR[job.status] || "text-muted"}`}>{job.status}</span>
          {!isTerminal && <span className="w-1.5 h-1.5 bg-accent rounded-full animate-pulse" />}
        </div>
        <div className="text-xs text-muted font-mono">{job.job_id?.slice(0, 8)}...</div>
      </div>
      {job.model && <div className="text-xs font-mono text-muted mb-1"><span className="text-accent">{job.model}</span>{job.tier && <span className="ml-2">({job.tier})</span>}</div>}
      {job.content && <div className="mt-2 text-sm font-mono text-text bg-bg rounded p-3 max-h-32 overflow-y-auto whitespace-pre-wrap">{job.content}</div>}
      {job.error && <div className="mt-2 text-sm font-mono text-red bg-red/5 rounded p-3">[ERROR] {job.error}</div>}
      {job.latency && (
        <div className="mt-2 flex gap-3 text-xs font-mono text-muted">
          <span>routing: <b className="text-accent">{job.latency.routing_ms?.toFixed(0)}ms</b></span>
          <span>model: <b className="text-accent">{job.latency.model_ms?.toFixed(0)}ms</b></span>
          <span>total: <b className="text-amber">{job.latency.total_ms?.toFixed(0)}ms</b></span>
        </div>
      )}
      {job.usage && <div className="mt-1 text-xs font-mono text-muted">{job.usage.total_tokens} tokens</div>}
    </div>
  )
}

export function AsyncJobs() {
  const [prompt, setPrompt]     = useState("")
  const [taskType, setTaskType] = useState("general")
  const [loading, setLoading]   = useState(false)
  const { jobs, addJob, updateJob } = useStore()
  const pollRefs = useRef({})

  async function handleEnqueue() {
    if (!prompt.trim() || loading) return
    setLoading(true)
    try {
      const res = await api.enqueue([{ role: "user", content: prompt }], taskType)
      addJob(res.job_id, { job_id: res.job_id, status: "queued", prompt })
      pollJob(res.job_id)
      setPrompt("")
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  function pollJob(jobId) {
    if (pollRefs.current[jobId]) return
    const interval = setInterval(async () => {
      try {
        const job = await api.job(jobId)
        updateJob(jobId, job)
        if (["success", "failed", "timeout"].includes(job.status)) {
          clearInterval(interval)
          delete pollRefs.current[jobId]
        }
      } catch (e) { clearInterval(interval) }
    }, 1500)
    pollRefs.current[jobId] = interval
  }

  useEffect(() => () => Object.values(pollRefs.current).forEach(clearInterval), [])

  const jobList = Object.values(jobs).reverse()

  return (
    <div className="p-4 h-full flex gap-4">
      <div className="w-80 flex-shrink-0 flex flex-col gap-3">
        <div className="text-xs text-muted font-mono">ENQUEUE ASYNC JOB</div>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleEnqueue() }
          }}
          placeholder="Enter prompt... (Enter to enqueue, Shift+Enter for new line)" rows={6}
          className="w-full bg-surface border border-border rounded px-3 py-2.5 text-sm font-mono text-text resize-none focus:outline-none focus:border-accent/50 placeholder:text-muted/40" />
        <select value={taskType} onChange={(e) => setTaskType(e.target.value)}
          className="w-full bg-surface border border-border rounded px-3 py-2 text-sm font-mono text-text focus:outline-none focus:border-accent/50">
          {["general","chat","code","reasoning","summarise"].map(t => <option key={t}>{t}</option>)}
        </select>
        <button onClick={handleEnqueue} disabled={loading || !prompt.trim()}
          className="w-full py-2.5 rounded font-mono text-sm font-medium border transition-all disabled:opacity-40 disabled:cursor-not-allowed enabled:bg-accent/10 enabled:border-accent/40 enabled:text-accent enabled:hover:bg-accent/20">
          {loading ? "Enqueueing..." : "Enqueue Job →"}
        </button>
        <div className="text-xs text-muted font-mono space-y-1 border border-border rounded p-3">
          <div className="text-text mb-2">How it works:</div>
          <div>1. Job queued → Celery picks up</div>
          <div>2. Worker routes to model tier</div>
          <div>3. Ollama runs inference</div>
          <div>4. Result stored in Redis</div>
          <div>5. Status auto-polls every 1.5s</div>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        <div className="text-xs text-muted font-mono mb-3">JOBS ({jobList.length})</div>
        {jobList.length === 0 ? (
          <div className="flex items-center justify-center h-48 text-muted font-mono text-sm">No jobs yet — enqueue one</div>
        ) : (
          <div className="space-y-3">{jobList.map((job) => <JobCard key={job.job_id} job={job} />)}</div>
        )}
      </div>
    </div>
  )
}
