from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from research_x.memory.answer import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_OPENAI_MODEL,
    OPENAI_COMPATIBLE_PRESETS,
    _api_key,
    _extract_chat_text,
    _json_hash,
    _post_json,
)
from research_x.memory.api_budget import api_units, budgeted_api_call, rough_text_tokens
from research_x.memory.schema import ensure_memory_schema, memory_document_count

RELATION_JUDGE_ROLE = "answer_engine"
DEFAULT_PROMPT_VERSION = "memory-relation-judge-v1"
FAKE_JUDGE_MODEL = "fake-relation-judge-v1"
DEFAULT_CANDIDATE_RELATION_TYPES = ("obsolete_candidate",)
JUDGED_RELATION_TYPES = {"supports", "contradicts"}


@dataclass(frozen=True)
class RelationJudgeCandidate:
    candidate_id: str
    relation_id: str
    relation_type: str
    evidence_doc_id: str
    assessed_doc_id: str
    evidence_title: str
    evidence_text: str
    assessed_title: str
    assessed_text: str
    evidence_json: dict[str, Any]

    def as_prompt_item(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_relation_type": self.relation_type,
            "evidence_doc_id": self.evidence_doc_id,
            "assessed_doc_id": self.assessed_doc_id,
            "evidence_title": self.evidence_title,
            "evidence_text": _truncate(self.evidence_text, 1200),
            "assessed_title": self.assessed_title,
            "assessed_text": _truncate(self.assessed_text, 1200),
            "candidate_evidence": self.evidence_json,
        }


@dataclass(frozen=True)
class RelationJudgeDecision:
    candidate_id: str
    relation_type: str
    confidence: float
    rationale: str
    evidence_status: str = "inference"
    raw_response_hash: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RelationJudgeSummary:
    db_path: str
    provider: str
    provider_role: str
    model: str
    prompt_version: str
    candidates: int
    decisions: int
    accepted: int
    inserted: int
    skipped: int
    dry_run: bool
    by_type: dict[str, int]


class RelationJudgeProvider(Protocol):
    provider_id: str
    provider_role: str
    model: str

    def judge(
        self,
        candidates: tuple[RelationJudgeCandidate, ...],
        *,
        prompt_version: str,
    ) -> tuple[RelationJudgeDecision, ...]:
        """Judge whether newer/local evidence supports or contradicts an assessed document."""


class FakeRelationJudgeProvider:
    provider_id = "fake"
    provider_role = RELATION_JUDGE_ROLE

    def __init__(self, *, model: str = FAKE_JUDGE_MODEL) -> None:
        self.model = model

    def judge(
        self,
        candidates: tuple[RelationJudgeCandidate, ...],
        *,
        prompt_version: str,
    ) -> tuple[RelationJudgeDecision, ...]:
        decisions: list[RelationJudgeDecision] = []
        for candidate in candidates:
            evidence_text = f"{candidate.evidence_title}\n{candidate.evidence_text}"
            assessed_text = f"{candidate.assessed_title}\n{candidate.assessed_text}"
            shared = _shared_signal_terms(evidence_text, assessed_text)
            lowered = evidence_text.casefold()
            if any(marker in lowered for marker in _CONTRADICTION_MARKERS):
                relation_type = "contradicts"
                confidence = 0.74 if shared else 0.58
                rationale = (
                    "deterministic fake judge: newer evidence contains staleness/negative "
                    "wording."
                )
            elif len(shared) >= 2:
                relation_type = "supports"
                confidence = 0.62
                rationale = (
                    "deterministic fake judge: documents share multiple topic terms and no "
                    "contradiction marker was found."
                )
            else:
                relation_type = "no_relation"
                confidence = 0.25
                rationale = "deterministic fake judge: insufficient shared topical signal."
            decisions.append(
                RelationJudgeDecision(
                    candidate_id=candidate.candidate_id,
                    relation_type=relation_type,
                    confidence=confidence,
                    rationale=f"{rationale} shared_terms={sorted(shared)[:8]}",
                )
            )
        return tuple(decisions)


