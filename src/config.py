from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # vLLM
    vllm_base_url: str = "http://localhost:8000/v1"
    vllm_model: str = "openai/gpt-oss-20b"

    # Database
    db_path: str = "data/jobs.db"

    # API server
    api_host: str = "0.0.0.0"
    api_port: int = 8080

    # Naukri credentials
    naukri_email: str = ""
    naukri_password: str = ""

    # Scraping
    scrape_concurrency: int = 3
    request_timeout: int = 30

    @property
    def db_url(self) -> str:
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"

    @property
    def profile_path(self) -> Path:
        return Path("profile/profile.yaml")


settings = Settings()
