import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, model_validator

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class GitHubConfig(BaseModel):
    token: str = ""
    base_url: str = "https://api.github.com"
    timeout: int = 30


class TrendingConfig(BaseModel):
    period: str = "daily"
    language: str = ""
    limit: int = 50


class FilterConfig(BaseModel):
    days_threshold: int = 3


class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = 200
    temperature: float = 0.5
    summary_prompt: str = ""


class SMTPConfig(BaseModel):
    host: str = "smtp.gmail.com"
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    use_ssl: bool = False  # For port 465


class EmailConfig(BaseModel):
    enabled: bool = True
    smtp: SMTPConfig = SMTPConfig()
    from_address: str = ""
    to_addresses: List[str] = []
    subject: str = "Daily GitHub Trending - New Repositories"

    @model_validator(mode='after')
    def infer_from_address(self):
        """Infer from_address from smtp.username if from_address is empty"""
        if not self.from_address and self.smtp.username:
            self.from_address = f"GitHub Trending <{self.smtp.username}>"
        return self


class SchedulerConfig(BaseModel):
    enabled: bool = True
    time: str = "09:00"
    timezone: str = "Asia/Shanghai"


class Config(BaseModel):
    github: GitHubConfig = GitHubConfig()
    trending: TrendingConfig = TrendingConfig()
    filter: FilterConfig = FilterConfig()
    llm: LLMConfig = LLMConfig()
    email: EmailConfig = EmailConfig()
    scheduler: SchedulerConfig = SchedulerConfig()


def _replace_env_vars(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_spec = value[2:-1]  # Remove ${ and }

        # Check for default value syntax: KEY:-default_value or KEY:=default_value
        if ":-" in env_spec:
            env_key, default_value = env_spec.split(":-", 1)
            default_value = default_value.strip().strip('"').strip("'")
            return os.getenv(env_key, default_value)
        elif ":=" in env_spec:
            env_key, default_value = env_spec.split(":=", 1)
            default_value = default_value.strip().strip('"').strip("'")
            return os.getenv(env_key, default_value)
        else:
            # No default value
            return os.getenv(env_spec, "")
    elif isinstance(value, dict):
        return {k: _replace_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_replace_env_vars(item) for item in value]
    return value


def load_yaml_config(config_path: str) -> Dict[str, Any]:
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)

    if not config_data:
        return {}

    # Replace environment variables
    config_data = _replace_env_vars(config_data)

    # Map YAML field names to model field names for email config
    if 'email' in config_data and isinstance(config_data['email'], dict):
        # Map 'to' to 'to_addresses'
        if 'to' in config_data['email'] and 'to_addresses' not in config_data['email']:
            config_data['email']['to_addresses'] = config_data['email'].pop('to')
        # Map 'from' to 'from_address'
        if 'from' in config_data['email'] and 'from_address' not in config_data['email']:
            config_data['email']['from_address'] = config_data['email'].pop('from')

    return config_data


def get_config(config_path: Optional[str] = None) -> Config:
    if config_path is None:
        config_path = os.getenv('CONFIG_PATH', 'config.yaml')

    config_file = Path(config_path)
    if config_file.exists():
        config_data = load_yaml_config(str(config_file))
        return Config(**config_data)
    else:
        return Config()


def save_config(config: Config, config_path: str = 'config.yaml') -> None:
    config_dict = config.model_dump()
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config_dict, f, allow_unicode=True, default_flow_style=False)
