#!/usr/bin/env python3
"""
Tests for jira_utils.py pagination functionality

Tests all pagination scenarios:
- Empty results (no issues)
- Single page (< 50 results)
- Multiple pages (51-500 results)
- Safety limit enforcement (501+ results)
- API error handling
- Rate limiting with exponential backoff
"""
import pytest
import os
from unittest.mock import patch, MagicMock, call
import time

os.environ.setdefault('JIRA_SERVER', 'https://test.atlassian.net')
os.environ.setdefault('JIRA_EMAIL', 'test@test.com')
os.environ.setdefault('JIRA_API_TOKEN', 'test')

from jira_tools.utils import search_jira_with_jql


class TestPaginationEmptyResults:
    """Tests for empty result sets"""

    @patch('jira_tools.utils.requests.get')
    def test_search_with_no_results(self, mock_get):
        """Test pagination with zero results"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'total': 0,
            'isLast': True,
            'issues': []
        }
        mock_get.return_value = mock_response

        result = search_jira_with_jql('project = EMPTY')

        assert result['total'] == 0
        assert result['issues'] == []
        assert mock_get.call_count == 1


class TestPaginationSinglePage:
    """Tests for single page results (< 50 issues)"""

    @patch('jira_tools.utils.requests.get')
    def test_search_with_single_page_results(self, mock_get):
        """Test pagination with results that fit in one page"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'total': 25,
            'isLast': True,
            'issues': [{'key': f'PROJ-{i}'} for i in range(1, 26)]
        }
        mock_get.return_value = mock_response

        result = search_jira_with_jql('project = PROJ')

        assert result['total'] == 25
        assert len(result['issues']) == 25
        assert mock_get.call_count == 1

    @patch('jira_tools.utils.requests.get')
    def test_search_with_exactly_50_results(self, mock_get):
        """Test pagination with exactly 50 results (boundary case)"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'total': 50,
            'isLast': True,
            'issues': [{'key': f'PROJ-{i}'} for i in range(1, 51)]
        }
        mock_get.return_value = mock_response

        result = search_jira_with_jql('project = PROJ')

        assert result['total'] == 50
        assert len(result['issues']) == 50
        assert mock_get.call_count == 1


class TestPaginationMultiplePages:
    """Tests for multi-page results (51-500 issues)"""

    @patch('jira_tools.utils.requests.get')
    def test_search_with_two_pages(self, mock_get):
        """Test pagination with 75 results (2 pages)"""
        # First page
        page1_response = MagicMock()
        page1_response.status_code = 200
        page1_response.json.return_value = {
            'total': 75,
            'isLast': False,
            'nextPageToken': 'token-page-2',
            'issues': [{'key': f'PROJ-{i}'} for i in range(1, 51)]
        }

        # Second page
        page2_response = MagicMock()
        page2_response.status_code = 200
        page2_response.json.return_value = {
            'total': 75,
            'isLast': True,
            'issues': [{'key': f'PROJ-{i}'} for i in range(51, 76)]
        }

        mock_get.side_effect = [page1_response, page2_response]

        result = search_jira_with_jql('project = PROJ')

        assert result['total'] == 75
        assert len(result['issues']) == 75
        assert mock_get.call_count == 2
        assert result['issues'][0]['key'] == 'PROJ-1'
        assert result['issues'][74]['key'] == 'PROJ-75'

    @patch('jira_tools.utils.requests.get')
    def test_search_with_three_pages(self, mock_get):
        """Test pagination with 125 results (3 pages)"""
        # First page
        page1_response = MagicMock()
        page1_response.status_code = 200
        page1_response.json.return_value = {
            'total': 125,
            'isLast': False,
            'nextPageToken': 'token-page-2',
            'issues': [{'key': f'PROJ-{i}'} for i in range(1, 51)]
        }

        # Second page
        page2_response = MagicMock()
        page2_response.status_code = 200
        page2_response.json.return_value = {
            'total': 125,
            'isLast': False,
            'nextPageToken': 'token-page-3',
            'issues': [{'key': f'PROJ-{i}'} for i in range(51, 101)]
        }

        # Third page
        page3_response = MagicMock()
        page3_response.status_code = 200
        page3_response.json.return_value = {
            'total': 125,
            'isLast': True,
            'issues': [{'key': f'PROJ-{i}'} for i in range(101, 126)]
        }

        mock_get.side_effect = [page1_response, page2_response, page3_response]

        result = search_jira_with_jql('project = PROJ')

        assert result['total'] == 125
        assert len(result['issues']) == 125
        assert mock_get.call_count == 3
        assert result['issues'][0]['key'] == 'PROJ-1'
        assert result['issues'][124]['key'] == 'PROJ-125'

    @patch('jira_tools.utils.requests.get')
    def test_search_with_exactly_500_results(self, mock_get):
        """Test pagination with exactly 500 results (max expected)"""
        responses = []
        for page in range(10):  # 10 pages of 50 each = 500
            response = MagicMock()
            response.status_code = 200
            start = page * 50
            is_last_page = (page == 9)
            response_data = {
                'total': 500,
                'isLast': is_last_page,
                'issues': [{'key': f'PROJ-{i}'} for i in range(start + 1, start + 51)]
            }
            # Add nextPageToken only if not last page
            if not is_last_page:
                response_data['nextPageToken'] = f'token-page-{page + 2}'
            response.json.return_value = response_data
            responses.append(response)

        mock_get.side_effect = responses

        result = search_jira_with_jql('project = PROJ')

        assert result['total'] == 500
        assert len(result['issues']) == 500
        assert mock_get.call_count == 10
        assert result['issues'][0]['key'] == 'PROJ-1'
        assert result['issues'][499]['key'] == 'PROJ-500'


class TestPaginationSafetyLimit:
    """Tests for safety limit enforcement"""

    @patch('jira_tools.utils.requests.get')
    def test_search_exceeds_safety_limit(self, mock_get):
        """Test that exceeding safety limit raises error"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'total': 600,  # Exceeds 500 limit
            'isLast': False,
            'nextPageToken': 'token-page-2',
            'issues': [{'key': f'PROJ-{i}'} for i in range(1, 51)]
        }
        mock_get.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            search_jira_with_jql('project = PROJ')

        assert 'safety limit' in str(exc_info.value).lower() or '500' in str(exc_info.value)

    @patch('jira_tools.utils.requests.get')
    def test_search_exactly_at_safety_limit(self, mock_get):
        """Test that exactly 500 results is allowed"""
        responses = []
        for page in range(10):  # 10 pages of 50 each = 500
            response = MagicMock()
            response.status_code = 200
            start = page * 50
            is_last_page = (page == 9)
            response_data = {
                'total': 500,
                'isLast': is_last_page,
                'issues': [{'key': f'PROJ-{i}'} for i in range(start + 1, start + 51)]
            }
            if not is_last_page:
                response_data['nextPageToken'] = f'token-page-{page + 2}'
            response.json.return_value = response_data
            responses.append(response)

        mock_get.side_effect = responses

        # Should NOT raise an exception - 500 is at the limit and allowed
        result = search_jira_with_jql('project = PROJ')

        assert result['total'] == 500
        assert len(result['issues']) == 500

    @patch('jira_tools.utils.requests.get')
    def test_search_just_over_safety_limit(self, mock_get):
        """Test that 501 results triggers safety limit"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'total': 501,  # Just over the limit
            'isLast': False,
            'nextPageToken': 'token-page-2',
            'issues': [{'key': f'PROJ-{i}'} for i in range(1, 51)]
        }
        mock_get.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            search_jira_with_jql('project = PROJ')

        assert 'safety limit' in str(exc_info.value).lower() or '500' in str(exc_info.value)


class TestPaginationErrorHandling:
    """Tests for API error handling"""

    @patch('jira_tools.utils.requests.get')
    def test_search_with_api_error_on_first_page(self, mock_get):
        """Test that API errors on first page are propagated"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = 'Invalid JQL query'
        mock_get.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            search_jira_with_jql('invalid JQL')

        assert '400' in str(exc_info.value)

    @patch('jira_tools.utils.requests.get')
    def test_search_with_api_error_on_second_page(self, mock_get):
        """Test that API errors on subsequent pages are propagated"""
        # First page succeeds
        page1_response = MagicMock()
        page1_response.status_code = 200
        page1_response.json.return_value = {
            'total': 75,
            'isLast': False,
            'nextPageToken': 'token-page-2',
            'issues': [{'key': f'PROJ-{i}'} for i in range(1, 51)]
        }

        # Second page fails
        page2_response = MagicMock()
        page2_response.status_code = 500
        page2_response.text = 'Internal server error'

        mock_get.side_effect = [page1_response, page2_response]

        with pytest.raises(Exception) as exc_info:
            search_jira_with_jql('project = PROJ')

        assert '500' in str(exc_info.value)

    @patch('jira_tools.utils.requests.get')
    def test_search_with_authentication_error(self, mock_get):
        """Test that authentication errors are propagated"""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = 'Authentication failed'
        mock_get.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            search_jira_with_jql('project = PROJ')

        assert '401' in str(exc_info.value)


