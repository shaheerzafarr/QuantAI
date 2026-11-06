"""Database Engine & Session Management for QuantAI."""

import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from quantai.config.settings import get_config
from quantai.storage.models import Base


class DatabaseManager:
    _instance = None

    def __init__(self, db_url: str = None):
        config = get_config()
        self.url = db_url or config.storage.database_url

        # Ensure directory exists for sqlite if needed
        if self.url.startswith("sqlite:///"):
            filepath = self.url.replace("sqlite:///", "")
            os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
            self.engine = create_engine(
                self.url,
                connect_args={"check_same_thread": False},
                pool_pre_ping=True,
            )
        else:
            self.engine = create_engine(
                self.url,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
            )

        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, expire_on_commit=False, bind=self.engine
        )

    def init_db(self):
        """Create all tables in the database."""
        Base.metadata.create_all(bind=self.engine)

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Provide a transactional scope around a series of operations."""
        session: Session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def get_db_manager() -> DatabaseManager:
    if DatabaseManager._instance is None:
        DatabaseManager._instance = DatabaseManager()
    return DatabaseManager._instance


def init_database():
    mgr = get_db_manager()
    mgr.init_db()
