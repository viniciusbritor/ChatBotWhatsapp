import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo


_STANDARD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="milliseconds"),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_FIELDS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    # Suprime UserWarning de DEPRECIACAO do SDK Firestore sobre
    # ".where() posicional". O SDK ainda suporta; a migracao para
    # FieldFilter e backlog (BACKLOG 12/08/2026). Filtro especifico,
    # nao esconde outros warnings.
    try:
        import warnings as _warnings
        _warnings.filterwarnings(
            "ignore",
            message="Detected filter using positional arguments. Prefer using the",
            category=UserWarning,
        )
    except Exception:
        pass

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
