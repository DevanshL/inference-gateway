from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

ROUTING_DECISIONS_TOTAL = Counter("routing_decisions_total", "Desc", ["decision", "reason"])
TOKENS_ESTIMATED_TOTAL = Counter("tokens_estimated_total", "Desc", ["model"])
INFERENCE_REQUESTS_TOTAL = Counter("inference_requests_total", "Desc", ["model", "tier", "status"])
OLLAMA_ERRORS_TOTAL = Counter("ollama_errors_total", "Desc", ["model", "error_type"])
ACTIVE_INFERENCE_REQUESTS = Gauge("active_inference_requests", "Desc")
MODEL_FIRST_TOKEN_LATENCY_SECONDS = Histogram("model_first_token_latency_seconds", "Desc", ["model"])
INFERENCE_LATENCY_SECONDS = Histogram("inference_latency_seconds", "Desc", ["model", "tier"])

def get_metrics_output():
    return generate_latest(), CONTENT_TYPE_LATEST
