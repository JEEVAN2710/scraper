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
    "company_sources",
    "automations",
    "automation_runs",
    "extraction_runs",
    "financial_metrics",
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


def apply_v2_column_migrations(cursor, db_name: str) -> None:
    """Safely and idempotently apply V2 column and foreign key migrations to existing tables."""
    def get_existing_columns(table_name: str) -> set:
        cursor.execute(
            """
            SELECT COLUMN_NAME FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s;
            """,
            (db_name, table_name),
        )
        return {row[0] if isinstance(row, tuple) else row["COLUMN_NAME"] for row in cursor.fetchall()}

    def get_existing_constraints(table_name: str) -> set:
        cursor.execute(
            """
            SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s;
            """,
            (db_name, table_name),
        )
        return {row[0] if isinstance(row, tuple) else row["CONSTRAINT_NAME"] for row in cursor.fetchall()}

    # 1. companies
    comp_cols = get_existing_columns("companies")
    if "is_active" not in comp_cols:
        cursor.execute("ALTER TABLE companies ADD COLUMN is_active BOOLEAN DEFAULT TRUE;")
        logger.info("Added 'is_active' column to companies.")
    if "tracking_tier" not in comp_cols:
        cursor.execute("ALTER TABLE companies ADD COLUMN tracking_tier ENUM('standard', 'priority') DEFAULT 'standard';")
        logger.info("Added 'tracking_tier' column to companies.")

    # 2. documents
    doc_cols = get_existing_columns("documents")
    if "source_id" not in doc_cols:
        cursor.execute("ALTER TABLE documents ADD COLUMN source_id INT NULL;")
        logger.info("Added 'source_id' column to documents.")
    if "file_size_bytes" not in doc_cols:
        cursor.execute("ALTER TABLE documents ADD COLUMN file_size_bytes BIGINT NULL;")
        logger.info("Added 'file_size_bytes' column to documents.")
    if "page_count" not in doc_cols:
        cursor.execute("ALTER TABLE documents ADD COLUMN page_count INT NULL;")
        logger.info("Added 'page_count' column to documents.")
    if "text_density_score" not in doc_cols:
        cursor.execute("ALTER TABLE documents ADD COLUMN text_density_score FLOAT NULL;")
        logger.info("Added 'text_density_score' column to documents.")

    # Update processing_status ENUM on documents
    cursor.execute("""
        ALTER TABLE documents MODIFY COLUMN processing_status 
        ENUM('discovered', 'downloaded', 'extracting', 'ocr', 'extracted', 'chunked', 'ai_extracting', 'validating', 'analyzing', 'processed', 'failed') 
        DEFAULT 'downloaded';
    """)

    doc_constraints = get_existing_constraints("documents")
    if "fk_documents_source" not in doc_constraints:
        cursor.execute("""
            ALTER TABLE documents 
            ADD CONSTRAINT fk_documents_source 
            FOREIGN KEY (source_id) REFERENCES company_sources(id) ON DELETE SET NULL;
        """)
        logger.info("Added 'fk_documents_source' foreign key constraint.")

    # 3. document_chunks
    chunk_cols = get_existing_columns("document_chunks")
    if "word_count" not in chunk_cols:
        cursor.execute("ALTER TABLE document_chunks ADD COLUMN word_count INT NULL;")
        logger.info("Added 'word_count' column to document_chunks.")
    if "is_ocr" not in chunk_cols:
        cursor.execute("ALTER TABLE document_chunks ADD COLUMN is_ocr BOOLEAN DEFAULT FALSE;")
        logger.info("Added 'is_ocr' column to document_chunks.")

    # 4. financial_data
    fin_cols = get_existing_columns("financial_data")
    if "extraction_run_id" not in fin_cols:
        cursor.execute("ALTER TABLE financial_data ADD COLUMN extraction_run_id INT NULL;")
        logger.info("Added 'extraction_run_id' column to financial_data.")
    if "confidence_score" not in fin_cols:
        cursor.execute("ALTER TABLE financial_data ADD COLUMN confidence_score FLOAT DEFAULT 1.0;")
        logger.info("Added 'confidence_score' column to financial_data.")
    if "source_page" not in fin_cols:
        cursor.execute("ALTER TABLE financial_data ADD COLUMN source_page INT NULL;")
        logger.info("Added 'source_page' column to financial_data.")

    fin_constraints = get_existing_constraints("financial_data")
    if "fk_financial_data_extraction_run" not in fin_constraints:
        cursor.execute("""
            ALTER TABLE financial_data 
            ADD CONSTRAINT fk_financial_data_extraction_run 
            FOREIGN KEY (extraction_run_id) REFERENCES extraction_runs(id) ON DELETE SET NULL;
        """)
        logger.info("Added 'fk_financial_data_extraction_run' foreign key constraint.")

    # 5. risk_factors
    risk_cols = get_existing_columns("risk_factors")
    if "extraction_run_id" not in risk_cols:
        cursor.execute("ALTER TABLE risk_factors ADD COLUMN extraction_run_id INT NULL;")
        logger.info("Added 'extraction_run_id' column to risk_factors.")
    if "severity" not in risk_cols:
        cursor.execute("ALTER TABLE risk_factors ADD COLUMN severity ENUM('low', 'medium', 'high', 'critical') DEFAULT 'medium';")
        logger.info("Added 'severity' column to risk_factors.")
    if "confidence_score" not in risk_cols:
        cursor.execute("ALTER TABLE risk_factors ADD COLUMN confidence_score FLOAT DEFAULT 1.0;")
        logger.info("Added 'confidence_score' column to risk_factors.")

    risk_constraints = get_existing_constraints("risk_factors")
    if "fk_risk_factors_extraction_run" not in risk_constraints:
        cursor.execute("""
            ALTER TABLE risk_factors 
            ADD CONSTRAINT fk_risk_factors_extraction_run 
            FOREIGN KEY (extraction_run_id) REFERENCES extraction_runs(id) ON DELETE SET NULL;
        """)
        logger.info("Added 'fk_risk_factors_extraction_run' foreign key constraint.")

    # 6. processing_logs
    log_cols = get_existing_columns("processing_logs")
    if "automation_run_id" not in log_cols:
        cursor.execute("ALTER TABLE processing_logs ADD COLUMN automation_run_id INT NULL;")
        logger.info("Added 'automation_run_id' column to processing_logs.")
    if "duration_ms" not in log_cols:
        cursor.execute("ALTER TABLE processing_logs ADD COLUMN duration_ms INT NULL;")
        logger.info("Added 'duration_ms' column to processing_logs.")

    log_constraints = get_existing_constraints("processing_logs")
    if "fk_processing_logs_automation_run" not in log_constraints:
        cursor.execute("""
            ALTER TABLE processing_logs 
            ADD CONSTRAINT fk_processing_logs_automation_run 
            FOREIGN KEY (automation_run_id) REFERENCES automation_runs(id) ON DELETE SET NULL;
        """)
        logger.info("Added 'fk_processing_logs_automation_run' foreign key constraint.")


