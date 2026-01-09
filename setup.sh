#!/bin/bash

# GitHub Trending Agent Setup Script

set -e

echo "🚀 GitHub Trending Agent Setup"
echo "=============================="

# Check if Python 3.8+ is installed
python_version=$(python3 --version 2>/dev/null | cut -d' ' -f2 || echo "")
if [[ -z "$python_version" ]]; then
    echo "❌ Python 3 is not installed. Please install Python 3.8+ first."
    exit 1
fi

echo "✅ Python $python_version found"

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p data logs

# Copy example config if config.yaml doesn't exist
if [[ ! -f config.yaml ]]; then
    echo "📝 Copying example configuration..."
    cp config.yaml.example config.yaml
    echo "⚠️  Please edit config.yaml with your settings before running!"
fi

echo "📋 Setup completed!"
echo ""
echo "Next steps:"
echo "1. Edit config.yaml with your settings"
echo "2. Create .env file from .env.example"
echo "3. Get your GitHub token: https://github.com/settings/tokens"
echo "4. Get your LLM API key: https://platform.openai.com/api-keys"
echo "5. Run: python -m src.main --run-once (to test)"
echo "6. Run: python -m src.main (to start scheduler)"
