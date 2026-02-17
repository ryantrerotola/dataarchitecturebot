"""Tests for configuration loading."""

from __future__ import annotations

import os
import tempfile

import pytest

from snowflake_architect.config import load_config


def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "test-account")
    monkeypatch.setenv("SNOWFLAKE_USER", "test-user")
    monkeypatch.setenv("SNOWFLAKE_PASSWORD", "secret")
    monkeypatch.setenv("SNOWFLAKE_ROLE", "ANALYST")

    config = load_config()

    assert config.connection.account == "test-account"
    assert config.connection.user == "test-user"
    assert config.connection.password == "secret"
    assert config.connection.role == "ANALYST"


def test_load_config_from_yaml(monkeypatch, tmp_path):
    # Clear any env vars
    for key in ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD", "SNOWFLAKE_ROLE"]:
        monkeypatch.delenv(key, raising=False)

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
connection:
  account: yaml-account
  user: yaml-user
  password: yaml-pass
  role: SYSADMIN

scope:
  databases:
    - PROD_DB
    - DEV_DB

goals:
  - reduce_storage
  - simplify

stale_threshold_days: 60
"""
    )

    config = load_config(str(config_file))

    assert config.connection.account == "yaml-account"
    assert config.connection.user == "yaml-user"
    assert config.scope.databases == ["PROD_DB", "DEV_DB"]
    assert config.goals == ["reduce_storage", "simplify"]
    assert config.stale_threshold_days == 60


def test_env_vars_override_yaml(monkeypatch, tmp_path):
    monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "env-account")
    monkeypatch.setenv("SNOWFLAKE_USER", "env-user")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
connection:
  account: yaml-account
  user: yaml-user
"""
    )

    config = load_config(str(config_file))

    # Env vars should win
    assert config.connection.account == "env-account"
    assert config.connection.user == "env-user"


def test_missing_credentials_raises(monkeypatch):
    for key in ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD"]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValueError, match="account and user are required"):
        load_config()


def test_connect_params():
    from snowflake_architect.config import SnowflakeConnection

    conn = SnowflakeConnection(
        account="acct",
        user="usr",
        password="pw",
        role="ROLE",
        warehouse="WH",
    )
    params = conn.to_connect_params()
    assert params == {
        "account": "acct",
        "user": "usr",
        "password": "pw",
        "role": "ROLE",
        "warehouse": "WH",
    }
