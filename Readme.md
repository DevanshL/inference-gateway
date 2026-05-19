# Inference Gateway

A scalable, observable, and robust inference gateway bridging a backend FastAPI application with a React-based frontend dashboard. 

The system provides intelligent request routing, queueing with dead-letter recovery, comprehensive observability, and containerized deployment definitions.

## Architecture Flowchart

```mermaid
flowchart TD
    %% Styling
    classDef frontend fill:#e1f5fe,stroke:#0288d1,stroke-width:2px,color:#000
    classDef api fill:#e8f5e9,stroke:#388e3c,stroke-width:2px,color:#000
    classDef queue fill:#fff3e0,stroke:#f57c00,stroke-width:2px,color:#000
    classDef model fill:#fce4ec,stroke:#c2185b,stroke-width:2px,color:#000
    classDef obs fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#000

    Client["💻 React Dashboard UI"]:::frontend

    subgraph API ["API Layer (FastAPI)"]
        direction TB
        Gateway["⚡ Gateway Router"]:::api
        Classifier["🔀 Complexity Classifier"]:::api
        Recovery["🛠️ Dead Job Recovery Endpoint"]:::api
    end

    subgraph Processing ["Queue & Workers (Celery/Redis)"]
        direction TB
        Broker[("📥 Redis Message Broker")]:::queue
        Worker["⚙️ Celery Inference Worker"]:::queue
        DLQ[("💀 Redis Dead Letter Queue")]:::queue
    end

    subgraph Inference ["Models"]
        direction TB
        LocalModel["🧠 Simple Model (Direct)"]:::model
        Ollama["🤖 Ollama Model (Heavy)"]:::model
    end

    subgraph Observability ["Telemetry"]
        direction TB
        OTel["📡 OpenTelemetry SDK"]:::obs
        Prom["📊 Prometheus"]:::obs
        Jaeger["🔍 Jaeger Tracing"]:::obs
        Grafana["📈 Grafana Dashboards"]:::obs
    end

    %% Flow: Client to API
    Client <-->|"HTTP / WebSocket"| Gateway
    Gateway --> Classifier

    %% Flow: Routing
    Classifier -->|"Simple Query"| LocalModel
    Classifier -->|"Complex Query"| Broker

    %% Flow: Async Processing
    Broker -->|"Task (infer)"| Worker
    Worker -->|"Heavy Inference"| Ollama
    
    %% Flow: Failures
    Worker -.->|"Failed Tasks"| DLQ
    DLQ -.->|"Inspect/Recover"| Recovery

    %% Flow: Telemetry (Dotted lines)
    Gateway -.->|"Metrics & Traces"| OTel
    Worker -.->|"Metrics & Traces"| OTel
    OTel --> Prom
    OTel --> Jaeger
    Prom --> Grafana
```

## Project Structure

The project is structured into two primary components:

1. **`inference-gateway/`** - Backend Gateway Services
2. **`inference-gateway-ui/`** - Frontend React Dashboard

---

## Backend (`inference-gateway/`)

The backend architecture is designed across five phases to ensure a resilient and scalable inference platform.

### Phase 1: Core Gateway
- **FastAPI App Skeleton:** High-performance, async-first API framework.
- **Pydantic Config & SLA Thresholds:** Strongly typed configuration and Service Level Agreement definitions.
- **Ollama Client:** Asynchronous `httpx` client for interacting with Ollama models.
- **Basic Model Router:** A complexity classifier that dynamically routes requests to the appropriate model based on query complexity.

### Phase 2: Queue & Dead Letter Queue (DLQ)
- **Broker Setup:** Celery + Redis architecture for handling asynchronous inference tasks.
- **Task Definitions:** Predefined tasks for inference requests and retry logic.
- **Redis Streams DLQ:** Reliable Dead Letter Queue for managing and storing failed inference jobs.
- **Dead Job Recovery:** Dedicated endpoints to inspect and safely recover failed jobs from the DLQ.

### Phase 3: Observability
- **OpenTelemetry (OTel) SDK:** Comprehensive instrumentation across the gateway.
- **Performance Tracing:** `perf_counter` spans capturing detailed latency metrics per request.
- **Prometheus Metrics Exporter:** Exporting vital system and custom performance metrics.
- **Jaeger Trace Exporter:** Distributed tracing to track individual requests through the gateway and workers.
- **Grafana Dashboards:** Provisioned-as-code dashboards for immediate insight into system health, queue depth, and SLAs.

### Phase 4: Kubernetes Deployment
- **Minikube Setup:** Local development cluster configuration.
- **Manifests:** Deployment and Service definitions for backend components.
- **Horizontal Pod Autoscaling (HPA):** Dynamic scaling based on CPU utilization and Redis queue depth.
- **ConfigMaps:** Dynamic configuration injection for SLA thresholds without requiring pod restarts.

### Phase 5: Production Deployment (Render)
- **Render Setup:** `render.yaml` configuration for seamless PaaS deployment.
- **Dockerfile:** Production-optimized, multi-stage container images.
- **Managed Redis:** Utilizing Render's managed Redis instances for maximum reliability.

---

## Frontend (`inference-gateway-ui/`)

### Phase 6: React Dashboard
The frontend provides a real-time, interactive window into the gateway's operation and performance.
- **Tech Stack:** Built with Vite, React, Tailwind CSS, and Zustand for lightweight state management.
- **WebSocket Live Feed:** Real-time streaming of inference requests, completions, and system events.
- **Interactive Charts:** Powered by Recharts, visualizing key metrics like latency trends, model usage distribution, and active queue depth.
- **Request Inspector:** A dedicated trace viewer UI to inspect the complete lifecycle and routing decisions of individual inference requests.