"""爬取 GitHub Trending 页面（真正的 trending 数据）"""

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
    """爬取 https://github.com/trending 页面"""

    # 最大重试次数
    MAX_RETRIES = 3
    # 重试延迟（秒）
    RETRY_DELAY = 2
    # API 并发数
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
        爬取 GitHub Trending 页面

        Args:
            period: daily, weekly, monthly
            language: 编程语言（python, javascript 等）
            limit: 返回数量
            enrich_with_api: 是否使用 GitHub API 获取完整信息
            github_token: GitHub token（用于 API 请求）
        """
        # 构建URL
        url = self.base_url
        if language:
            url = f"{self.base_url}/{language}"

        # 添加时间范围参数
        since = self._get_since_param(period)
        if since:
            url = f"{url}?since={since}"

        logger.info(f"Scraping URL: {url}")

        # 使用重试机制获取页面
        soup = self._fetch_with_retry(url)
        if not soup:
            return []

        # 解析仓库列表
        repos = []
        articles = soup.select('article.Box-row')

        logger.info(f"Found {len(articles)} repositories on trending page")

        for article in articles[:limit]:
            repo = self._parse_repo_article(article)
            if repo:
                repos.append(repo)

        # 批量使用 GitHub API 获取完整信息（并发）
        if enrich_with_api and github_token and repos:
            repos = self._enrich_repos_from_api_batch(repos, github_token)

        return repos

    def _get_since_param(self, period: str) -> str:
        """获取 since 参数"""
        mapping = {
            "daily": "daily",
            "weekly": "weekly",
            "monthly": "monthly"
        }
        return mapping.get(period, "daily")

    def _fetch_with_retry(self, url: str, timeout: int = 30) -> Optional[BeautifulSoup]:
        """
        使用重试机制获取页面

        Args:
            url: 请求的 URL
            timeout: 请求超时时间

        Returns:
            BeautifulSoup 对象，失败返回 None
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

                # 如果不是最后一次尝试，等待后重试
                if attempt < self.max_retries - 1:
                    wait_time = self.RETRY_DELAY * (attempt + 1)
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)

        logger.error(f"Failed to fetch {url} after {self.max_retries} attempts: {last_error}")
        return None

    def _enrich_repos_from_api_batch(self, repos: List[Repository], github_token: str) -> List[Repository]:
        """
        使用并发请求批量获取 GitHub API 数据

        Args:
            repos: 仓库列表
            github_token: GitHub token

        Returns:
            丰富后的仓库列表
        """
        def enrich_single(repo: Repository) -> Repository:
            return self._enrich_repo_from_api(repo, github_token)

        logger.info(f"Enriching {len(repos)} repositories with API data (concurrent)...")

        with ThreadPoolExecutor(max_workers=self.API_MAX_WORKERS) as executor:
            # 提交所有任务
            future_to_repo = {executor.submit(enrich_single, repo): repo for repo in repos}

            # 收集结果
            enriched = []
            for future in as_completed(future_to_repo):
                repo = future_to_repo[future]
                try:
                    enriched_repo = future.result()
                    enriched.append(enriched_repo)
                except Exception as e:
                    logger.error(f"Error enriching {repo.full_name}: {e}")
                    enriched.append(repo)  # 即使失败也保留原始数据

        return enriched

    def _enrich_repo_from_api(self, repo: Repository, github_token: str) -> Repository:
        """使用 GitHub API 获取完整的仓库信息"""
        try:
            headers = {"Authorization": f"token {github_token}"}
            api_url = f"https://api.github.com/repos/{repo.full_name}"

            response = self.session.get(api_url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()

                # 解析日期
                created_at = None
                if data.get("created_at"):
                    created_at = datetime.fromisoformat(data["created_at"].replace('Z', '+00:00'))

                updated_at = None
                if data.get("updated_at"):
                    updated_at = datetime.fromisoformat(data["updated_at"].replace('Z', '+00:00'))

                pushed_at = None
                if data.get("pushed_at"):
                    pushed_at = datetime.fromisoformat(data["pushed_at"].replace('Z', '+00:00'))

                # 更新仓库信息
                repo.created_at = created_at
                repo.updated_at = updated_at
                repo.pushed_at = pushed_at
                repo.open_issues = data.get("open_issues_count", 0)

                # 获取 owner 头像
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
        解析单个仓库的 HTML

        GitHub Trending 页面结构：
        - article.Box-row
          - h2 > a (仓库名称和链接)
          - p (描述，位于 h2 后的第一个 p)
          - div (包含语言、stars、forks 等信息)
            - span[itemprop="programmingLanguage"] (语言)
            - a[href$="/stargazers"] (总星标数)
            - a (今日新增星标数，文本类似 "234 stars today")
            - a[href$="/network/members"] (forks 数)
          - a > img (owner 头像)
        """
        try:
            # 仓库名称和URL
            repo_link = article.select_one('h2 a')
            if not repo_link:
                return None

            # 清理仓库名称中的所有空白字符（空格、换行、制表符等）
            full_name = re.sub(r'\s+', '', repo_link.text)
            html_url = "https://github.com" + repo_link['href']

            # 描述 - 使用更精确的选择器
            # 描述是 h2 后的第一个 p 元素
            description_elem = article.select_one('h2 + p')
            description = description_elem.text.strip() if description_elem else None

            # 编程语言
            language_elem = article.select_one('span[itemprop="programmingLanguage"]')
            language = language_elem.text.strip() if language_elem else None

            # 星标数（总星标，带格式化的数字，如 "1,234"）
            stars_elem = article.select_one('a[href$="/stargazers"]')
            stars = self._parse_number(stars_elem.text) if stars_elem else 0

            # 今日新增星标数 - 包含 "stars today" 文本的链接
            stars_today = 0
            for link in article.select('a'):
                link_text = link.text.strip().lower()
                if 'star' in link_text and 'today' in link_text:
                    stars_today = self._parse_number(link.text)
                    break

            # Forks
            forks_elem = article.select_one('a[href$="/network/members"]')
            forks = self._parse_number(forks_elem.text) if forks_elem else 0

            # Owner 头像 - 查找包含 img 的 a 元素，且 img 的 src 包含 avatars
            owner_avatar_url = None
            avatar_link = article.select_one('a img[src*="avatars"]')
            if avatar_link:
                owner_avatar_url = avatar_link.get('src')
                # 移除头像 URL 中的 size 参数以获取原始大小
                if owner_avatar_url and '&s=' in owner_avatar_url:
                    owner_avatar_url = owner_avatar_url.split('&s=')[0]

            # 当前时间
            now = datetime.now(timezone.utc)

            # 解析 owner 和 repo name
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
                watchers=0,  # Trending 页面不显示
                open_issues=0,  # 稍后通过 API 获取
                owner_login=owner_login,
                owner_avatar_url=owner_avatar_url,
                created_at=None,  # 稍后通过 API 获取
                updated_at=None,
                pushed_at=None,
                first_seen_at=now,
                last_seen_at=now,
                appearance_count=1
            )

            # 将今日新增星标数存储在对象上（Pydantic 模型需要特殊处理）
            # 使用 object.__setattr__ 绕过 Pydantic 的字段验证
            object.__setattr__(repo, 'stars_today', stars_today)

            return repo

        except Exception as e:
            logger.error(f"Failed to parse repo article: {e}")
            return None

    def _parse_number(self, text: str) -> int:
        """
        解析带格式的数字

        支持格式：
        - "1,234" -> 1234
        - "5.2k" -> 5200
        - "1.5M" -> 1500000
        - "234 stars today" -> 234
        """
        if not text:
            return 0

        # 移除空格和单位文字
        cleaned = text.replace(',', '').strip()
        # 移除 "stars", "today", "forks" 等文字
        for word in ['stars', 'today', 'forks', 'star']:
            cleaned = cleaned.lower().replace(word, '').strip()

        # 处理 k/M/B 后缀
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
