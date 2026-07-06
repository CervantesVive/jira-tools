# jira-tools

CLI for working with JIRA issues from the terminal. Covers statistics, cross-system linking, release notifications, and changelog generation.

## Install

```bash
uv tool install .
```

## Prerequisites

Create a `.env` file (or export environment variables) with:

```
JIRA_SERVER=https://your-domain.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=<your-api-token>
```

Get an API token at: **Atlassian Account → Security → API tokens**.

## Commands

| Command | What it does |
|---------|-------------|
| `jira get-statistics` | Story point stats for a JQL query |
| `jira links` | Generate Google Sheets HYPERLINK formulas for JIRA issues |
| `jira to-linear` | Resolve JIRA keys to their linked Linear issue IDs |
| `jira weekly-changelog` | Weekly commit summary grouped by author across repos |
| `jira notify-release` | Post "released to production" comments on tickets in a commit range |

---

## FAQ

### How do I get story point statistics for a sprint or epic?

```bash
jira get-statistics 'project = "MyProject" AND sprint = "Sprint 42"'
```

Output is JSON (stdout) with total/resolved/unresolved counts and story points. Pipe to `jq` or save to a file.

Issues without story points are counted at a default of 3.

### How do I get a table view with verbose output?

```bash
jira get-statistics --verbose 'project = "MyProject" AND sprint in openSprints()'
```

Verbose output goes to stderr; JSON goes to stdout, so you can still pipe cleanly.

### What does `jira links` do?

It takes JIRA keys (or a `.txt` file containing them), fetches issue titles from the API, and generates Google Sheets `HYPERLINK()` formulas. Issues on consecutive lines in the input are grouped into a single multi-line cell; blank lines between groups produce separate cells.

```bash
jira links "CE-1234 CE-1235 CE-1236"

# From a text file
jira links issues.txt
```

Output is written to `jira_formulas.txt`. Copy each formula and paste it into a Google Sheets cell.

### How do I find the Linear issue ID for a JIRA ticket?

```bash
# Single key
jira to-linear CE-10239

# Multiple keys
jira to-linear CE-10239 CE-10240

# From a file (regex-extracts JIRA keys)
jira to-linear -f release-notes.txt

# From a JIRA CSV export
jira to-linear --from-csv export.csv

# Output as JSON for scripting
jira to-linear --json CE-10239
```

The command looks for a remote link on the JIRA issue pointing to `linear.app`.

### How do I automatically notify JIRA tickets after a production deploy?

```bash
# Auto-detect the last two successful release-prod.yaml runs
jira notify-release --repo owner/my-repo

# Preview without posting
jira notify-release --repo owner/my-repo --dry-run

# Explicit commit range
jira notify-release --repo owner/my-repo --from abc1234 --to def5678
```

The command scans commit messages between the two SHAs for JIRA keys (e.g. `CE-1234`) and posts an ADF-formatted "Released to production" comment on each one. Requires the `gh` CLI authenticated against the target repo.

### What does the `weekly-changelog` command do?

It scans configured local Git repositories for commits in the last 7 days (or a custom `--since` date) and prints a changelog grouped by repository and author, with JIRA ticket references and demo hints per commit.

```bash
jira weekly-changelog
jira weekly-changelog 2025-11-01
```

**Note:** The list of repositories is hardcoded in `REPOS` inside `weekly_changelog.py`. Edit that list before using this command.
