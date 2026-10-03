"""MySQL database connection management with connection pooling."""

import logging
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional
import mysql.connector
from mysql.connector import Error as MySQLError
from mysql.connector.pooling import MySQLConnectionPool, PooledMySQLConnection

from app.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages MySQL connection pooling and lifecycle."""

    _instance: Optional["DatabaseManager"] = None
    _pool: Optional[MySQLConnectionPool] = None

    def __new__(cls, settings: Optional[Settings] = None) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, settings: Optional[Settings] = None) -> None:
        if getattr(self, "_initialized", False):
            return
        try:
            self.settings: Settings = settings or get_settings()
            self._pool = None
            self._initialized = True
        except Exception as exc:
            logger.exception("Failed initializing DatabaseManager configuration: %s", exc)
            raise

    def initialize_pool(self, create_db_if_missing: bool = True) -> MySQLConnectionPool:
        """Initialize the connection pool, creating the target database first if requested."""
        if self._pool is not None:
            return self._pool

        try:
            if create_db_if_missing:
                self.create_database_if_not_exists()

            pool_config = self.settings.get_mysql_config(include_database=True)
            logger.info(
                "Initializing MySQL connection pool '%s' (size: %d) at %s:%s",
                self.settings.MYSQL_POOL_NAME,
                self.settings.MYSQL_POOL_SIZE,
                self.settings.MYSQL_HOST,
                self.settings.MYSQL_PORT,
            )
            self._pool = MySQLConnectionPool(
                pool_name=self.settings.MYSQL_POOL_NAME,
                pool_size=self.settings.MYSQL_POOL_SIZE,
                pool_reset_session=True,
                **pool_config,
            )
            logger.info("MySQL connection pool successfully initialized.")
            return self._pool
        except MySQLError as exc:
            logger.exception("Failed to initialize MySQL connection pool (MySQLError): %s", exc)
            raise
        except Exception as exc:
            logger.exception("Unexpected error initializing MySQL connection pool: %s", exc)
            raise

    def create_database_if_not_exists(self) -> None:
        """Connect to MySQL without a database selected to create the database if missing."""
        admin_config = self.settings.get_mysql_config(include_database=False)
        db_name = self.settings.MYSQL_DATABASE
        try:
            logger.info("Verifying MySQL database '%s' exists...", db_name)
            conn = mysql.connector.connect(**admin_config)
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
                    )
                    conn.commit()
                    logger.info("Database '%s' is verified/created.", db_name)
            finally:
                conn.close()
        except MySQLError as exc:
            logger.warning("Could not auto-create database '%s': %s", db_name, exc)
        except Exception as exc:
            logger.exception("Unexpected exception while attempting to create database '%s': %s", db_name, exc)

    @contextmanager
    def get_connection(self) -> Generator[PooledMySQLConnection, None, None]:
        """Context manager yielding a connection from the pool.

        The connection is automatically returned to the pool upon exit.
        """
        if self._pool is None:
            self.initialize_pool()

        connection = None
        try:
            connection = self._pool.get_connection()
            yield connection
        except MySQLError as exc:
            logger.exception("Error retrieving MySQL connection from pool: %s", exc)
            raise
        except Exception as exc:
            logger.exception("Unexpected error getting database connection: %s", exc)
            raise
        finally:
            if connection is not None:
                try:
                    if connection.is_connected():
                        connection.close()
                except Exception as close_exc:
                    logger.exception("Error closing MySQL connection: %s", close_exc)

    @contextmanager
    def get_cursor(
        self, dictionary: bool = True, autocommit: bool = False
    ) -> Generator[tuple[mysql.connector.cursor.MySQLCursor, PooledMySQLConnection], None, None]:
        """Context manager providing a cursor and connection with automatic transaction handling."""
        with self.get_connection() as conn:
            try:
                conn.autocommit = autocommit
                cursor = conn.cursor(dictionary=dictionary)
            except Exception as exc:
                logger.exception("Failed to create MySQL cursor: %s", exc)
                raise

            try:
                yield cursor, conn
                if not autocommit:
                    conn.commit()
            except Exception as exc:
                if not autocommit:
                    try:
                        conn.rollback()
                        logger.warning("Transaction rolled back due to error: %s", exc)
                    except MySQLError as rb_err:
                        logger.exception("Failed to rollback transaction: %s", rb_err)
                logger.exception("Exception occurred during cursor operation: %s", exc)
                raise
            finally:
                try:
                    cursor.close()
                except Exception as close_exc:
                    logger.exception("Error closing database cursor: %s", close_exc)

    def check_health(self) -> Dict[str, Any]:
        """Check connection health and return diagnostic status dictionary."""
        result: Dict[str, Any] = {
            "status": "unhealthy",
            "host": self.settings.MYSQL_HOST,
            "port": self.settings.MYSQL_PORT,
            "database": self.settings.MYSQL_DATABASE,
            "user": self.settings.MYSQL_USER,
            "server_version": None,
            "pool_initialized": self._pool is not None,
            "error": None,
        }

        try:
            config = self.settings.get_mysql_config(include_database=True)
            conn = mysql.connector.connect(**config)
            try:
                result["server_version"] = getattr(conn, "server_info", None) or conn.get_server_info()
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1 AS ping, CURRENT_TIMESTAMP() AS server_time;")
                    row = cursor.fetchone()
                    result["ping"] = row[0] if row else None
                    result["server_time"] = str(row[1]) if row and len(row) > 1 else None
                result["status"] = "healthy"
                result["error"] = None
            finally:
                conn.close()
        except MySQLError as exc:
            result["status"] = "unhealthy"
            result["error"] = f"[{exc.errno}] {exc.msg}"
            logger.warning("MySQL check_health reported MySQLError: %s", exc)
        except Exception as exc:
            result["status"] = "unhealthy"
            result["error"] = str(exc)
            logger.exception("Unexpected exception in database check_health: %s", exc)

        return result

    def close_pool(self) -> None:
        """Reset the connection pool."""
        try:
            self._pool = None
            logger.info("MySQL connection pool closed.")
        except Exception as exc:
            logger.exception("Exception while closing MySQL connection pool: %s", exc)


# Singleton helper function
def get_db_manager(settings: Optional[Settings] = None) -> DatabaseManager:
    """Return the global DatabaseManager instance."""
    return DatabaseManager(settings)
