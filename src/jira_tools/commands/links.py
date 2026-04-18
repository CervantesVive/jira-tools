"""Generate Google Sheets HYPERLINK formulas for JIRA issues."""
import sys
from pathlib import Path
from typing_extensions import Annotated
import typer
from jira_tools.utils import search_jira_with_jql, JIRA_SERVER


def extract_issues_from_keys(jira_keys):
    """Build JQL query from issue keys"""
    # Convert list of keys into JQL: key in (KEY-1, KEY-2, KEY-3)
    keys_str = ", ".join(jira_keys)
    jql = f"key in ({keys_str})"

    print(f"JQL Query: {jql}", file=sys.stderr)

    result = search_jira_with_jql(jql, fields=['key', 'fields', 'summary', 'title'])

    print(f"results: {result}", file=sys.stderr)

    issues = []
    for issue in result.get('issues', []):
        # Defensive access to avoid KeyError if expected keys are missing
        key = issue.get('key')
        fields = issue.get('fields') or {}
        title = fields.get('summary')
        if not key or not title:
            # Skip issues missing essential information
            print(f"Skipping issue due to missing key/title: {issue}", file=sys.stderr)
            continue
        url = f"{JIRA_SERVER}/browse/{key}"
        issues.append({'key': key, 'title': title, 'url': url})
        print(f"✓ {key}: {title}", file=sys.stderr)

    return issues


def extract_jira_keys(text):
    """Extract JIRA issue keys from text"""
    import re
    pattern = r'(?:https?://[^/]+/browse/)?([A-Z]+-\d+)'
    return re.findall(pattern, text)


def extract_jira_keys_with_spacing(text):
    """Extract JIRA issue keys and track if they're on consecutive lines"""
    import re

    lines = text.split('\n')
    results = []
    last_jira_line_index = -1

    for i, line in enumerate(lines):
        # Check if line contains a JIRA key
        match = re.search(r'(?:https?://[^/]+/browse/)?([A-Z]+-\d+)', line)

        if match:
            # Check if this JIRA is consecutive with the last JIRA
            if last_jira_line_index >= 0:
                lines_between = i - last_jira_line_index
                if lines_between > 1:  # Not consecutive (gap exists)
                    results.append({'type': 'break'})

            results.append({'type': 'key', 'key': match.group(1)})
            last_jira_line_index = i

    return results


def fetch_issues_with_spacing(parsed_items):
    """Fetch issues while preserving spacing information"""
    # Extract just the keys for JQL query
    jira_keys = [item.get('key') for item in parsed_items if item.get('type') == 'key' and item.get('key')]

    if not jira_keys:
        return []

    # Build JQL and fetch
    keys_str = ", ".join(jira_keys)
    jql = f"key in ({keys_str})"
    print(f"JQL Query: {jql}", file=sys.stderr)

    result = search_jira_with_jql(jql, fields=['key', 'fields', 'summary', 'title'])

    # Create lookup dict
    issue_map = {}
    for issue in result.get('issues', []):
        key = issue.get('key')
        fields = issue.get('fields') or {}
        title = fields.get('summary')
        if not key or not title:
            print(f"Skipping issue due to missing key/title: {issue}", file=sys.stderr)
            continue
        url = f"{JIRA_SERVER}/browse/{key}"
        issue_map[key] = {'key': key, 'title': title, 'url': url}
        print(f"✓ {key}: {title}", file=sys.stderr)

    # Build final results preserving spacing
    final_results = []
    for item in parsed_items:
        if item.get('type') == 'break':
            final_results.append({'type': 'break'})
        elif item.get('type') == 'key' and item.get('key') in issue_map:
            final_results.append(issue_map[item.get('key')])

    return final_results


