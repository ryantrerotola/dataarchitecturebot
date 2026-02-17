"""Configuration management - supports both env vars and YAML config files."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SnowflakeConnection:
    account: str
    user: str
    password: str | None = None
    private_key_path: str | None = None
    role: str | None = None
    warehouse: str | None = None
    database: str | None = None
    authenticator: str | None = None

    def to_connect_params(self) -> dict:
        params = {"account": self.account, "user": self.user}
        if self.password:
            params["password"] = self.password
        if self.private_key_path:
            params["private_key_file_path"] = self.private_key_path
        if self.role:
            params["role"] = self.role
        if self.warehouse:
            params["warehouse"] = self.warehouse
        if self.database:
            params["database"] = self.database
        if self.authenticator:
            params["authenticator"] = self.authenticator
        return params


@dataclass
class AnalysisScope:
    """Which databases/schemas to analyze. Empty lists mean 'all accessible'."""

    databases: list[str] = field(default_factory=list)
    exclude_databases: list[str] = field(
        default_factory=lambda: ["SNOWFLAKE", "SNOWFLAKE_SAMPLE_DATA"]
    )
    schemas: list[str] = field(default_factory=list)
    exclude_schemas: list[str] = field(default_factory=lambda: ["INFORMATION_SCHEMA"])


@dataclass
class Config:
    connection: SnowflakeConnection
    scope: AnalysisScope = field(default_factory=AnalysisScope)
    goals: list[str] = field(default_factory=list)
    stale_threshold_days: int = 90
    low_usage_threshold_days: int = 30
    output_dir: str = "./reports"


def load_config(config_path: str | None = None) -> Config:
    """Load config from YAML file with env var overrides.

    Priority: env vars > config file > defaults.
    """
    file_cfg: dict = {}
    if config_path:
        path = Path(config_path)
        if path.exists():
            with open(path) as f:
                file_cfg = yaml.safe_load(f) or {}

    conn_cfg = file_cfg.get("connection", {})

    connection = SnowflakeConnection(
        account=os.environ.get("SNOWFLAKE_ACCOUNT", conn_cfg.get("account", "")),
        user=os.environ.get("SNOWFLAKE_USER", conn_cfg.get("user", "")),
        password=os.environ.get("SNOWFLAKE_PASSWORD", conn_cfg.get("password")),
        private_key_path=os.environ.get(
            "SNOWFLAKE_PRIVATE_KEY_PATH", conn_cfg.get("private_key_path")
        ),
        role=os.environ.get("SNOWFLAKE_ROLE", conn_cfg.get("role")),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", conn_cfg.get("warehouse")),
        database=os.environ.get("SNOWFLAKE_DATABASE", conn_cfg.get("database")),
        authenticator=os.environ.get("SNOWFLAKE_AUTHENTICATOR", conn_cfg.get("authenticator")),
    )

    if not connection.account or not connection.user:
        raise ValueError(
            "Snowflake account and user are required. "
            "Set SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER env vars or provide a config file."
        )

    scope_cfg = file_cfg.get("scope", {})
    scope = AnalysisScope(
        databases=scope_cfg.get("databases", []),
        exclude_databases=scope_cfg.get("exclude_databases", ["SNOWFLAKE", "SNOWFLAKE_SAMPLE_DATA"]),
        schemas=scope_cfg.get("schemas", []),
        exclude_schemas=scope_cfg.get("exclude_schemas", ["INFORMATION_SCHEMA"]),
    )

    return Config(
        connection=connection,
        scope=scope,
        goals=file_cfg.get("goals", []),
        stale_threshold_days=file_cfg.get("stale_threshold_days", 90),
        low_usage_threshold_days=file_cfg.get("low_usage_threshold_days", 30),
        output_dir=file_cfg.get("output_dir", "./reports"),
    )
