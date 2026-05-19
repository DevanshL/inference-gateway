const BASE = import.meta.env.VITE_GATEWAY_URL || "http://localhost:8000"

export const api = {
  health: () => fetch(`${BASE}/health/ready`).then(r => r.json()),
  models: () => fetch(`${BASE}/health/models`).then(r => r.json()),

  infer: (messages, taskType = "general", forceTier = null, temperature = 0.7, maxTokens = 4096, imageB64 = null) =>
    fetch(`${BASE}/infer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages, task_type: taskType, force_tier: forceTier,
        temperature, max_tokens: maxTokens,
        ...(imageB64 && { image_b64: imageB64 }),
      }),
    }).then(r => r.json()),

  route: (messages, taskType = "general") =>
    fetch(`${BASE}/infer/route`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, task_type: taskType }),
    }).then(r => r.json()),

  enqueue: (messages, taskType = "general", forceTier = null) =>
    fetch(`${BASE}/infer/async`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, task_type: taskType, force_tier: forceTier }),
    }).then(r => r.json()),

  job: (jobId) => fetch(`${BASE}/jobs/${jobId}`).then(r => r.json()),
  dlq: () => fetch(`${BASE}/jobs/dlq/entries`).then(r => r.json()),
  metrics: () => fetch(`${BASE}/metrics`).then(r => r.text()),

  async *stream(messages, taskType = "general", temperature = 0.7, maxTokens = 4096, imageB64 = null) {
    const resp = await fetch(`${BASE}/infer/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages, task_type: taskType, stream: true,
        temperature, max_tokens: maxTokens,
        ...(imageB64 && { image_b64: imageB64 }),
      }),
    })
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split("\n")
      buffer = lines.pop()
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const chunk = line.slice(6)
          if (chunk === "[DONE]") return
          if (chunk.startsWith("[ERROR]")) throw new Error(chunk)
          if (chunk) {
            try {
              yield JSON.parse(chunk)
            } catch {
              yield chunk
            }
          }
        }
      }
    }
  },
}