def generate_html(results):
    """Generate HTML with grouped hyperlinks in single divs"""
    html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>JIRA Links</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; }
        .link-group { margin: 10px 0; padding: 10px; background: #f5f5f5; }
        .link-group a { color: #0066cc; text-decoration: none; }
        .link-group a:hover { text-decoration: underline; }
        .instructions { background: #fff3cd; padding: 15px; margin-bottom: 20px; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="instructions">
        <strong>Instructions:</strong> Select the links below and copy (Ctrl/Cmd+C), then paste into Google Sheets.
    </div>
"""

    # Group consecutive links
    current_group = []

    def render_link(link):
        url = link.get("url")
        title = link.get("title") or link.get("key") or "Unknown"
        if not url:
            return None
        return f'        <a href="{url}">{title}</a>'

    for item in results:
        if item.get('type') == 'break':
            # Close current group if exists
            if current_group:
                html += '    <div class="link-group">\n'
                for i, link in enumerate(current_group):
                    rendered = render_link(link)
                    if not rendered:
                        continue
                    html += rendered
                    if i < len(current_group) - 1:  # Not the last link
                        html += '<br>'
                    html += '\n'
                html += '    </div>\n'
                current_group = []
            html += '    <br><br>\n'
        else:
            current_group.append(item)

    # Close final group if exists
    if current_group:
        html += '    <div class="link-group">\n'
        for i, link in enumerate(current_group):
            rendered = render_link(link)
            if not rendered:
                continue
            html += rendered
            if i < len(current_group) - 1:  # Not the last link
                html += '<br>'
            html += '\n'
        html += '    </div>\n'

    html += """
</body>
</html>
"""
    return html


def generate_formula_output(results, output_file="jira_formulas.txt"):
    """Generate HYPERLINK formulas for Google Sheets"""
    groups = []
    current_group = []

    for item in results:
        if item.get('type') == 'break':
            if current_group:
                groups.append(current_group)
                current_group = []
        else:
            current_group.append(item)

    if current_group:
        groups.append(current_group)

    # Build formulas
    formulas = []
    for group in groups:
        # Filter out invalid links (missing URL)
        valid_links = []
        for link in group:
            url = link.get("url")
            if not url:
                continue
            title = link.get("title") or link.get("key") or "Unknown"
            valid_links.append((url, title))

        if not valid_links:
            continue

        if len(valid_links) == 1:
            # Single link
            url, title = valid_links[0]
            formula = f'=HYPERLINK("{url}", "{title}")'
        else:
            # Multiple links - concatenate with CHAR(10)
            parts = []
            for url, title in valid_links:
                parts.append(f'HYPERLINK("{url}", "{title}")')
            formula = "=" + " & CHAR(10) & ".join(parts)

        formulas.append(formula)

    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        for formula in formulas:
            f.write(formula + '\n\n')

    print(f"\n✓ Generated {output_file}", file=sys.stderr)
    print(f"✓ {len(formulas)} formulas created", file=sys.stderr)
    print(f"\nInstructions:", file=sys.stderr)
    print(f"1. Open {output_file}", file=sys.stderr)
    print(f"2. Copy each formula", file=sys.stderr)
    print(f"3. Paste into a Google Sheets cell", file=sys.stderr)
    print(f"4. Enable 'Wrap text' for the cell to see multiple lines", file=sys.stderr)


def links(
    input_text: Annotated[str, typer.Argument(help="JIRA keys, URLs, or path to a .txt file")],
):
    # Read input from file if it's a .txt path
    if input_text.endswith('.txt'):
        with open(input_text, 'r') as f:
            input_text = f.read()

    # Extract JIRA keys with spacing info
    parsed_items = extract_jira_keys_with_spacing(input_text)

    jira_count = sum(1 for item in parsed_items if item.get('type') == 'key')
    if jira_count == 0:
        typer.echo("No JIRA issues found in input", err=True)
        raise typer.Exit(1)

    typer.echo(f"Found {jira_count} JIRA issues", err=True)

    # Fetch using JQL while preserving spacing
    results = fetch_issues_with_spacing(parsed_items)

    # Generate formulas to text file
    generate_formula_output(results)
