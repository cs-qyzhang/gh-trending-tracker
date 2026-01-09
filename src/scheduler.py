import logging
import signal
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import Config
from src.emailer import EmailSender
from src.fetcher import GitHubFetcher
from src.filter import RepositoryFilter
from src.logger_config import setup_logging
from src.models import TrendingReport

logger = logging.getLogger(__name__)

class Scheduler:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.scheduler_config = self.config.scheduler
        self._scheduler = None
        self._lock = threading.Lock()

    def start(self, run_immediately: bool = False) -> None:
        if not self.scheduler_config.enabled:
            logger.info("Scheduler is disabled")
            return

        self._scheduler = BlockingScheduler(
            timezone=self.scheduler_config.timezone
        )

        trigger = CronTrigger(
            hour=self.scheduler_config.time.split(":")[0],
            minute=self.scheduler_config.time.split(":")[1]
        )

        self._scheduler.add_job(
            self._run_task,
            trigger=trigger,
            id="github_trending_task",
            name="GitHub Trending Analysis",
            replace_existing=True
        )

        job = self._scheduler.get_job('github_trending_task')
        logger.info(f"Scheduler started. Job scheduled: {job}")

        if run_immediately:
            logger.info("Running task immediately...")
            self._run_task()

        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped by user")
            self.stop()

    def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    def _run_task(self) -> None:
        if not self._lock.acquire(blocking=False):
            logger.warning("Task already running, skipping...")
            return

        start_time = datetime.now()

        try:
            logger.info("Starting GitHub trending analysis task...")
            report = self._execute_pipeline()
            logger.info(f"Task completed in {(datetime.now() - start_time).total_seconds():.2f}s")
        except Exception as e:
            logger.error(f"Task failed: {e}", exc_info=True)
        finally:
            self._lock.release()

    def _execute_pipeline(self) -> TrendingReport:
        logger.info("Step 1: Fetching GitHub trending repositories...")
        fetcher = GitHubFetcher(self.config)
        repos = fetcher.fetch_trending_repos()

        logger.info(f"Step 2: Filtering new repositories from {len(repos)} trending repos...")
        repo_filter = RepositoryFilter(self.config)
        new_repos = repo_filter.filter_new_repos(repos)

        logger.info(f"Found {len(new_repos)} new repositories")

        if not new_repos:
            logger.info("No new repositories found, creating empty report")
            return TrendingReport(
                generated_at=datetime.now(timezone.utc),
                period=self.config.trending.period,
                language=self.config.trending.language,
                new_repos_count=0,
                total_repos_count=len(repos),
                repositories=[]
            )

        logger.info("Step 3: Enriching repositories with README...")
        enriched_repos = []
        for repo in new_repos:
            enriched_repo = fetcher.enrich_repository(repo)
            enriched_repos.append(enriched_repo)

        logger.info("Step 4: Saving to database...")
        repo_filter.save_repositories(enriched_repos)

        logger.info("Step 5: Generating summaries and sending email...")
        # Create report with repositories in original order (no ranking)
        from src.llm import LLMSummarizer
        from src.models import RepositorySummary

        llm_summarizer = LLMSummarizer(self.config)

        repository_summaries = []
        for repo in enriched_repos:
            summary = llm_summarizer.summarize_repository(repo)
            repo_summary = RepositorySummary(
                repository=repo,
                summary=summary
            )
            repository_summaries.append(repo_summary)

        report = TrendingReport(
            generated_at=datetime.now(timezone.utc),
            period=self.config.trending.period,
            language=self.config.trending.language,
            new_repos_count=len(enriched_repos),
            total_repos_count=len(repos),
            repositories=repository_summaries
        )

        emailer = EmailSender(self.config)
        emailer.send_report(report)

        return report

    def run_once(self) -> TrendingReport:
        return self._execute_pipeline()