class TestPaginationRateLimiting:
    """Tests for rate limiting with exponential backoff"""

    @patch('jira_tools.utils.time.sleep')
    @patch('jira_tools.utils.requests.get')
    def test_search_with_rate_limit_retry_success(self, mock_get, mock_sleep):
        """Test that rate limiting triggers exponential backoff and succeeds"""
        # First call: rate limited
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.text = 'Rate limit exceeded'

        # Second call: success
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            'total': 25,
            'isLast': True,
            'issues': [{'key': f'PROJ-{i}'} for i in range(1, 26)]
        }

        mock_get.side_effect = [rate_limit_response, success_response]

        result = search_jira_with_jql('project = PROJ')

        assert result['total'] == 25
        assert len(result['issues']) == 25
        assert mock_get.call_count == 2
        # Verify exponential backoff was triggered (first retry after 1 second)
        mock_sleep.assert_called_once_with(1)

    @patch('jira_tools.utils.time.sleep')
    @patch('jira_tools.utils.requests.get')
    def test_search_with_multiple_rate_limit_retries(self, mock_get, mock_sleep):
        """Test exponential backoff with multiple rate limit responses"""
        # Multiple rate limit responses followed by success
        rate_limit_response1 = MagicMock()
        rate_limit_response1.status_code = 429
        rate_limit_response1.text = 'Rate limit exceeded'

        rate_limit_response2 = MagicMock()
        rate_limit_response2.status_code = 429
        rate_limit_response2.text = 'Rate limit exceeded'

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            'total': 10,
            'isLast': True,
            'issues': [{'key': f'PROJ-{i}'} for i in range(1, 11)]
        }

        mock_get.side_effect = [rate_limit_response1, rate_limit_response2, success_response]

        result = search_jira_with_jql('project = PROJ')

        assert result['total'] == 10
        assert mock_get.call_count == 3
        # Verify exponential backoff: 1s, 2s
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0] == call(1)
        assert mock_sleep.call_args_list[1] == call(2)

    @patch('jira_tools.utils.time.sleep')
    @patch('jira_tools.utils.requests.get')
    def test_search_with_rate_limit_on_second_page(self, mock_get, mock_sleep):
        """Test rate limiting during pagination (second page)"""
        # First page succeeds
        page1_response = MagicMock()
        page1_response.status_code = 200
        page1_response.json.return_value = {
            'total': 75,
            'isLast': False,
            'nextPageToken': 'token-page-2',
            'issues': [{'key': f'PROJ-{i}'} for i in range(1, 51)]
        }

        # Second page: rate limited
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.text = 'Rate limit exceeded'

        # Second page retry: success
        page2_response = MagicMock()
        page2_response.status_code = 200
        page2_response.json.return_value = {
            'total': 75,
            'isLast': True,
            'issues': [{'key': f'PROJ-{i}'} for i in range(51, 76)]
        }

        mock_get.side_effect = [page1_response, rate_limit_response, page2_response]

        result = search_jira_with_jql('project = PROJ')

        assert result['total'] == 75
        assert len(result['issues']) == 75
        assert mock_get.call_count == 3
        mock_sleep.assert_called_once_with(1)

    @patch('jira_tools.utils.time.sleep')
    @patch('jira_tools.utils.requests.get')
    def test_search_with_max_retries_exceeded(self, mock_get, mock_sleep):
        """Test that exceeding max retries raises error"""
        # All responses are rate limited
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.text = 'Rate limit exceeded'

        # Return rate limit for many attempts (more than max retries)
        mock_get.return_value = rate_limit_response

        with pytest.raises(Exception) as exc_info:
            search_jira_with_jql('project = PROJ')

        assert 'rate limit' in str(exc_info.value).lower() or '429' in str(exc_info.value)


