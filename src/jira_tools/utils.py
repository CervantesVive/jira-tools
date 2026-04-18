"""
jira_utils.py

Purpose
- Provide small helper functions and configuration used by JIRA-related scripts in this repository.
- Wrap JIRA Cloud REST API v3 search calls and centralize environment-based configuration.

Provided functions
- search_jira_with_jql(jql_query, fields=None): Perform a JQL search using the REST API, optionally limiting returned fields.
- extract_jira_keys(text): Extract JIRA keys (or keys in URLs) from arbitrary text.

Environment and Dependencies
- Environment variables required (commonly loaded via .env):
  - JIRA_SERVER: Base URL of your JIRA Cloud instance, e.g., https://your-domain.atlassian.net
  - JIRA_EMAIL: Account email used for API authentication
  - JIRA_API_TOKEN: API token for Basic auth
- External deps: requests, python-dotenv

Usage notes
- This module can optionally print configuration and request headers to stdout/stderr for debugging.
  Set jira_utils.VERBOSE = True in calling scripts to enable debugging output.
  Sensitive information (API tokens, Authorization headers) is automatically masked to prevent exposure in logs.
- Environment variables are validated at module load time - missing variables will raise EnvironmentError with setup instructions.
- All JIRA-related scripts (e.g., get_jira_statistics.py, jira_links.py) import and use these helpers.
"""
import sys
import base64
import urllib.parse
import requests
import os
import time
from dotenv import load_dotenv

load_dotenv()

JIRA_SERVER = os.getenv('JIRA_SERVER')
JIRA_EMAIL = os.getenv('JIRA_EMAIL')
JIRA_API_TOKEN = os.getenv('JIRA_API_TOKEN')

# Pagination configuration
MAX_RESULTS_SAFETY_LIMIT = 500  # Maximum allowed results (queries with more will be rejected)
MAX_RETRY_ATTEMPTS = 5  # Maximum retry attempts for rate limiting
RATE_LIMIT_BASE_BACKOFF = 1  # Base time in seconds for exponential backoff (1s, 2s, 4s, 8s, 16s)

# Validate required environment variables
missing_vars = []
if not JIRA_SERVER:
    missing_vars.append('JIRA_SERVER')
if not JIRA_EMAIL:
    missing_vars.append('JIRA_EMAIL')
if not JIRA_API_TOKEN:
    missing_vars.append('JIRA_API_TOKEN')

if missing_vars:
    error_msg = (
        f"Missing required environment variables: {', '.join(missing_vars)}\n\n"
        "Please ensure the following are set:\n"
        "  - JIRA_SERVER: Base URL of your JIRA instance (e.g., https://your-domain.atlassian.net)\n"
        "  - JIRA_EMAIL: Your JIRA account email\n"
        "  - JIRA_API_TOKEN: Your JIRA API token\n\n"
        "You can set these in a .env file in the project root or export them as environment variables."
    )
    raise EnvironmentError(error_msg)

# Module-level verbose flag - can be set by calling scripts before importing
# Example: import jira_utils; jira_utils.VERBOSE = True
VERBOSE = False