class App:
    def __init__(self):
        self.config = None
        self.scheduler = None

    def setup_logging(self, level: int = logging.INFO) -> None:
        """Setup logging using the centralized logging configuration."""
        setup_logging(log_level=level)

    def load_config(self, config_path: str = "config.yaml") -> Config:
        from src.config import get_config
        self.config = get_config(config_path)
        return self.config

    def send_latest_report(self, config_path: str = "config.yaml", report_file: Optional[str] = None) -> bool:
        """Send the latest report via email with simplified HTML to avoid spam filters"""
        self.load_config(config_path)

        if not self.config.email.enabled:
            logger.error("Email is disabled in configuration")
            return False

        if not self.config.email.to_addresses:
            logger.error("No recipient addresses configured")
            return False

        from src.filter import RepositoryFilter
        from src.llm import LLMSummarizer
        from src.models import RepositorySummary

        # Load latest report data from database
        try:
            repo_filter = RepositoryFilter(self.config)
            llm_summarizer = LLMSummarizer(self.config)

            # Get recent repositories (last 3 days)
            recent_repos = repo_filter.get_recent_repos(days=3)

            if not recent_repos:
                logger.warning("No recent repositories found in database")
                return False

            logger.info(f"Found {len(recent_repos)} recent repositories")

            # Create RepositorySummary objects with AI summaries
            repository_summaries = []
            for repo in recent_repos:
                summary = llm_summarizer.summarize_repository(repo)
                repo_summary = RepositorySummary(
                    repository=repo,
                    summary=summary
                )
                repository_summaries.append(repo_summary)

            # Create a report
            report = TrendingReport(
                generated_at=datetime.now(timezone.utc),
                period="daily",
                language="",
                new_repos_count=len([r for r in recent_repos if r.appearance_count == 1]),
                total_repos_count=len(recent_repos),
                repositories=repository_summaries
            )

            # Generate simplified HTML
            email_sender = EmailSender(self.config)

            # Generate simplified HTML
            html_content = email_sender._generate_html_report(report)
            text_content = email_sender._generate_text_report(report)

            # Save HTML to file
            email_sender._save_html_report(html_content, report)

            # Send the email
            subject = self.config.email.subject or "GitHub Trending Report"

            success = True
            for recipient in self.config.email.to_addresses:
                try:
                    email_sender._send_email(
                        to_addr=recipient,
                        subject=subject,
                        html_content=html_content,
                        text_content=text_content
                    )
                    logger.info(f"Email sent successfully to {recipient}")
                except Exception as e:
                    logger.error(f"Failed to send email to {recipient}: {e}", exc_info=True)
                    success = False

            return success

        except Exception as e:
            logger.error(f"Failed to send report: {e}", exc_info=True)
            return False

    def run(self, run_once: bool = False, config_path: str = "config.yaml") -> None:
        self.setup_logging()
        self.load_config(config_path)

        logger.info("GitHub Trending Agent starting...")

        self.scheduler = Scheduler(self.config)

        def signal_handler(signum, frame):
            logger.info("Received shutdown signal")
            self.scheduler.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        if run_once:
            report = self.scheduler.run_once()
            logger.info(f"Report generated with {len(report.repositories)} repositories")
        else:
            self.scheduler.start(run_immediately=True)


def main():
    import argparse

    # Setup logging before anything else
    setup_logging(log_level=logging.INFO)

    parser = argparse.ArgumentParser(description="GitHub Trending Agent")
    parser.add_argument(
        "--scheduler",
        action="store_true",
        help="Run in scheduler mode (continuous execution with APScheduler)"
    )
    parser.add_argument(
        "--send-email",
        action="store_true",
        help="Send the latest report via email (skip fetching and ranking)"
    )
    parser.add_argument(
        "--email-file",
        type=str,
        help="Path to a specific HTML report file to send (use with --send-email)"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to configuration file"
    )

    args = parser.parse_args()

    try:
        app = App()

        # Handle send email mode
        if args.send_email:
            logger.info("Sending report via email...")
            success = app.send_latest_report(
                config_path=args.config,
                report_file=args.email_file
            )
            if success:
                logger.info("Email sent successfully")
                sys.exit(0)
            else:
                logger.error("Failed to send email")
                sys.exit(1)
        else:
            # Normal run mode (default: run once, use --scheduler for continuous mode)
            app.run(run_once=not args.scheduler, config_path=args.config)
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
