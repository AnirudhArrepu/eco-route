import json
from functools import lru_cache

import boto3
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import settings

class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=1)
def get_database_url():
    if not settings.database_secret_arn:
        return settings.database_url

    response = boto3.client("secretsmanager", region_name=settings.aws_region).get_secret_value(
        SecretId=settings.database_secret_arn
    )
    secret = json.loads(response["SecretString"])
    host = secret.get("host") or settings.database_host
    if not host:
        raise ValueError("DATABASE_HOST is required when the database secret omits its host")
    return URL.create(
        "postgresql+psycopg",
        username=secret["username"],
        password=secret["password"],
        host=host,
        port=int(settings.database_port or secret.get("port", 5432)),
        database=secret.get("dbname") or "ecoroute",
    )


database_url = get_database_url()
kwargs = {"check_same_thread": False} if str(database_url).startswith("sqlite") else {}
engine = create_engine(database_url, pool_pre_ping=True, connect_args=kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
