from __future__ import annotations

import json
import re
import sqlite3
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from research_x.bookmark_classifier import (
    BookmarkClassification,
    BookmarkClassificationRun,
    BookmarkClassifierSettings,
    classify_bookmarks,
    load_bookmark_categories,
    write_label_outputs,
)
from research_x.contracts import XItem, utc_now
from research_x.x_store import write_label_store_outputs

LABEL_SCOPE_BOOKMARKS = "bookmarks"
LABEL_EXISTING_KINDS = ("bookmarks", "tweets", "all")


@dataclass(frozen=True)
class ExistingLabelCandidate:
    item: XItem
    account_id: str | None
    label_scope: str


@dataclass(frozen=True)
class ExistingLabelReport:
    status: str
    db_path: str
    kind: str
    account_id: str | None
    selected_items: int
    unique_tweets: int
    candidate_total: int
    already_labeled: int
    written_labels: int
    model: str
    generated_at: datetime
    output_dir: str | None = None
    error_type: str | None = None
    error_message: str | None = None


def label_existing_items(
    *,
    db_path: str | Path,
    account: str | None = None,
    kind: str = LABEL_SCOPE_BOOKMARKS,
    limit: int | None = 100,
    include_labeled: bool = False,
    out_dir: str | Path | None = None,
    model: str = "gpt-4o-mini",
    api_key_env: str = "OPENAI_API_KEY",
    categories_path: str | Path | None = None,
    batch_size: int = 20,
    classifier_provider: str = "openai_responses",
    api_base_url: str | None = None,
    retry_attempts: int = 3,
    retry_base_seconds: float = 10.0,
    request_timeout_seconds: float = 120.0,
    reasoning_effort: str | None = None,
    cancel_check: Callable[[], bool] | None = None,
    min_request_interval_seconds: float = 0.0,
    stop_on_rate_limit: bool = False,
) -> tuple[ExistingLabelReport, BookmarkClassificationRun]:
    if kind not in LABEL_EXISTING_KINDS:
        raise ValueError(f"kind must be one of {', '.join(LABEL_EXISTING_KINDS)}")

    db = Path(db_path)
    categories = load_bookmark_categories(categories_path)
    counts = count_existing_label_candidates(db, account=account, kind=kind)
    candidates = load_existing_label_candidates(
        db,
        account=account,
        kind=kind,
        limit=limit,
        include_labeled=include_labeled,
    )
    unique_items = _unique_items(candidate.item for candidate in candidates)
    output_path = Path(out_dir) if out_dir else None
    started = time.monotonic()
    written_labels = 0
    processed_items = 0
    generated_at = utc_now()
    resolved_model = model
    classifications: list[BookmarkClassification] = []
    status = "empty" if not unique_items else "ok"
    error_type = None
    error_message = None
    metadata = {
        "api_key_env": api_key_env,
        "provider": classifier_provider,
        "api_base_url": api_base_url,
        "batch_size": batch_size,
        "category_count": len(categories),
        "candidate_total": counts["total"],
        "already_labeled": counts["labeled"],
        "retry_attempts": retry_attempts,
        "retry_base_seconds": retry_base_seconds,
        "request_timeout_seconds": request_timeout_seconds,
        "reasoning_effort": reasoning_effort,
        "min_request_interval_seconds": min_request_interval_seconds,
        "stop_on_rate_limit": stop_on_rate_limit,
    }
    settings = BookmarkClassifierSettings(
        model=model,
        api_key_env=api_key_env,
        batch_size=batch_size,
        provider=classifier_provider,
        api_base_url=api_base_url,
        request_timeout_seconds=request_timeout_seconds,
        reasoning_effort=reasoning_effort,
    )
    request_pacer = _RequestPacer(max(0.0, min_request_interval_seconds))
    _write_label_progress(
        output_path,
        total=len(unique_items),
        done=0,
        written_labels=0,
        started=started,
        status=status,
    )
    for chunk in _chunks(unique_items, max(1, batch_size)):
        if cancel_check and cancel_check():
            status = "canceled"
            error_type = "Cancelled"
            error_message = "classification canceled before the next batch"
            break
        run = _classify_adaptive(
            chunk,
            settings=settings,
            categories=categories,
            output_path=output_path,
            total=len(unique_items),
            processed_items=processed_items,
            written_labels=written_labels,
            started=started,
            retry_attempts=retry_attempts,
            retry_base_seconds=retry_base_seconds,
            cancel_check=cancel_check,
            stop_on_rate_limit=stop_on_rate_limit,
            request_pacer=request_pacer,
        )
        resolved_model = run.model
        generated_at = run.generated_at
        classifications.extend(run.classifications)
        chunk_ids = {item.source_id for item in chunk}
        written_labels += _write_classification_groups(
            db,
            candidates=tuple(
                candidate for candidate in candidates if candidate.item.source_id in chunk_ids
            ),
            classifications=run.classifications,
            model=run.model,
            generated_at=run.generated_at,
        )
        if run.status in {"ok", "empty"}:
            processed_items += len(chunk)
        elif run.classifications:
            processed_items += len(
                {classification.source_id for classification in run.classifications}
            )
        if run.status not in {"ok", "empty"}:
            status = run.status
            error_type = run.error_type
            error_message = run.error_message
            break
        _write_label_progress(
            output_path,
            total=len(unique_items),
            done=processed_items,
            written_labels=written_labels,
            started=started,
            status=status,
        )
    else:
        status = "ok" if unique_items else "empty"

    classification_run = BookmarkClassificationRun(
        status=status,
        model=resolved_model,
        generated_at=generated_at,
        classifications=tuple(classifications),
        error_type=error_type,
        error_message=error_message,
        metadata=metadata,
    )
    _write_label_progress(
        output_path,
        total=len(unique_items),
        done=processed_items if status not in {"ok", "empty"} else len(unique_items),
        written_labels=written_labels,
        started=started,
        status=status,
        finished=True,
        error_message=error_message,
    )
    if output_path is not None:
        write_label_outputs(
            output_path,
            items=unique_items,
            classification_run=classification_run,
            categories=categories,
            item_filename="existing_label_items.jsonl",
            classification_filename="existing_label_classifications.jsonl",
            report_filename="existing_label_report.json",
            genres_dir_name="existing_label_genres",
            store_summary={
                "db_path": str(db),
                "kind": kind,
                "account_id": account,
                "selected_items": len(candidates),
                "unique_tweets": len(unique_items),
                "candidate_total": counts["total"],
                "already_labeled": counts["labeled"],
                "written_labels": written_labels,
            },
        )

    report = ExistingLabelReport(
        status=classification_run.status,
        db_path=str(db),
        kind=kind,
        account_id=account,
        selected_items=len(candidates),
        unique_tweets=len(unique_items),
        candidate_total=counts["total"],
        already_labeled=counts["labeled"],
        written_labels=written_labels,
        model=classification_run.model,
        generated_at=classification_run.generated_at,
        output_dir=str(output_path) if output_path else None,
        error_type=classification_run.error_type,
        error_message=classification_run.error_message,
    )
    if output_path is not None:
        (output_path / "existing_label_db_report.json").write_text(
            json.dumps(_jsonable(report), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return report, classification_run


def load_existing_label_candidates(
    db_path: str | Path,
    *,
    account: str | None = None,
    kind: str = LABEL_SCOPE_BOOKMARKS,
    limit: int | None = 100,
    include_labeled: bool = False,
) -> tuple[ExistingLabelCandidate, ...]:
    if kind not in LABEL_EXISTING_KINDS:
        raise ValueError(f"kind must be one of {', '.join(LABEL_EXISTING_KINDS)}")
    query, params = _candidate_query(
        account=account,
        kind=kind,
        include_labeled=include_labeled,
        limit=limit,
    )
    with sqlite3.connect(Path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    return tuple(_candidate_from_row(row) for row in rows)


def count_existing_label_candidates(
    db_path: str | Path,
    *,
    account: str | None = None,
    kind: str = LABEL_SCOPE_BOOKMARKS,
) -> dict[str, int]:
    all_query, all_params = _candidate_query(
        account=account,
        kind=kind,
        limit=None,
        include_labeled=True,
    )
    unlabeled_query, unlabeled_params = _candidate_query(
        account=account,
        kind=kind,
        limit=None,
        include_labeled=False,
    )
    with sqlite3.connect(Path(db_path)) as conn:
        total = int(conn.execute(f"SELECT COUNT(*) FROM ({all_query})", all_params).fetchone()[0])
        unlabeled = int(
            conn.execute(
                f"SELECT COUNT(*) FROM ({unlabeled_query})",
                unlabeled_params,
            ).fetchone()[0]
        )
    return {
        "total": total,
        "unlabeled": unlabeled,
        "labeled": max(0, total - unlabeled),
    }


def _candidate_query(
    *,
    account: str | None,
    kind: str,
    include_labeled: bool,
    limit: int | None,
) -> tuple[str, tuple[Any, ...]]:
    parts: list[str] = []
    params: list[Any] = []
    if kind in (LABEL_SCOPE_BOOKMARKS, "all"):
        query, query_params = _bookmark_candidate_query(
            account=account,
            include_labeled=include_labeled,
        )
        parts.append(query)
        params.extend(query_params)
    if kind in ("tweets", "all"):
        query, query_params = _tweet_candidate_query(
            account=account,
            include_labeled=include_labeled,
        )
        parts.append(query)
        params.extend(query_params)
    if not parts:
        raise ValueError(f"unsupported kind: {kind}")
    union = " UNION ALL ".join(parts)
    sql = f"SELECT * FROM ({union}) ORDER BY sort_account, sort_scope, sort_position"
    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    return sql, tuple(params)


def _bookmark_candidate_query(
    *,
    account: str | None,
    include_labeled: bool,
) -> tuple[str, tuple[Any, ...]]:
    params: list[Any] = [account, account]
    labeled_filter = ""
    if not include_labeled:
        labeled_filter = """
            AND NOT EXISTS (
                SELECT 1 FROM ai_labels al
                WHERE al.tweet_id = ab.tweet_id
                  AND al.label_scope = 'bookmarks'
                  AND al.account_id IS ab.account_id
            )
        """
    return (
        f"""
        SELECT
            ab.account_id AS account_id,
            'bookmarks' AS label_scope,
            ab.bookmark_index AS sort_position,
            COALESCE(ab.account_id, '') AS sort_account,
            'bookmarks' AS sort_scope,
            ab.observed_at AS observed_at,
            ab.providers_json AS bookmark_providers_json,
            ab.run_id AS run_id,
            t.tweet_id AS tweet_id,
            t.url AS url,
            t.author_screen_name AS author_screen_name,
            t.text AS text,
            t.created_at AS created_at,
            t.first_observed_at AS first_observed_at,
            t.last_observed_at AS last_observed_at,
            t.role AS role,
            t.collection_kind AS collection_kind,
            t.providers_json AS tweet_providers_json,
            t.raw_json AS raw_json
        FROM account_bookmarks ab
        JOIN tweets t ON t.tweet_id = ab.tweet_id
        WHERE (? IS NULL OR ab.account_id = ?)
        {labeled_filter}
        """,
        tuple(params),
    )


def _tweet_candidate_query(
    *,
    account: str | None,
    include_labeled: bool,
) -> tuple[str, tuple[Any, ...]]:
    params: list[Any] = [account, account]
    labeled_filter = ""
    if not include_labeled:
        labeled_filter = """
            AND NOT EXISTS (
                SELECT 1 FROM ai_labels al
                WHERE al.tweet_id = ci.tweet_id
                  AND al.label_scope = ci.collection_kind
                  AND al.account_id IS ci.account_id
            )
        """
    return (
        f"""
        SELECT
            ci.account_id AS account_id,
            ci.collection_kind AS label_scope,
            ci.position AS sort_position,
            COALESCE(ci.account_id, '') AS sort_account,
            ci.collection_kind AS sort_scope,
            ci.observed_at AS observed_at,
            ci.providers_json AS bookmark_providers_json,
            ci.run_id AS run_id,
            t.tweet_id AS tweet_id,
            t.url AS url,
            t.author_screen_name AS author_screen_name,
            t.text AS text,
            t.created_at AS created_at,
            t.first_observed_at AS first_observed_at,
            t.last_observed_at AS last_observed_at,
            t.role AS role,
            t.collection_kind AS collection_kind,
            t.providers_json AS tweet_providers_json,
            t.raw_json AS raw_json
        FROM collection_items ci
        JOIN tweets t ON t.tweet_id = ci.tweet_id
        WHERE ci.collection_kind != 'bookmarks'
          AND (? IS NULL OR ci.account_id = ?)
        {labeled_filter}
        """,
        tuple(params),
    )


def _candidate_from_row(row: sqlite3.Row) -> ExistingLabelCandidate:
    raw = _loads_json(row["raw_json"])
    raw.setdefault("_db", {})
    raw["_db"].update(
        {
            "account_id": row["account_id"],
            "label_scope": row["label_scope"],
            "role": row["role"],
            "collection_kind": row["collection_kind"],
            "run_id": row["run_id"],
            "providers": _loads_json(row["tweet_providers_json"]),
            "bookmark_providers": _loads_json(row["bookmark_providers_json"]),
        }
    )
    return ExistingLabelCandidate(
        item=XItem(
            source_id=str(row["tweet_id"]),
            url=row["url"],
            author=row["author_screen_name"],
            text=row["text"],
            created_at=_parse_datetime(row["created_at"]),
            observed_at=(
                _parse_datetime(row["observed_at"])
                or _parse_datetime(row["last_observed_at"])
                or _parse_datetime(row["first_observed_at"])
                or utc_now()
            ),
            raw=raw,
        ),
        account_id=row["account_id"],
        label_scope=str(row["label_scope"]),
    )


def _unique_items(items: Iterable[XItem]) -> tuple[XItem, ...]:
    result: dict[str, XItem] = {}
    for item in items:
        result.setdefault(item.source_id, item)
    return tuple(result.values())


def _candidate_groups(
    candidates: Iterable[ExistingLabelCandidate],
) -> dict[tuple[str, str | None], tuple[str, ...]]:
    grouped: dict[tuple[str, str | None], list[str]] = defaultdict(list)
    seen: set[tuple[str, str | None, str]] = set()
    for candidate in candidates:
        key = (candidate.label_scope, candidate.account_id, candidate.item.source_id)
        if key in seen:
            continue
        seen.add(key)
        grouped[(candidate.label_scope, candidate.account_id)].append(candidate.item.source_id)
    return {key: tuple(value) for key, value in grouped.items()}


def _write_classification_groups(
    db_path: Path,
    *,
    candidates: tuple[ExistingLabelCandidate, ...],
    classifications: Iterable[BookmarkClassification],
    model: str,
    generated_at: datetime,
) -> int:
    classification_by_id = {
        classification.source_id: classification
        for classification in classifications
    }
    written = 0
    for (label_scope, account_id), source_ids in _candidate_groups(candidates).items():
        group_classifications = tuple(
            classification_by_id[source_id]
            for source_id in source_ids
            if source_id in classification_by_id
        )
        if not group_classifications:
            continue
        write_label_store_outputs(
            db_path,
            classifications=group_classifications,
            label_scope=label_scope,
            account_id=account_id,
            model=model,
            generated_at=generated_at,
        )
        written += len(group_classifications)
    return written


def _chunks(items: tuple[XItem, ...], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


@dataclass
class _RequestPacer:
    min_interval_seconds: float
    last_started: float | None = None

    def wait(
        self,
        *,
        output_path: Path | None,
        total: int,
        processed_items: int,
        written_labels: int,
        started: float,
        cancel_check: Callable[[], bool] | None,
    ) -> bool:
        if self.min_interval_seconds <= 0:
            self.last_started = time.monotonic()
            return bool(cancel_check and cancel_check())
        now = time.monotonic()
        wait_seconds = 0.0
        if self.last_started is not None:
            elapsed = now - self.last_started
            wait_seconds = max(0.0, self.min_interval_seconds - elapsed)
        if wait_seconds > 0:
            _write_label_progress(
                output_path,
                total=total,
                done=processed_items,
                written_labels=written_labels,
                started=started,
                status="throttling",
                error_message=f"waiting {wait_seconds:.1f}s before next classifier request",
                retry_after_seconds=wait_seconds,
                next_retry_at=time.time() + wait_seconds,
            )
            if _sleep_until_cancel_or_timeout(wait_seconds, cancel_check):
                return True
        self.last_started = time.monotonic()
        return bool(cancel_check and cancel_check())


def _classify_with_retries(
    chunk: tuple[XItem, ...],
    *,
    settings: BookmarkClassifierSettings,
    categories: Any,
    output_path: Path | None,
    total: int,
    processed_items: int,
    written_labels: int,
    started: float,
    retry_attempts: int,
    retry_base_seconds: float,
    cancel_check: Callable[[], bool] | None,
    stop_on_rate_limit: bool,
    request_pacer: _RequestPacer,
) -> BookmarkClassificationRun:
    attempts = max(0, retry_attempts)
    for attempt in range(attempts + 1):
        if cancel_check and cancel_check():
            return _cancelled_run(settings)
        if request_pacer.wait(
            output_path=output_path,
            total=total,
            processed_items=processed_items,
            written_labels=written_labels,
            started=started,
            cancel_check=cancel_check,
        ):
            return _cancelled_run(settings)
        run = classify_bookmarks(chunk, settings=settings, categories=categories)
        if stop_on_rate_limit and _is_rate_limited(run):
            return _quota_exhausted_run(run)
        if not _should_retry_classification(run) or attempt >= attempts:
            return run
        retry_hint = _retry_after_seconds(run)
        wait_seconds = max(max(0.0, retry_base_seconds) * (attempt + 1), retry_hint or 0.0)
        if retry_hint is not None:
            wait_seconds += 1.0
        retry_status = "rate_limited" if _is_rate_limited(run) else "retrying"
        next_retry_at = time.time() + wait_seconds
        _write_label_progress(
            output_path,
            total=total,
            done=processed_items,
            written_labels=written_labels,
            started=started,
            status=retry_status,
            error_message=(
                f"{run.error_type or 'ClassifierError'}: {run.error_message or run.status}; "
                f"retry {attempt + 1}/{attempts} after {wait_seconds:.0f}s"
            ),
            retry_after_seconds=wait_seconds,
            next_retry_at=next_retry_at,
            retry_attempt=attempt + 1,
            retry_attempts=attempts,
        )
        if _sleep_until_cancel_or_timeout(wait_seconds, cancel_check):
            return _cancelled_run(settings)
    return run


def _classify_adaptive(
    chunk: tuple[XItem, ...],
    *,
    settings: BookmarkClassifierSettings,
    categories: Any,
    output_path: Path | None,
    total: int,
    processed_items: int,
    written_labels: int,
    started: float,
    retry_attempts: int,
    retry_base_seconds: float,
    cancel_check: Callable[[], bool] | None,
    stop_on_rate_limit: bool,
    request_pacer: _RequestPacer,
) -> BookmarkClassificationRun:
    effective_retry_attempts = retry_attempts if len(chunk) <= 1 else 0
    run = _classify_with_retries(
        chunk,
        settings=settings,
        categories=categories,
        output_path=output_path,
        total=total,
        processed_items=processed_items,
        written_labels=written_labels,
        started=started,
        retry_attempts=effective_retry_attempts,
        retry_base_seconds=retry_base_seconds,
        cancel_check=cancel_check,
        stop_on_rate_limit=stop_on_rate_limit,
        request_pacer=request_pacer,
    )
    if not _should_retry_classification(run) or len(chunk) <= 1:
        return run

    midpoint = max(1, len(chunk) // 2)
    _write_label_progress(
        output_path,
        total=total,
        done=processed_items,
        written_labels=written_labels,
        started=started,
        status="splitting",
        error_message=(
            f"{run.error_type or 'ClassifierError'}: {run.error_message or run.status}; "
            f"splitting batch {len(chunk)} -> {midpoint}+{len(chunk) - midpoint}"
        ),
    )
    left = _classify_adaptive(
        chunk[:midpoint],
        settings=settings,
        categories=categories,
        output_path=output_path,
        total=total,
        processed_items=processed_items,
        written_labels=written_labels,
        started=started,
        retry_attempts=retry_attempts,
        retry_base_seconds=retry_base_seconds,
        cancel_check=cancel_check,
        stop_on_rate_limit=stop_on_rate_limit,
        request_pacer=request_pacer,
    )
    left_done = len({classification.source_id for classification in left.classifications})
    right = _classify_adaptive(
        chunk[midpoint:],
        settings=settings,
        categories=categories,
        output_path=output_path,
        total=total,
        processed_items=processed_items + left_done,
        written_labels=written_labels + left_done,
        started=started,
        retry_attempts=retry_attempts,
        retry_base_seconds=retry_base_seconds,
        cancel_check=cancel_check,
        stop_on_rate_limit=stop_on_rate_limit,
        request_pacer=request_pacer,
    )
    classifications = left.classifications + right.classifications
    if left.status == "canceled" or right.status == "canceled":
        status = "canceled"
        error_type = right.error_type or left.error_type
        error_message = right.error_message or left.error_message
    elif left.status == "quota_exhausted" or right.status == "quota_exhausted":
        status = "quota_exhausted"
        error_type = right.error_type or left.error_type
        error_message = right.error_message or left.error_message
    elif left.status in {"ok", "empty"} and right.status in {"ok", "empty"}:
        status = "ok"
        error_type = None
        error_message = None
    elif classifications:
        status = "partial"
        error_type = right.error_type or left.error_type
        error_message = right.error_message or left.error_message
    else:
        status = "error"
        error_type = right.error_type or left.error_type
        error_message = right.error_message or left.error_message
    return BookmarkClassificationRun(
        status=status,
        model=right.model or left.model,
        generated_at=right.generated_at,
        classifications=classifications,
        error_type=error_type,
        error_message=error_message,
        metadata={
            "adaptive_split": True,
            "left_status": left.status,
            "right_status": right.status,
        },
    )


def _should_retry_classification(run: BookmarkClassificationRun) -> bool:
    if run.status not in {"error", "partial"}:
        return False
    message = f"{run.error_type or ''} {run.error_message or ''}".lower()
    return any(
        token in message
        for token in (
            " 429",
            " 503",
            "quota",
            "rate",
            "resource_exhausted",
            "unavailable",
            "timeout",
        )
    )


def _is_rate_limited(run: BookmarkClassificationRun) -> bool:
    message = f"{run.error_type or ''} {run.error_message or ''}".lower()
    return any(token in message for token in (" 429", "quota", "rate", "resource_exhausted"))


def _retry_after_seconds(run: BookmarkClassificationRun) -> float | None:
    message = run.error_message or ""
    match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", message, flags=re.IGNORECASE)
    if match:
        return max(0.0, float(match.group(1)))
    match = re.search(r"retryDelay[\"']?\s*[:=]\s*[\"']?([0-9]+(?:\.[0-9]+)?)s", message)
    if match:
        return max(0.0, float(match.group(1)))
    return None


def _cancelled_run(settings: BookmarkClassifierSettings) -> BookmarkClassificationRun:
    return BookmarkClassificationRun(
        status="canceled",
        model=settings.model,
        generated_at=utc_now(),
        classifications=(),
        error_type="Cancelled",
        error_message="classification canceled by user request",
    )


def _quota_exhausted_run(run: BookmarkClassificationRun) -> BookmarkClassificationRun:
    return BookmarkClassificationRun(
        status="quota_exhausted",
        model=run.model,
        generated_at=run.generated_at,
        classifications=run.classifications,
        error_type=run.error_type,
        error_message=run.error_message,
        metadata=run.metadata,
    )


def _sleep_until_cancel_or_timeout(
    seconds: float,
    cancel_check: Callable[[], bool] | None,
) -> bool:
    if seconds <= 0:
        return bool(cancel_check and cancel_check())
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if cancel_check and cancel_check():
            return True
        time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
    return bool(cancel_check and cancel_check())


def _write_label_progress(
    out_dir: Path | None,
    *,
    total: int,
    done: int,
    written_labels: int,
    started: float,
    status: str,
    finished: bool = False,
    error_message: str | None = None,
    retry_after_seconds: float | None = None,
    next_retry_at: float | None = None,
    retry_attempt: int | None = None,
    retry_attempts: int | None = None,
) -> None:
    if out_dir is None:
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    elapsed = max(0.001, time.monotonic() - started)
    remaining = max(0, total - done)
    rate = done / elapsed if done else 0.0
    payload = {
        "updated_at": utc_now().isoformat(),
        "status": status,
        "finished": finished,
        "total": total,
        "done": done,
        "remaining": remaining,
        "written_labels": written_labels,
        "elapsed_seconds": elapsed,
        "items_per_second": rate,
        "estimated_remaining_seconds": remaining / rate if rate > 0 else None,
        "error_message": error_message,
        "retry_after_seconds": retry_after_seconds,
        "next_retry_at": next_retry_at,
        "retry_attempt": retry_attempt,
        "retry_attempts": retry_attempts,
    }
    (out_dir / "label_progress.json").write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _loads_json(value: Any) -> Any:
    if value in (None, ""):
        return {}
    if isinstance(value, dict | list):
        return value
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return {}


def _jsonable(value: Any):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
