"""Resolve JIRA ticket IDs to their Linear equivalents."""
import csv
import json
import re
import sys
from pathlib import Path
from typing import List, Optional
from typing import Annotated
import typer
from jira_tools import utils as jira_utils


def find_linear_link(remote_links):
    """Extract Linear issue ID and URL from a list of JIRA remote links.

    Args:
        remote_links: List of remote link objects from the JIRA API

    Returns:
        tuple: (linear_id, linear_url) or (None, None) if no Linear link found
    """
    for link in remote_links:
        obj = link.get("object", {})
        url = obj.get("url", "")
        title = obj.get("title", "")

        if "linear.app" not in url:
            continue

        # Title format: "WEB-458: Open in Linear"
        # Extract the issue ID (everything before the first colon)
        match = re.match(r"^([A-Z]+-\d+)", title)
        linear_id = match.group(1) if match else None

        return linear_id, url

    return None, None


def lookup_linear_ids(jira_keys):
    """Look up Linear equivalents for a list of JIRA keys.

    Args:
        jira_keys: List of JIRA issue keys (e.g. ["CE-10239", "CE-10240"])

    Returns:
        list of dicts with keys: jira_key, linear_id, linear_url
    """
    results = []
    for key in jira_keys:
        if jira_utils.VERBOSE:
            print(f"Fetching remote links for {key}...", file=sys.stderr)

        remote_links = jira_utils.get_remote_links(key)

        if jira_utils.VERBOSE:
            print(f"  {len(remote_links)} remote link(s) found", file=sys.stderr)
            for link in remote_links:
                obj = link.get("object", {})
                print(f"    - {obj.get('title', '(no title)')}  {obj.get('url', '')}", file=sys.stderr)

        linear_id, linear_url = find_linear_link(remote_links)

        if jira_utils.VERBOSE:
            if linear_id:
                print(f"  Linear match: {linear_id} → {linear_url}", file=sys.stderr)
            else:
                print(f"  No Linear link found", file=sys.stderr)

        results.append({
            "jira_key": key,
            "linear_id": linear_id,
            "linear_url": linear_url,
        })

    return results


def print_table(results):
    """Print results as a human-readable table."""
    for r in results:
        jira_key = r["jira_key"]
        if r["linear_id"]:
            print(f"{jira_key}  →  {r['linear_id']}  {r['linear_url']}")
        else:
            print(f"{jira_key}  →  (no Linear link found)")


_ISSUE_KEY_COLUMN_CANDIDATES = ["Issue key", "Issue Key", "Key"]


def read_keys_from_csv(path):
    """Extract JIRA issue keys from a JIRA CSV export file.

    Reads the issue key column directly rather than using regex over raw text.
    Uses csv.reader (not DictReader) to handle duplicate column names in JIRA exports.

    Args:
        path: Path to the CSV file

    Returns:
        list: Non-empty JIRA issue keys in the order they appear

    Raises:
        SystemExit: If the file is not found or has no recognizable issue key column
    """
    try:
        text = Path(path).read_text(encoding='utf-8-sig')  # utf-8-sig strips UTF-8 BOM
    except FileNotFoundError:
        print(f"Error: CSV file not found: {path}", file=sys.stderr)
        sys.exit(1)

    reader = csv.reader(text.splitlines())
    try:
        headers = next(reader)
    except StopIteration:
        print(f"Error: CSV file is empty: {path}", file=sys.stderr)
        sys.exit(1)

    col_index = None
    for candidate in _ISSUE_KEY_COLUMN_CANDIDATES:
        if candidate in headers:
            col_index = headers.index(candidate)
            break

    if col_index is None:
        print(
            f"Error: could not find issue key column in CSV headers: {headers}\n"
            f"Expected one of: {_ISSUE_KEY_COLUMN_CANDIDATES}",
            file=sys.stderr,
        )
        sys.exit(1)

    keys = []
    for row in reader:
        if col_index < len(row):
            val = row[col_index].strip()
            if val:
                keys.append(val)

    return keys


def to_linear(
    keys: Annotated[Optional[List[str]], typer.Argument(help="JIRA issue keys (e.g. CE-10239)")] = None,
    file: Annotated[Optional[str], typer.Option("-f", "--file", help="File containing JIRA keys (regex extraction)")] = None,
    csv_file: Annotated[Optional[str], typer.Option("--csv", help="JIRA CSV export — reads Issue key column directly")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON array")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output")] = False,
):
    if verbose:
        jira_utils.VERBOSE = True

    all_keys = list(keys or [])

    if file:
        try:
            text = Path(file).read_text()
        except FileNotFoundError:
            typer.echo(f"Error: file not found: {file}", err=True)
            raise typer.Exit(1)
        all_keys.extend(jira_utils.extract_jira_keys(text))

    if csv_file:
        all_keys.extend(read_keys_from_csv(csv_file))

    seen = set()
    unique_keys = []
    for k in all_keys:
        if k not in seen:
            seen.add(k)
            unique_keys.append(k)

    if not unique_keys:
        typer.echo("Error: no JIRA keys provided. Use positional args, -f FILE, or --csv FILE.", err=True)
        raise typer.Exit(1)

    results = lookup_linear_ids(unique_keys)

    if json_output:
        typer.echo(json.dumps(results, indent=2))
    else:
        print_table(results)
