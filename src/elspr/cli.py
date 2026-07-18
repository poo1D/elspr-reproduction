"""Command-line entry point for the ELSPR reproduction."""

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Annotated, Literal

import typer

from elspr.data import load_data_config, prepare_data
from elspr.filtering import filter_question_judgments
from elspr.graph import (
    analyze_scc,
    average_structural_entropy,
    build_question_graph,
    dataset_non_transitivity,
    read_graph,
    reconstruct_sccs,
    structural_entropy,
    write_graph,
    write_graph_svg,
)
from elspr.io import read_jsonl, write_jsonl
from elspr.judging import (
    aggregate_pair_judgments,
    execute_judgments,
    judge_dry_run,
    load_judge_config,
)
from elspr.schemas import JudgmentRecord
from elspr.toy import TOY_CASES, run_toy_case
from elspr.training import (
    build_training_variants,
    load_training_data_config,
    load_training_run_config,
    train_lora,
)

app = typer.Typer(
    help="Auditable ELSPR preference-data purification pipeline.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Run the ELSPR reproduction pipeline."""


@app.command()
def version() -> None:
    """Print the package version."""
    from elspr import __version__

    typer.echo(__version__)


@app.command("prepare-data")
def prepare_data_command(
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
) -> None:
    """Prepare a pinned, checksum-verified response subset."""

    result = prepare_data(load_data_config(config))
    typer.echo(
        f"prepared questions={result.question_count} "
        f"models={result.model_count} responses={result.response_count} "
        f"at {result.responses_path.parent}"
    )


@app.command()
def judge(
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    resume: Annotated[bool, typer.Option()] = False,
    execute_paid: Annotated[bool, typer.Option()] = False,
    approved_budget_cny: Annotated[float, typer.Option(min=0)] = 0.0,
    max_new_requests: Annotated[int, typer.Option(min=0)] = 0,
) -> None:
    """Render requests or execute an explicitly authorized paid batch."""

    judge_config = load_judge_config(config)
    if judge_config.provider == "dry_run":
        if execute_paid:
            raise typer.BadParameter(
                "provider is dry_run; paid execution was not attempted"
            )
        result = judge_dry_run(judge_config)
        typer.echo(
            f"dry-run questions={result.question_count} models={result.model_count} "
            f"requests={result.request_count} "
            f"estimated_input_tokens={result.estimated_input_tokens} "
            f"maximum_output_tokens={result.maximum_output_tokens}"
        )
        return
    if not resume:
        raise typer.BadParameter("provider execution requires --resume")
    execution = execute_judgments(
        judge_config,
        execute_paid=execute_paid,
        approved_budget_cny=approved_budget_cny,
        max_new_requests=max_new_requests,
    )
    typer.echo(
        f"execution cached={execution.cached_count} new={execution.new_count} "
        f"failed={execution.failed_count} pending={execution.pending_count} "
        f"actual_cost_cny={execution.actual_cost_cny:.6f}"
    )


@app.command("prepare-training")
def prepare_training(
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
) -> None:
    """Build traceable raw, cleaned, and size-matched random SFT data."""

    result = build_training_variants(load_training_data_config(config))
    typer.echo(
        f"training-data raw={result.raw_count} cleaned={result.cleaned_count} "
        f"random={result.random_count} at {result.manifest_path.parent}"
    )


@app.command()
def train(
    variant: Annotated[Literal["raw", "cleaned", "random"], typer.Option()],
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    execute_training: Annotated[bool, typer.Option()] = False,
    resume_from_checkpoint: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Plan or explicitly execute one pinned LoRA training variant."""

    result = train_lora(
        load_training_run_config(config),
        variant=variant,
        execute_training=execute_training,
        resume_from_checkpoint=resume_from_checkpoint,
    )
    typer.echo(
        f"training variant={result.variant} run_id={result.run_id} "
        f"examples={result.example_count} plan={result.plan_path} "
        f"executed={execute_training}"
    )


def _safe_name(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    digest = hashlib.sha256(value.encode()).hexdigest()[:8]
    return f"{slug or 'question'}-{digest}"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _graph_files(path: Path) -> list[Path]:
    return sorted(path.glob("*.json")) if path.is_dir() else [path]


@app.command("build-graphs")
def build_graphs(
    judgments: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output_dir: Annotated[Path, typer.Option()] = Path("artifacts/graphs"),
) -> None:
    """Aggregate judgments and write one validated graph per question."""

    records = read_jsonl(judgments, JudgmentRecord)
    by_question: dict[str, list[JudgmentRecord]] = defaultdict(list)
    for record in records:
        by_question[record.question_id].append(record)

    manifest: list[dict[str, object]] = []
    for question_id, question_records in sorted(by_question.items()):
        relations = aggregate_pair_judgments(question_records)
        question_graph = build_question_graph(relations)
        filename = f"{_safe_name(question_id)}.json"
        write_graph(
            output_dir / filename,
            question_graph.graph,
            question_id=question_id,
        )
        svg_filename = f"{Path(filename).stem}.svg"
        write_graph_svg(
            output_dir / svg_filename,
            question_graph.graph,
            title=f"ELSPR graph: {question_id}",
        )
        manifest.append(
            {
                "question_id": question_id,
                "file": filename,
                "visualization": svg_filename,
                "nodes": question_graph.graph.number_of_nodes(),
                "edges": question_graph.graph.number_of_edges(),
            }
        )
    _write_json(output_dir / "manifest.json", {"graphs": manifest})
    typer.echo(f"wrote {len(manifest)} graphs to {output_dir}")


@app.command()
def analyze(
    graphs: Annotated[Path, typer.Option(exists=True)],
    output: Annotated[Path, typer.Option()] = Path("artifacts/analysis.json"),
) -> None:
    """Compute per-question and aggregate SCC and entropy metrics."""

    loaded = [
        (question_id, graph)
        for path in _graph_files(graphs)
        if path.name != "manifest.json"
        for question_id, graph in [read_graph(path)]
    ]
    questions: list[dict[str, object]] = []
    for question_id, graph in loaded:
        scc = analyze_scc(graph)
        entropy = structural_entropy(graph)
        reciprocal_edges = sum(
            1 for source, target in graph.edges if graph.has_edge(target, source)
        )
        questions.append(
            {
                "question_id": question_id,
                "nodes": scc.total_nodes,
                "scc_count": len(scc.components),
                "max_scc_size": scc.max_scc_size,
                "components": scc.components,
                "non_transitive_components": scc.non_transitive_components,
                "non_transitive_nodes": scc.non_transitive_nodes,
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
    graph_values = [graph for _, graph in loaded]
    payload = {
        "question_count": len(loaded),
        "rho_non_trans": dataset_non_transitivity(graph_values),
        "tau_avg": average_structural_entropy(graph_values),
        "questions": questions,
    }
    _write_json(output, payload)
    typer.echo(f"wrote analysis to {output}")


@app.command("filter")
def filter_command(
    graphs: Annotated[Path, typer.Option(exists=True)],
    judgments: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output_dir: Annotated[Path, typer.Option()] = Path("artifacts/filtered"),
) -> None:
    """Reconstruct graphs and split ordered judgments."""

    records = read_jsonl(judgments, JudgmentRecord)
    by_question: dict[str, list[JudgmentRecord]] = defaultdict(list)
    for record in records:
        by_question[record.question_id].append(record)

    cleaned: list[JudgmentRecord] = []
    discarded: list[JudgmentRecord] = []
    decisions: list[dict[str, object]] = []
    reconstructed_manifest: list[dict[str, str]] = []
    reconstructed_dir = output_dir / "reconstructed_graphs"
    for path in _graph_files(graphs):
        if path.name == "manifest.json":
            continue
        question_id, graph = read_graph(path)
        reconstruction = reconstruct_sccs(graph)
        reconstructed_name = path.name
        reconstructed_svg_name = f"{path.stem}.svg"
        write_graph(
            reconstructed_dir / reconstructed_name,
            reconstruction.graph,
            question_id=question_id,
        )
        write_graph_svg(
            reconstructed_dir / reconstructed_svg_name,
            reconstruction.graph,
            title=f"ELSPR reconstructed graph: {question_id}",
        )
        reconstructed_manifest.append(
            {
                "question_id": question_id,
                "file": reconstructed_name,
                "visualization": reconstructed_svg_name,
            }
        )
        result = filter_question_judgments(
            reconstruction.graph,
            by_question.pop(question_id, []),
            question_id=question_id,
        )
        cleaned.extend(result.cleaned)
        discarded.extend(result.discarded)
        decisions.extend(
            {
                "question_id": item.judgment.question_id,
                "left_model": item.judgment.left_model,
                "right_model": item.judgment.right_model,
                "original": item.judgment.normalized_left_outcome.value,
                "target": item.target.value,
                "kept": item.kept,
                "reason": item.reason,
            }
            for item in result.decisions
        )
    if by_question:
        raise typer.BadParameter(
            f"judgments have no graph for questions {sorted(by_question)}"
        )
    write_jsonl(output_dir / "cleaned.jsonl", cleaned)
    write_jsonl(output_dir / "discarded.jsonl", discarded)
    _write_json(output_dir / "decisions.json", decisions)
    _write_json(
        reconstructed_dir / "manifest.json",
        {"graphs": reconstructed_manifest},
    )
    typer.echo(f"cleaned={len(cleaned)} discarded={len(discarded)}")


def _toy_summary(case: str, output_dir: Path) -> dict[str, object]:
    result = run_toy_case(case)
    case_dir = output_dir / case
    relations = aggregate_pair_judgments(result.judgments)
    write_jsonl(case_dir / "judgments.jsonl", result.judgments)
    write_jsonl(case_dir / "pair_relations.jsonl", relations)
    write_jsonl(case_dir / "cleaned.jsonl", result.filtering.cleaned)
    write_jsonl(case_dir / "discarded.jsonl", result.filtering.discarded)
    write_graph(
        case_dir / "graph.json",
        result.question_graph.graph,
        question_id=result.question_graph.question_id,
    )
    write_graph_svg(
        case_dir / "graph.svg",
        result.question_graph.graph,
        title=f"ELSPR graph: {result.question_graph.question_id}",
    )
    write_graph(
        case_dir / "reconstructed_graph.json",
        result.reconstruction.graph,
        question_id=result.question_graph.question_id,
    )
    write_graph_svg(
        case_dir / "reconstructed_graph.svg",
        result.reconstruction.graph,
        title=f"ELSPR reconstructed graph: {result.question_graph.question_id}",
    )
    analysis = {
        "question_id": result.question_graph.question_id,
        "rho_non_trans": result.scc.rho_non_trans,
        "tau": result.entropy.tau,
        "h2": result.entropy.h2,
        "components": result.scc.components,
        "non_transitive_components": result.scc.non_transitive_components,
        "tie_classes": result.reconstruction.tie_classes,
        "quotient_is_dag": True,
        "raw_count": len(result.judgments),
        "cleaned_count": len(result.filtering.cleaned),
        "discarded_count": len(result.filtering.discarded),
    }
    _write_json(case_dir / "analysis.json", analysis)
    return {"case": case, **analysis}


@app.command("toy-pipeline")
def toy_pipeline(
    output_dir: Annotated[Path, typer.Option()] = Path("artifacts/toy"),
    case: Annotated[str, typer.Option()] = "all",
) -> None:
    """Run one or all deterministic cases and save every major artifact."""

    cases = TOY_CASES if case == "all" else (case,)
    invalid = set(cases) - set(TOY_CASES)
    if invalid:
        raise typer.BadParameter(f"unknown case {sorted(invalid)}")
    summaries = [_toy_summary(item, output_dir) for item in cases]
    _write_json(output_dir / "summary.json", {"cases": summaries})
    typer.echo(f"completed {len(summaries)} toy cases in {output_dir}")


@app.command()
def report(
    run_dir: Annotated[Path, typer.Option(exists=True, file_okay=False)],
) -> None:
    """Generate a Markdown report from a toy-pipeline run."""

    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        raise typer.BadParameter(f"missing {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    lines = [
        "# ELSPR Level 1 Toy Report",
        "",
        "| Case | rho_non_trans | tau | Raw | Cleaned | Discarded |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in summary["cases"]:
        lines.append(
            f"| {item['case']} | {item['rho_non_trans']:.6f} | "
            f"{item['tau']:.6f} | {item['raw_count']} | "
            f"{item['cleaned_count']} | {item['discarded_count']} |"
        )
    lines.extend(
        [
            "",
            (
                "Every row is backed by the JSON and JSONL artifacts "
                "in its case directory."
            ),
            "",
        ]
    )
    output = run_dir / "REPORT.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    typer.echo(f"wrote report to {output}")


if __name__ == "__main__":
    app()
