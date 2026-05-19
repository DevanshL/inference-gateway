import { useState, useRef, useEffect } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import remarkBreaks from "remark-breaks"
import { api } from "../lib/api"
import { useStore } from "../store"

const TASK_TYPES = ["general", "chat", "code", "reasoning", "summarise", "vision"]

const EXAMPLES = [
  { label: "Simple math",           content: "What is 2+2?",                                                                          type: "general" },
  { label: "BST implementation",    content: "Implement a binary search tree with insert, delete, and search in Python",              type: "code" },
  { label: "Architecture analysis", content: "Compare REST and GraphQL APIs — analyse trade-offs in detail",                         type: "reasoning" },
  { label: "Summarise",             content: "Summarise the key concepts of distributed systems in 5 bullet points",                 type: "summarise" },
  { label: "SQL query",             content: "Write a SQL query to find the top 10 customers by revenue with monthly breakdown",     type: "code" },
  { label: "Regex pattern",         content: "Write a regex to validate email addresses and explain each part",                      type: "code" },
]

const TIER_COLORS = {
  fast:    "text-green  border-green/30  bg-green/10",
  quality: "text-purple border-purple/30 bg-purple/10",
  code:    "text-accent border-accent/30 bg-accent/10",
  vision:  "text-amber  border-amber/30  bg-amber/10",
}

