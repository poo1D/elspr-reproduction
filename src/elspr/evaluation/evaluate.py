"""Strict unseen-question graph evaluation and conclusion-direction report."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

import yaml

from elspr.graph import (
    analyze_scc,
    average_structural_entropy,
    build_question_graph,
    dataset_non_transitivity,
    structural_entropy,
    write_graph,
    write_graph_svg,
)
from elspr.io import read_jsonl
from elspr.judging import aggregate_pair_judgments
from elspr.schemas import JudgmentRecord, StrictModel

Variant = Literal["raw", "cleaned", "random"]


class EvaluationError(ValueError):
    """Raised when unseen evaluation inputs are incomplete or contaminated."""


class EvaluationConfig(StrictModel):
    """Pinned judgments and outputs for three evaluator variants."""

    data_manifest: Path
    training_manifest: Path
    raw_judgments: Path
    cleaned_judgments: Path
    random_judgments: Path
    output_dir: Path


class EvaluationResult(StrictModel):
    """Main output paths and conclusion flags."""

    summary_path: Path
    report_path: Path
    question_count: int
    cleaned_improves_rho: bool
    cleaned_improves_tau: bool


def load_evaluation_config(path: Path) -> EvaluationConfig:
    """Load a strict YAML evaluation configuration."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EvaluationError("evaluation config must be a YAML mapping")
    return EvaluationConfig.model_validate(payload)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path) -> tuple[set[str], set[str], int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        train_ids = set(payload["split"]["train_question_ids"])
        evaluation_ids = set(payload["split"]["evaluation_question_ids"])
        model_count = int(payload["model_count"])
    except (KeyError, TypeError, ValueError) as error:
        raise EvaluationError(f"invalid data manifest: {error}") from error
    if not train_ids or not evaluation_ids or train_ids & evaluation_ids:
        raise EvaluationError("data manifest must contain disjoint non-empty splits")
    return train_ids, evaluation_ids, model_count


def _variant_metrics(
    *,
    variant: Variant,
    judgments_path: Path,
    train_ids: set[str],
    evaluation_ids: set[str],
    model_count: int,
    output_dir: Path,
) -> dict[str, Any]:
    judgments = read_jsonl(judgments_path, JudgmentRecord)
    observed_ids = {record.question_id for record in judgments}
    leaked = observed_ids & train_ids
    unknown = observed_ids - train_ids - evaluation_ids
    if leaked:
        raise EvaluationError(
            f"{variant} evaluation contains {len(leaked)} training questions"
        )
    if unknown:
        raise EvaluationError(
            f"{variant} evaluation contains {len(unknown)} unknown questions"
        )
    if observed_ids != evaluation_ids:
        raise EvaluationError(
            f"{variant} evaluation question mismatch: "
            f"expected={len(evaluation_ids)} observed={len(observed_ids)}"
        )
    expected_per_question = model_count * (model_count - 1)
    by_question: dict[str, list[JudgmentRecord]] = defaultdict(list)
    for record in judgments:
        by_question[record.question_id].append(record)
    wrong_counts = {
        question_id: len(records)
        for question_id, records in by_question.items()
        if len(records) != expected_per_question
    }
    if wrong_counts:
        raise EvaluationError(
            f"{variant} expected {expected_per_question} judgments per question; "
            f"mismatches={wrong_counts}"
        )

    graphs = []
    questions: list[dict[str, Any]] = []
    graph_dir = output_dir / variant / "graphs"
    for question_id in sorted(evaluation_ids):
        relations = aggregate_pair_judgments(by_question[question_id])
        graph = build_question_graph(relations).graph
        graphs.append(graph)
        scc = analyze_scc(graph)
        entropy = structural_entropy(graph)
        reciprocal_edges = sum(
            1 for source, target in graph.edges if graph.has_edge(target, source)
        )
        questions.append(
            {
                "question_id": question_id,
                "nodes": graph.number_of_nodes(),
                "edges": graph.number_of_edges(),
                "components": scc.components,
                "non_transitive_components": scc.non_transitive_components,
                "scc_count": len(scc.components),
                "max_scc_size": scc.max_scc_size,
                "rho_non_trans": scc.rho_non_trans,
                "h2": entropy.h2,
                "tau": entropy.tau,
                "tie_ratio": (
                    reciprocal_edges / graph.number_of_edges()
                    if graph.number_of_edges()
                    else 0.0
                ),
            }
        )
        filename = f"{question_id}.json"
        write_graph(graph_dir / filename, graph, question_id=question_id)
        write_graph_svg(
            graph_dir / f"{question_id}.svg",
            graph,
            title=f"{variant} unseen graph: {question_id}",
        )
    return {
        "variant": variant,
        "judgments_path": str(judgments_path),
        "judgments_sha256": _sha256_file(judgments_path),
        "judgment_count": len(judgments),
        "question_count": len(questions),
        "rho_non_trans": dataset_non_transitivity(graphs),
        "tau_avg": average_structural_entropy(graphs),
        "mean_tie_ratio": sum(item["tie_ratio"] for item in questions) / len(questions),
        "questions": questions,
    }


def _markdown_report(summary: dict[str, Any]) -> str:
    metrics = summary["variants"]
    lines = [
        "# ELSPR Level 2 Unseen Evaluation",
        "",
        "| Variant | Judgments | rho_non_trans | tau_avg | Mean tie ratio |",
        "|---|---:|---:|---:|---:|",
    ]
    for variant in ("raw", "cleaned", "random"):
        item = metrics[variant]
        lines.append(
            f"| {variant} | {item['judgment_count']} | "
            f"{item['rho_non_trans']:.6f} | {item['tau_avg']:.6f} | "
            f"{item['mean_tie_ratio']:.6f} |"
        )
    conclusion = summary["conclusion"]
    lines.extend(
        [
            "",
            "## Direction check",
            "",
            f"- cleaned rho lower than raw: {conclusion['cleaned_improves_rho']}",
            f"- cleaned tau lower than raw: {conclusion['cleaned_improves_tau']}",
            (
                "- cleaned improves both required metrics: "
                f"{conclusion['cleaned_improves_both']}"
            ),
            (
                "- random matches or beats cleaned on both metrics: "
                f"{conclusion['random_matches_or_beats_cleaned_both']}"
            ),
            "",
            (
                "A single small random baseline cannot establish stability; "
                "the last flag is descriptive, not a stability claim."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def evaluate_variants(config: EvaluationConfig) -> EvaluationResult:
    """Evaluate all variants on exactly the frozen unseen question set."""

    train_ids, evaluation_ids, model_count = _load_manifest(config.data_manifest)
    training_manifest = json.loads(config.training_manifest.read_text(encoding="utf-8"))
    metrics = {
        variant: _variant_metrics(
            variant=variant,
            judgments_path=getattr(config, f"{variant}_judgments"),
            train_ids=train_ids,
            evaluation_ids=evaluation_ids,
            model_count=model_count,
            output_dir=config.output_dir,
        )
        for variant in ("raw", "cleaned", "random")
    }
    cleaned_improves_rho = (
        metrics["cleaned"]["rho_non_trans"] < metrics["raw"]["rho_non_trans"]
    )
    cleaned_improves_tau = metrics["cleaned"]["tau_avg"] < metrics["raw"]["tau_avg"]
    random_matches_or_beats = (
        metrics["random"]["rho_non_trans"] <= metrics["cleaned"]["rho_non_trans"]
        and metrics["random"]["tau_avg"] <= metrics["cleaned"]["tau_avg"]
    )
    summary = {
        "schema_version": 1,
        "data_manifest_sha256": _sha256_file(config.data_manifest),
        "training_manifest_sha256": _sha256_file(config.training_manifest),
        "training_counts": {
            key: training_manifest[key]
            for key in ("raw_count", "cleaned_count", "random_count")
        },
        "train_question_count": len(train_ids),
        "evaluation_question_count": len(evaluation_ids),
        "model_count": model_count,
        "variants": metrics,
        "conclusion": {
            "cleaned_improves_rho": cleaned_improves_rho,
            "cleaned_improves_tau": cleaned_improves_tau,
            "cleaned_improves_both": (cleaned_improves_rho and cleaned_improves_tau),
            "random_matches_or_beats_cleaned_both": random_matches_or_beats,
        },
    }
    config.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = config.output_dir / "summary.json"
    report_path = config.output_dir / "REPORT.md"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(_markdown_report(summary), encoding="utf-8")
    return EvaluationResult(
        summary_path=summary_path,
        report_path=report_path,
        question_count=len(evaluation_ids),
        cleaned_improves_rho=cleaned_improves_rho,
        cleaned_improves_tau=cleaned_improves_tau,
    )
