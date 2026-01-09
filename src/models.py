from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Repository(BaseModel):
    name: str
    full_name: str
    description: Optional[str] = None
    html_url: str
    language: Optional[str] = None
    stars: int = 0
    forks: int = 0
    watchers: int = 0
    open_issues: int = 0
    owner_login: str
    owner_avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    pushed_at: Optional[datetime] = None
    readme_content: Optional[str] = None
    first_seen_at: datetime = None
    last_seen_at: datetime = None
    appearance_count: int = 1

    def __hash__(self):
        return hash(self.full_name)

    def __eq__(self, other):
        if isinstance(other, Repository):
            return self.full_name == other.full_name
        return False


class RepositorySummary(BaseModel):
    repository: Repository
    summary: str


class TrendingReport(BaseModel):
    generated_at: datetime
    period: str
    language: str
    new_repos_count: int
    total_repos_count: int
    repositories: list[RepositorySummary]