def run_migrations(
    db_manager: DatabaseManager = None,
    schema_file: Path = None,
    schema_v2_file: Path = None,
) -> Tuple[bool, Dict[str, str]]:
    """Execute schema migrations (V1 base + V2 extensions) and verify table creation.

    Connects first without requiring target database to exist, executes
    CREATE DATABASE and all DDL statements from schema.sql and schema_v2.sql,
    applies idempotent column migrations, then verifies table and view creation.

    Returns:
        Tuple[bool, Dict[str, str]]: (success, table_status_map)
    """
    try:
        if db_manager is None:
            db_manager = get_db_manager()

        if schema_file is None:
            schema_file = Path(__file__).parent / "schema.sql"

        if schema_v2_file is None:
            schema_v2_file = Path(__file__).parent / "schema_v2.sql"

        if not schema_file.exists():
            error_msg = f"Base schema file not found at: {schema_file}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        logger.info("Starting schema migration with base '%s' and V2 '%s'", schema_file, schema_v2_file)

        # 1. Read and parse SQL scripts
        with open(schema_file, "r", encoding="utf-8") as f:
            base_sql = f.read()
        statements = parse_sql_statements(base_sql)

        v2_statements = []
        if schema_v2_file.exists():
            with open(schema_v2_file, "r", encoding="utf-8") as f:
                v2_sql = f.read()
            v2_statements = parse_sql_statements(v2_sql)

        total_statements = len(statements) + len(v2_statements)
        logger.info("Found %d DDL statement(s) to execute (%d base, %d v2).", total_statements, len(statements), len(v2_statements))

        # 2. Execute statements using administrative connection (no pre-selected DB required)
        admin_config = db_manager.settings.get_mysql_config(include_database=False)
        target_db = db_manager.settings.MYSQL_DATABASE
        try:
            conn = mysql.connector.connect(**admin_config)
            try:
                with conn.cursor() as cursor:
                    # Execute base schema statements
                    for idx, stmt in enumerate(statements, start=1):
                        first_line = stmt.split("\n", 1)[0].strip()
                        logger.debug("Executing base statement %d/%d: %s", idx, len(statements), first_line)
                        cursor.execute(stmt)

                    # Select target database explicitly for v2 statements
                    cursor.execute(f"USE `{target_db}`;")

                    # Execute V2 schema statements
                    for idx, stmt in enumerate(v2_statements, start=1):
                        first_line = stmt.split("\n", 1)[0].strip()
                        logger.debug("Executing V2 statement %d/%d: %s", idx, len(v2_statements), first_line)
                        cursor.execute(stmt)

                    # Apply idempotent column additions and constraints
                    apply_v2_column_migrations(cursor, target_db)

                    conn.commit()
                logger.info("All migration statements and alterations executed successfully.")
            finally:
                conn.close()
        except Exception as exc:
            logger.exception("Failed executing migration statements: %s", exc)
            return False, {"error": str(exc)}

        # 3. Verify table and view existence
        status_map: Dict[str, str] = {}
        try:
            verify_config = db_manager.settings.get_mysql_config(include_database=True)
            vconn = mysql.connector.connect(**verify_config)
            try:
                with vconn.cursor(dictionary=True) as cursor:
                    cursor.execute("SHOW FULL TABLES;")
                    rows = cursor.fetchall()
                    existing_tables = set()
                    for r in rows:
                        # Values contain table name and table type ('BASE TABLE' or 'VIEW')
                        # e.g., {'Tables_in_financial_ai': 'companies', 'Table_type': 'BASE TABLE'}
                        for k, v in r.items():
                            if k.startswith("Tables_in_"):
                                existing_tables.add(v)

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
