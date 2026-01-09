import logging
from typing import List, Optional

import httpx

from src.config import Config, LLMConfig
from src.models import Repository

logger = logging.getLogger(__name__)


class LLMSummarizer:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.llm_config = self.config.llm
        self._client = None

    @property
    def client(self):
        if self._client is None:
            # Create custom httpx client with Claude Code headers
            http_client = httpx.Client(
                headers={
                    "User-Agent": "claude-code/1.0.0",
                    "X-Client-Platform": "cli",
                    "X-Client-Version": "1.0.0",
                },
                timeout=httpx.Timeout(60.0, connect=10.0)
            )

            if self.llm_config.provider == "openai":
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.llm_config.api_key,
                    base_url=self.llm_config.base_url or None,
                    http_client=http_client
                )
            elif self.llm_config.provider == "anthropic":
                from anthropic import Anthropic
                self._client = Anthropic(
                    api_key=self.llm_config.api_key,
                    base_url=self.llm_config.base_url or None,
                    http_client=http_client
                )
            else:
                raise ValueError(f"Unsupported LLM provider: {self.llm_config.provider}")
        return self._client

    def summarize_repository(self, repo: Repository) -> str:
        """Generate summary with stars, description, and AI analysis"""
        prompt = self._build_summary_prompt(repo)

        try:
            response = self._call_llm(prompt)
            ai_summary = self._parse_response(response)
            ai_summary = ai_summary.strip()
        except Exception as e:
            logger.error(f"Failed to summarize repository {repo.full_name}: {e}")
            ai_summary = None

        # Build final summary with all three parts
        return self._build_final_summary(repo, ai_summary)

    def summarize_repositories(self, repos: List[Repository]) -> List[str]:
        summaries = []
        for repo in repos:
            logger.info(f"Summarizing repository: {repo.full_name}")
            summary = self.summarize_repository(repo)
            summaries.append(summary)
        return summaries

    def _build_summary_prompt(self, repo: Repository) -> str:
        prompt_template = self.llm_config.summary_prompt
        context = self._build_context(repo)

        prompt = prompt_template.format(
            repo_name=repo.full_name,
            description=repo.description or "No description",
            language=repo.language or "Unknown",
            stars=repo.stars,
            readme=context
        )

        return prompt

    def _build_context(self, repo: Repository) -> str:
        context_parts = []

        if repo.description:
            context_parts.append(f"Description: {repo.description}")

        if repo.readme_content:
            readme_snippet = repo.readme_content[:2000]
            context_parts.append(f"README content:\n{readme_snippet}")

        return "\n".join(context_parts) if context_parts else "No additional context available"

    def _call_llm(self, prompt: str) -> str:
        if self.llm_config.provider == "openai":
            response = self.client.chat.completions.create(
                model=self.llm_config.model,
                messages=[
                    {"role": "system", "content": "You are a helpful tech analyst assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=self.llm_config.max_tokens,
                temperature=self.llm_config.temperature
            )
            return response.choices[0].message.content or ""

        elif self.llm_config.provider == "anthropic":
            response = self.client.messages.create(
                model=self.llm_config.model,
                max_tokens=self.llm_config.max_tokens,
                temperature=self.llm_config.temperature,
                extra_headers={
                    "anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15",
                    "anthropic-dangerous-direct-browser-access": "true",
                },
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.content[0].text if response.content else ""

        return ""

    def _parse_response(self, response: str) -> str:
        lines = response.strip().split("\n")
        for line in lines:
            if line.strip() and not line.startswith("#"):
                return line.strip()

        if len(response) > 10:
            return response.strip()[:200]

        return response

    def _build_final_summary(self, repo: Repository, ai_summary: Optional[str] = None) -> str:
        """Build final summary with stars, description, and AI analysis separated by lines"""
        parts = []

        # First line: Star count
        if repo.stars > 0:
            parts.append(f"⭐ {repo.stars} stars")

        # Second line: Repository's own description
        if repo.description:
            parts.append(repo.description)

        # Third line: AI summary (if available)
        if ai_summary:
            parts.append(ai_summary)

        # Join with separator line (will be converted to <hr> in HTML)
        separator = "\n---\n"
        return separator.join(parts)

    def _fallback_summary(self, repo: Repository) -> str:
        """Generate a simple summary without redundant repository/language info"""
        return self._build_final_summary(repo, ai_summary=None)

    def evaluate_novelty(self, repo: Repository, context: str = "") -> float:
        prompt = f"""
Evaluate the novelty of this GitHub repository on a scale of 0.0 to 1.0.

Repository: {repo.full_name}
Description: {repo.description or "No description"}
Language: {repo.language or "Unknown"}
Stars: {repo.stars}
Created: {repo.created_at}

{context}

Rate how novel this repository is (0.0 = not novel at all, 1.0 = highly novel/innovative). 
Only respond with a number between 0.0 and 1.0.
"""

        try:
            response = self._call_llm(prompt)
            score = float(response.strip())
            return max(0.0, min(1.0, score))
        except (ValueError, Exception) as e:
            logger.warning(f"Failed to evaluate novelty: {e}")
            return 0.5

    def evaluate_importance(self, repo: Repository, context: str = "") -> float:
        prompt = f"""
Evaluate the importance/impact of this GitHub repository on a scale of 0.0 to 1.0.

Repository: {repo.full_name}
Description: {repo.description or "No description"}
Language: {repo.language or "Unknown"}
Stars: {repo.stars}
Forks: {repo.forks}
Issues: {repo.open_issues}

{context}

Rate how important or impactful this repository is (0.0 = not important, 1.0 = very important).
Only respond with a number between 0.0 and 1.0.
"""

        try:
            response = self._call_llm(prompt)
            score = float(response.strip())
            return max(0.0, min(1.0, score))
        except (ValueError, Exception) as e:
            logger.warning(f"Failed to evaluate importance: {e}")
            return 0.5
