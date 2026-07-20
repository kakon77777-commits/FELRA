from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any



@dataclass(frozen=True)
class ProvenanceNode:
    node_id: str
    kind: str
    label: str
    path: str | None = None
    sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.node_id,
            "kind": self.kind,
            "label": self.label,
            "path": self.path,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class ProvenanceEdge:
    source: str
    target: str
    relation: str

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "relation": self.relation}


def _dot_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_provenance(run: Any, config_sha256: str) -> dict[str, Any]:
    nodes: list[ProvenanceNode] = [
        ProvenanceNode(
            "project",
            "project",
            run.project.title,
            path="project_snapshot.yaml",
            sha256=config_sha256,
        )
    ]
    edges: list[ProvenanceEdge] = []

    for dataset in run.datasets.values():
        node_id = f"dataset:{dataset.spec.dataset_id}"
        nodes.append(
            ProvenanceNode(
                node_id,
                "dataset",
                dataset.spec.dataset_id,
                path=f"datasets/{dataset.spec.dataset_id}/normalized.csv",
                sha256=dataset.quality.source_sha256,
            )
        )
        edges.append(ProvenanceEdge("project", node_id, "declares"))

    for bundle in run.bundles:
        node_id = f"claim:{bundle.claim.claim_id}"
        nodes.append(
            ProvenanceNode(
                node_id,
                "claim",
                bundle.claim.statement,
                path=f"claims/{bundle.claim.claim_id}/metrics.json",
            )
        )
        edges.append(ProvenanceEdge("project", node_id, "defines"))
        dataset_id = bundle.metadata.get("dataset")
        if dataset_id:
            edges.append(ProvenanceEdge(f"dataset:{dataset_id}", node_id, "evaluates"))

    for analysis in run.analyses:
        node_id = f"analysis:{analysis.analysis_id}"
        nodes.append(
            ProvenanceNode(
                node_id,
                "analysis",
                analysis.title,
                path=f"analyses/{analysis.analysis_id}/metrics.json",
            )
        )
        edges.append(ProvenanceEdge("project", node_id, "defines"))
        spec = next((item for item in run.project.analyses if item.analysis_id == analysis.analysis_id), None)
        dataset_id = getattr(spec, "dataset", None)
        if dataset_id:
            edges.append(ProvenanceEdge(f"dataset:{dataset_id}", node_id, "feeds"))
        if analysis.claim_id:
            edges.append(ProvenanceEdge(node_id, f"claim:{analysis.claim_id}", "supports"))
        for artifact in analysis.artifacts:
            artifact_id = f"artifact:{analysis.analysis_id}:{artifact}"
            nodes.append(ProvenanceNode(artifact_id, "artifact", Path(artifact).name, path=artifact))
            edges.append(ProvenanceEdge(node_id, artifact_id, "produces"))

    for figure in run.figures:
        figure_id = f"figure:{figure}"
        nodes.append(ProvenanceNode(figure_id, "figure", Path(figure).name, path=figure))
        edges.append(ProvenanceEdge("project", figure_id, "produces"))

    nodes.append(ProvenanceNode("manifest", "manifest", "Run manifest", path="manifest.json"))
    edges.append(ProvenanceEdge("project", "manifest", "summarizes"))
    return {
        "schema_version": "1.0",
        "project_id": run.project.project_id,
        "nodes": [node.to_dict() for node in nodes],
        "edges": [edge.to_dict() for edge in edges],
    }


def write_provenance(payload: dict[str, Any], output_dir: Path) -> list[str]:
    provenance_dir = output_dir / "provenance"
    provenance_dir.mkdir(parents=True, exist_ok=True)

    json_path = provenance_dir / "provenance.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    dot_lines = ["digraph FELRA {", "  rankdir=LR;", "  node [shape=box];"]
    for node in payload["nodes"]:
        dot_lines.append(
            f'  "{_dot_escape(node["id"])}" [label="{_dot_escape(node["label"])}\\n[{node["kind"]}]"];'
        )
    for edge in payload["edges"]:
        dot_lines.append(
            f'  "{_dot_escape(edge["source"])}" -> "{_dot_escape(edge["target"])}" '
            f'[label="{_dot_escape(edge["relation"])}"];'
        )
    dot_lines.append("}")
    dot_path = provenance_dir / "provenance.dot"
    dot_path.write_text("\n".join(dot_lines) + "\n", encoding="utf-8")

    svg_path = provenance_dir / "provenance.svg"
    _render_graph_svg(payload, svg_path)
    return [str(path.relative_to(output_dir)) for path in (json_path, dot_path, svg_path)]


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_graph_svg(payload: dict[str, Any], path: Path) -> None:
    kind_order = ["project", "dataset", "claim", "analysis", "artifact", "figure", "manifest"]
    grouped: dict[str, list[dict[str, Any]]] = {kind: [] for kind in kind_order}
    for node in payload["nodes"]:
        grouped.setdefault(node["kind"], []).append(node)
    active_kinds = [kind for kind in kind_order if grouped.get(kind)]
    column_width = 220
    row_height = 90
    margin = 50
    max_rows = max((len(grouped[kind]) for kind in active_kinds), default=1)
    width = margin * 2 + max(1, len(active_kinds)) * column_width
    height = margin * 2 + max_rows * row_height
    positions: dict[str, tuple[int, int]] = {}
    for column, kind in enumerate(active_kinds):
        items = grouped[kind]
        for row, item in enumerate(items):
            x = margin + column * column_width + 80
            y = margin + row * row_height + 35
            positions[item["id"]] = (x, y)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="black"/></marker></defs>',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="20" y="25" font-family="sans-serif" font-size="16">FELRA Evidence Provenance Graph</text>',
    ]
    for edge in payload["edges"]:
        source = positions.get(edge["source"])
        target = positions.get(edge["target"])
        if source is None or target is None:
            continue
        x1, y1 = source
        x2, y2 = target
        lines.append(
            f'<line x1="{x1 + 75}" y1="{y1}" x2="{x2 - 75}" y2="{y2}" stroke="black" stroke-width="1" marker-end="url(#arrow)"/>'
        )
    for node in payload["nodes"]:
        x, y = positions[node["id"]]
        label = str(node["label"])
        if len(label) > 30:
            label = label[:27] + "..."
        lines.extend(
            [
                f'<rect x="{x - 75}" y="{y - 25}" width="150" height="50" rx="8" fill="white" stroke="black"/>',
                f'<text x="{x}" y="{y - 2}" text-anchor="middle" font-family="sans-serif" font-size="10">{_xml_escape(label)}</text>',
                f'<text x="{x}" y="{y + 14}" text-anchor="middle" font-family="sans-serif" font-size="9">[{_xml_escape(node["kind"])}]</text>',
            ]
        )
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
