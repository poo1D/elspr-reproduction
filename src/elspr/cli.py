"""Command-line entry point for the ELSPR reproduction."""

import typer

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


if __name__ == "__main__":
    app()
