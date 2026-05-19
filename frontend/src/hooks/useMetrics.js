import { useEffect, useRef } from "react"
import { api } from "../lib/api"
import { useStore } from "../store"

function extractCounter(text, metricName, labelFilter = "") {
  const lines = text.split("\n").filter(
    (l) => l.startsWith(metricName) && !l.startsWith("#") && l.includes(labelFilter)
  )
  return lines.reduce((sum, l) => {
    const match = l.match(/\s([\d.e+]+)$/)
    return sum + (match ? parseFloat(match[1]) : 0)
  }, 0)
}

function extractGauge(text, metricName) {
  const line = text.split("\n").find(
    (l) => l.startsWith(metricName) && !l.startsWith("#")
  )
  if (!line) return 0
  const match = line.match(/\s([\d.e+]+)$/)
  return match ? parseFloat(match[1]) : 0
}

export function useMetrics() {
  const { setMetrics, setHealth, setModels, addLatencyPoint } = useStore()
  const intervalRef = useRef(null)

  useEffect(() => {
    async function poll() {
      try {
        const health = await api.health()
        setHealth(health)

        const modelsData = await api.models()
        setModels(modelsData.models || [])

        const text = await api.metrics()

        const totalRequests  = extractCounter(text, "inference_requests_total")
        const successCount   = extractCounter(text, "inference_requests_total", 'status="success"')
        const errorCount     = extractCounter(text, "inference_requests_total", 'status="error"')
        const activeRequests = extractGauge(text, "active_inference_requests")
        const fastCount      = extractCounter(text, "routing_decisions_total", 'decision="fast"')
        const qualityCount   = extractCounter(text, "routing_decisions_total", 'decision="quality"')
        const codeCount      = extractCounter(text, "routing_decisions_total", 'decision="code"')
        const visionCount    = extractCounter(text, "routing_decisions_total", 'decision="vision"')

        setMetrics({
          totalRequests,
          successRate: totalRequests > 0 ? Math.round((successCount / totalRequests) * 100) : 100,
          activeRequests,
          errorCount,
          fastTierCount: fastCount,
          qualityTierCount: qualityCount,
          codeTierCount: codeCount,
          visionTierCount: visionCount,
        })

        addLatencyPoint({ time: new Date().toLocaleTimeString(), active: activeRequests })
      } catch (e) {
        setHealth(null)
      }
    }

    poll()
    intervalRef.current = setInterval(poll, 5000)
    return () => clearInterval(intervalRef.current)
  }, [])
}
