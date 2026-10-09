import os


class Settings:
    database_url = os.environ.get(
        "DATABASE_URL", "postgresql://library:changeme@localhost:5432/georgii_valiaikin"
    )
    db_schema = os.environ.get("DB_SCHEMA", "georgii_valiaikin")
    db_pool_size = int(os.environ.get("DB_POOL_SIZE", "10"))
    secret_key = os.environ.get("SECRET_KEY", "changeme")


settings = Settings()
