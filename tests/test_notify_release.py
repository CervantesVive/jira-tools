"""Tests for src/jira/notify_release.py"""
import json
import os
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault('JIRA_SERVER', 'https://test.atlassian.net')
os.environ.setdefault('JIRA_EMAIL', 'test@test.com')
os.environ.setdefault('JIRA_API_TOKEN', 'test')

from jira_tools.commands.notify_release import (
    auto_detect_shas,
    build_release_comment_adf,
    extract_tickets_from_commits,
    get_commits_between,
    notify_tickets,
    notify_release,
    run_gh,
)


# ---------------------------------------------------------------------------
# extract_tickets_from_commits
# ---------------------------------------------------------------------------

class TestExtractTicketsFromCommits:
    def test_extracts_keys_from_commit_messages(self):
        commits = [
            {"commit": {"message": "WEB-123 fix login bug"}},
            {"commit": {"message": "CE-456 add feature\nAlso fixes WEB-789"}},
        ]
        result = extract_tickets_from_commits(commits)
        assert result == ["WEB-123", "CE-456", "WEB-789"]

    def test_deduplicates_keys(self):
        commits = [
            {"commit": {"message": "WEB-123 first commit"}},
            {"commit": {"message": "WEB-123 second commit mentioning same ticket"}},
        ]
        result = extract_tickets_from_commits(commits)
        assert result == ["WEB-123"]

    def test_preserves_first_seen_order(self):
        commits = [
            {"commit": {"message": "CE-999 something"}},
            {"commit": {"message": "WEB-1 something"}},
            {"commit": {"message": "CE-999 again"}},
        ]
        result = extract_tickets_from_commits(commits)
        assert result == ["CE-999", "WEB-1"]

    def test_handles_empty_commits(self):
        assert extract_tickets_from_commits([]) == []

    def test_handles_commits_without_tickets(self):
        commits = [
            {"commit": {"message": "chore: bump deps"}},
            {"commit": {"message": "Merge branch 'main'"}},
        ]
        assert extract_tickets_from_commits(commits) == []

    def test_handles_missing_message_field(self):
        commits = [{"commit": {}}, {}]
        assert extract_tickets_from_commits(commits) == []

    def test_extracts_from_jira_urls(self):
        commits = [
            {"commit": {"message": "Fixes https://acme.atlassian.net/browse/WEB-100"}},
        ]
        result = extract_tickets_from_commits(commits)
        assert "WEB-100" in result


# ---------------------------------------------------------------------------
# auto_detect_shas
# ---------------------------------------------------------------------------

class TestAutoDetectShas:
    @patch("jira_tools.commands.notify_release.run_gh")
    def test_returns_shas_and_url_from_two_runs(self, mock_run_gh):
        runs = [
            {"headSha": "aaaa1111", "url": "https://github.com/runs/1"},
            {"headSha": "bbbb2222", "url": "https://github.com/runs/2"},
        ]
        mock_run_gh.return_value = json.dumps(runs)

        from_sha, to_sha, run_url = auto_detect_shas("Acme/acme-retail")

        assert from_sha == "bbbb2222"
        assert to_sha == "aaaa1111"
        assert run_url == "https://github.com/runs/1"

    @patch("jira_tools.commands.notify_release.run_gh")
    def test_exits_when_fewer_than_two_runs(self, mock_run_gh):
        mock_run_gh.return_value = json.dumps([{"headSha": "aaaa1111", "url": "url"}])

        with pytest.raises(SystemExit):
            auto_detect_shas("Acme/acme-retail")

    @patch("jira_tools.commands.notify_release.run_gh")
    def test_exits_when_no_runs(self, mock_run_gh):
        mock_run_gh.return_value = ""

        with pytest.raises(SystemExit):
            auto_detect_shas("Acme/acme-retail")


# ---------------------------------------------------------------------------
# get_commits_between
# ---------------------------------------------------------------------------

