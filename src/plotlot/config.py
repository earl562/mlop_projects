"""PlotLot configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    geocodio_api_key: str = ""
    database_url: str = "postgresql+asyncpg://plotlot:plotlot@localhost:5432/plotlot"
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    hf_token: str = ""
    mlflow_tracking_uri: str = "http://localhost:5000"
    mlflow_experiment_name: str = "plotlot-rag"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