export function Playground() {
  const { addRequest, models, pg, setPg } = useStore()

  // Destructure persisted state from store
  const {
    prompt, taskType, forceTier, temperature, streaming,
    response, streamText, routing, error, imageB64, imagePreview,
  } = pg

  // Shorthand setters that patch only the changed field
  const setPrompt       = (v) => setPg({ prompt: v })
  const setTaskType     = (v) => setPg({ taskType: v })
  const setForceTier    = (v) => setPg({ forceTier: v })
  const setTemp         = (v) => setPg({ temperature: v })
  const setStreaming     = (v) => setPg({ streaming: v })
  const setResponse     = (v) => setPg({ response: v })
  const setStreamText   = (v) => setPg({ streamText: v })
  const setRouting      = (v) => setPg({ routing: v })
  const setError        = (v) => setPg({ error: v })
  const setImageB64     = (v) => setPg({ imageB64: v })
  const setImagePreview = (v) => setPg({ imagePreview: v })

  // Truly transient — don't need to survive tab switches
  const [loading, setLoading] = useState(false)
  const [copied,  setCopied]  = useState(false)

  const outputRef   = useRef(null)
  const textareaRef = useRef(null)
  const fileRef     = useRef(null)
  const abortRef    = useRef(false)

  // Auto-scroll
  useEffect(() => {
    if (outputRef.current)
      outputRef.current.scrollTop = outputRef.current.scrollHeight
  }, [streamText, response])

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = Math.min(el.scrollHeight, 300) + "px"
  }, [prompt])

  function handleImageUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      const img = new Image()
      img.onload = () => {
        // Resize to max 768px — LLaVA 7B works best at this resolution
        const MAX = 768
        let { width, height } = img
        if (width > MAX || height > MAX) {
          if (width > height) { height = Math.round(height * MAX / width); width = MAX }
          else                { width = Math.round(width * MAX / height); height = MAX }
        }
        const canvas = document.createElement("canvas")
        canvas.width  = width
        canvas.height = height
        canvas.getContext("2d").drawImage(img, 0, 0, width, height)
        // Compress to JPEG 0.85 quality — strips EXIF and massively reduces size
        const dataUrl = canvas.toDataURL("image/jpeg", 0.85)
        setImagePreview(dataUrl)
        setImageB64(dataUrl.split(",")[1])   // raw base64, no data URL prefix
        setTaskType("vision")
      }
      img.src = ev.target.result
    }
    reader.readAsDataURL(file)
  }

  function clearImage() {
    setImageB64(null)
    setImagePreview(null)
    if (fileRef.current) fileRef.current.value = ""
    if (taskType === "vision") setTaskType("general")
  }

  async function handleSubmit() {
    if (!prompt.trim() || loading) return
    setLoading(true)
    setResponse(null)
    setStreamText("")
    setRouting(null)
    setError(null)
    setCopied(false)
    abortRef.current = false

    const messages = [{ role: "user", content: prompt }]
    const start = Date.now()

    try {
      if (streaming) {
        const dec = await api.route(messages, taskType)
        setRouting(dec)
        let full = ""
        for await (const chunk of api.stream(messages, taskType, temperature, 1024, imageB64)) {
          if (abortRef.current) break
          full += chunk
          setStreamText(full)
        }
        addRequest({ prompt, model: dec.model, tier: dec.tier, total_ms: Date.now() - start, status: "success", ts: new Date() })
      } else {
        const res = await api.infer(messages, taskType, forceTier || null, temperature, 1024, imageB64)
        setResponse(res)
        setRouting(res.routing)
        if (res.status === "error") {
          setError(res.error || "Inference failed — check gateway logs")
        }
        addRequest({ prompt, model: res.model, tier: res.tier, total_ms: res.latency?.total_ms, status: res.status, ts: new Date() })
      }
    } catch (e) {
      if (!abortRef.current) setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function handleStop() {
    abortRef.current = true
    setLoading(false)
  }

  function handleClear() {
    setPrompt("")
    setResponse(null)
    setStreamText("")
    setRouting(null)
    setError(null)
    setCopied(false)
    clearImage()
    if (textareaRef.current) textareaRef.current.style.height = "auto"
  }

  async function handleCopy() {
    if (!content) return
    await navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const content = streaming ? streamText : response?.content
  const isStreaming = loading && streaming

  // Build dynamic tier options from available models
  const tierOptions = [
    { value: "",        label: "Auto (recommended)" },
    { value: "fast",    label: `Fast — ${models.find(m => m.includes("mistral")) || "mistral"}` },
    { value: "quality", label: `Quality — ${models.find(m => m.includes("llama")) || "llama3.2"}` },
    { value: "code",    label: `Code — ${models.find(m => m.includes("coder") || m.includes("deepseek")) || "qwen2.5-coder"}` },
    { value: "vision",  label: `Vision — ${models.find(m => m.includes("llava") || m.includes("vision")) || "llava"}` },
  ]

  return (
    <div className="flex h-full gap-4 p-4">
      {/* ── Left panel ── */}
      <div className="w-[420px] flex flex-col gap-3 flex-shrink-0 overflow-y-auto">

        {/* Examples */}
        <div>
          <div className="text-xs text-muted font-mono mb-2">EXAMPLES</div>
          <div className="grid grid-cols-2 gap-2">
            {EXAMPLES.map((ex) => (
              <button key={ex.label}
                onClick={() => { setPrompt(ex.content); setTaskType(ex.type) }}
                className="text-left px-3 py-2 rounded border border-border bg-surface hover:border-accent/40 hover:bg-accent/5 transition-all">
                <div className="text-xs text-accent font-mono">{ex.label}</div>
                <div className="text-xs text-muted mt-0.5 truncate">{ex.content.slice(0, 40)}...</div>
              </button>
            ))}
          </div>
        </div>

        {/* Image upload */}
        <div>
          <div className="text-xs text-muted font-mono mb-2">IMAGE (vision tier)</div>
          {imagePreview ? (
            <div className="relative">
              <img src={imagePreview} alt="upload" className="w-full h-32 object-cover rounded border border-border" />
              <button onClick={clearImage}
                className="absolute top-1 right-1 bg-bg border border-border rounded px-2 py-0.5 text-xs font-mono text-red hover:bg-red/10 transition-colors">
                Remove ✕
              </button>
            </div>
          ) : (
            <label className="flex items-center justify-center h-16 border border-dashed border-border rounded cursor-pointer hover:border-accent/40 hover:bg-accent/5 transition-all">
              <input ref={fileRef} type="file" accept="image/*" onChange={handleImageUpload} className="hidden" />
              <span className="text-xs text-muted font-mono">Click to upload image → routes to llava</span>
            </label>
          )}
        </div>

        {/* Prompt */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted font-mono">PROMPT</span>
            {(prompt || imageB64) && (
              <button onClick={handleClear} className="text-xs font-mono text-muted hover:text-red transition-colors">Clear ✕</button>
            )}
          </div>
          <textarea
            ref={textareaRef}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit() }
            }}
            placeholder="Enter your prompt... (Enter to send, Shift+Enter for new line)"
            rows={4}
            className="w-full bg-surface border border-border rounded px-3 py-2.5 text-sm text-text font-mono resize-none focus:outline-none focus:border-accent/50 transition-colors placeholder:text-muted/40 overflow-hidden"
          />
        </div>

        {/* Config */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="text-xs text-muted font-mono mb-1.5">TASK TYPE</div>
            <select value={taskType} onChange={(e) => setTaskType(e.target.value)}
              className="w-full bg-surface border border-border rounded px-3 py-2 text-sm text-text font-mono focus:outline-none focus:border-accent/50">
              {TASK_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <div className="text-xs text-muted font-mono mb-1.5">FORCE TIER</div>
            <select value={forceTier} onChange={(e) => setForceTier(e.target.value)}
              className="w-full bg-surface border border-border rounded px-3 py-2 text-sm text-text font-mono focus:outline-none focus:border-accent/50">
              {tierOptions.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
        </div>

        {/* Temperature + stream */}
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <div className="text-xs text-muted font-mono mb-1.5">TEMPERATURE: {temperature}</div>
            <input type="range" min="0" max="2" step="0.1" value={temperature}
              onChange={(e) => setTemp(parseFloat(e.target.value))} className="w-full accent-[#00d4ff]" />
          </div>
          <div className="flex items-center gap-2 mt-4">
            <button onClick={() => setStreaming(!streaming)}
              disabled={!!imageB64}
              className={`relative w-10 h-5 rounded-full transition-colors ${streaming && !imageB64 ? "bg-accent/30 border border-accent/50" : "bg-border opacity-50"}`}>
              <div className={`absolute top-0.5 w-4 h-4 rounded-full transition-all ${streaming && !imageB64 ? "left-5 bg-accent" : "left-0.5 bg-muted"}`} />
            </button>
            <span className="text-xs font-mono text-muted">stream</span>
          </div>
        </div>

        {/* Run / Stop */}
        {isStreaming ? (
          <button onClick={handleStop}
            className="w-full py-2.5 rounded font-mono text-sm font-medium border bg-red/10 border-red/40 text-red hover:bg-red/20 transition-all">
            Stop Generation ⏹
          </button>
        ) : (
          <button onClick={handleSubmit} disabled={loading || (!prompt.trim() && !imageB64)}
            className="w-full py-2.5 rounded font-mono text-sm font-medium border transition-all disabled:opacity-40 disabled:cursor-not-allowed enabled:bg-accent/10 enabled:border-accent/40 enabled:text-accent enabled:hover:bg-accent/20">
            {loading ? "Running inference..." : "Run Inference ⌘↵"}
          </button>
        )}

        {/* Routing decision */}
        {routing && (
          <div className="rounded border border-border bg-surface p-3 animate-fade-in">
            <div className="text-xs text-muted font-mono mb-2">ROUTING DECISION</div>
            <div className="flex items-center gap-2 mb-1.5">
              <span className={`px-2 py-0.5 rounded text-xs font-mono font-bold border ${TIER_COLORS[routing.tier] || "text-muted"}`}>
                {routing.tier}
              </span>
              <span className="text-sm text-bright font-mono">{routing.model}</span>
            </div>
            <div className="text-xs text-muted font-mono">{routing.reason}</div>
            <div className="flex gap-3 mt-2 text-xs font-mono text-muted">
              <span>~{routing.estimated_tokens} tokens</span>
              <span>complexity: {routing.complexity_score?.toFixed(2)}</span>
            </div>
          </div>
        )}

        {/* Available models */}
        {models.length > 0 && (
          <div className="rounded border border-border bg-surface p-3">
            <div className="text-xs text-muted font-mono mb-2">AVAILABLE MODELS</div>
            <div className="flex flex-wrap gap-1.5">
              {models.map((m) => (
                <span key={m} className="px-2 py-0.5 rounded border border-border text-xs font-mono text-muted">
                  {m}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Right panel — Output ── */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="text-xs text-muted font-mono mb-2 flex items-center justify-between">
          <span>OUTPUT</span>
          <div className="flex items-center gap-3">
            {response && (
              <span className="text-muted">
                {response.latency?.total_ms?.toFixed(0)}ms · {response.usage?.total_tokens} tokens · {response.model}
              </span>
            )}
            {content && !isStreaming && (
              <button onClick={handleCopy}
                className="text-xs font-mono px-2 py-0.5 rounded border border-border hover:border-accent/40 hover:text-accent transition-all">
                {copied ? "Copied ✓" : "Copy"}
              </button>
            )}
          </div>
        </div>

        <div ref={outputRef}
          className="flex-1 bg-surface border border-border rounded p-4 overflow-y-auto text-sm text-text leading-relaxed">
          {error && <div className="text-red font-mono animate-fade-in">[ERROR] {error}</div>}
          {!content && !error && !loading && (
            <div className="text-muted/40 italic font-mono">Response will appear here...</div>
          )}
          {content && (
            <div className="prose prose-invert prose-sm max-w-none
              prose-headings:text-bright prose-headings:font-display prose-headings:font-semibold
              prose-p:text-text prose-p:leading-relaxed prose-p:my-2
              prose-strong:text-accent prose-strong:font-semibold
              prose-li:text-text prose-li:my-0.5
              prose-ul:my-2 prose-ol:my-2
              prose-code:text-green prose-code:bg-bg prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:font-mono
              prose-pre:bg-bg prose-pre:border prose-pre:border-border prose-pre:rounded prose-pre:p-3
              prose-blockquote:border-accent/30 prose-blockquote:text-muted
              prose-hr:border-border">
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                {isStreaming ? content + " ▋" : content}
              </ReactMarkdown>
            </div>
          )}
          {loading && !streaming && (
            <div className="flex items-center gap-2 text-muted">
              {[0, 150, 300].map((d) => (
                <div key={d} className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce" style={{ animationDelay: `${d}ms` }} />
              ))}
            </div>
          )}
        </div>

        {/* Latency breakdown */}
        {response?.latency && (
          <div className="mt-3 flex gap-4 text-xs font-mono animate-slide-up">
            {[["routing", response.latency.routing_ms], ["model", response.latency.model_ms], ["total", response.latency.total_ms]].map(([label, val]) => (
              <div key={label} className="flex items-center gap-1.5">
                <span className="text-muted">{label}</span>
                <span className={`font-bold ${val > 10000 ? "text-amber" : val > 3000 ? "text-green" : "text-accent"}`}>
                  {val?.toFixed(0)}ms
                </span>
              </div>
            ))}
            {response.usage && (
              <>
                <div className="w-px bg-border" />
                <span className="text-muted">{response.usage.prompt_tokens}+{response.usage.completion_tokens} tokens</span>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}