from __future__ import annotations

from collections.abc import Mapping
from html import escape
from typing import Any

from research_x.control_artifacts.model import ControlArtifactView, load_control_artifact_view
from research_x.control_artifacts.sanitize import assert_safe_review_html

BANNER = "Not evidence / Review artifact only"


def render_control_artifact_html(payload: Mapping[str, Any] | ControlArtifactView) -> str:
    view = (
        payload
        if isinstance(payload, ControlArtifactView)
        else load_control_artifact_view(payload)
    )
    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{escape(view.title)}</title>",
        "</head>",
        "<body>",
        f"<header><strong>{BANNER}</strong></header>",
        f"<h1>{escape(view.title)}</h1>",
        "<dl>",
        f"<dt>View ID</dt><dd>{escape(view.view_id)}</dd>",
        f"<dt>View kind</dt><dd>{escape(view.view_kind)}</dd>",
        f"<dt>Owner plane</dt><dd>{escape(view.owner_plane)}</dd>",
        f"<dt>Generated at</dt><dd>{escape(view.generated_at)}</dd>",
        "<dt>Answer support allowed</dt><dd>false</dd>",
        "</dl>",
        "<section>",
        "<h2>Source Artifacts</h2>",
        "<ul>",
    ]
    for source in view.source_artifacts:
        lines.append(
            "<li>"
            f"{escape(source.artifact_id)} "
            f"({escape(source.artifact_kind)}): "
            f"{escape(source.artifact_path)}"
            "</li>"
        )
    lines.extend(["</ul>", "</section>"])
    if view.view_kind == "diagram_review":
        lines.extend(
            [
                "<section>",
                "<h2>Diagram Review</h2>",
                "<dl>",
                f"<dt>Diagram kind</dt><dd>{escape(view.diagram_kind)}</dd>",
                f"<dt>Source of structure</dt><dd>{escape(view.source_of_structure)}</dd>",
                "<dt>Consistency refs</dt><dd>",
                ", ".join(escape(item) for item in view.consistency_refs) or "needs_review",
                "</dd>",
                "</dl>",
                "</section>",
            ]
        )
    lines.extend(["<main>"])
    for section in view.sections:
        lines.append("<section>")
        lines.append(f"<h2>{escape(section.heading)}</h2>")
        if section.body:
            lines.append(f"<p>{escape(section.body)}</p>")
        if section.items:
            lines.append("<ul>")
            for item in section.items:
                lines.append(f"<li>{escape(item)}</li>")
            lines.append("</ul>")
        lines.append("</section>")
    lines.extend(["</main>", "<section>", "<h2>Gates</h2>", "<ul>"])
    for gate in view.gates:
        lines.append(
            "<li>"
            f"{escape(gate.gate_id)}: {escape(gate.label)} "
            f"[{escape(gate.status)}]"
            "</li>"
        )
    lines.extend(["</ul>", "</section>", "</body>", "</html>"])
    html_text = "\n".join(lines) + "\n"
    assert_safe_review_html(html_text)
    return html_text
