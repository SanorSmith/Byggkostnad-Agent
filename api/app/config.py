"""Settings loaded from the environment.

Model names and the embedding dimension are pinned here. Changing the
embedding model means re-embedding every stored chunk: vectors from two
models live in different spaces and cosine search across them silently
returns noise.
"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Embedding models we know the output dimension of. A model/dimension pair
# that disagrees with this table fails at startup instead of at query time.
KNOWN_EMBEDDING_DIMS: dict[str, int] = {
    "voyage-3": 1024,
    "voyage-3-large": 1024,
    "text-embedding-3-small": 1536,
}

DEFAULT_SCB_BASE_URL = "https://api.scb.se/OV0104/v1/doris/sv/ssd/START/PR/PR0502/PR0502A"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"
    anthropic_effort: str = "medium"
    judge_model: str = "claude-haiku-4-5"

    embedding_provider: str = "voyage"
    embedding_model: str = "voyage-3"
    embedding_dim: int = 1024
    voyage_api_key: str = ""

    scb_base_url: str = DEFAULT_SCB_BASE_URL

    cors_origins: str = "http://localhost:3000,https://byggkostnad-agent.vercel.app"
    cors_origin_regex: str = r"https://byggkostnad-agent(-[a-z0-9-]+)?\.vercel\.app"
    ask_rate_limit_per_minute: int = 10

    @model_validator(mode="after")
    def _check_embedding_pin(self) -> "Settings":
        if self.anthropic_model == "":
            self.anthropic_model = "claude-opus-5"
        known = KNOWN_EMBEDDING_DIMS.get(self.embedding_model)
        if known is not None and known != self.embedding_dim:
            raise ValueError(
                f"EMBEDDING_DIM={self.embedding_dim} does not match {self.embedding_model} "
                f"({known}). Change both together and re-embed."
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
