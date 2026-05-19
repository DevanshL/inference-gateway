import { useStore } from "./store"
import { useMetrics } from "./hooks/useMetrics"
import { Header } from "./components/Header"
import { Playground } from "./components/Playground"
import { Dashboard } from "./components/Dashboard"
import { AsyncJobs } from "./components/AsyncJobs"
import { Routing } from "./components/Routing"
import { DLQ } from "./components/DLQ"

export default function App() {
  const { activeTab, health } = useStore()
  useMetrics()

  const tabs = {
    playground: <Playground />,
    dashboard:  <Dashboard />,
    jobs:       <AsyncJobs />,
    routing:    <Routing />,
    dlq:        <DLQ />,
  }

  return (
    <div className="scanlines h-screen flex flex-col bg-bg overflow-hidden">
      <Header />
      {health === null && (
        <div className="bg-red/10 border-b border-red/20 px-6 py-2 text-xs font-mono text-red flex items-center gap-2">
          <span className="w-1.5 h-1.5 bg-red rounded-full animate-pulse" />
          Gateway not reachable at localhost:8000 — ensure python main.py is running
        </div>
      )}
      <main className="flex-1 overflow-hidden">
        {tabs[activeTab]}
      </main>
    </div>
  )
}
