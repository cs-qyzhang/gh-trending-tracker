"""Scrape GitHub Trending page (real trending data)"""

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from src.models import Repository

logger = logging.getLogger(__name__)


class GitHubTrendingScraper:
    """Scrape https://github.com/trending page"""

    # Maximum retry attempts
    MAX_RETRIES = 3
    # Retry delay in seconds
    RETRY_DELAY = 2
    # API concurrent workers
    API_MAX_WORKERS = 5

    def __init__(self, max_retries: int = None):
        self.base_url = "https://github.com/trending"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self.max_retries = max_retries or self.MAX_RETRIES

    def scrape_trending(
        self,
        period: str = "daily",
        language: str = "",
        limit: int = 50,
        enrich_with_api: bool = False,
        github_token: str = None
    ) -> List[Repository]:
        """
        Scrape GitHub Trending page

        Args:
            period: daily, weekly, monthly
            language: Programming language (python, javascript, etc.)
            limit: Number of results to return
            enrich_with_api: Whether to use GitHub API to fetch complete info
            github_token: GitHub token (for API requests)

        Returns:
            List of repositories
        """
        # Build URL
        url = self.base_url
        if language:
            url = f"{self.base_url}/{language}"

        # Add time range parameter
        since = self._get_since_param(period)
        if since:
            url = f"{url}?since={since}"

        logger.info(f"Scraping URL: {url}")

        # Fetch page with retry mechanism
        soup = self._fetch_with_retry(url)
        if not soup:
            return []

        # Parse repository list
        repos = []
        articles = soup.select('article.Box-row')

        logger.info(f"Found {len(articles)} repositories on trending page")

        for article in articles[:limit]:
            repo = self._parse_repo_article(article)
            if repo:
                repos.append(repo)

        # Batch fetch complete info using GitHub API (concurrent)
        if enrich_with_api and github_token and repos:
            repos = self._enrich_repos_from_api_batch(repos, github_token)

        return repos

    def _get_since_param(self, period: str) -> str:
        """Get since parameter"""
        mapping = {
            "daily": "daily",
            "weekly": "weekly",
            "monthly": "monthly"
        }
        return mapping.get(period, "daily")

    def _fetch_with_retry(self, url: str, timeout: int = 30) -> Optional[BeautifulSoup]:
        """
        Fetch page with retry mechanism

        Args:
            url: Request URL
            timeout: Request timeout

        Returns:
            BeautifulSoup object, returns None on failure
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=timeout)
                response.raise_for_status()
                return BeautifulSoup(response.text, 'html.parser')

            except requests.exceptions.RequestException as e:
                last_error = e
                logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}")

                # If not the last attempt, wait and retry
                if attempt < self.max_retries - 1:
                    wait_time = self.RETRY_DELAY * (attempt + 1)
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)

        logger.error(f"Failed to fetch {url} after {self.max_retries} attempts: {last_error}")
        return None

    def _enrich_repos_from_api_batch(self, repos: List[Repository], github_token: str) -> List[Repository]:
        """
        Batch fetch GitHub API data using concurrent requests

        Args:
            repos: Repository list
            github_token: GitHub token

        Returns:
            Enriched repository list
        """
        def enrich_single(repo: Repository) -> Repository:
            return self._enrich_repo_from_api(repo, github_token)

        logger.info(f"Enriching {len(repos)} repositories with API data (concurrent)...")

        with ThreadPoolExecutor(max_workers=self.API_MAX_WORKERS) as executor:
            # Submit all tasks
            future_to_repo = {executor.submit(enrich_single, repo): repo for repo in repos}

            # Collect results
            enriched = []
            for future in as_completed(future_to_repo):
                repo = future_to_repo[future]
                try:
                    enriched_repo = future.result()
                    enriched.append(enriched_repo)
                except Exception as e:
                    logger.error(f"Error enriching {repo.full_name}: {e}")
                    enriched.append(repo)  # Keep original data even on failure

        return enriched

    def _enrich_repo_from_api(self, repo: Repository, github_token: str) -> Repository:
        """Fetch complete repository info using GitHub API"""
        try:
            headers = {"Authorization": f"token {github_token}"}
            api_url = f"https://api.github.com/repos/{repo.full_name}"

            response = self.session.get(api_url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()

                # Parse dates
                created_at = None
                if data.get("created_at"):
                    created_at = datetime.fromisoformat(data["created_at"].replace('Z', '+00:00'))

                updated_at = None
                if data.get("updated_at"):
                    updated_at = datetime.fromisoformat(data["updated_at"].replace('Z', '+00:00'))

                pushed_at = None
                if data.get("pushed_at"):
                    pushed_at = datetime.fromisoformat(data["pushed_at"].replace('Z', '+00:00'))

                # Update repository info
                repo.created_at = created_at
                repo.updated_at = updated_at
                repo.pushed_at = pushed_at
                repo.open_issues = data.get("open_issues_count", 0)

                # Get owner avatar
                if data.get("owner"):
                    repo.owner_avatar_url = data["owner"].get("avatar_url")

                logger.debug(f"Enriched {repo.full_name} with API data")

            else:
                logger.warning(f"Failed to fetch API data for {repo.full_name}: {response.status_code}")

        except Exception as e:
            logger.error(f"Error enriching {repo.full_name}: {e}")

        return repo

    def _parse_repo_article(self, article) -> Optional[Repository]:
        """
        Parse HTML for a single repository

        GitHub Trending page structure:
        - article.Box-row
          - h2 > a (repo name and link)
          - p (description, first p after h2)
          - div (contains language, stars, forks, etc.)
            - span[itemprop="programmingLanguage"] (language)
            - a[href$="/stargazers"] (total star count)
            - a (stars added today, text like "234 stars today")
            - a[href$="/network/members"] (fork count)
          - a > img (owner avatar)
        """
        try:
            # Repo name and URL
            repo_link = article.select_one('h2 a')
            if not repo_link:
                return None

            # Clean all whitespace in repo name (spaces, newlines, tabs, etc.)
            full_name = re.sub(r'\s+', '', repo_link.text)
            html_url = "https://github.com" + repo_link['href']

            # Description - use more precise selector
            # Description is the first p element after h2
            description_elem = article.select_one('h2 + p')
            description = description_elem.text.strip() if description_elem else None

            # Programming language
            language_elem = article.select_one('span[itemprop="programmingLanguage"]')
            language = language_elem.text.strip() if language_elem else None

            # Star count (total stars, formatted number like "1,234")
            stars_elem = article.select_one('a[href$="/stargazers"]')
            stars = self._parse_number(stars_elem.text) if stars_elem else 0

            # Stars added today - link containing "stars today" text
            stars_today = 0
            for link in article.select('a'):
                link_text = link.text.strip().lower()
                if 'star' in link_text and 'today' in link_text:
                    stars_today = self._parse_number(link.text)
                    break

            # Forks
            forks_elem = article.select_one('a[href$="/network/members"]')
            forks = self._parse_number(forks_elem.text) if forks_elem else 0

            # Owner avatar - find a element containing img, and img src includes avatars
            owner_avatar_url = None
            avatar_link = article.select_one('a img[src*="avatars"]')
            if avatar_link:
                owner_avatar_url = avatar_link.get('src')
                # Remove size parameter from avatar URL to get original size
                if owner_avatar_url and '&s=' in owner_avatar_url:
                    owner_avatar_url = owner_avatar_url.split('&s=')[0]

            # Current time
            now = datetime.now(timezone.utc)

            # Parse owner and repo name
            parts = full_name.split('/')
            owner_login = parts[0] if len(parts) > 1 else ''
            repo_name = parts[1] if len(parts) > 1 else full_name

            repo = Repository(
                name=repo_name,
                full_name=full_name,
                description=description,
                html_url=html_url,
                language=language,
                stars=stars,
                forks=forks,
                watchers=0,  # Not shown on Trending page
                open_issues=0,  # Will fetch via API later
                owner_login=owner_login,
                owner_avatar_url=owner_avatar_url,
                created_at=None,  # Will fetch via API later
                updated_at=None,
                pushed_at=None,
                first_seen_at=now,
                last_seen_at=now,
                appearance_count=1
            )

            # Store stars added today on the object (Pydantic model requires special handling)
            # Use object.__setattr__ to bypass Pydantic field validation
            object.__setattr__(repo, 'stars_today', stars_today)

            return repo

        except Exception as e:
            logger.error(f"Failed to parse repo article: {e}")
            return None

    def _parse_number(self, text: str) -> int:
        """
        Parse formatted numbers

        Supported formats:
        - "1,234" -> 1234
        - "5.2k" -> 5200
        - "1.5M" -> 1500000
        - "234 stars today" -> 234
        """
        if not text:
            return 0

        # Remove spaces and unit text
        cleaned = text.replace(',', '').strip()
        # Remove text like "stars", "today", "forks"
        for word in ['stars', 'today', 'forks', 'star']:
            cleaned = cleaned.lower().replace(word, '').strip()

        # Handle k/M/B suffixes
        multiplier = 1
        if 'k' in cleaned.lower():
            multiplier = 1000
            cleaned = cleaned.lower().replace('k', '')
        elif 'm' in cleaned.lower():
            multiplier = 1_000_000
            cleaned = cleaned.lower().replace('m', '')
        elif 'b' in cleaned.lower():
            multiplier = 1_000_000_000
            cleaned = cleaned.lower().replace('b', '')

        try:
            return int(float(cleaned) * multiplier)
        except (ValueError, TypeError):
            logger.warning(f"Failed to parse number: {text!r}")
            return 0