class OpenAICompatibleRelationJudgeProvider:
    provider_role = RELATION_JUDGE_ROLE

    def __init__(
        self,
        *,
        provider_id: str,
        base_url: str,
        api_key_env: str,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self.provider_id = provider_id
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.model = model
        self.timeout_seconds = timeout_seconds

    def judge(
        self,
        candidates: tuple[RelationJudgeCandidate, ...],
        *,
        prompt_version: str,
    ) -> tuple[RelationJudgeDecision, ...]:
        if not candidates:
            return ()
        payload = {
            "model": self.model,
            "messages": _judge_messages(candidates, prompt_version=prompt_version),
            "temperature": 0,
        }
        raw = _post_json_budgeted(
            f"{self.base_url}/chat/completions",
            payload,
            headers={"Authorization": f"Bearer {_api_key(self.api_key_env)}"},
            timeout_seconds=self.timeout_seconds,
            budget_provider=self.provider_id,
            budget_model=self.model,
            budget_units=api_units(
                calls=3,
                retries=2,
                input_tokens=rough_text_tokens(payload),
                documents=len(candidates),
            ),
        )
        raw_hash = _json_hash(raw)
        parsed = _extract_json_object(_extract_chat_text(raw))
        decisions = parsed.get("decisions")
        if not isinstance(decisions, list):
            raise RuntimeError("relation judge response did not include decisions[]")
        candidate_ids = {candidate.candidate_id for candidate in candidates}
        result: list[RelationJudgeDecision] = []
        for item in decisions:
            if not isinstance(item, dict):
                continue
            candidate_id = str(item.get("candidate_id") or "")
            if candidate_id not in candidate_ids:
                continue
            relation_type = _normalize_judged_relation_type(str(item.get("relation_type") or ""))
            confidence = _bounded_float(item.get("confidence"), default=0.0)
            rationale = _truncate(str(item.get("rationale") or ""), 600)
            result.append(
                RelationJudgeDecision(
                    candidate_id=candidate_id,
                    relation_type=relation_type,
                    confidence=confidence,
                    rationale=rationale,
                    raw_response_hash=raw_hash,
                )
            )
        return tuple(result)


def judge_memory_relations(
    db_path: str | Path,
    *,
    provider: str = "fake",
    model: str | None = None,
    api_key_env: str | None = None,
    base_url: str | None = None,
    candidate_relation_types: tuple[str, ...] | None = None,
    limit: int = 50,
    batch_size: int = 10,
    min_confidence: float = 0.55,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    timeout_seconds: float = 90.0,
    store: bool = True,
) -> RelationJudgeSummary:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    provider_impl = _provider(
        provider,
        model=model,
        api_key_env=api_key_env,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )
    candidate_types = candidate_relation_types or DEFAULT_CANDIDATE_RELATION_TYPES
    with sqlite3.connect(path, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        ensure_memory_schema(conn)
        if memory_document_count(conn) == 0:
            raise RuntimeError("memory_documents is empty; run memory build-corpus first")
        candidates = _load_candidates(
            conn,
            relation_types=tuple(dict.fromkeys(candidate_types)),
            limit=max(1, limit),
        )
        now = _utc_now()
        decisions: list[RelationJudgeDecision] = []
        accepted = 0
        inserted = 0
        skipped = 0
        by_type: Counter[str] = Counter()
        for batch in _chunks(candidates, max(1, batch_size)):
            batch_decisions = provider_impl.judge(batch, prompt_version=prompt_version)
            decisions.extend(batch_decisions)
            decision_by_candidate = {
                decision.candidate_id: decision for decision in batch_decisions
            }
            batch_inserted = 0
            for candidate in batch:
                decision = decision_by_candidate.get(candidate.candidate_id)
                if (
                    decision is None
                    or decision.relation_type not in JUDGED_RELATION_TYPES
                    or decision.confidence < min_confidence
                ):
                    skipped += 1
                    continue
                accepted += 1
                by_type[decision.relation_type] += 1
                if store:
                    _store_judged_relation(
                        conn,
                        candidate,
                        decision,
                        provider=provider_impl,
                        prompt_version=prompt_version,
                        now=now,
                    )
                    inserted += 1
                    batch_inserted += 1
            if store:
                _store_tool_call(
                    conn,
                    provider=provider_impl,
                    prompt_version=prompt_version,
                    batch=batch,
                    decisions=batch_decisions,
                    inserted=batch_inserted,
                    now=now,
                )
    return RelationJudgeSummary(
        db_path=str(path),
        provider=provider_impl.provider_id,
        provider_role=provider_impl.provider_role,
        model=provider_impl.model,
        prompt_version=prompt_version,
        candidates=len(candidates),
        decisions=len(decisions),
        accepted=accepted,
        inserted=inserted,
        skipped=skipped,
        dry_run=not store,
        by_type=dict(sorted(by_type.items())),
    )


def relation_judge_summary_json(summary: RelationJudgeSummary) -> str:
    return json.dumps(asdict(summary), ensure_ascii=False, indent=2, sort_keys=True)


def format_relation_judge_summary(summary: RelationJudgeSummary) -> str:
    return "\n".join(
        [
            f"db: {summary.db_path}",
            f"provider: {summary.provider}/{summary.model}",
            f"prompt: {summary.prompt_version}",
            f"candidates: {summary.candidates}",
            f"decisions: {summary.decisions}",
            f"accepted: {summary.accepted}",
            f"inserted: {summary.inserted}",
            f"skipped: {summary.skipped}",
            f"dry_run: {summary.dry_run}",
            f"by_type: {summary.by_type or {}}",
        ]
    )


def summary_as_dict(summary: RelationJudgeSummary) -> dict[str, Any]:
    return asdict(summary)


def _provider(
    provider: str,
    *,
    model: str | None,
    api_key_env: str | None,
    base_url: str | None,
    timeout_seconds: float,
) -> RelationJudgeProvider:
    provider_id = provider.strip().lower()
    if provider_id == "fake":
        return FakeRelationJudgeProvider(model=model or FAKE_JUDGE_MODEL)
    if provider_id == "openai_compatible":
        if not base_url:
            raise ValueError("--base-url is required for openai_compatible")
        return OpenAICompatibleRelationJudgeProvider(
            provider_id=provider_id,
            base_url=base_url,
            api_key_env=api_key_env or "OPENAI_API_KEY",
            model=model or DEFAULT_OPENAI_MODEL,
            timeout_seconds=timeout_seconds,
        )
    if provider_id in OPENAI_COMPATIBLE_PRESETS:
        preset = OPENAI_COMPATIBLE_PRESETS[provider_id]
        default_model = DEFAULT_GEMINI_MODEL if provider_id == "gemini" else DEFAULT_OPENAI_MODEL
        return OpenAICompatibleRelationJudgeProvider(
            provider_id=provider_id,
            base_url=base_url or str(preset["base_url"]),
            api_key_env=api_key_env or str(preset["api_key_env"]),
            model=model or str(preset.get("model") or default_model),
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"unknown relation judge provider: {provider}")


def _load_candidates(
    conn: sqlite3.Connection,
    *,
    relation_types: tuple[str, ...],
    limit: int,
) -> tuple[RelationJudgeCandidate, ...]:
    placeholders = ",".join("?" for _ in relation_types)
    rows = conn.execute(
        f"""
        SELECT
            r.relation_id,
            r.relation_type,
            r.evidence_json,
            s.doc_id AS source_doc_id,
            s.title AS source_title,
            s.body AS source_body,
            s.compact_text AS source_compact,
            t.doc_id AS target_doc_id,
            t.title AS target_title,
            t.body AS target_body,
            t.compact_text AS target_compact
        FROM memory_relations r
        JOIN memory_documents s ON s.doc_id = r.source_doc_id
        JOIN memory_documents t ON t.doc_id = r.target_doc_id
        WHERE r.relation_type IN ({placeholders})
          AND NOT EXISTS (
              SELECT 1
              FROM memory_relations existing
              WHERE existing.relation_type IN ('supports', 'contradicts')
                AND (
                    (
                        existing.source_doc_id = t.doc_id
                        AND existing.target_doc_id = s.doc_id
                    )
                    OR (
                        existing.source_doc_id = s.doc_id
                        AND existing.target_doc_id = t.doc_id
                    )
                )
          )
        ORDER BY r.strength DESC, r.updated_at DESC, r.relation_id
        LIMIT ?
        """,
        (*relation_types, limit),
    ).fetchall()
    candidates: list[RelationJudgeCandidate] = []
    for row in rows:
        evidence_doc_id, assessed_doc_id = _judged_direction(row)
        if evidence_doc_id == str(row["source_doc_id"]):
            evidence_title = str(row["source_title"] or "")
            evidence_text = _combined_doc_text(row["source_body"], row["source_compact"])
            assessed_title = str(row["target_title"] or "")
            assessed_text = _combined_doc_text(row["target_body"], row["target_compact"])
        else:
            evidence_title = str(row["target_title"] or "")
            evidence_text = _combined_doc_text(row["target_body"], row["target_compact"])
            assessed_title = str(row["source_title"] or "")
            assessed_text = _combined_doc_text(row["source_body"], row["source_compact"])
        candidate_id = _hash_id("relation-judge-candidate", str(row["relation_id"]))[:24]
        candidates.append(
            RelationJudgeCandidate(
                candidate_id=candidate_id,
                relation_id=str(row["relation_id"]),
                relation_type=str(row["relation_type"]),
                evidence_doc_id=evidence_doc_id,
                assessed_doc_id=assessed_doc_id,
                evidence_title=evidence_title,
                evidence_text=evidence_text,
                assessed_title=assessed_title,
                assessed_text=assessed_text,
                evidence_json=_loads_json(row["evidence_json"]),
            )
        )
    return tuple(candidates)


def _judged_direction(row: sqlite3.Row) -> tuple[str, str]:
    relation_type = str(row["relation_type"])
    source_doc_id = str(row["source_doc_id"])
    target_doc_id = str(row["target_doc_id"])
    if relation_type in {"older_than", "obsolete_candidate"}:
        return target_doc_id, source_doc_id
    return source_doc_id, target_doc_id


def _store_judged_relation(
    conn: sqlite3.Connection,
    candidate: RelationJudgeCandidate,
    decision: RelationJudgeDecision,
    *,
    provider: RelationJudgeProvider,
    prompt_version: str,
    now: str,
) -> None:
    relation_id = _hash_id(
        "judged-relation",
        candidate.evidence_doc_id,
        candidate.assessed_doc_id,
        decision.relation_type,
    )[:24]
    evidence = {
        "candidate_relation_id": candidate.relation_id,
        "candidate_relation_type": candidate.relation_type,
        "provider": provider.provider_id,
        "provider_role": provider.provider_role,
        "model": provider.model,
        "prompt_version": prompt_version,
        "decision": decision.as_dict(),
        "judged_at": now,
        "evidence_doc_id": candidate.evidence_doc_id,
        "assessed_doc_id": candidate.assessed_doc_id,
    }
    conn.execute(
        """
        INSERT INTO memory_relations (
            relation_id, source_doc_id, target_doc_id, relation_type,
            strength, status, evidence_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(relation_id) DO UPDATE SET
            strength=excluded.strength,
            status=excluded.status,
            evidence_json=excluded.evidence_json,
            updated_at=excluded.updated_at
        """,
        (
            relation_id,
            candidate.evidence_doc_id,
            candidate.assessed_doc_id,
            decision.relation_type,
            decision.confidence,
            "diagnostic_fixture" if provider.provider_id == "fake" else "ai_judged",
            json.dumps(evidence, ensure_ascii=False, sort_keys=True),
            now,
            now,
        ),
    )


def _store_tool_call(
    conn: sqlite3.Connection,
    *,
    provider: RelationJudgeProvider,
    prompt_version: str,
    batch: tuple[RelationJudgeCandidate, ...],
    decisions: tuple[RelationJudgeDecision, ...],
    inserted: int,
    now: str,
) -> None:
    tool_call_id = _hash_id(
        "relation-judge-tool-call",
        provider.provider_id,
        provider.model,
        prompt_version,
        *(candidate.candidate_id for candidate in batch),
    )[:24]
    conn.execute(
        """
        INSERT INTO memory_tool_calls (
            tool_call_id, run_id, provider, provider_role, action,
            input_json, output_json, status, error, started_at, finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tool_call_id) DO UPDATE SET
            output_json=excluded.output_json,
            status=excluded.status,
            error=excluded.error,
            finished_at=excluded.finished_at
        """,
        (
            tool_call_id,
            None,
            provider.provider_id,
            provider.provider_role,
            "judge_relations",
            json.dumps(
                {
                    "prompt_version": prompt_version,
                    "candidate_ids": [candidate.candidate_id for candidate in batch],
                    "candidate_relation_ids": [candidate.relation_id for candidate in batch],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            json.dumps(
                {
                    "decision_count": len(decisions),
                    "inserted": inserted,
                    "decisions": [decision.as_dict() for decision in decisions],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "ok",
            None,
            now,
            now,
        ),
    )


def _judge_messages(
    candidates: tuple[RelationJudgeCandidate, ...],
    *,
    prompt_version: str,
) -> list[dict[str, str]]:
    items = [candidate.as_prompt_item() for candidate in candidates]
    system = (
        "You judge relations for a local personal memory-search database. "
        "For each candidate, decide whether the evidence document supports, contradicts, "
        "or has no clear relation to the assessed document. Use only the supplied text. "
        "Return strict JSON only. Do not invent external facts."
    )
    user = json.dumps(
        {
            "prompt_version": prompt_version,
            "allowed_relation_types": ["supports", "contradicts", "no_relation"],
            "schema": {
                "decisions": [
                    {
                        "candidate_id": "string",
                        "relation_type": "supports|contradicts|no_relation",
                        "confidence": "number between 0 and 1",
                        "rationale": "short reason grounded in supplied text",
                    }
                ]
            },
            "candidates": items,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise RuntimeError("relation judge response was not JSON") from exc
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise RuntimeError("relation judge JSON root must be an object")
    return parsed


def _normalize_judged_relation_type(value: str) -> str:
    normalized = value.strip().casefold().replace("-", "_")
    if normalized in {"support", "supported", "supports"}:
        return "supports"
    if normalized in {"contradict", "contradicted", "contradicts", "conflicts"}:
        return "contradicts"
    return "no_relation"


def _bounded_float(value: Any, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _chunks(
    candidates: tuple[RelationJudgeCandidate, ...],
    size: int,
) -> list[tuple[RelationJudgeCandidate, ...]]:
    return [candidates[index : index + size] for index in range(0, len(candidates), size)]


_CONTRADICTION_MARKERS = (
    "非推奨",
    "廃止",
    "古い",
    "間違い",
    "誤り",
    "修正",
    "訂正",
    "obsolete",
    "deprecated",
    "incorrect",
    "wrong",
    "no longer",
)

_SIGNAL_TERMS = (
    "AI",
    "LLM",
    "RAG",
    "強化学習",
    "機械学習",
    "ロボット",
    "ネットワーク",
    "キオクシア",
    "株価",
    "ピザ",
    "カフェ",
    "技術",
    "論文",
)


def _shared_signal_terms(left: str, right: str) -> set[str]:
    left_folded = left.casefold()
    right_folded = right.casefold()
    shared = {
        term
        for term in _SIGNAL_TERMS
        if term.casefold() in left_folded and term.casefold() in right_folded
    }
    left_words = set(re.findall(r"[A-Za-z][A-Za-z0-9_+-]{2,}", left_folded))
    right_words = set(re.findall(r"[A-Za-z][A-Za-z0-9_+-]{2,}", right_folded))
    shared.update(sorted(left_words & right_words)[:12])
    return shared


def _loads_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _combined_doc_text(body: Any, compact: Any) -> str:
    parts = []
    for value in (body, compact):
        text = str(value or "").strip()
        if text and text not in parts:
            parts.append(text)
    return "\n".join(parts)


def _post_json_budgeted(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_seconds: float,
    budget_provider: str,
    budget_model: str,
    budget_units: dict[str, int | float],
) -> dict[str, Any]:
    with budgeted_api_call(
        provider=budget_provider,
        model=budget_model,
        provider_role=RELATION_JUDGE_ROLE,
        operation="relation_judge",
        units=budget_units,
        request_payload=payload,
        metadata={"url": url},
    ):
        return _post_json(
            url,
            payload,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )


def _truncate(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max(0, max_chars - 3)].rstrip() + "..."


def _hash_id(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")
