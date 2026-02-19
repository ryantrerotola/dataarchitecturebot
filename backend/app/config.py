from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Snowflake
    snowflake_account: str = ""
    snowflake_user: str = ""
    snowflake_password: str = ""
    snowflake_role: str = "SYSADMIN"
    snowflake_warehouse: str = "COMPUTE_WH"
    snowflake_authenticator: str = ""

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Alation
    alation_datasource_id: int = 1

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
