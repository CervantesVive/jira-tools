"""Calculate story point statistics for JIRA issues matching a JQL query."""
import sys
import json
from typing_extensions import Annotated
import typer
from jira_tools import utils as jira_utils

# Configuration constants
# JIRA custom field ID for story points (adjust for your instance if different)
STORY_POINT_FIELD_ID = 'customfield_10115'

# Default story points for issues without explicit values
DEFAULT_STORY_POINTS = 3


def calculate_story_points_for_issues(issues):
    """Calculate story points for a list of issues

    Args:
        issues: List of issue objects from JIRA API with story point field

    Returns:
        tuple: (total_points, defaulted_count, explicit_count)
    """

    total_points = 0
    defaulted_count = 0
    explicit_count = 0

    for issue in issues:
        # Get story points (use default if None)
        story_points = issue['fields'].get(STORY_POINT_FIELD_ID)
        is_defaulted = story_points is None

        if is_defaulted:
            story_points = DEFAULT_STORY_POINTS
            defaulted_count += 1
        else:
            explicit_count += 1

        total_points += story_points

    return total_points, defaulted_count, explicit_count


def get_jql_query_statistics(jql_query):
    """Get comprehensive statistics for issues matching a JQL query

    Args:
        jql_query: JQL query string to filter issues

    Returns:
        dict: Statistics including:
            - total_points: Total story points across all issues
            - resolved_points: Story points of resolved issues
            - unresolved_points: Story points of unresolved issues
            - resolved_points_percentage: Percentage of resolved story points
            - total_issues: Total number of issues
            - resolved_issues: Number of resolved issues
            - unresolved_issues: Number of unresolved issues
            - resolved_issues_percentage: Percentage of resolved issues
    """
    fields = ['key', 'summary', 'resolution', STORY_POINT_FIELD_ID]

    # Get all issues matching the JQL query
    result = jira_utils.search_jira_with_jql(jql_query, fields)
    issues = result.get('issues', [])

    # Separate resolved and unresolved issues
    resolved_issues = []
    unresolved_issues = []

    for issue in issues:
        resolution = issue['fields'].get('resolution')
        if resolution is not None:
            resolved_issues.append(issue)
        else:
            unresolved_issues.append(issue)

    # Calculate story points for resolved issues
    resolved_points, _, _ = calculate_story_points_for_issues(resolved_issues)

    # Calculate story points for unresolved issues
    unresolved_points, _, _ = calculate_story_points_for_issues(unresolved_issues)

    # Total is sum of resolved and unresolved
    total_points = resolved_points + unresolved_points

    # Calculate counts
    total_issues = len(issues)
    total_resolved_issues = len(resolved_issues)
    total_unresolved_issues = len(unresolved_issues)

    # Calculate percentages (rounded to nearest whole number)
    resolved_points_percentage = round((resolved_points / total_points * 100)) if total_points > 0 else 0
    resolved_issues_percentage = round((total_resolved_issues / total_issues * 100)) if total_issues > 0 else 0

    return {
        'total_points': total_points,
        'resolved_points': resolved_points,
        'unresolved_points': unresolved_points,
        'resolved_points_percentage': resolved_points_percentage,
        'total_issues': total_issues,
        'resolved_issues': total_resolved_issues,
        'unresolved_issues': total_unresolved_issues,
        'resolved_issues_percentage': resolved_issues_percentage
    }


def get_statistics(
    jql_query: Annotated[str, typer.Argument(help="JQL query string")],
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output")] = False,
):
    if verbose:
        jira_utils.VERBOSE = True

    if not jql_query.strip():
        typer.echo("Error: JQL query cannot be empty", err=True)
        raise typer.Exit(1)

    if verbose:
        typer.echo(f"Processing JQL query...", err=True)
        typer.echo(f"  JQL: {jql_query}", err=True)

    # Get comprehensive statistics for the query
    stats = get_jql_query_statistics(jql_query)

    # Verbose console output with statistics
    if verbose:
        typer.echo(f"  Found {stats['total_issues']} issues, {stats['total_points']} total points", err=True)

        if stats['total_issues'] > 0:
            typer.echo(f"    Resolved: {stats['resolved_issues']} issues, {stats['resolved_points']} points ({stats['resolved_points_percentage']}%)", err=True)
            typer.echo(f"    Unresolved: {stats['unresolved_issues']} issues, {stats['unresolved_points']} points", err=True)

        typer.echo("", err=True)

    # JSON output to stdout (always)
    output = {
        'jql_query': jql_query,
        **stats
    }
    typer.echo(json.dumps(output, indent=2))
