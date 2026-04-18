#!/usr/bin/env python3
"""
Tests for get_jira_statistics.py

Tests all functions in the module including:
- calculate_story_points_for_issues: Story point calculation with defaulting
- get_jql_query_statistics: JQL query statistics calculation with percentages
"""
import pytest
import os
from unittest.mock import patch

os.environ.setdefault('JIRA_SERVER', 'https://test.atlassian.net')
os.environ.setdefault('JIRA_EMAIL', 'test@test.com')
os.environ.setdefault('JIRA_API_TOKEN', 'test')

from jira_tools.commands.get_statistics import (
    DEFAULT_STORY_POINTS,
    STORY_POINT_FIELD_ID,
    calculate_story_points_for_issues,
    get_jql_query_statistics
)


class TestConstants:
    """Tests for module-level constants"""

    def test_default_story_points_value(self):
        """Test that DEFAULT_STORY_POINTS has the expected value"""
        assert DEFAULT_STORY_POINTS == 3
        assert isinstance(DEFAULT_STORY_POINTS, int)

    def test_story_point_field_id_value(self):
        """Test that STORY_POINT_FIELD_ID has the expected value"""
        assert STORY_POINT_FIELD_ID == 'customfield_10115'
        assert isinstance(STORY_POINT_FIELD_ID, str)


class TestCalculateStoryPointsForIssues:
    """Tests for calculate_story_points_for_issues function"""

    def test_calculate_with_all_explicit_points(self):
        """Test calculation when all issues have explicit story points"""
        issues = [
            {
                'key': 'PROJ-1',
                'fields': {
                    'summary': 'Task 1',
                    'customfield_10115': 3
                }
            },
            {
                'key': 'PROJ-2',
                'fields': {
                    'summary': 'Task 2',
                    'customfield_10115': 5
                }
            },
            {
                'key': 'PROJ-3',
                'fields': {
                    'summary': 'Task 3',
                    'customfield_10115': 8
                }
            }
        ]

        total_points, defaulted_count, explicit_count = calculate_story_points_for_issues(issues)

        assert total_points == 16
        assert defaulted_count == 0
        assert explicit_count == 3

    def test_calculate_with_all_defaulted_points(self):
        """Test calculation when all issues use default story points"""
        issues = [
            {
                'key': 'PROJ-1',
                'fields': {
                    'summary': 'Task 1',
                    'customfield_10115': None
                }
            },
            {
                'key': 'PROJ-2',
                'fields': {
                    'summary': 'Task 2',
                    'customfield_10115': None
                }
            }
        ]

        total_points, defaulted_count, explicit_count = calculate_story_points_for_issues(issues)

        assert total_points == 6  # 2 issues * 3 default points
        assert defaulted_count == 2
        assert explicit_count == 0

    def test_calculate_with_mixed_points(self):
        """Test calculation with mix of explicit and defaulted story points"""
        issues = [
            {
                'key': 'PROJ-1',
                'fields': {
                    'summary': 'Task 1',
                    'customfield_10115': 3
                }
            },
            {
                'key': 'PROJ-2',
                'fields': {
                    'summary': 'Task 2',
                    'customfield_10115': None
                }
            },
            {
                'key': 'PROJ-3',
                'fields': {
                    'summary': 'Task 3',
                    'customfield_10115': 8
                }
            }
        ]

        total_points, defaulted_count, explicit_count = calculate_story_points_for_issues(issues)

        assert total_points == 14  # 3 + 3 (defaulted) + 8
        assert defaulted_count == 1
        assert explicit_count == 2

    def test_calculate_with_zero_points(self):
        """Test calculation when an issue has 0 story points"""
        issues = [
            {
                'key': 'PROJ-1',
                'fields': {
                    'summary': 'Task 1',
                    'customfield_10115': 0
                }
            }
        ]

        total_points, defaulted_count, explicit_count = calculate_story_points_for_issues(issues)

        assert total_points == 0
        assert defaulted_count == 0
        assert explicit_count == 1

    def test_calculate_with_empty_issues_list(self):
        """Test calculation with empty issues list"""
        issues = []

        total_points, defaulted_count, explicit_count = calculate_story_points_for_issues(issues)

        assert total_points == 0
        assert defaulted_count == 0
        assert explicit_count == 0



