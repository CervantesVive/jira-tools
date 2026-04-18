"""Generate a weekly changelog from local Git repositories."""
import subprocess
import sys
import re
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path
from typing import Optional
from typing import Annotated
import typer

# Configuration
REPOS = [
    "/Users/ivopletikosic/development/acme-ui",
    "/Users/ivopletikosic/development/acme-retail"
]

# JIRA project keys to look for (customize this)
JIRA_PATTERNS = [
    r'\b([A-Z]{2,10}-\d+)\b',  # Standard JIRA format like ABC-123
]


def extract_jira_refs(text):
    """Extract JIRA references from commit message"""
    refs = []
    for pattern in JIRA_PATTERNS:
        refs.extend(re.findall(pattern, text))
    return list(set(refs))  # Unique refs


def get_git_changes(repo_path, since_date):
    """Get git changes from a repository since a specific date"""
    try:
        result = subprocess.run(
            [
                'git', 'log',
                f'--since={since_date}',
                '--pretty=format:%aN|%ae|%h|%s|%ar|%aI'
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )

        changes = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('|')
            if len(parts) >= 6:
                changes.append({
                    'author': parts[0],
                    'email': parts[1],
                    'hash': parts[2],
                    'message': parts[3],
                    'relative_time': parts[4],
                    'timestamp': parts[5],
                    'jira_refs': extract_jira_refs(parts[3])
                })

        return changes
    except subprocess.CalledProcessError as e:
        print(f"Error getting changes from {repo_path}: {e}", file=sys.stderr)
        return []


def format_change_description(commit):
    """Format a commit into a friendly description"""
    msg = commit['message']

    # Clean up common commit message prefixes
    msg = re.sub(r'^(feat|fix|docs|style|refactor|test|chore):\s*', '', msg, flags=re.IGNORECASE)
    msg = re.sub(r'^(feature|bugfix|hotfix)\/[^:]+:\s*', '', msg, flags=re.IGNORECASE)

    # Capitalize first letter
    if msg:
        msg = msg[0].upper() + msg[1:]

    return msg


def generate_demo_hint(commit):
    """Generate a hint about how to demo this change"""
    msg = commit['message'].lower()

    if 'ui' in msg or 'frontend' in msg or 'component' in msg:
        return "Check UI changes"
    elif 'api' in msg or 'endpoint' in msg or 'route' in msg:
        return "Test API endpoint"
    elif 'bug' in msg or 'fix' in msg:
        return "Verify bug fix"
    elif 'test' in msg:
        return "Review test coverage"
    elif 'performance' in msg or 'optimize' in msg:
        return "Measure performance improvement"
    elif 'database' in msg or 'migration' in msg or 'schema' in msg:
        return "Review database changes"
    else:
        return "Review functionality"


def generate_changelog(repos, since_date):
    """Generate changelog for all repositories"""
    all_changes_by_repo = {}

    for repo_path in repos:
        repo_name = Path(repo_path).name
        changes = get_git_changes(repo_path, since_date)
        if changes:
            all_changes_by_repo[repo_name] = changes

    if not all_changes_by_repo:
        print(f"No changes found since {since_date}")
        return

    # Print header
    print("=" * 80)
    print(f"WEEKLY CHANGELOG - Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Changes since: {since_date}")
    print("=" * 80)
    print()

    # Process each repository
    for repo_name, changes in all_changes_by_repo.items():
        print(f"\n{'#' * 80}")
        print(f"# REPOSITORY: {repo_name}")
        print(f"{'#' * 80}\n")

        # Group by author
        by_author = defaultdict(list)
        for change in changes:
            by_author[change['author']].append(change)

        # Print changes by author
        for author in sorted(by_author.keys()):
            author_changes = by_author[author]
            print(f"\n## {author} ({len(author_changes)} commits)")
            print("-" * 80)

            for commit in author_changes:
                description = format_change_description(commit)
                demo_hint = generate_demo_hint(commit)
                jira_refs = commit['jira_refs']

                print(f"\n• {description}")
                print(f"  Demo: {demo_hint}")
                if jira_refs:
                    print(f"  JIRA: {', '.join(jira_refs)}")
                else:
                    print(f"  JIRA: No reference found")
                print(f"  Commit: {commit['hash']} ({commit['relative_time']})")

    print("\n" + "=" * 80)


def weekly_changelog(
    since: Annotated[Optional[str], typer.Argument(help="Since date (e.g. 2025-11-01). Default: 7 days ago.")] = None,
):
    # Determine since date
    if since:
        since_date = since
    else:
        # Default to 7 days ago
        week_ago = datetime.now() - timedelta(days=7)
        since_date = week_ago.strftime('%Y-%m-%d')

    print(f"Scanning repositories for changes since {since_date}...\n")
    generate_changelog(REPOS, since_date)
