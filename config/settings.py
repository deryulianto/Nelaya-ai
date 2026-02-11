from pydantic import BaseSettings
class Settings(BaseSettings):
    app_name: str = "NELAYA-AI LAB"
    debug: bool = True
    class Config:
        env_file = "config/.env"
settings = Settings()
