"""Tests for GitHubTrendingScraper module"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.trending_scraper import GitHubTrendingScraper
from src.models import Repository


class TestParseNumber:
    """Test number parsing functionality"""

    def setup_method(self):
        self.scraper = GitHubTrendingScraper()

    def test_parse_simple_number(self):
        """Test simple numbers"""
        assert self.scraper._parse_number("1234") == 1234
        assert self.scraper._parse_number("1,234") == 1234
        assert self.scraper._parse_number("12,345") == 12345

    def test_parse_k_suffix(self):
        """Test k suffix"""
        assert self.scraper._parse_number("5k") == 5000
        assert self.scraper._parse_number("5.2k") == 5200
        assert self.scraper._parse_number("1.5k") == 1500
        assert self.scraper._parse_number("0.5k") == 500

    def test_parse_m_suffix(self):
        """Test M suffix"""
        assert self.scraper._parse_number("1M") == 1_000_000
        assert self.scraper._parse_number("1.5M") == 1_500_000
        assert self.scraper._parse_number("0.5M") == 500_000

    def test_parse_b_suffix(self):
        """Test B suffix"""
        assert self.scraper._parse_number("1B") == 1_000_000_000
        assert self.scraper._parse_number("2.5B") == 2_500_000_000

    def test_parse_with_text(self):
        """Test numbers with text"""
        assert self.scraper._parse_number("1234 stars") == 1234
        assert self.scraper._parse_number("5.2k stars") == 5200
        assert self.scraper._parse_number("234 stars today") == 234
        assert self.scraper._parse_number("1.5k forks") == 1500

    def test_parse_empty_and_invalid(self):
        """Test empty and invalid values"""
        assert self.scraper._parse_number("") == 0
        assert self.scraper._parse_number(None) == 0
        assert self.scraper._parse_number("invalid") == 0
        assert self.scraper._parse_number("N/A") == 0


class TestParseRepoArticle:
    """Test repository HTML parsing"""

    def setup_method(self):
        self.scraper = GitHubTrendingScraper()

    def test_parse_basic_repo(self):
        """Test basic repository parsing"""
        html = """
        <article class="Box-row">
            <h2>
                <a href="/user/repo">user
                /
                repo</a>
            </h2>
            <p>A test repository description</p>
            <div>
                <span itemprop="programmingLanguage">Python</span>
                <a href="/user/repo/stargazers">1,234</a>
                <a href="/user/repo/network/members">567</a>
            </div>
            <a href="/user">
                <img src="https://avatars.githubusercontent.com/u/123?v=4&amp;s=40" />
            </a>
        </article>
        """
        soup = BeautifulSoup(html, 'html.parser')
        article = soup.select_one('article.Box-row')

        repo = self.scraper._parse_repo_article(article)

        assert repo is not None
        assert repo.name == "repo"
        assert repo.full_name == "user/repo"
        assert repo.description == "A test repository description"
        assert repo.language == "Python"
        assert repo.stars == 1234
        assert repo.forks == 567
        assert repo.owner_login == "user"
        assert repo.owner_avatar_url is not None

    def test_parse_repo_with_stars_today(self):
        """Test parsing with stars today count"""
        html = """
        <article class="Box-row">
            <h2>
                <a href="/user/repo">user/repo</a>
            </h2>
            <p>A test repository</p>
            <div>
                <span itemprop="programmingLanguage">JavaScript</span>
                <a href="/user/repo/stargazers">5,000</a>
                <a href="#" class="no-underline">123 stars today</a>
                <a href="/user/repo/network/members">200</a>
            </div>
        </article>
        """
        soup = BeautifulSoup(html, 'html.parser')
        article = soup.select_one('article.Box-row')

        repo = self.scraper._parse_repo_article(article)

        assert repo is not None
        assert repo.stars == 5000
        assert repo.stars_today == 123

    def test_parse_repo_with_k_stars(self):
        """Test stars with k suffix"""
        html = """
        <article class="Box-row">
            <h2>
                <a href="/user/repo">user/repo</a>
            </h2>
            <p>A test repository</p>
            <div>
                <span itemprop="programmingLanguage">Rust</span>
                <a href="/user/repo/stargazers">5.2k</a>
                <a href="#" class="no-underline">1.2k stars today</a>
                <a href="/user/repo/network/members">300</a>
            </div>
        </article>
        """
        soup = BeautifulSoup(html, 'html.parser')
        article = soup.select_one('article.Box-row')

        repo = self.scraper._parse_repo_article(article)

        assert repo is not None
        assert repo.stars == 5200
        assert repo.stars_today == 1200

    def test_parse_repo_without_language(self):
        """Test repository without language"""
        html = """
        <article class="Box-row">
            <h2>
                <a href="/user/repo">user/repo</a>
            </h2>
            <p>A test repository</p>
            <div>
                <a href="/user/repo/stargazers">100</a>
                <a href="/user/repo/network/members">50</a>
            </div>
        </article>
        """
        soup = BeautifulSoup(html, 'html.parser')
        article = soup.select_one('article.Box-row')

        repo = self.scraper._parse_repo_article(article)

        assert repo is not None
        assert repo.language is None

    def test_parse_repo_without_description(self):
        """Test repository without description"""
        html = """
        <article class="Box-row">
            <h2>
                <a href="/user/repo">user/repo</a>
            </h2>
            <div>
                <span itemprop="programmingLanguage">Go</span>
                <a href="/user/repo/stargazers">100</a>
            </div>
        </article>
        """
        soup = BeautifulSoup(html, 'html.parser')
        article = soup.select_one('article.Box-row')

        repo = self.scraper._parse_repo_article(article)

        assert repo is not None
        assert repo.description is None

    def test_parse_invalid_article(self):
        """Test invalid article element"""
        html = '<article class="Box-row"><p>No content</p></article>'
        soup = BeautifulSoup(html, 'html.parser')
        article = soup.select_one('article.Box-row')

        repo = self.scraper._parse_repo_article(article)

        assert repo is None


class TestFetchWithRetry:
    """Test retry mechanism"""

    def setup_method(self):
        self.scraper = GitHubTrendingScraper(max_retries=3)

    @patch('requests.Session.get')
    def test_successful_request(self, mock_get):
        """Test successful request"""
        mock_response = MagicMock()
        mock_response.text = "<html><body>Test</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        soup = self.scraper._fetch_with_retry("https://example.com")

        assert soup is not None
        assert "Test" in str(soup)

    @patch('requests.Session.get')
    @patch('src.trending_scraper.time.sleep')
    def test_retry_on_failure(self, mock_sleep, mock_get):
        """Test retry on failure"""
        import requests
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        soup = self.scraper._fetch_with_retry("https://example.com")

        assert soup is None
        # Should retry 3 times
        assert mock_get.call_count == 3

    @patch('requests.Session.get')
    @patch('src.trending_scraper.time.sleep')
    def test_retry_then_success(self, mock_sleep, mock_get):
        """Test retry then success"""
        import requests
        mock_response = MagicMock()
        mock_response.text = "<html><body>Success</body></html>"
        mock_response.raise_for_status = MagicMock()

        # First two fail, third succeeds
        mock_get.side_effect = [
            requests.exceptions.RequestException("Network error"),
            requests.exceptions.RequestException("Network error"),
            mock_response
        ]

        soup = self.scraper._fetch_with_retry("https://example.com")

        assert soup is not None
        assert "Success" in str(soup)
        assert mock_get.call_count == 3


class TestGetSinceParam:
    """Test since parameter conversion"""

    def setup_method(self):
        self.scraper = GitHubTrendingScraper()

    def test_daily_period(self):
        assert self.scraper._get_since_param("daily") == "daily"

    def test_weekly_period(self):
        assert self.scraper._get_since_param("weekly") == "weekly"

    def test_monthly_period(self):
        assert self.scraper._get_since_param("monthly") == "monthly"

    def test_invalid_period(self):
        assert self.scraper._get_since_param("invalid") == "daily"


class TestInitialization:
    """Test initialization"""

    def test_default_initialization(self):
        scraper = GitHubTrendingScraper()
        assert scraper.max_retries == 3
        assert scraper.base_url == "https://github.com/trending"

    def test_custom_retries(self):
        scraper = GitHubTrendingScraper(max_retries=5)
        assert scraper.max_retries == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
