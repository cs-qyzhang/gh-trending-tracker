# GitHub Trending Agent

A smart agent that tracks GitHub trending repositories, filters new repositories, summarizes them using LLM, ranks by novelty and importance, and sends email reports.

## Features

- **Automated Tracking**: Fetches GitHub trending repositories daily
- **Smart Filtering**: Identifies genuinely new repositories (not seen in the last X days)
- **LLM Summarization**: Uses AI to generate one-sentence summaries of each repository
- **Intelligent Ranking**: Ranks repositories by novelty (40%), importance (40%), and trending score (20%)
- **Email Reports**: Sends beautiful HTML email reports with rankings and summaries

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/gh-trending.git
cd gh-trending

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Copy the example configuration and edit it:

```bash
cp config.yaml.example config.yaml
```

### Configuration Options

```yaml
# GitHub API Configuration
github:
  token: ${GITHUB_TOKEN}  # Your GitHub Personal Access Token
  base_url: "https://api.github.com"
  timeout: 30

# Trending Fetch Settings
trending:
  period: daily  # daily, weekly, monthly
  language: ""    # Empty for all languages, e.g., "python"
  limit: 50       # Number of repos to fetch

# Filter Settings
filter:
  days_threshold: 3  # Filter repos that appeared in the last X days

# LLM Configuration
llm:
  provider: "openai"  # openai, anthropic
  model: "gpt-4o-mini"
  api_key: ${LLM_API_KEY}

# Ranking Configuration
ranking:
  novelty_weight: 0.4
  importance_weight: 0.4
  trending_weight: 0.2

# Email Configuration
email:
  enabled: true
  smtp:
    host: "smtp.gmail.com"
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
  from: "GitHub Trending <your-email@gmail.com>"
  to:
    - "recipient@example.com"

# Scheduler Configuration
scheduler:
  enabled: true
  time: "09:00"
  timezone: "Asia/Shanghai"
```

## Environment Variables

Create a `.env` file or set environment variables:

```bash
export GITHUB_TOKEN="your-github-token"
export LLM_API_KEY="your-openai-api-key"
export SMTP_USERNAME="your-email@gmail.com"
export SMTP_PASSWORD="your-app-password"
```

## Usage

### Run Once

```bash
python -m src.main --run-once
```

### Run as Scheduler

```bash
python -m src.main
```

### Run Tests

```bash
pytest tests/ -v
```

## Project Structure

```
gh-trending/
├── src/
│   ├── __init__.py
│   ├── config.py          # Configuration management
│   ├── fetcher.py         # GitHub API client
│   ├── filter.py          # Repository filtering and persistence
│   ├── llm.py            # LLM integration for summaries
│   ├── ranker.py         # Repository ranking engine
│   ├── emailer.py        # Email sending
│   ├── scheduler.py      # APScheduler integration
│   ├── models.py         # Pydantic models
│   └── main.py           # Entry point
├── tests/
│   └── test_core.py      # Unit tests
├── config.yaml           # Configuration file
├── requirements.txt      # Python dependencies
└── README.md
```

## Scoring System

Repositories are ranked using a weighted scoring system:

- **Novelty (40%)**: Based on repository age and first appearance
- **Importance (40%)**: Based on stars, forks, and community engagement
- **Trending (20%)**: Based on current star velocity and activity

## License

MIT
