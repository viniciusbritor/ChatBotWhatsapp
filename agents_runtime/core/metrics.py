import threading
import time
from typing import Any, Dict

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry()

AGENTS_LOADED = Gauge(
    "agents_runtime_agents_loaded",
    "Agentes carregados no cache apos o ultimo reload atomico",
    registry=REGISTRY,
)
AGENTS_HEALTHY = Gauge(
    "agents_runtime_agents_healthy",
    "Agentes classificados como saudaveis",
    registry=REGISTRY,
)
AGENTS_DEGRADED = Gauge(
    "agents_runtime_agents_degraded",
    "Agentes classificados como degradados",
    registry=REGISTRY,
)
AGENTS_UNVERIFIED = Gauge(
    "agents_runtime_agents_unverified",
    "Agentes sem execucao ou probe recente",
    registry=REGISTRY,
)
AGENTS_IN_FLIGHT = Gauge(
    "agents_runtime_agents_in_flight",
    "Execucoes em andamento somadas em todos os agentes",
    registry=REGISTRY,
)

CHAT_REQUESTS = Counter(
    "agents_runtime_chat_requests_total",
    "Total de requisicoes /chat recebidas",
    ["outcome"],
    registry=REGISTRY,
)

CHAT_LATENCY = Histogram(
    "agents_runtime_chat_latency_seconds",
    "Latencia end-to-end de /chat",
    ("outcome",),
    registry=REGISTRY,
)

EMBEDDINGS_REQUESTS = Counter(
    "agents_runtime_embeddings_total",
    "Total de chamadas de embeddings",
    ("provider", "outcome"),
    registry=REGISTRY,
)

AUDIO_TRANSCRIPTIONS = Counter(
    "agents_runtime_audio_transcriptions_total",
    "Total de transcricoes de audio",
    ("outcome",),
    registry=REGISTRY,
)

INDEX_OPERATIONS = Counter(
    "agents_runtime_index_operations_total",
    "Operacoes de indexacao vetorial",
    ("collection", "outcome"),
    registry=REGISTRY,
)

_PROVIDER_LATENCY = Histogram(
    "agents_runtime_llm_provider_latency_seconds",
    "Latencia por provedor LLM",
    ("provider", "outcome"),
    registry=REGISTRY,
)

_LOCK = threading.RLock()
_LAST_OBSERVED: Dict[str, float] = {}


def _record_latency(hist: Histogram, *labels: str, started_at: float) -> None:
    elapsed = max(0.0, time.monotonic() - started_at)
    hist.labels(*labels).observe(elapsed)


def observe_inventory(inventory: Dict[str, Any]) -> None:
    counts = inventory.get("counts", {}) or {}
    with _LOCK:
        AGENTS_LOADED.set(int(counts.get("loaded", 0)))
        AGENTS_HEALTHY.set(int(counts.get("healthy", 0)))
        AGENTS_DEGRADED.set(int(counts.get("degraded", 0)))
        AGENTS_UNVERIFIED.set(int(counts.get("unverified", 0)))
        AGENTS_IN_FLIGHT.set(int(counts.get("in_flight", 0)))


def record_chat(started_at: float, *, success: bool, indexed: bool = False) -> None:
    outcome = "success" if success else "error"
    CHAT_REQUESTS.labels(outcome=outcome).inc()
    _record_latency(CHAT_LATENCY, outcome, started_at=started_at)


def record_chat_indexed(indexed: bool) -> None:
    outcome = "indexed" if indexed else "skipped"
    INDEX_OPERATIONS.labels(collection="memory", outcome=outcome).inc()


def record_embedding(provider: str, success: bool) -> None:
    outcome = "success" if success else "error"
    EMBEDDINGS_REQUESTS.labels(provider=provider, outcome=outcome).inc()


def record_audio_transcription(success: bool, *, empty: bool = False) -> None:
    if empty:
        outcome = "empty"
    elif success:
        outcome = "success"
    else:
        outcome = "error"
    AUDIO_TRANSCRIPTIONS.labels(outcome=outcome).inc()


def record_provider_latency(provider: str, success: bool, started_at: float) -> None:
    outcome = "success" if success else "error"
    _record_latency(_PROVIDER_LATENCY, provider, outcome, started_at=started_at)


def generate_metrics() -> bytes:
    return generate_latest(REGISTRY)


METRICS_CONTENT_TYPE = CONTENT_TYPE_LATEST


__all__ = [
    "observe_inventory",
    "record_chat",
    "record_chat_indexed",
    "record_embedding",
    "record_audio_transcription",
    "record_provider_latency",
    "generate_metrics",
    "METRICS_CONTENT_TYPE",
]
