"""Notify JIRA tickets about production releases by posting ADF-formatted comments."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import Optional
from typing_extensions import Annotated

import typer
from dotenv import load_dotenv

load_dotenv()

from jira_tools.utils import extract_jira_keys, post_comment_to_issue, JIRA_SERVER
from tools_shared.logging import setup_logging, log_info, log_warning, log_error, log_success


# ---------------------------------------------------------------------------
# gh CLI helpers
# ---------------------------------------------------------------------------

def check_gh_installed():
    """Verify that the gh CLI is available on PATH.

    Raises:
        SystemExit: if gh is not found, with install instructions.
    """
    if shutil.which("gh") is None:
        log_error(
            "gh CLI is not installed or not on PATH.\n"
            "Install it from https://cli.github.com/ and authenticate with `gh auth login`."
        )
        sys.exit(1)


def run_gh(args: list[str]) -> str:
    """Run a gh CLI command and return stdout.

    Args:
        args: Command-line arguments **after** ``gh`` (e.g. ``["api", "…"]``).

    Returns:
        Stripped stdout string.

    Raises:
        RuntimeError: on non-zero exit code.
    """
    cmd = ["gh"] + args
    log_info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gh command failed (exit {result.returncode}): {result.stderr.strip()}")
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Commit-range resolution
# ---------------------------------------------------------------------------

def auto_detect_shas(repo: str) -> tuple[str, str, str]:
    """Detect the previous and current release SHAs from workflow runs.

    Queries the last 2 successful runs of ``release-prod.yaml``.

    Args:
        repo: GitHub repo in ``owner/name`` format.

    Returns:
        Tuple of (from_sha, to_sha, run_url) where *run_url* is the
        current (most recent) workflow run URL.

    Raises:
        SystemExit: if fewer than 2 successful runs are found.
    """
    raw = run_gh([
        "run", "list",
        "--repo", repo,
        "--workflow", "release-prod.yaml",
        "--status", "success",
        "--limit", "2",
        "--json", "headSha,url",
    ])

    runs = json.loads(raw) if raw else []
    if len(runs) < 2:
        log_error("Could not auto-detect release SHAs: fewer than 2 successful workflow runs found.")
        sys.exit(0)

    # runs[0] = most recent, runs[1] = previous
    to_sha = runs[0]["headSha"]
    from_sha = runs[1]["headSha"]
    run_url = runs[0]["url"]
    return from_sha, to_sha, run_url


def get_commits_between(repo: str, from_sha: str, to_sha: str) -> list[dict]:
    """Fetch commits between two SHAs via the GitHub compare API.

    Args:
        repo: GitHub repo in ``owner/name`` format.
        from_sha: Base commit SHA.
        to_sha: Head commit SHA.

    Returns:
        List of commit dicts from the GitHub API response.
    """
    raw = run_gh([
        "api",
        f"repos/{repo}/compare/{from_sha}...{to_sha}",
        "--jq", ".commits",
    ])
    return json.loads(raw) if raw else []


# ---------------------------------------------------------------------------
# Ticket extraction
# ---------------------------------------------------------------------------

def extract_tickets_from_commits(commits: list[dict]) -> list[str]:
    """Extract deduplicated JIRA keys from a list of commit objects.

    Scans each commit's message using ``jira_utils.extract_jira_keys``.

    Args:
        commits: GitHub API commit objects (must have ``commit.message``).

    Returns:
        Deduplicated list of JIRA keys preserving first-seen order.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for commit in commits:
        message = commit.get("commit", {}).get("message", "")
        keys = extract_jira_keys(message)
        for key in keys:
            if key not in seen:
                seen.add(key)
                ordered.append(key)
    return ordered


# ---------------------------------------------------------------------------
# ADF comment builder
# ---------------------------------------------------------------------------

def build_release_comment_adf(to_sha: str, run_url: str | None = None) -> dict:
    """Build an Atlassian Document Format comment for a release notification.

    Args:
        to_sha: The release commit SHA (shown in the comment).
        run_url: Optional GitHub Actions run URL to link to.

    Returns:
        ADF-formatted dict suitable for JIRA REST API v3 ``/comment`` endpoint.
    """
    short_sha = to_sha[:7]

    # Build inline content for first paragraph
    inline: list[dict] = [
        {"type": "text", "text": "Released to "},
        {"type": "text", "text": "production", "marks": [{"type": "strong"}]},
    ]

    if run_url:
        inline.append({"type": "text", "text": " via "})
        inline.append({
            "type": "text",
            "text": "GitHub Actions",
            "marks": [{"type": "link", "attrs": {"href": run_url}}],
        })

    return {
        "version": 1,
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": inline},
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Commit: "},
                    {"type": "text", "text": short_sha, "marks": [{"type": "code"}]},
                ],
            },
        ],
    }


