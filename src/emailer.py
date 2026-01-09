import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional

from src.config import Config
from src.models import RepositorySummary, TrendingReport

logger = logging.getLogger(__name__)


class EmailSender:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.email_config = self.config.email

    def send_report(self, report: TrendingReport) -> bool:
        """Send report via email using simplified HTML to avoid spam filters"""
        if not self.email_config.enabled:
            logger.info("Email sending is disabled")
            return False

        if not self.email_config.to_addresses:
            logger.warning("No recipient addresses configured. Skipping email sending.")
            return False

        # Generate simplified HTML report
        html_content = self._generate_html_report(report)
        text_content = self._generate_text_report(report)

        # Save HTML to file before sending
        self._save_html_report(html_content, report)

        subject = self._generate_subject(report)

        logger.info(f"Attempting to send email to {len(self.email_config.to_addresses)} recipients")
        logger.info(f"HTML content length: {len(html_content)} characters (simplified to avoid spam filters)")

        success = True
        for recipient in self.email_config.to_addresses:
            try:
                self._send_email(
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

    def _generate_subject(self, report: TrendingReport) -> str:
        date_str = report.generated_at.strftime("%Y-%m-%d")
        new_count = report.new_repos_count

        if self.email_config.subject:
            return self.email_config.subject

        return f"GitHub Trending - {date_str} - {new_count} new repositories"

    def _save_html_report(self, html_content: str, report: TrendingReport) -> None:
        """Save HTML report to file before sending email."""
        try:
            # Create reports directory
            reports_dir = Path("data/reports")
            reports_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename with timestamp
            timestamp = report.generated_at.strftime("%Y%m%d_%H%M%S")
            filename = reports_dir / f"trending_report_{timestamp}.html"

            # Save HTML content to file
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(html_content)

            logger.info(f"HTML report saved to: {filename}")

        except Exception as e:
            logger.error(f"Failed to save HTML report: {e}")

    def _generate_html_report(self, report: TrendingReport) -> str:
        """Generate simplified HTML report for email (avoid spam filters)"""
        repos_html = ""
        # Show ALL repositories (removed the 5 repo limit)
        all_repos = report.repositories

        for i, repo_summary in enumerate(all_repos, 1):
            repo = repo_summary.repository

            # Process summary - convert newlines to breaks and separators to HR tags
            # Remove extra <br> tags around HR to eliminate spacing
            summary_html = repo_summary.summary.replace('\n---\n', '<hr style="border: 0; border-top: 1px solid #e1e4e8; margin: 12px 0;">')
            summary_html = summary_html.replace('\n', '<br>')

            repos_html += f"""
            <div style="border: 1px solid #ddd; padding: 15px; margin-bottom: 15px; border-radius: 5px;">
                <div style="margin-bottom: 8px;">
                    <strong>#{i}</strong>
                    <a href="{repo.html_url}" style="color: #0366d6; text-decoration: none; margin-left: 10px;">
                        {repo.full_name}
                    </a>
                    <span style="background: #e1e4e8; padding: 2px 6px; border-radius: 3px; font-size: 11px; margin-left: 10px;">
                        {repo.language or 'Unknown'}
                    </span>
                </div>
                <div style="margin: 8px 0; color: #586069; line-height: 1.6;">{summary_html}</div>
            </div>
            """

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px;">
            <div style="background: #0366d6; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px;">
                <h1 style="margin: 0; font-size: 20px;">GitHub Trending Report</h1>
                <p style="margin: 10px 0 0 0; font-size: 14px;">
                    {report.generated_at.strftime('%Y-%m-%d %H:%M')} | Period: {report.period} | {report.language or 'All Languages'}
                </p>
            </div>

            <div style="display: flex; gap: 15px; margin-bottom: 20px;">
                <div style="flex: 1; background: #f6f8fa; padding: 15px; border-radius: 5px; text-align: center;">
                    <div style="font-size: 24px; font-weight: bold; color: #0366d6;">{report.total_repos_count}</div>
                    <div style="font-size: 12px; color: #586069;">Total Repos</div>
                </div>
                <div style="flex: 1; background: #f6f8fa; padding: 15px; border-radius: 5px; text-align: center;">
                    <div style="font-size: 24px; font-weight: bold; color: #0366d6;">{report.new_repos_count}</div>
                    <div style="font-size: 12px; color: #586069;">New Repos</div>
                </div>
            </div>

            {repos_html}

            <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e1e4e8; font-size: 12px; color: #666;">
                <p>Generated by GitHub Trending Agent</p>
                <p>Total repositories in this report: {len(report.repositories)}</p>
            </div>
        </body>
        </html>
        """

        return html

    def _generate_text_report(self, report: TrendingReport) -> str:
        lines = [
            f"GitHub Trending Report - {report.generated_at.strftime('%Y-%m-%d')}",
            f"Period: {report.period} | Language: {report.language or 'All'}",
            f"Total: {report.total_repos_count} | New: {report.new_repos_count}",
            "",
            "=" * 60,
            ""
        ]

        for i, repo_summary in enumerate(report.repositories, 1):
            repo = repo_summary.repository
            lines.extend([
                f"{i}. {repo.full_name}",
                f"   {repo_summary.summary}",
                f"   ⭐ {repo.stars} | 🍴 {repo.forks}",
                f"   Link: {repo.html_url}",
                ""
            ])

        lines.extend([
            "=" * 60,
            "Generated by GitHub Trending Agent"
        ])

        return "\n".join(lines)

    @staticmethod
    def _extract_email_address(from_address: str) -> str:
        """Extract pure email address from a formatted address like 'Name <email@domain.com>'."""
        if "<" in from_address and ">" in from_address:
            return from_address.split("<")[1].split(">")[0]
        return from_address

    def _send_email(
        self,
        to_addr: str,
        subject: str,
        html_content: str,
        text_content: str
    ) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.email_config.from_address
        msg["To"] = to_addr
        msg["List-Unsubscribe"] = "<>"

        part1 = MIMEText(text_content, "plain", _charset="utf-8")
        part2 = MIMEText(html_content, "html", _charset="utf-8")

        msg.attach(part1)
        msg.attach(part2)

        smtp_config = self.email_config.smtp

        logger.info(f"Connecting to SMTP server: {smtp_config.host}:{smtp_config.port}")
        logger.info(f"From address: {self.email_config.from_address}")
        logger.info(f"SMTP username: {smtp_config.username}")

        # Extract email address from from_address if it contains a name
        from_address = self._extract_email_address(self.email_config.from_address)
        logger.info(f"Using from address for MAIL FROM: {from_address}")

        # Use SMTP_SSL for port 465, otherwise use SMTP with optional STARTTLS
        if smtp_config.use_ssl or smtp_config.port == 465:
            logger.info("Using SMTP_SSL connection")
            with smtplib.SMTP_SSL(smtp_config.host, smtp_config.port, timeout=30) as server:
                server.login(smtp_config.username, smtp_config.password)
                server.send_message(msg)
                logger.info("Email sent via SMTP_SSL")
        else:
            logger.info("Using SMTP connection with STARTTLS")
            with smtplib.SMTP(smtp_config.host, smtp_config.port, timeout=30) as server:
                if smtp_config.use_tls:
                    server.starttls()
                server.login(smtp_config.username, smtp_config.password)
                server.send_message(msg)
                logger.info("Email sent via SMTP with STARTTLS")

    def test_connection(self) -> bool:
        try:
            smtp_config = self.email_config.smtp
            with smtplib.SMTP(smtp_config.host, smtp_config.port) as server:
                if smtp_config.use_tls:
                    server.starttls()
                server.login(smtp_config.username, smtp_config.password)
            return True
        except Exception as e:
            logger.error(f"SMTP connection test failed: {e}")
            return False

    def send_test_email(self, recipient: str) -> bool:
        if not self.email_config.enabled:
            return False

        test_report = TrendingReport(
            generated_at=datetime.now(timezone.utc),
            period="test",
            language="test",
            new_repos_count=0,
            total_repos_count=0,
            repositories=[]
        )

        html_content = """
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>GitHub Trending Agent - Test Email</h2>
            <p>This is a test email to verify your email configuration is working correctly.</p>
            <p>If you received this email, your settings are properly configured!</p>
        </body>
        </html>
        """

        text_content = "GitHub Trending Agent - Test Email\n\nThis is a test email to verify your email configuration is working correctly."

        try:
            self._send_email(
                to_addr=recipient,
                subject="GitHub Trending Agent - Test Email",
                html_content=html_content,
                text_content=text_content
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send test email: {e}")
            return False
