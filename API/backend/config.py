"""
Arquivo de configuracao do projeto Copilot Medico.
Carrega chaves e parametros do backend por variaveis de ambiente.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ENV_PATH = Path(__file__).with_name(".env")
API_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    db_url: str = "sqlite:///app.db"
    app_title: str = "Copilot M\u00e9dico"
    gemini_api_key: str = ""

    auth_secret_key: str = ""
    auth_token_expiration_minutes: int = 60
    auth_users_db_file: str = str(Path(__file__).with_name("users_db.json"))
    auth_bootstrap_email: str = ""
    auth_bootstrap_password: str = ""
    auth_bootstrap_name: str = "Administrador"
    auth_bootstrap_profiles: str = "administrador"

    # Use "*" em desenvolvimento; em producao prefira lista separada por virgulas.
    cors_origins: str = "*"

    model_config = SettingsConfigDict(
        env_file=(str(API_ENV_PATH), str(BACKEND_ENV_PATH)),
        extra="ignore",
    )


settings = Settings()
