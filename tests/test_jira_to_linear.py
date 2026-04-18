#!/usr/bin/env python3
"""
Tests for jira_to_linear.py

Tests the pure data transformation functions that require no API calls:
- read_keys_from_csv: extract JIRA keys from a JIRA CSV export file
- find_linear_link: extract Linear issue ID and URL from JIRA remote link objects

API-dependent functions (lookup_linear_ids) are not tested here as they
require a live JIRA environment.
"""
import os
import pytest

os.environ.setdefault('JIRA_SERVER', 'https://test.atlassian.net')
os.environ.setdefault('JIRA_EMAIL', 'test@test.com')
os.environ.setdefault('JIRA_API_TOKEN', 'test_token')

from jira_tools.commands.to_linear import read_keys_from_csv, find_linear_link


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_csv(tmp_path, lines):
    """Write lines to a temp CSV file and return its path."""
    p = tmp_path / "export.csv"
    p.write_text("\n".join(lines), encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# TestReadKeysFromCsv
# ---------------------------------------------------------------------------

class TestReadKeysFromCsv:
    """Tests for reading JIRA keys from CSV export files."""

    def test_reads_keys_from_issue_key_column(self, tmp_path):
        path = write_csv(tmp_path, [
            "Issue Type,Issue key,Summary,Assignee",
            "Story,CE-100,First issue,Dean Hamilton",
            "Story,CE-101,Second issue,Abrar Rakin",
        ])
        assert read_keys_from_csv(path) == ["CE-100", "CE-101"]

    def test_accepts_issue_Key_capitalization(self, tmp_path):
        """Column named 'Issue Key' (capital K) is also recognized."""
        path = write_csv(tmp_path, [
            "Issue Key,Summary",
            "CE-200,Some issue",
        ])
        assert read_keys_from_csv(path) == ["CE-200"]

    def test_accepts_key_column_name(self, tmp_path):
        """Column named just 'Key' is also recognized."""
        path = write_csv(tmp_path, [
            "Key,Summary",
            "CE-300,Another issue",
        ])
        assert read_keys_from_csv(path) == ["CE-300"]

    def test_skips_empty_rows(self, tmp_path):
        path = write_csv(tmp_path, [
            "Issue key,Summary",
            "CE-100,Has a key",
            ",No key here",
            "CE-102,Also has a key",
        ])
        assert read_keys_from_csv(path) == ["CE-100", "CE-102"]

    def test_strips_whitespace_from_keys(self, tmp_path):
        path = write_csv(tmp_path, [
            "Issue key,Summary",
            " CE-100 ,Padded key",
        ])
        assert read_keys_from_csv(path) == ["CE-100"]

    def test_preserves_order(self, tmp_path):
        path = write_csv(tmp_path, [
            "Issue key,Summary",
            "CE-103,Third",
            "CE-101,First",
            "CE-102,Second",
        ])
        assert read_keys_from_csv(path) == ["CE-103", "CE-101", "CE-102"]

    def test_handles_duplicate_column_names(self, tmp_path):
        """JIRA CSVs often have duplicate headers (e.g. Sprint); issue key is read correctly."""
        path = write_csv(tmp_path, [
            "Issue key,Sprint,Sprint,Sprint,Priority",
            "CE-100,Sprint A,,,High",
        ])
        assert read_keys_from_csv(path) == ["CE-100"]

    def test_handles_utf8_bom(self, tmp_path):
        p = tmp_path / "bom.csv"
        p.write_bytes(b'\xef\xbb\xbfIssue key,Summary\r\nCE-100,BOM test\r\n')
        assert read_keys_from_csv(str(p)) == ["CE-100"]

    def test_file_not_found_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            read_keys_from_csv(str(tmp_path / "missing.csv"))

    def test_empty_file_exits(self, tmp_path):
        p = tmp_path / "empty.csv"
        p.write_text("", encoding="utf-8")
        with pytest.raises(SystemExit):
            read_keys_from_csv(str(p))

    def test_no_issue_key_column_exits(self, tmp_path):
        path = write_csv(tmp_path, [
            "Summary,Assignee,Status",
            "Some issue,Someone,Backlog",
        ])
        with pytest.raises(SystemExit):
            read_keys_from_csv(path)

    def test_returns_empty_list_when_no_data_rows(self, tmp_path):
        path = write_csv(tmp_path, [
            "Issue key,Summary",
        ])
        assert read_keys_from_csv(path) == []


# ---------------------------------------------------------------------------
# TestFindLinearLink
# ---------------------------------------------------------------------------

class TestFindLinearLink:
    """Tests for extracting Linear issue ID and URL from JIRA remote links."""

    def test_finds_linear_link(self):
        links = [{
            "object": {
                "url": "https://linear.app/acme/issue/WEB-458",
                "title": "WEB-458: Open in Linear",
            }
        }]
        linear_id, url = find_linear_link(links)
        assert linear_id == "WEB-458"
        assert url == "https://linear.app/acme/issue/WEB-458"

    def test_returns_none_when_no_links(self):
        linear_id, url = find_linear_link([])
        assert linear_id is None
        assert url is None

    def test_ignores_non_linear_links(self):
        links = [{
            "object": {
                "url": "https://github.com/Acme/acme-retail/pull/123",
                "title": "PR #123",
            }
        }]
        linear_id, url = find_linear_link(links)
        assert linear_id is None
        assert url is None

    def test_finds_linear_link_among_multiple(self):
        links = [
            {
                "object": {
                    "url": "https://github.com/Acme/repo/pull/1",
                    "title": "PR #1",
                }
            },
            {
                "object": {
                    "url": "https://linear.app/acme/issue/MOBILE-99",
                    "title": "MOBILE-99: Open in Linear",
                }
            },
        ]
        linear_id, url = find_linear_link(links)
        assert linear_id == "MOBILE-99"

    def test_handles_title_without_colon(self):
        """If title doesn't match the expected format, linear_id is None but url is returned."""
        links = [{
            "object": {
                "url": "https://linear.app/acme/issue/WEB-200",
                "title": "no id here",
            }
        }]
        linear_id, url = find_linear_link(links)
        assert linear_id is None
        assert url == "https://linear.app/acme/issue/WEB-200"

    def test_handles_missing_object_key(self):
        links = [{"id": 1}]
        linear_id, url = find_linear_link(links)
        assert linear_id is None
        assert url is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
