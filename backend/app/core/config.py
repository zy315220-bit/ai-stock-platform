from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    use_demo_data: bool = False
    frontend_origin: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()