class TestPaginationURLConstruction:
    """Tests for correct URL construction with pagination parameters"""

    @patch('jira_tools.utils.requests.get')
    def test_search_constructs_correct_pagination_urls(self, mock_get):
        """Test that pagination URLs include correct nextPageToken parameter"""
        # First page
        page1_response = MagicMock()
        page1_response.status_code = 200
        page1_response.json.return_value = {
            'total': 75,
            'isLast': False,
            'nextPageToken': 'my-token-page-2',
            'issues': [{'key': f'PROJ-{i}'} for i in range(1, 51)]
        }

        # Second page
        page2_response = MagicMock()
        page2_response.status_code = 200
        page2_response.json.return_value = {
            'total': 75,
            'isLast': True,
            'issues': [{'key': f'PROJ-{i}'} for i in range(51, 76)]
        }

        mock_get.side_effect = [page1_response, page2_response]

        search_jira_with_jql('project = PROJ')

        # Verify URL construction
        assert mock_get.call_count == 2
        # First call should not have nextPageToken
        first_call_url = mock_get.call_args_list[0][0][0]
        assert 'nextPageToken' not in first_call_url
        # Second call should have nextPageToken
        second_call_url = mock_get.call_args_list[1][0][0]
        assert 'nextPageToken=my-token-page-2' in second_call_url or 'nextPageToken%3Dmy-token-page-2' in second_call_url


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
