import { create } from "zustand"

export const useStore = create((set) => ({
  health: null,
  models: [],
  setHealth: (health) => set({ health }),
  setModels: (models) => set({ models }),

  metrics: {
    totalRequests: 0,
    successRate: 100,
    activeRequests: 0,
    fastTierCount: 0,
    qualityTierCount: 0,
    codeTierCount: 0,
    visionTierCount: 0,
    errorCount: 0,
  },
  setMetrics: (metrics) => set({ metrics }),

  latencyHistory: [],
  addLatencyPoint: (point) =>
    set((s) => ({ latencyHistory: [...s.latencyHistory.slice(-29), point] })),

  requestHistory: [],
  addRequest: (req) =>
    set((s) => ({ requestHistory: [req, ...s.requestHistory.slice(0, 49)] })),

  jobs: {},
  addJob: (jobId, data) =>
    set((s) => ({ jobs: { ...s.jobs, [jobId]: data } })),
  updateJob: (jobId, data) =>
    set((s) => ({ jobs: { ...s.jobs, [jobId]: { ...s.jobs[jobId], ...data } } })),

  dlqEntries: [],
  setDlqEntries: (dlqEntries) => set({ dlqEntries }),

  // ── Persistent Playground state ───────────────────────────────────────────
  pg: {
    prompt: "", taskType: "general", forceTier: "", temperature: 0.7,
    streaming: true, response: null, streamText: "", routing: null,
    error: null, imageB64: null, imagePreview: null,
  },
  setPg: (patch) => set((s) => ({ pg: { ...s.pg, ...patch } })),

  activeTab: "playground",
  setActiveTab: (activeTab) => set({ activeTab }),
}))