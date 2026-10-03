"""Database migration runner to execute schema DDL scripts with comprehensive error logging."""

import logging
from pathlib import Path
from typing import Dict, List, Tuple
import mysql.connector

from app.database.connection import DatabaseManager, get_db_manager

logger = logging.getLogger(__name__)

EXPECTED_TABLES = [
    "companies",
    "documents",
    "financial_data",
    "risk_factors",
    "document_chunks",
    "processing_logs",
]


def parse_sql_statements(sql_script: str) -> List[str]:
    """Parse a SQL script into individual executable statements."""
    try:
        statements: List[str] = []
        current: List[str] = []

        for line in sql_script.splitlines():
            trimmed = line.strip()
            # Skip full-line comments and empty lines
            if not trimmed or trimmed.startswith("--") or trimmed.startswith("#"):
                continue

            current.append(line)
            if trimmed.endswith(";"):
                statement = "\n".join(current).strip()
                if statement:
                    statements.append(statement)
                current = []

        if current:
            trailing = "\n".join(current).strip()
            if trailing:
                statements.append(trailing)

        return statements
    except Exception as exc:
        logger.exception("Failed parsing SQL statements from script: %s", exc)
        raise


def run_migrations(
    db_manager: DatabaseManager = None, schema_file: Path = None
) -> Tuple[bool, Dict[str, str]]:
    """Execute initial schema migration and verify table creation.

    Connects first without requiring target database to exist, executes
    CREATE DATABASE and all DDL statements, then verifies table creation.

    Returns:
        Tuple[bool, Dict[str, str]]: (success, table_status_map)
    """
    try:
        if db_manager is None:
            db_manager = get_db_manager()

        if schema_file is None:
            schema_file = Path(__file__).parent / "schema.sql"

        if not schema_file.exists():
            error_msg = f"Schema file not found at: {schema_file}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        logger.info("Starting schema migration from: %s", schema_file)

        # 1. Read and parse SQL script
        try:
            with open(schema_file, "r", encoding="utf-8") as f:
                sql_content = f.read()
        except Exception as read_exc:
            logger.exception("Failed reading schema file '%s': %s", schema_file, read_exc)
            raise

        statements = parse_sql_statements(sql_content)
        logger.info("Found %d DDL statement(s) to execute.", len(statements))

        # 2. Execute statements using administrative connection (no pre-selected DB required)
        admin_config = db_manager.settings.get_mysql_config(include_database=False)
        try:
            conn = mysql.connector.connect(**admin_config)
            try:
                with conn.cursor() as cursor:
                    for idx, stmt in enumerate(statements, start=1):
                        first_line = stmt.split("\n", 1)[0].strip()
                        logger.debug("Executing statement %d/%d: %s", idx, len(statements), first_line)
                        cursor.execute(stmt)
                    conn.commit()
                logger.info("All migration statements executed successfully.")
            finally:
                conn.close()
        except Exception as exc:
            logger.exception("Failed executing migration statements: %s", exc)
            return False, {"error": str(exc)}

        # 3. Verify table existence
        status_map: Dict[str, str] = {}
        try:
            verify_config = db_manager.settings.get_mysql_config(include_database=True)
            vconn = mysql.connector.connect(**verify_config)
            try:
                with vconn.cursor(dictionary=True) as cursor:
                    cursor.execute("SHOW TABLES;")
                    rows = cursor.fetchall()
                    existing_tables = set()
                    for r in rows:
                        existing_tables.update(r.values())

                    for table in EXPECTED_TABLES:
                        if table in existing_tables:
                            status_map[table] = "CREATED / VERIFIED"
                        else:
                            status_map[table] = "MISSING"

                    all_verified = all(status_map[t] == "CREATED / VERIFIED" for t in EXPECTED_TABLES)
                    logger.info("Migration verification complete. All tables present: %s", all_verified)
                    return all_verified, status_map
            finally:
                vconn.close()
        except Exception as exc:
            logger.exception("Failed to verify created tables: %s", exc)
            return False, {"error": str(exc)}

    except Exception as exc:
        logger.exception("Unhandled error during run_migrations: %s", exc)
        return False, {"error": str(exc)}