# Print configuration values
if VERBOSE:
    print("=" * 80, file=sys.stderr)
    print("JIRA Configuration:", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print(f"JIRA_SERVER: {JIRA_SERVER}", file=sys.stderr)
    print(f"JIRA_EMAIL: {JIRA_EMAIL}", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print(file=sys.stderr)

def search_jira_with_jql(jql_query, fields=None):
    """Search JIRA using JQL via REST API v3 with automatic pagination

    Automatically fetches all pages of results up to MAX_RESULTS_SAFETY_LIMIT.
    Implements exponential backoff for rate limiting (429 responses).

    Args:
        jql_query: JQL query string to filter issues
        fields: Optional list of field names to include in response

    Returns:
        dict: Combined response with all issues from all pages:
            - total: Total number of issues matching query
            - startAt: Always 0 (first result index)
            - maxResults: Total issues returned
            - issues: Combined list of all issues from all pages

    Raises:
        Exception: If total results exceed MAX_RESULTS_SAFETY_LIMIT
        Exception: If API returns non-200 status (after retries for 429)
        Exception: If rate limiting retries exceed MAX_RETRY_ATTEMPTS
    """
    encoded_jql = urllib.parse.quote(jql_query)

    # Build base URL
    base_url = f"{JIRA_SERVER}/rest/api/3/search/jql?jql={encoded_jql}"
    if fields:
        fields_param = ",".join(fields)
        base_url += f"&fields={fields_param}"

    # Prepare authentication headers
    auth_string = f"{JIRA_EMAIL}:{JIRA_API_TOKEN}"
    auth_bytes = auth_string.encode('ascii')
    auth_base64 = base64.b64encode(auth_bytes).decode('ascii')

    headers = {
        "Authorization": f"Basic {auth_base64}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    # Print headers (mask sensitive values)
    if VERBOSE:
        print("=" * 80)
        print("Request Headers:")
        print("=" * 80)
        for key, value in headers.items():
            if key.lower() == 'authorization':
                # Mask authorization header to prevent credential exposure
                print(f"{key}: Basic {'*' * 8}")
            else:
                print(f"{key}: {value}")
        print("=" * 80)
        print()

    # Fetch first page
    first_response = _fetch_page_with_retry(base_url, headers, page_token=None)
    total = first_response.get('total', 0)

    # Check safety limit
    if total > MAX_RESULTS_SAFETY_LIMIT:
        raise Exception(
            f"Query returned {total} results, exceeding safety limit of {MAX_RESULTS_SAFETY_LIMIT}. "
            f"Please refine your JQL query to return fewer results."
        )

    # Collect all issues starting with first page
    all_issues = first_response.get('issues', [])
    is_last = first_response.get('isLast', True)

    if VERBOSE:
        print(f"First page: {len(all_issues)} issues (total: {total}, isLast: {is_last})", file=sys.stderr)

    # Fetch remaining pages if needed
    current_response = first_response  # Track current page for iteration
    while not is_last:
        next_page_token = current_response.get('nextPageToken')

        if not next_page_token:
            if VERBOSE:
                print("Warning: isLast=false but no nextPageToken provided, stopping pagination", file=sys.stderr)
            break

        if VERBOSE:
            print(f"Fetching next page (token: {next_page_token[:20]}...)...", file=sys.stderr)

        next_response = _fetch_page_with_retry(base_url, headers, page_token=next_page_token)
        next_issues = next_response.get('issues', [])
        all_issues.extend(next_issues)

        # Update for next iteration
        current_response = next_response
        is_last = next_response.get('isLast', True)

        if VERBOSE:
            print(f"  Retrieved {len(next_issues)} issues (total so far: {len(all_issues)}, isLast: {is_last})", file=sys.stderr)

        # Safety check: if no issues returned, break to avoid infinite loop
        if not next_issues:
            break

    # Return combined result
    return {
        'total': total,
        'startAt': 0,
        'maxResults': len(all_issues),
        'issues': all_issues
    }


def _fetch_page_with_retry(base_url, headers, page_token=None):
    """Fetch a single page of JIRA results with exponential backoff retry for rate limiting

    Args:
        base_url: Base URL for the API request
        headers: Request headers including authentication
        page_token: Optional page token for pagination (None for first page)

    Returns:
        dict: JSON response from JIRA API containing:
            - issues: List of issues for this page
            - isLast: Boolean indicating if this is the last page
            - nextPageToken: Token for next page (if isLast=false)
            - total: Total number of results

    Raises:
        Exception: If API returns non-200/non-429 status
        Exception: If rate limiting retries exceed MAX_RETRY_ATTEMPTS
    """
    # Construct URL with pagination token if needed
    url = base_url
    if page_token is not None:
        url += f"&nextPageToken={page_token}"

    if VERBOSE:
        print(f"Fetching: {url}", file=sys.stderr)

    # Retry loop with exponential backoff for rate limiting
    for attempt in range(MAX_RETRY_ATTEMPTS):
        response = requests.get(url, headers=headers)

        # Success
        if response.status_code == 200:
            return response.json()

        # Rate limiting - retry with exponential backoff
        if response.status_code == 429:
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                # Exponential backoff: 1s, 2s, 4s, 8s, 16s
                wait_time = RATE_LIMIT_BASE_BACKOFF * (2 ** attempt)
                if VERBOSE:
                    print(f"Rate limited (429), retrying in {wait_time}s (attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS})...", file=sys.stderr)
                time.sleep(wait_time)
                continue
            else:
                raise Exception(f"Rate limit exceeded after {MAX_RETRY_ATTEMPTS} retry attempts")

        # Other errors - fail immediately
        raise Exception(f"API Error {response.status_code}: {response.text}")

    # Should never reach here, but just in case
    raise Exception(f"Failed to fetch page after {MAX_RETRY_ATTEMPTS} attempts")


def _get_auth_headers():
    """Build authentication headers for JIRA REST API v3

    Returns:
        dict: Headers with Basic auth, Accept, and Content-Type
    """
    auth_string = f"{JIRA_EMAIL}:{JIRA_API_TOKEN}"
    auth_bytes = auth_string.encode('ascii')
    auth_base64 = base64.b64encode(auth_bytes).decode('ascii')

    return {
        "Authorization": f"Basic {auth_base64}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }


def post_comment_to_issue(issue_key, comment_adf):
    """Post an ADF-formatted comment to a JIRA issue

    Uses REST API v3 with the same auth and rate-limit retry logic
    as search_jira_with_jql.

    Args:
        issue_key: JIRA issue key (e.g. "WEB-123")
        comment_adf: Atlassian Document Format dict for the comment body

    Returns:
        tuple: (success: bool, status_code: int, message: str)
    """
    url = f"{JIRA_SERVER}/rest/api/3/issue/{issue_key}/comment"
    headers = _get_auth_headers()
    payload = {"body": comment_adf}

    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            response = requests.post(url, headers=headers, json=payload)
        except requests.RequestException as e:
            return (False, 0, f"Request failed: {e}")

        if response.status_code in (200, 201):
            return (True, response.status_code, "Comment posted")

        if response.status_code == 404:
            return (False, 404, f"Issue {issue_key} not found")

        if response.status_code == 429:
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                wait_time = RATE_LIMIT_BASE_BACKOFF * (2 ** attempt)
                time.sleep(wait_time)
                continue
            return (False, 429, f"Rate limit exceeded after {MAX_RETRY_ATTEMPTS} retries")

        return (False, response.status_code, f"API error: {response.text[:200]}")

    return (False, 0, f"Failed after {MAX_RETRY_ATTEMPTS} attempts")


def get_remote_links(issue_key):
    """Fetch all remote links for a JIRA issue

    Calls REST API v3 /issue/{key}/remotelink and returns the full list
    of remote link objects. Implements the same retry logic as other
    API calls in this module.

    Args:
        issue_key: JIRA issue key (e.g. "CE-10239")

    Returns:
        list: Remote link objects, each with keys: id, self, application, object
              Returns empty list if issue not found (404) or has no remote links.

    Raises:
        Exception: If API returns a non-200/non-404 status after retries
    """
    url = f"{JIRA_SERVER}/rest/api/3/issue/{issue_key}/remotelink"
    headers = _get_auth_headers()

    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            response = requests.get(url, headers=headers)
        except requests.RequestException as e:
            return []

        if response.status_code == 200:
            return response.json()

        if response.status_code == 404:
            if VERBOSE:
                print(f"Issue {issue_key} not found (404)", file=sys.stderr)
            return []

        if response.status_code == 429:
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                wait_time = RATE_LIMIT_BASE_BACKOFF * (2 ** attempt)
                if VERBOSE:
                    print(f"Rate limited (429), retrying in {wait_time}s (attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS})...", file=sys.stderr)
                time.sleep(wait_time)
                continue
            raise Exception(f"Rate limit exceeded after {MAX_RETRY_ATTEMPTS} retry attempts")

        raise Exception(f"API Error {response.status_code}: {response.text}")

    raise Exception(f"Failed after {MAX_RETRY_ATTEMPTS} attempts")


def extract_jira_keys(text):
    """Extract JIRA issue keys from text"""
    import re
    pattern = r'(?:https?://[^/]+/browse/)?([A-Z]+-\d+)'
    return re.findall(pattern, text)
