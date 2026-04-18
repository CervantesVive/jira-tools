"""Jira CLI — entry point for the `jira` command."""
import typer

from jira_tools.commands.get_statistics import get_statistics
from jira_tools.commands.links import links
from jira_tools.commands.to_linear import to_linear
from jira_tools.commands.weekly_changelog import weekly_changelog
from jira_tools.commands.notify_release import notify_release

app = typer.Typer(
    name="jira",
    help="JIRA API CLI tools.",
    no_args_is_help=True,
)

app.command(name="get-statistics")(get_statistics)
app.command(name="links")(links)
app.command(name="to-linear")(to_linear)
app.command(name="weekly-changelog")(weekly_changelog)
app.command(name="notify-release")(notify_release)

if __name__ == "__main__":
    app()