# ---------------------------------------------------------------------------
# Notification engine
# ---------------------------------------------------------------------------

def notify_tickets(
    tickets: list[str],
    to_sha: str,
    run_url: str | None,
    dry_run: bool,
) -> list[dict]:
    """Post release comments to each JIRA ticket.

    Args:
        tickets: List of JIRA issue keys.
        to_sha: Release commit SHA (used in comment body).
        run_url: Optional workflow run URL.
        dry_run: If True, skip actual API calls.

    Returns:
        List of result dicts: ``{"ticket", "status", "message"}``.
    """
    comment_adf = build_release_comment_adf(to_sha, run_url)
    results: list[dict] = []

    for ticket in tickets:
        if dry_run:
            results.append({"ticket": ticket, "status": "skipped", "message": "Dry run"})
            log_info(f"[DRY RUN] Would post comment to {ticket}")
            continue

        success, status_code, message = post_comment_to_issue(ticket, comment_adf)
        if success:
            results.append({"ticket": ticket, "status": "posted", "message": message})
            log_success(f"Posted comment to {ticket}")
        else:
            results.append({"ticket": ticket, "status": "failed", "message": message})
            log_warning(f"Failed to post to {ticket}: {message}")

    return results


# ---------------------------------------------------------------------------
# Rich output
# ---------------------------------------------------------------------------

def print_summary(results: list[dict], dry_run: bool):
    """Print a summary table of notification results using rich.

    Args:
        results: List of result dicts from ``notify_tickets``.
        dry_run: Whether this was a dry-run invocation.
    """
    try:
        from rich.console import Console
        from rich.table import Table
        _print_rich_summary(results, dry_run)
    except ImportError:
        _print_plain_summary(results, dry_run)


def _print_rich_summary(results: list[dict], dry_run: bool):
    from rich.console import Console
    from rich.table import Table

    console = Console()

    if dry_run:
        console.print("\n[bold yellow]── DRY RUN ── No comments were posted ──[/bold yellow]\n")

    table = Table(title="Release Notification Results")
    table.add_column("Ticket", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Link")

    for r in results:
        status = r["status"]
        if status == "posted":
            style = "[green]posted[/green]"
        elif status == "skipped":
            style = "[yellow]skipped[/yellow]"
        else:
            style = f"[red]failed[/red] ({r['message']})"

        link = f"{JIRA_SERVER}/browse/{r['ticket']}"
        table.add_row(r["ticket"], style, link)

    console.print(table)

    posted = sum(1 for r in results if r["status"] == "posted")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "failed")
    console.print(f"\nTotal: {len(results)} | Posted: {posted} | Skipped: {skipped} | Failed: {failed}")


def _print_plain_summary(results: list[dict], dry_run: bool):
    if dry_run:
        print("\n── DRY RUN ── No comments were posted ──\n")

    print(f"{'Ticket':<16} {'Status':<10} Link")
    print("-" * 60)
    for r in results:
        link = f"{JIRA_SERVER}/browse/{r['ticket']}"
        print(f"{r['ticket']:<16} {r['status']:<10} {link}")

    posted = sum(1 for r in results if r["status"] == "posted")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "failed")
    print(f"\nTotal: {len(results)} | Posted: {posted} | Skipped: {skipped} | Failed: {failed}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def notify_release(
    repo: Annotated[str, typer.Option("--repo", help="GitHub repo (owner/name)", show_default=False)],
    from_sha: Annotated[Optional[str], typer.Option("--from", help="Starting SHA (auto-detected if omitted)")] = None,
    to_sha: Annotated[Optional[str], typer.Option("--to", help="Ending SHA (auto-detected if omitted)")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be posted without posting")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output")] = False,
):
    setup_logging(verbose)
    check_gh_installed()

    # Resolve commit range
    run_url: str | None = None
    if from_sha and to_sha:
        log_info(f"Explicit range: {from_sha[:7]}..{to_sha[:7]}")
    else:
        log_info("Auto-detecting release SHAs from workflow runs...")
        from_sha, to_sha, run_url = auto_detect_shas(repo)
        log_info(f"Detected range: {from_sha[:7]}..{to_sha[:7]}")

    # Fetch commits
    log_info("Fetching commits...")
    commits = get_commits_between(repo, from_sha, to_sha)
    log_info(f"Found {len(commits)} commits")

    if not commits:
        print("No commits found in the specified range.")
        return

    # Extract tickets
    tickets = extract_tickets_from_commits(commits)
    log_info(f"Found {len(tickets)} unique JIRA tickets: {', '.join(tickets)}")

    if not tickets:
        print("No JIRA tickets found in commit messages.")
        return

    # Notify
    results = notify_tickets(tickets, to_sha, run_url, dry_run=dry_run)

    # Summary
    print_summary(results, dry_run=dry_run)
