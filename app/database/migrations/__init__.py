"""Database migrations package."""

from app.database.migrations.runner import run_migrations

__all__ = ["run_migrations"]
