# Project Structure

```
gh-trending-tracker/
├── src/
│   ├── __init__.py              # Module exports
│   ├── config.py                # Configuration management (Pydantic models)
│   ├── emailer.py               # Email sender with HTML template generation
│   ├── fetcher.py               # GitHub API client (for enrichment)
│   ├── filter.py                # Repository filtering and persistence (SQLite)
│   ├── llm.py                   # LLM integration (OpenAI/Anthropic-compatible)
│   ├── logger_config.py         # Centralized logging configuration
│   ├── main.py                  # Module initialization
│   ├── models.py                # Pydantic data models
│   ├── scheduler.py             # Main application entry point and scheduler
│   └── trending_scraper.py      # Web scraper for GitHub trending page
├── tests/
│   ├── test_core.py            # Core functionality unit tests
│   └── test_trending_scraper.py # Scraper unit tests
├── data/                       # SQLite database directory
│   └── .gitkeep
├── logs/                       # Log files directory
│   └── .gitkeep
├── venv/                       # Python virtual environment (not in git)
├── .git/                       # Git repository (not in tree)
├── config.yaml                 # Application configuration file
├── requirements.txt            # Python dependencies
├── README.md                   # Project documentation
├── PROJECT_STRUCTURE.md        # This file
└── CLAUDE.md                   # Project instructions for Claude Code
```

## Module Descriptions

### Core Modules

- **config.py**: Configuration management using Pydantic models. Loads from `config.yaml` and supports environment variable substitution.

- **models.py**: Pydantic data models for type safety:
  - `Repository`: GitHub repository data
  - `TrendingReport`: Report containing multiple repositories
  - `RepositorySummary`: Repository with AI-generated summary

### Data Collection

- **trending_scraper.py**: Web scraper for GitHub trending page
  - Uses BeautifulSoup4 for HTML parsing
  - Retry mechanism with exponential backoff
  - Supports daily/weekly/monthly trending
  - Language-specific trending support
  - Concurrent API enrichment with thread pool

- **fetcher.py**: GitHub API client for additional repository data
  - Fetches README content
  - Gets detailed repository information
  - Requires GitHub token (optional)

### Data Processing

- **filter.py**: Repository filtering and persistence
  - SQLite database for tracking seen repositories
  - Identifies new repositories based on appearance history
  - Supports configurable days threshold

- **llm.py**: LLM integration for summarization
  - Supports OpenAI API
  - Supports Anthropic API
  - Supports custom endpoints (e.g., GLM-4)
  - Customizable prompt templates

### Output

- **emailer.py**: Email report generation and sending
  - HTML template generation
  - SMTP with SSL/TLS support
  - Simplified HTML to avoid spam filters
  - Multiple recipient support

### Application

- **scheduler.py**: Main application and scheduler
  - APScheduler integration for automated runs
  - Signal handling for graceful shutdown
  - Command-line interface
  - Pipeline orchestration

### Infrastructure

- **logger_config.py**: Centralized logging configuration
  - Rotating file handler (10MB, 5 backups)
  - Console output
  - Daily log files
  - UTF-8 encoding

## Data Flow

1. **trending_scraper.py** scrapes GitHub trending page
2. **fetcher.py** enriches data with GitHub API (optional)
3. **filter.py** identifies new repositories using SQLite database
4. **llm.py** generates summaries for new repositories
5. **emailer.py** sends HTML email report
6. **scheduler.py** orchestrates the pipeline

## Dependencies

Key dependencies:
- `pydantic`: Data validation and settings management
- `requests`: HTTP client for web scraping
- `beautifulsoup4`: HTML parsing
- `apscheduler`: Task scheduling
- `langchain-openai`: LLM integration (OpenAI)
- `anthropic`: LLM integration (Anthropic)
- `sqlalchemy`: Database ORM
- `pyyaml`: Configuration file parsing
- `python-dotenv`: Environment variable management