class TestGetJqlQueryStatistics:
    """Tests for get_jql_query_statistics function"""

    @patch('jira_tools.commands.get_statistics.jira_utils.search_jira_with_jql')
    def test_query_with_all_resolved_issues(self, mock_search):
        """Test statistics when all issues are resolved"""
        mock_search.return_value = {
            'issues': [
                {
                    'key': 'PROJ-1',
                    'fields': {
                        'summary': 'Task 1',
                        'resolution': {'name': 'Done'},
                        'customfield_10115': 5
                    }
                },
                {
                    'key': 'PROJ-2',
                    'fields': {
                        'summary': 'Task 2',
                        'resolution': {'name': 'Done'},
                        'customfield_10115': 8
                    }
                }
            ]
        }

        stats = get_jql_query_statistics('project = PROJ')

        assert stats['total_points'] == 13
        assert stats['resolved_points'] == 13
        assert stats['unresolved_points'] == 0
        assert stats['resolved_points_percentage'] == 100
        assert stats['total_issues'] == 2
        assert stats['resolved_issues'] == 2
        assert stats['unresolved_issues'] == 0
        assert stats['resolved_issues_percentage'] == 100

    @patch('jira_tools.commands.get_statistics.jira_utils.search_jira_with_jql')
    def test_query_with_all_unresolved_issues(self, mock_search):
        """Test statistics when all issues are unresolved"""
        mock_search.return_value = {
            'issues': [
                {
                    'key': 'PROJ-1',
                    'fields': {
                        'summary': 'Task 1',
                        'resolution': None,
                        'customfield_10115': 5
                    }
                },
                {
                    'key': 'PROJ-2',
                    'fields': {
                        'summary': 'Task 2',
                        'resolution': None,
                        'customfield_10115': 8
                    }
                }
            ]
        }

        stats = get_jql_query_statistics('project = PROJ')

        assert stats['total_points'] == 13
        assert stats['resolved_points'] == 0
        assert stats['unresolved_points'] == 13
        assert stats['resolved_points_percentage'] == 0
        assert stats['total_issues'] == 2
        assert stats['resolved_issues'] == 0
        assert stats['unresolved_issues'] == 2
        assert stats['resolved_issues_percentage'] == 0

    @patch('jira_tools.commands.get_statistics.jira_utils.search_jira_with_jql')
    def test_query_with_mixed_resolution_status(self, mock_search):
        """Test statistics with mixed resolved and unresolved issues"""
        mock_search.return_value = {
            'issues': [
                {
                    'key': 'PROJ-1',
                    'fields': {
                        'summary': 'Task 1',
                        'resolution': {'name': 'Done'},
                        'customfield_10115': 5
                    }
                },
                {
                    'key': 'PROJ-2',
                    'fields': {
                        'summary': 'Task 2',
                        'resolution': None,
                        'customfield_10115': 8
                    }
                },
                {
                    'key': 'PROJ-3',
                    'fields': {
                        'summary': 'Task 3',
                        'resolution': {'name': 'Done'},
                        'customfield_10115': 3
                    }
                },
                {
                    'key': 'PROJ-4',
                    'fields': {
                        'summary': 'Task 4',
                        'resolution': None,
                        'customfield_10115': 2
                    }
                }
            ]
        }

        stats = get_jql_query_statistics('project = PROJ')

        assert stats['total_points'] == 18
        assert stats['resolved_points'] == 8
        assert stats['unresolved_points'] == 10
        assert stats['resolved_points_percentage'] == 44
        assert stats['total_issues'] == 4
        assert stats['resolved_issues'] == 2
        assert stats['unresolved_issues'] == 2
        assert stats['resolved_issues_percentage'] == 50

    @patch('jira_tools.commands.get_statistics.jira_utils.search_jira_with_jql')
    def test_query_with_defaulted_story_points(self, mock_search):
        """Test statistics with defaulted story points"""
        mock_search.return_value = {
            'issues': [
                {
                    'key': 'PROJ-1',
                    'fields': {
                        'summary': 'Task 1',
                        'resolution': {'name': 'Done'},
                        'customfield_10115': None
                    }
                },
                {
                    'key': 'PROJ-2',
                    'fields': {
                        'summary': 'Task 2',
                        'resolution': None,
                        'customfield_10115': None
                    }
                }
            ]
        }

        stats = get_jql_query_statistics('project = PROJ')

        assert stats['total_points'] == 6  # 2 issues * 3 default points
        assert stats['resolved_points'] == 3
        assert stats['unresolved_points'] == 3
        assert stats['resolved_points_percentage'] == 50
        assert stats['total_issues'] == 2
        assert stats['resolved_issues'] == 1
        assert stats['unresolved_issues'] == 1
        assert stats['resolved_issues_percentage'] == 50

    @patch('jira_tools.commands.get_statistics.jira_utils.search_jira_with_jql')
    def test_query_with_no_issues(self, mock_search):
        """Test statistics when no issues match the query"""
        mock_search.return_value = {'issues': []}

        stats = get_jql_query_statistics('project = NONEXISTENT')

        assert stats['total_points'] == 0
        assert stats['resolved_points'] == 0
        assert stats['unresolved_points'] == 0
        assert stats['resolved_points_percentage'] == 0
        assert stats['total_issues'] == 0
        assert stats['resolved_issues'] == 0
        assert stats['unresolved_issues'] == 0
        assert stats['resolved_issues_percentage'] == 0

    @patch('jira_tools.commands.get_statistics.jira_utils.search_jira_with_jql')
    def test_query_verifies_correct_fields_requested(self, mock_search):
        """Test that the correct fields are requested from JIRA API"""
        mock_search.return_value = {'issues': []}

        get_jql_query_statistics('project = PROJ')

        # Verify the API was called with correct fields
        mock_search.assert_called_once_with(
            'project = PROJ',
            ['key', 'summary', 'resolution', 'customfield_10115']
        )

    @patch('jira_tools.commands.get_statistics.jira_utils.search_jira_with_jql')
    def test_query_with_zero_story_points(self, mock_search):
        """Test statistics when issues have 0 story points"""
        mock_search.return_value = {
            'issues': [
                {
                    'key': 'PROJ-1',
                    'fields': {
                        'summary': 'Task 1',
                        'resolution': {'name': 'Done'},
                        'customfield_10115': 0
                    }
                },
                {
                    'key': 'PROJ-2',
                    'fields': {
                        'summary': 'Task 2',
                        'resolution': None,
                        'customfield_10115': 5
                    }
                }
            ]
        }

        stats = get_jql_query_statistics('project = PROJ')

        assert stats['total_points'] == 5
        assert stats['resolved_points'] == 0
        assert stats['unresolved_points'] == 5
        assert stats['resolved_points_percentage'] == 0
        assert stats['total_issues'] == 2
        assert stats['resolved_issues'] == 1
        assert stats['unresolved_issues'] == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
