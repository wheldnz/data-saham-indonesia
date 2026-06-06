import os
from typing import List, Union

from pydantic import AnyHttpUrl, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "AlphaHunter IDX"
    
    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # Database setup
    # For MVP we are using SQLite. Later this can be changed to PostgreSQL via env var.
    # The default location will be in the backend directory
    base_dir: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_path: str = os.path.join(base_dir, "alphahunter.db")
    SQLALCHEMY_DATABASE_URI: str = f"sqlite:///{db_path}"

    class Config:
        case_sensitive = True
        env_file = ".env"


settings = Settings()
