import typer

from audio2score import __version__

app = typer.Typer(help="Klavieraufnahme rein, Noten raus.", no_args_is_help=True)


def _version(value: bool) -> None:
    if value:
        typer.echo(f"audio2score {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version, is_eager=True, help="Version anzeigen."
    ),
) -> None:
    pass
