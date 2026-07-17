import json
from pathlib import Path

from typer.testing import CliRunner

from elspr.cli import app
from elspr.io import write_jsonl
from elspr.toy import toy_judgments

runner = CliRunner()


def test_one_command_toy_pipeline_writes_all_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "toy"

    result = runner.invoke(app, ["toy-pipeline", "--output-dir", str(output)])

    assert result.exit_code == 0, result.output
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert len(summary["cases"]) == 5
    for case in ["linear", "cycle", "all_tie", "position_bias", "reconstruction"]:
        case_dir = output / case
        assert (case_dir / "judgments.jsonl").exists()
        assert (case_dir / "pair_relations.jsonl").exists()
        assert (case_dir / "graph.json").exists()
        assert (case_dir / "analysis.json").exists()
        assert (case_dir / "reconstructed_graph.json").exists()
        assert (case_dir / "cleaned.jsonl").exists()
        assert (case_dir / "discarded.jsonl").exists()


def test_report_is_generated_from_toy_summary(tmp_path: Path) -> None:
    output = tmp_path / "toy"
    assert (
        runner.invoke(
            app,
            ["toy-pipeline", "--output-dir", str(output), "--case", "linear"],
        ).exit_code
        == 0
    )

    result = runner.invoke(app, ["report", "--run-dir", str(output)])

    assert result.exit_code == 0, result.output
    report = (output / "REPORT.md").read_text(encoding="utf-8")
    assert "| linear | 0.000000 | 0.000000 | 6 | 6 | 0 |" in report


def test_build_analyze_and_filter_commands_compose(tmp_path: Path) -> None:
    judgments_path = tmp_path / "judgments.jsonl"
    graphs_dir = tmp_path / "graphs"
    analysis_path = tmp_path / "analysis.json"
    filtered_dir = tmp_path / "filtered"
    write_jsonl(judgments_path, toy_judgments("linear"))

    build = runner.invoke(
        app,
        [
            "build-graphs",
            "--judgments",
            str(judgments_path),
            "--output-dir",
            str(graphs_dir),
        ],
    )
    analysis = runner.invoke(
        app,
        [
            "analyze",
            "--graphs",
            str(graphs_dir),
            "--output",
            str(analysis_path),
        ],
    )
    filtering = runner.invoke(
        app,
        [
            "filter",
            "--graphs",
            str(graphs_dir),
            "--judgments",
            str(judgments_path),
            "--output-dir",
            str(filtered_dir),
        ],
    )

    assert build.exit_code == 0, build.output
    assert analysis.exit_code == 0, analysis.output
    assert filtering.exit_code == 0, filtering.output
    metrics = json.loads(analysis_path.read_text(encoding="utf-8"))
    assert metrics["rho_non_trans"] == 0.0
    assert metrics["tau_avg"] == 0.0
    assert len((filtered_dir / "cleaned.jsonl").read_text().splitlines()) == 6
    assert (filtered_dir / "discarded.jsonl").read_text() == ""


def test_toy_pipeline_rejects_unknown_case(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "toy-pipeline",
            "--output-dir",
            str(tmp_path),
            "--case",
            "missing",
        ],
    )

    assert result.exit_code != 0
    assert "unknown case" in result.output
