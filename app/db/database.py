from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker,declarative_base

from app.config import settings


connect_args = {"check_same_thread":False} if settings.DATABASE_URL.startswith("sqlite") else{}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args
    )

Sessionlocal = sessionmaker(
    autoflush=False,
    autocommit=False,
    bind=engine
)

Base = declarative_base()

def get_db():
    db = Sessionlocal()
    try:
        yield db
    finally:
        db.close
