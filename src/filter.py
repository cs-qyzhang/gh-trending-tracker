import logging
import os
from datetime import datetime, timedelta
from typing import List, Optional, Set

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from src.config import Config
from src.models import Repository

logger = logging.getLogger(__name__)

Base = declarative_base()


class RepositoryRecord(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    full_name = Column(String(500), nullable=False, unique=True, index=True)
    description = Column(Text)
    html_url = Column(String(1000))
    language = Column(String(100))
    stars = Column(Integer, default=0)
    forks = Column(Integer, default=0)
    watchers = Column(Integer, default=0)
    open_issues = Column(Integer, default=0)
    owner_login = Column(String(255))
    owner_avatar_url = Column(String(1000))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    pushed_at = Column(DateTime)
    readme_content = Column(Text)
    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
    appearance_count = Column(Integer, default=1)

    def to_model(self) -> Repository:
        return Repository(
            name=self.name,
            full_name=self.full_name,
            description=self.description,
            html_url=self.html_url,
            language=self.language,
            stars=self.stars,
            forks=self.forks,
            watchers=self.watchers,
            open_issues=self.open_issues,
            owner_login=self.owner_login,
            owner_avatar_url=self.owner_avatar_url,
            created_at=self.created_at,
            updated_at=self.updated_at,
            pushed_at=self.pushed_at,
            readme_content=self.readme_content,
            first_seen_at=self.first_seen_at,
            last_seen_at=self.last_seen_at,
            appearance_count=self.appearance_count
        )

    @classmethod
    def from_model(cls, repo: Repository) -> "RepositoryRecord":
        return cls(
            name=repo.name,
            full_name=repo.full_name,
            description=repo.description,
            html_url=repo.html_url,
            language=repo.language,
            stars=repo.stars,
            forks=repo.forks,
            watchers=repo.watchers,
            open_issues=repo.open_issues,
            owner_login=repo.owner_login,
            owner_avatar_url=repo.owner_avatar_url,
            created_at=repo.created_at,
            updated_at=repo.updated_at,
            pushed_at=repo.pushed_at,
            readme_content=repo.readme_content,
            first_seen_at=repo.first_seen_at,
            last_seen_at=repo.last_seen_at,
            appearance_count=repo.appearance_count
        )


class RepositoryFilter:
    def __init__(self, config: Optional[Config] = None, db_path: Optional[str] = None):
        self.config = config or Config()
        self.db_path = db_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data",
            "repos.db"
        )
        self._engine = None
        self._session_factory = None

    @property
    def engine(self):
        if self._engine is None:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._engine = create_engine(f"sqlite:///{self.db_path}", echo=False)
        return self._engine

    @property
    def session_factory(self):
        if self._session_factory is None:
            Base.metadata.create_all(self.engine)
            self._session_factory = sessionmaker(bind=self.engine)
        return self._session_factory

    def get_session(self) -> Session:
        return self.session_factory()

    def is_new_repository(self, repo: Repository, days_threshold: Optional[int] = None) -> bool:
        days = days_threshold or self.config.filter.days_threshold
        threshold_date = datetime.now() - timedelta(days=days)

        with self.get_session() as session:
            existing = session.query(RepositoryRecord).filter(
                RepositoryRecord.full_name == repo.full_name
            ).first()

            if existing is None:
                return True
            else:
                repo.first_seen_at = existing.first_seen_at
                return False

    def filter_new_repos(
        self,
        repos: List[Repository],
        days_threshold: Optional[int] = None
    ) -> List[Repository]:
        days = days_threshold or self.config.filter.days_threshold
        threshold_date = datetime.now() - timedelta(days=days)

        with self.get_session() as session:
            existing_repos = session.query(RepositoryRecord.full_name).all()
            existing_names = {r[0] for r in existing_repos}

            new_repos = []
            for repo in repos:
                if repo.full_name not in existing_names:
                    new_repos.append(repo)
                    logger.info(f"New repository found: {repo.full_name}")
                else:
                    record = session.query(RepositoryRecord).filter(
                        RepositoryRecord.full_name == repo.full_name
                    ).first()
                    if record:
                        repo.first_seen_at = record.first_seen_at
                        repo.appearance_count = record.appearance_count + 1

        return new_repos

    def save_repositories(self, repos: List[Repository]) -> None:
        with self.get_session() as session:
            for repo in repos:
                existing = session.query(RepositoryRecord).filter(
                    RepositoryRecord.full_name == repo.full_name
                ).first()

                if existing:
                    existing.last_seen_at = repo.last_seen_at
                    existing.stars = repo.stars
                    existing.forks = repo.forks
                    existing.appearance_count += 1
                    if repo.readme_content and not existing.readme_content:
                        existing.readme_content = repo.readme_content
                else:
                    record = RepositoryRecord.from_model(repo)
                    session.add(record)

            session.commit()

    def get_recent_repos(self, days: int = 7) -> List[Repository]:
        threshold_date = datetime.now() - timedelta(days=days)

        with self.get_session() as session:
            records = session.query(RepositoryRecord).filter(
                RepositoryRecord.last_seen_at >= threshold_date
            ).order_by(RepositoryRecord.last_seen_at.desc()).all()

            return [r.to_model() for r in records]

    def get_trending_repos(self, days: int = 30, limit: int = 10) -> List[Repository]:
        with self.get_session() as session:
            records = session.query(RepositoryRecord).order_by(
                RepositoryRecord.appearance_count.desc(),
                RepositoryRecord.stars.desc()
            ).limit(limit).all()

            return [r.to_model() for r in records]

    def cleanup_old_records(self, days: int = 90) -> int:
        threshold_date = datetime.now() - timedelta(days=days)

        with self.get_session() as session:
            count = session.query(RepositoryRecord).filter(
                RepositoryRecord.last_seen_at < threshold_date
            ).delete()
            session.commit()

            logger.info(f"Cleaned up {count} old repository records")
            return count

    def get_statistics(self) -> dict:
        with self.get_session() as session:
            total = session.query(RepositoryRecord).count()
            new_today = session.query(RepositoryRecord).filter(
                RepositoryRecord.first_seen_at >= datetime.now().replace(hour=0, minute=0, second=0)
            ).count()

            return {
                "total_repositories": total,
                "new_today": new_today
            }
