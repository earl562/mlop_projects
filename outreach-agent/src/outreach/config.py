from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Gmail SMTP — email sending via App Password (no OAuth, no Google Cloud)
    # Requires 2-Step Verification: https://myaccount.google.com/security
    # Then generate App Password:   https://myaccount.google.com/apppasswords
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    # The From: header address (usually same as smtp_user for Gmail)
    smtp_from_email: str = ""

    # Hunter.io — email finder (free: 25 searches/month)
    hunter_api_key: str = ""

    # Twitter API v2 (Basic tier required for DMs to non-followers)
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_secret: str = ""
    twitter_bearer_token: str = ""

    # Tavily Search API (free: 1,000 searches/month — https://tavily.com)
    tavily_api_key: str = ""

    # Eventbrite (free tier, event discovery)
    eventbrite_api_key: str = ""

    # Database
    database_url: str = "sqlite+aiosqlite:///./outreach.db"

    # PlotLot context (used to personalize pitches)
    plotlot_demo_url: str = "https://plotlot.app"
    plotlot_counties: str = "Miami-Dade, Broward, Palm Beach, Monroe"

    # Outreach settings
    max_emails_per_run: int = 300
    # Path to the demo video to attach to outgoing emails
    outreach_attachment_path: str = ""


settings = Settings()
