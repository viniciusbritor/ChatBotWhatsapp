import asyncio
import hashlib
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.masker import mask_pii
from core.timezone import BRT, now_brt

logger = logging.getLogger(__name__)

MEMORY_COLLECTION = os.getenv("RAG_MEMORY_COLLECTION", "conversation-memory-v2")
PRIVATE_COLLECTION = os.getenv("RAG_PRIVATE_COLLECTION", "agent-knowledge-v2")
MEMORY_TTL_DAYS = int(os.getenv("MEMORY_TTL_DAYS", "90"))


def _owner_hash(phone: str) -> str:
    normalized = "".join(character for character in str(phone) if character.isdigit())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _now_brt() -> datetime:
    return now_brt()


def _get_firestore():
    try:
        from google.cloud import firestore

        project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT")
        if not project or os.getenv("FIRESTORE_EMULATOR_HOST"):
            return None
        return firestore.Client(project=project)
    except Exception as exc:
        logger.warning("Firestore unavailable: %s", exc)
        return None


def _embed_query_text(text: str) -> Optional[List[float]]:
    try:
        from core.rag import embed_query

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            coro = embed_query(text)
            try:
                return loop.run_until_complete(coro)
            except RuntimeError:
                pass
        return asyncio.run(embed_query(text))
    except Exception as exc:
        logger.warning("memory_manager.embed failed: %s", exc)
        return None


class MemoryManager:
    def __init__(self, ttl_days: int = MEMORY_TTL_DAYS):
        self.ttl_days = ttl_days
        self._db = _get_firestore()

    def remember(
        self,
        phone: str,
        text: str,
        role: str,
        agent_id: str,
        conversation_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        response_identity: str = "Jennifer",
    ) -> Dict[str, Any]:
        if self._db is None:
            return {"status": "skipped", "reason": "firestore_unavailable"}
        masked = mask_pii(text).strip()
        if len(masked) < 3:
            return {"status": "skipped", "reason": "empty_text"}
        embedding = _embed_query_text(masked)
        if embedding is None:
            return {"status": "skipped", "reason": "embedding_unavailable"}
        owner = _owner_hash(phone)
        stable_key = turn_id or f"{time.time_ns()}:{role}:{masked}"
        document_id = hashlib.sha256(f"{owner}:{stable_key}".encode("utf-8")).hexdigest()[:32]
        now = _now_brt()
        data = {
            "owner_hash": owner,
            "conversation_id": conversation_id or owner,
            "message_id": stable_key,
            "turn_id": stable_key,
            "direction": role,
            "agent_id": agent_id or "jennifier",
            "response_identity": response_identity,
            "text_masked": masked[:2000],
            "embedding": embedding,
            "embedding_model": os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small"),
            "embedding_dim": int(os.getenv("RAG_EMBEDDING_DIM", "1536")),
            "schema_version": int(os.getenv("RAG_SCHEMA_VERSION", "2")),
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=self.ttl_days)).isoformat(),
        }
        from google.cloud.firestore_v1.vector import Vector

        data["vector_embedding"] = Vector(embedding)
        self._db.collection(MEMORY_COLLECTION).document(document_id).set(data)
        return {"status": "indexed", "doc_id": document_id, "owner_hash": owner}

    def recall(
        self,
        phone: str,
        query: str,
        limit: int = 5,
        recency_weight: float = 0.3,
    ) -> List[Dict[str, Any]]:
        if self._db is None:
            return []
        owner = _owner_hash(phone)
        query_vec = _embed_query_text(query)
        if query_vec is None:
            return []
        from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
        from google.cloud.firestore_v1.vector import Vector

        coll = self._db.collection(MEMORY_COLLECTION)
        def execute():
            return list(
                coll.where("owner_hash", "==", owner)
                .where("schema_version", "==", 2)
                .find_nearest(
                    vector_field="vector_embedding",
                    query_vector=Vector(query_vec),
                    limit=max(1, min(int(limit), 20)),
                    distance_measure=DistanceMeasure.COSINE,
                    distance_result_field="vector_distance",
                )
                .get()
            )
        try:
            documents = execute()
        except Exception as exc:
            logger.warning("memory recall failed: %s", exc)
            return []
        now = _now_brt()
        results = []
        for d in documents:
            data = d.to_dict() or {}
            distance = float(data.get("vector_distance", 0.0))
            similarity = max(0.0, min(1.0, 1.0 - distance / 2.0))
            age_days = 0.0
            try:
                created = datetime.fromisoformat(data["created_at"])
                age_days = (now - created.astimezone(BRT)).total_seconds() / 86400.0
            except Exception:
                pass
            recency = max(0.0, 1.0 - age_days / max(1.0, self.ttl_days))
            score = (1 - recency_weight) * similarity + recency_weight * recency
            results.append(
                {
                    "doc_id": d.id,
                    "text": data.get("text_masked", ""),
                    "agent_id": data.get("agent_id", "jennifier"),
                    "direction": data.get("direction", "in"),
                    "response_identity": data.get("response_identity", "Jennifer"),
                    "similarity": round(similarity, 3),
                    "recency": round(recency, 3),
                    "score": round(score, 3),
                    "age_days": round(age_days, 1),
                    "created_at": data.get("created_at", ""),
                }
            )
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]

    def summarize_recent(self, phone: str, window_days: int = 7, limit: int = 20) -> Optional[str]:
        if self._db is None:
            return None
        owner = _owner_hash(phone)
        cutoff = _now_brt() - timedelta(days=window_days)
        def execute():
            return (
                self._db.collection(MEMORY_COLLECTION)
                .where("owner_hash", "==", owner)
                .where("created_at", ">=", cutoff.isoformat())
                .order_by("created_at", direction="DESCENDING")
                .limit(limit)
                .stream()
            )
        try:
            docs = list(execute())
        except Exception as exc:
            logger.warning("memory summarize fetch failed: %s", exc)
            return None
        messages = []
        for d in docs:
            data = d.to_dict() or {}
            role = data.get("direction", "in")
            text = (data.get("text_masked") or "")[:300]
            if not text:
                continue
            messages.append(f"{role}: {text}")
        if not messages:
            return None
        prompt = (
            "Resuma de forma concisa as mensagens do usuario nas ultimas "
            f"{window_days} dias (max 6 frases, pt-BR, tom Jennifer):\n\n"
            + "\n".join(messages)
        )
        try:
            from core.llm_provider import LLMProvider

            llm = LLMProvider()
            response = asyncio.run(
                llm.chat(
                    system_prompt="Voce e Jennifer. Resuma de forma concisa e calorosa.",
                    user_prompt=prompt,
                    model="MiniMax-M3",
                    json_mode=False,
                    temperature=0.3,
                    max_tokens=400,
                    thinking_disabled=True,
                )
            )
            if isinstance(response, dict):
                return response.get("content")
            return None
        except Exception as exc:
            logger.warning("memory summarize llm failed: %s", exc)
            return None


_default: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    global _default
    if _default is None:
        _default = MemoryManager()
    return _default
