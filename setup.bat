@echo off
REM GitHub Trending Agent Setup Script for Windows

echo 🚀 GitHub Trending Agent Setup
echo ==============================

REM Check if Python 3.8+ is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python is not installed. Please install Python 3.8+ first.
    exit /b 1
)

echo ✅ Python found

REM Create virtual environment
echo 📦 Creating virtual environment...
python -m venv venv

REM Activate virtual environment
echo 🔧 Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo 📥 Installing dependencies...
pip install -r requirements.txt

REM Create necessary directories
echo 📁 Creating directories...
if not exist data mkdir data
if not exist logs mkdir logs

REM Copy example config if config.yaml doesn't exist
if not exist config.yaml (
    echo 📝 Copying example configuration...
    copy config.yaml.example config.yaml
    echo ⚠️  Please edit config.yaml with your settings before running!
)

REM Create .env.example
echo # GitHub Token (required) - Create at https://github.com/settings/tokens > .env.example
echo # Scopes needed: read:user, read:org, public_repo >> .env.example
echo GITHUB_TOKEN=ghp_your_github_token_here >> .env.example
echo. >> .env.example
echo # LLM API Key (required) - OpenAI or Anthropic >> .env.example
echo LLM_API_KEY=your_llm_api_key_here >> .env.example
echo. >> .env.example
echo # SMTP Email Configuration (optional but recommended) >> .env.example
echo SMTP_USERNAME=your_email@gmail.com >> .env.example
echo SMTP_PASSWORD=your_app_password_here >> .env.example

echo 📋 Setup completed!
echo.
echo Next steps:
echo 1. Edit config.yaml with your settings
echo 2. Create .env file from .env.example
echo 3. Get your GitHub token: https://github.com/settings/tokens
echo 4. Get your LLM API key: https://platform.openai.com/api-keys
echo 5. Run: python -m src.main --run-once (to test)
echo 6. Run: python -m src.main (to start scheduler)

pause
