"""Configuration system using Pydantic BaseSettings + YAML."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from ics_append.exceptions import ConfigError

logger = logging.getLogger(__name__)

MATCH_MONTH_PATTERN = re.compile(r"^\d{4}\.(0[1-9]|1[0-2])$")
CLIENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,20}$")


class ClientConfig(BaseModel):
    """Per-client file format overrides."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ref_column: str | None = None
    ref_header_row: Annotated[int | None, Field(ge=0, le=100)] = None
    dm_column: str | None = None
    dm_header_row: Annotated[int | None, Field(ge=0, le=100)] = None

    @field_validator("ref_column", "dm_column")
    @classmethod
    def column_name_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Column name must not be blank")
        return v.strip() if v else v

    @model_validator(mode="after")
    def column_requires_header_row(self) -> ClientConfig:
        if self.ref_column and self.ref_header_row is None:
            raise ValueError("ref_header_row required when ref_column is set")
        if self.dm_column and self.dm_header_row is None:
            raise ValueError("dm_header_row required when dm_column is set")
        return self


class Settings(BaseSettings):
    """Application configuration -- immutable after loading."""

    model_config = SettingsConfigDict(
        frozen=True,
        extra="forbid",
        yaml_file="config.yaml",
        env_prefix="ICS_APPEND_",
    )

    base_dir: Path
    ars_dir: Path | None = None
    output_dir: Path = Path("output/")
    match_month: str | None = None
    dry_run: bool = False
    overwrite: bool = True
    csv_copy: bool = False
    clients: dict[str, ClientConfig] = Field(default_factory=dict)
    default_ref_keywords: list[str] = Field(
        default_factory=lambda: ["referral", "ref", "ics_detailed"]
    )
    default_dm_keywords: list[str] = Field(
        default_factory=lambda: ["direct mail", "directmail", "new accounts"]
    )
    hash_min_length: int = 6
    match_rate_warn_threshold: float = 0.5

    @field_validator("base_dir", "ars_dir", "output_dir", mode="before")
    @classmethod
    def expand_paths(cls, v: str | Path | None) -> Path | None:
        if v is None:
            return v
        return Path(v).expanduser().resolve()

    @field_validator("match_month")
    @classmethod
    def validate_match_month_format(cls, v: str | None) -> str | None:
        if v is not None and not MATCH_MONTH_PATTERN.match(v):
            raise ValueError(f"match_month must be YYYY.MM format, got '{v}'")
        return v

    @field_validator("clients")
    @classmethod
    def normalize_client_keys(cls, v: dict[str, ClientConfig]) -> dict[str, ClientConfig]:
        normalized: dict[str, ClientConfig] = {}
        for key, config in v.items():
            clean = key.strip()
            if not clean:
                raise ValueError("Client key must not be empty")
            if clean in normalized:
                raise ValueError(f"Duplicate client key: '{clean}'")
            normalized[clean] = config
        return normalized

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Priority: init kwargs (CLI) > env vars > YAML file."""
        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(settings_cls),
        )

    def get_client(self, client_id: str) -> ClientConfig:
        """Return client-specific config, defaulting to empty config."""
        return self.clients.get(client_id.strip(), ClientConfig())

    @classmethod
    def from_args(cls, base_dir: Path, **kwargs) -> Settings:
        """Create settings directly from arguments (no YAML needed)."""
        try:
            return cls(base_dir=base_dir, **kwargs)
        except Exception as e:
            raise ConfigError(f"Configuration error: {e}") from e
