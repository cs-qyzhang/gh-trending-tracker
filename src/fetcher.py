import logging
import time
from typing import Optional

import requests

from src.config import Config
from src.models import Repository
from src.trending_scraper import GitHubTrendingScraper

logger = logging.getLogger(__name__)


class GitHubFetcher:
    """GitHub Trending 数据获取器 - 仅通过爬取页面获取"""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-Trending-Agent"
        })
        if self.config.github.token:
            print("Using GitHub token for API authentication")
            self.session.headers["Authorization"] = f"Bearer {self.config.github.token}"
        else:
            print("No GitHub token provided. Limited API access.")
        self.session.timeout = self.config.github.timeout

    def fetch_trending_repos(
        self,
        period: Optional[str] = None,
        language: Optional[str] = None,
        limit: Optional[int] = None,
        enrich_with_api: bool = False
    ) -> list[Repository]:
        """
        获取 GitHub Trending 仓库（通过爬取页面）

        Args:
            period: daily, weekly, monthly
            language: 编程语言（如 python, javascript）
            limit: 返回数量
            enrich_with_api: 是否使用 GitHub API 获取完整信息（如 created_at）

        Returns:
            仓库列表
        """
        period = period or self.config.trending.period
        language = language or self.config.trending.language
        limit = limit or self.config.trending.limit

        logger.info(f"Fetching trending repos: period={period}, language={language or 'All'}, limit={limit}")

        scraper = GitHubTrendingScraper()
        repos = scraper.scrape_trending(
            period=period,
            language=language,
            limit=limit,
            enrich_with_api=enrich_with_api,
            github_token=self.config.github.token if enrich_with_api else None
        )
        logger.info(f"Scraped {len(repos)} repositories from trending page")

        return repos

    def fetch_repo_readme(self, repo_full_name: str) -> Optional[str]:
        """
        获取仓库 README 内容

        Args:
            repo_full_name: 仓库全名，如 "owner/repo"

        Returns:
            README 内容，失败返回 None
        """
        max_retries = 3
        retry_delay = 2  # seconds

        for attempt in range(max_retries):
            try:
                readme_url = f"{self.config.github.base_url}/repos/{repo_full_name}/readme"
                response = self.session.get(readme_url)

                # Handle rate limiting
                if response.status_code == 403:
                    if 'Retry-After' in response.headers:
                        retry_after = int(response.headers['Retry-After'])
                        logger.warning(f"Rate limit exceeded. Retrying after {retry_after} seconds...")
                        time.sleep(retry_after)
                        continue
                    elif attempt < max_retries - 1:
                        logger.warning(f"Rate limit exceeded. Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue

                response.raise_for_status()
                data = response.json()
                import base64
                content = data.get("content", "")
                return base64.b64decode(content).decode("utf-8", errors="ignore")
            except requests.RequestException as e:
                if attempt == max_retries - 1:  # Last attempt
                    logger.warning(f"Failed to fetch README for {repo_full_name}: {e}")
                    return None
                # Retry on other errors too
                logger.warning(f"Attempt {attempt + 1} failed for {repo_full_name}, retrying...")
                time.sleep(retry_delay)
                retry_delay *= 2
        return None

    def enrich_repository(self, repo: Repository) -> Repository:
        """
        丰富仓库信息（获取 README）

        Args:
            repo: 仓库对象

        Returns:
            丰富后的仓库对象
        """
        readme = self.fetch_repo_readme(repo.full_name)
        # 使用 object.__setattr__ 绕过 Pydantic 的字段验证
        object.__setattr__(repo, 'readme_content', readme)
        return repo