class TestGetCommitsBetween:
    @patch("jira_tools.commands.notify_release.run_gh")
    def test_returns_parsed_commits(self, mock_run_gh):
        commits = [{"sha": "aaa", "commit": {"message": "WEB-1 fix"}}]
        mock_run_gh.return_value = json.dumps(commits)

        result = get_commits_between("owner/repo", "sha1", "sha2")

        assert len(result) == 1
        assert result[0]["sha"] == "aaa"
        mock_run_gh.assert_called_once()

    @patch("jira_tools.commands.notify_release.run_gh")
    def test_returns_empty_on_empty_output(self, mock_run_gh):
        mock_run_gh.return_value = ""
        assert get_commits_between("owner/repo", "sha1", "sha2") == []


# ---------------------------------------------------------------------------
# run_gh
# ---------------------------------------------------------------------------

class TestRunGh:
    @patch("jira_tools.commands.notify_release.subprocess.run")
    def test_returns_stdout_on_success(self, mock_subprocess):
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="output\n", stderr="")
        assert run_gh(["api", "test"]) == "output"

    @patch("jira_tools.commands.notify_release.subprocess.run")
    def test_raises_on_failure(self, mock_subprocess):
        mock_subprocess.return_value = MagicMock(returncode=1, stdout="", stderr="bad request")
        with pytest.raises(RuntimeError, match="gh command failed"):
            run_gh(["api", "test"])


# ---------------------------------------------------------------------------
# build_release_comment_adf
# ---------------------------------------------------------------------------

class TestBuildReleaseCommentAdf:
    def test_builds_valid_adf_structure(self):
        adf = build_release_comment_adf("abcdef1234567890")
        assert adf["type"] == "doc"
        assert adf["version"] == 1
        assert len(adf["content"]) == 2

    def test_includes_short_sha(self):
        adf = build_release_comment_adf("abcdef1234567890")
        # The second paragraph should contain the short SHA
        commit_para = adf["content"][1]
        code_node = commit_para["content"][1]
        assert code_node["text"] == "abcdef1"
        assert {"type": "code"} in code_node["marks"]

    def test_includes_run_url_when_provided(self):
        adf = build_release_comment_adf("abc123", run_url="https://example.com/run/1")
        first_para = adf["content"][0]
        texts = [n.get("text") for n in first_para["content"]]
        assert "GitHub Actions" in texts

    def test_omits_run_url_when_not_provided(self):
        adf = build_release_comment_adf("abc123", run_url=None)
        first_para = adf["content"][0]
        texts = [n.get("text") for n in first_para["content"]]
        assert "GitHub Actions" not in texts


# ---------------------------------------------------------------------------
# notify_tickets (dry-run)
# ---------------------------------------------------------------------------

class TestNotifyTicketsDryRun:
    def test_dry_run_skips_all_tickets(self):
        results = notify_tickets(["WEB-1", "CE-2"], "abc123", None, dry_run=True)

        assert len(results) == 2
        assert all(r["status"] == "skipped" for r in results)

    @patch("jira_tools.commands.notify_release.post_comment_to_issue")
    def test_dry_run_does_not_call_api(self, mock_post):
        notify_tickets(["WEB-1"], "abc123", None, dry_run=True)
        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# notify_tickets (posting)
# ---------------------------------------------------------------------------

class TestNotifyTicketsPosting:
    @patch("jira_tools.commands.notify_release.post_comment_to_issue")
    def test_posts_comment_to_each_ticket(self, mock_post):
        mock_post.return_value = (True, 201, "Comment posted")

        results = notify_tickets(["WEB-1", "CE-2"], "abc123", None, dry_run=False)

        assert mock_post.call_count == 2
        assert all(r["status"] == "posted" for r in results)

    @patch("jira_tools.commands.notify_release.post_comment_to_issue")
    def test_records_failure_and_continues(self, mock_post):
        mock_post.side_effect = [
            (False, 404, "Issue WEB-1 not found"),
            (True, 201, "Comment posted"),
        ]

        results = notify_tickets(["WEB-1", "CE-2"], "abc123", None, dry_run=False)

        assert results[0]["status"] == "failed"
        assert results[1]["status"] == "posted"
        assert mock_post.call_count == 2


