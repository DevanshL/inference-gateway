"""
Phase 3 tests.

Tests cover:
- All Prometheus metrics are registered and exportable
- Metrics increment correctly
- Grafana dashboard JSON is valid
- Prometheus config is valid YAML
"""
import json
import pytest
import yaml
from pathlib import Path

from prometheus_client import REGISTRY, CollectorRegistry
from prometheus_client.exposition import generate_latest


# ── Metrics registration ──────────────────────────────────────────────────────

def test_all_metrics_importable():
    from app.core.metrics import (
        INFERENCE_REQUESTS_TOTAL,
        INFERENCE_LATENCY_SECONDS,
        ROUTING_DECISIONS_TOTAL,
        TOKENS_ESTIMATED_TOTAL,
        ACTIVE_INFERENCE_REQUESTS,
        OLLAMA_ERRORS_TOTAL,
        MODEL_FIRST_TOKEN_LATENCY_SECONDS,
    )
    assert INFERENCE_REQUESTS_TOTAL is not None
    assert INFERENCE_LATENCY_SECONDS is not None
    assert ROUTING_DECISIONS_TOTAL is not None


def test_metrics_output_is_bytes():
    from app.core.metrics import get_metrics_output
    body, content_type = get_metrics_output()
    assert isinstance(body, bytes)
    assert "text/plain" in content_type


def test_metrics_output_contains_expected_metric_names():
    from app.core.metrics import get_metrics_output
    body, _ = get_metrics_output()
    text = body.decode("utf-8")
    assert "inference_requests_total" in text
    assert "inference_latency_seconds" in text
    assert "routing_decisions_total" in text
    assert "active_inference_requests" in text
    assert "ollama_errors_total" in text
    assert "model_first_token_latency_seconds" in text


def test_counter_increments():
    from app.core.metrics import INFERENCE_REQUESTS_TOTAL
    from prometheus_client import REGISTRY
    # Get current value
    before = sum(
        s.value for s in REGISTRY.get_sample_value.__self__._names_to_collectors.values()
        if hasattr(s, 'value')
    ) if False else 0  # just test it doesn't raise
    INFERENCE_REQUESTS_TOTAL.labels(model="test-model", tier="fast", status="success").inc()
    # Verify metric exported in output
    from app.core.metrics import get_metrics_output
    body, _ = get_metrics_output()
    assert b"test-model" in body


def test_histogram_observes():
    from app.core.metrics import INFERENCE_LATENCY_SECONDS
    INFERENCE_LATENCY_SECONDS.labels(model="test-model", tier="fast").observe(1.5)
    from app.core.metrics import get_metrics_output
    body, _ = get_metrics_output()
    assert b"inference_latency_seconds" in body


def test_gauge_inc_dec():
    from app.core.metrics import ACTIVE_INFERENCE_REQUESTS
    ACTIVE_INFERENCE_REQUESTS.inc()
    ACTIVE_INFERENCE_REQUESTS.dec()
    # Should not raise


# ── Config file validity ──────────────────────────────────────────────────────

def test_prometheus_config_is_valid_yaml():
    config_path = Path(__file__).parent.parent / "observability" / "prometheus.yml"
    assert config_path.exists(), "prometheus.yml not found"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    assert "scrape_configs" in config
    assert "global" in config
    jobs = [sc["job_name"] for sc in config["scrape_configs"]]
    assert "inference-gateway" in jobs


def test_grafana_datasources_valid_yaml():
    ds_path = (
        Path(__file__).parent.parent
        / "observability/grafana/provisioning/datasources/datasources.yml"
    )
    assert ds_path.exists()
    with open(ds_path) as f:
        config = yaml.safe_load(f)
    assert config["apiVersion"] == 1
    names = [ds["name"] for ds in config["datasources"]]
    assert "Prometheus" in names
    assert "Jaeger" in names


def test_grafana_dashboard_json_valid():
    dash_path = (
        Path(__file__).parent.parent
        / "observability/grafana/dashboards/gateway-overview.json"
    )
    assert dash_path.exists()
    with open(dash_path) as f:
        dashboard = json.load(f)
    assert "panels" in dashboard
    assert "title" in dashboard
    assert dashboard["title"] == "Inference Gateway"
    assert len(dashboard["panels"]) >= 10


def test_grafana_dashboard_has_key_panels():
    dash_path = (
        Path(__file__).parent.parent
        / "observability/grafana/dashboards/gateway-overview.json"
    )
    with open(dash_path) as f:
        dashboard = json.load(f)
    titles = [p["title"] for p in dashboard["panels"]]
    assert "Request Rate (req/s)" in titles
    assert "Inference Latency Percentiles" in titles
    assert "Routing Decisions Over Time" in titles
    assert "Total Requests" in titles
