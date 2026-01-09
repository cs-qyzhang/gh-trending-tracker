import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config, get_config, GitHubConfig, LLMConfig, EmailConfig
from src.models import Repository, RepositorySummary, TrendingReport
from src.fetcher import GitHubFetcher
from src.filter import RepositoryFilter
from src.llm import LLMSummarizer
from src.emailer import EmailSender


class TestConfig:
    def test_default_config(self):
        config = Config()
        assert config.github.base_url == "https://api.github.com"
        assert config.trending.period == "daily"
        assert config.filter.days_threshold == 3
        assert config.email.enabled is True

    def test_config_from_yaml(self, tmp_path):
        config_content = """
github:
  token: "test-token"
  timeout: 60
trending:
  period: "weekly"
  limit: 100
filter:
  days_threshold: 7
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        config = get_config(str(config_file))

        assert config.github.token == "test-token"
        assert config.github.timeout == 60
        assert config.trending.period == "weekly"
        assert config.trending.limit == 100
        assert config.filter.days_threshold == 7

    def test_email_from_address_inference(self):
        """测试 from_address 从 smtp.username 自动推断"""
        config = Config()
        config.email.smtp.username = "test@example.com"

        # 重新创建 EmailConfig 以触发验证器
        email_config = EmailConfig(
            enabled=True,
            smtp=config.email.smtp,
            from_address="",  # 留空
            to_addresses=["recipient@example.com"]
        )

        assert email_config.from_address == "GitHub Trending <test@example.com>"

    def test_email_from_address_explicit(self):
        """测试显式指定的 from_address 不会被覆盖"""
        email_config = EmailConfig(
            enabled=True,
            smtp={"username": "test@example.com"},
            from_address="Custom Name <custom@example.com>",  # 显式指定
            to_addresses=["recipient@example.com"]
        )

        assert email_config.from_address == "Custom Name <custom@example.com>"


class TestRepository:
    def test_repository_creation(self):
        repo = Repository(
            name="test-repo",
            full_name="user/test-repo",
            description="A test repository",
            html_url="https://github.com/user/test-repo",
            language="Python",
            stars=100,
            forks=20,
            owner_login="user"
        )

        assert repo.name == "test-repo"
        assert repo.full_name == "user/test-repo"
        assert repo.stars == 100
        assert repo.appearance_count == 1

    def test_repository_equality(self):
        repo1 = Repository(
            name="test-repo",
            full_name="user/test-repo",
            html_url="https://github.com/user/test-repo",
            owner_login="user"
        )
        repo2 = Repository(
            name="test-repo",
            full_name="user/test-repo",
            html_url="https://github.com/user/test-repo",
            owner_login="user"
        )

        assert repo1 == repo2
        assert hash(repo1) == hash(repo2)


class TestGitHubFetcher:
    def test_fetcher_initialization(self):
        config = Config()
        fetcher = GitHubFetcher(config)

        assert fetcher.session is not None
        assert fetcher.config == config

    @patch('src.trending_scraper.GitHubTrendingScraper.scrape_trending')
    def test_fetch_trending_repos(self, mock_scrape):
        """测试通过爬取页面获取 trending"""
        from datetime import datetime, timezone, timezone

        mock_repo = Repository(
            name="test-repo",
            full_name="user/test-repo",
            description="A test repo",
            html_url="https://github.com/user/test-repo",
            language="Python",
            stars=100,
            forks=20,
            owner_login="user",
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc)
        )
        mock_scrape.return_value = [mock_repo]

        config = Config()
        fetcher = GitHubFetcher(config)
        repos = fetcher.fetch_trending_repos(limit=10)

        assert len(repos) == 1
        assert repos[0].name == "test-repo"
        assert repos[0].stars == 100


class TestRepositoryFilter:
    def test_filter_initialization(self, tmp_path):
        config = Config()
        db_path = str(tmp_path / "test.db")
        filter_obj = RepositoryFilter(config, db_path=db_path)

        assert filter_obj.db_path == db_path

    def test_is_new_repository(self, tmp_path):
        config = Config()
        db_path = str(tmp_path / "test.db")

        repo = Repository(
            name="new-repo",
            full_name="user/new-repo",
            html_url="https://github.com/user/new-repo",
            owner_login="user"
        )

        filter_obj = RepositoryFilter(config, db_path=db_path)
        assert filter_obj.is_new_repository(repo) is True

    def test_save_and_filter_repos(self, tmp_path):
        config = Config()
        db_path = str(tmp_path / "test.db")

        repo1 = Repository(
            name="repo1",
            full_name="user/repo1",
            html_url="https://github.com/user/repo1",
            owner_login="user",
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc)
        )
        repo2 = Repository(
            name="repo2",
            full_name="user/repo2",
            html_url="https://github.com/user/repo2",
            owner_login="user",
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc)
        )

        filter_obj = RepositoryFilter(config, db_path=db_path)
        filter_obj.save_repositories([repo1, repo2])

        assert filter_obj.is_new_repository(repo1) is False
        assert filter_obj.is_new_repository(repo2) is False

        new_repo = Repository(
            name="new-repo",
            full_name="user/new-repo",
            html_url="https://github.com/user/new-repo",
            owner_login="user"
        )
        assert filter_obj.is_new_repository(new_repo) is True


class TestLLMSummarizer:
    def test_summarizer_initialization(self):
        config = Config()
        summarizer = LLMSummarizer(config)

        assert summarizer.llm_config.provider == "openai"

    def test_fallback_summary(self):
        config = Config()
        summarizer = LLMSummarizer(config)

        repo = Repository(
            name="test-repo",
            full_name="user/test-repo",
            description="A test repository",
            html_url="https://github.com/user/test-repo",
            language="Python",
            stars=100,
            owner_login="user"
        )

        summary = summarizer._fallback_summary(repo)
        assert "100" in summary
        assert "A test repository" in summary


class TestEmailSender:
    def test_email_sender_initialization(self):
        config = Config()
        emailer = EmailSender(config)

        assert emailer.email_config.enabled is True

    def test_generate_text_report(self):
        config = Config()
        emailer = EmailSender(config)

        repo = Repository(
            name="test-repo",
            full_name="user/test-repo",
            html_url="https://github.com/user/test-repo",
            owner_login="user",
            stars=100,
            forks=20
        )
        repo_summary = RepositorySummary(
            repository=repo,
            summary="A test summary"
        )

        report = TrendingReport(
            generated_at=datetime.now(),
            period="daily",
            language="Python",
            new_repos_count=1,
            total_repos_count=1,
            repositories=[repo_summary]
        )

        text = emailer._generate_text_report(report)
        assert "test-repo" in text
        assert "GitHub Trending Report" in text

    def test_generate_html_report(self):
        config = Config()
        emailer = EmailSender(config)

        repo = Repository(
            name="test-repo",
            full_name="user/test-repo",
            html_url="https://github.com/user/test-repo",
            owner_login="user",
            stars=100,
            forks=20
        )
        repo_summary = RepositorySummary(
            repository=repo,
            summary="A test summary"
        )

        report = TrendingReport(
            generated_at=datetime.now(),
            period="daily",
            language="Python",
            new_repos_count=1,
            total_repos_count=1,
            repositories=[repo_summary]
        )

        html = emailer._generate_html_report(report)
        assert "<html>" in html
        assert "test-repo" in html


class TestTrendingReport:
    def test_report_creation(self):
        report = TrendingReport(
            generated_at=datetime.now(),
            period="daily",
            language="Python",
            new_repos_count=5,
            total_repos_count=10,
            repositories=[]
        )

        assert report.generated_at is not None
        assert report.period == "daily"
        assert report.new_repos_count == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
