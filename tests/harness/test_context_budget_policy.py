from __future__ import annotations

import json
from pathlib import Path

from research_x.memory.context_budget import ContextBudgetPolicy, budget_json_payload


def test_context_budget_offload_preserves_restore_pointer_and_citation_refs(
    tmp_path: Path,
) -> None:
    payload = {
        "run_id": "context-budget-test",
        "context_chunks": [
            {
                "chunk_id": "chunk-1",
                "source_kind": "local_x_db",
                "source_id": "tweet-1",
                "source_url": "https://x.com/example/status/1",
                "chunk_text": "source-backed context " * 120,
                "metadata": {},
            }
        ],
        "citation_annotations": [
            {
                "citation_id": "citation-1",
                "chunk_id": "chunk-1",
                "source_kind": "local_x_db",
                "source_id": "tweet-1",
                "source_url": "https://x.com/example/status/1",
                "field_path": "context_chunks[0]",
                "evidence_status": "fact",
            }
        ],
    }
    original_text = payload["context_chunks"][0]["chunk_text"]
    policy = ContextBudgetPolicy(
        max_output_chars=500,
        max_inline_chunk_chars=80,
        preview_chars=40,
        offload_dir=tmp_path / "offloads",
    )

    budgeted = budget_json_payload(payload, policy=policy, payload_kind="memory_context")
    pointer = budgeted.payload["context_chunks"][0]["metadata"]["offload_pointer"]
    artifact = json.loads(Path(pointer["artifact_path"]).read_text(encoding="utf-8"))

    assert budgeted.payload["context_budget"]["non_destructive"] is True
    assert budgeted.payload["context_budget"]["offloaded_item_count"] == 1
    assert pointer["source_id"] == "tweet-1"
    assert pointer["citation_refs"][0]["citation_id"] == "citation-1"
    assert artifact["content"] == original_text
    assert payload["context_chunks"][0]["chunk_text"] == original_text


def test_context_budget_policy_doc_rejects_citing_compressed_summaries() -> None:
    policy_doc = Path("docs/context-budget-policy.md").read_text(encoding="utf-8")

    assert "compressed summary != source bundle" in policy_doc
    assert "Do not cite compressed summaries" in policy_doc
    assert "Headroom or similar tools are optional adapters" in policy_doc
