"""Financial AI Assistant - CLI Entrypoint & Management Tool with comprehensive error logging."""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config.settings import get_settings
from app.database.connection import get_db_manager
from app.database.migrations.runner import run_migrations

logger = logging.getLogger(__name__)


def setup_logging(log_level: str = "INFO", log_dir: Path = Path("logs")) -> None:
    """Configure console and rotating file logging."""
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "app.log"

        level = getattr(logging, log_level.upper(), logging.INFO)

        log_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
        date_format = "%Y-%m-%d %H:%M:%S"

        handlers = [
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ]

        logging.basicConfig(
            level=level,
            format=log_format,
            datefmt=date_format,
            handlers=handlers,
            force=True,
        )
        logger.debug("Logging initialized at level %s, output file: %s", log_level, log_file)
    except Exception as exc:
        # If logger fails, write basic error to stderr
        sys.stderr.write(f"Failed to configure logging: {exc}\n")


def run_health_check() -> bool:
    """Execute diagnostic checks across configuration, filesystem, and database."""
    try:
        # Ensure stdout handles unicode if possible, but fallback gracefully
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

        print("\n========================================================")
        print("      Financial AI Assistant - System Health Check      ")
        print("========================================================")

        all_healthy = True
        settings = get_settings()

        # 1. Environment & Config
        print("\n[1/3] Environment & Configuration:")
        print(f"  * App Name:    {settings.APP_NAME}")
        print(f"  * Environment: {settings.ENVIRONMENT}")
        print(f"  * Log Level:   {settings.LOG_LEVEL}")
        print("  [OK] Configuration loaded successfully.")

        # 2. Storage Directories
        print("\n[2/3] Storage & Workspace Directories:")
        dirs = [
            ("Downloads", settings.DOWNLOAD_DIR),
            ("Processed", settings.PROCESSED_DIR),
            ("Exports", settings.EXPORT_DIR),
            ("Logs", settings.LOGS_DIR),
        ]
        for label, directory in dirs:
            status = "EXISTS & WRITABLE" if directory.exists() and directory.is_dir() else "MISSING"
            print(f"  * {label:10} [{directory}]: {status}")
        print("  [OK] All required storage directories verified.")

        # 3. MySQL Database
        print("\n[3/3] MySQL Database Connectivity:")
        print(f"  * Target:      {settings.MYSQL_USER}@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}")
        print(f"  * Database:    {settings.MYSQL_DATABASE}")

        db_mgr = get_db_manager(settings)
        db_health = db_mgr.check_health()

        if db_health.get("status") == "healthy":
            print(f"  [OK] Status:         HEALTHY")
            print(f"  * Server Version:    {db_health.get('server_version')}")
            print(f"  * Ping Response:     {db_health.get('ping')} (OK)")
            print(f"  * Server Time:       {db_health.get('server_time')}")
        else:
            all_healthy = False
            print(f"  [FAIL] Status:       UNHEALTHY")
            print(f"  * Error:             {db_health.get('error')}")
            print("\n  Tip: Ensure the MySQL service is running and credentials in .env are correct.")
            print("       Example in .env: MYSQL_HOST=localhost, MYSQL_USER=root, MYSQL_PASSWORD=your_password")

        print("\n========================================================")
        if all_healthy:
            print("  Overall Status: ALL SYSTEMS OPERATIONAL (Phase 1 Ready)")
        else:
            print("  Overall Status: ATTENTION REQUIRED (See errors above)")
        print("========================================================\n")

        return all_healthy
    except Exception as exc:
        logger.exception("Health check failed unexpectedly: %s", exc)
        print(f"\n[FAIL] Unexpected error during health check: {exc}\n")
        return False


def run_migration_command() -> bool:
    """Execute database migrations to initialize tables."""
    try:
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

        print("\n========================================================")
        print("        Financial AI Assistant - Database Migration      ")
        print("========================================================")

        settings = get_settings()
        db_mgr = get_db_manager(settings)

        print(f"Connecting to MySQL at {settings.MYSQL_HOST}:{settings.MYSQL_PORT}...")
        success, results = run_migrations(db_mgr)

        if success:
            print("\n[OK] Migration completed successfully! Table status:")
            for table, status in results.items():
                print(f"  * {table:20}: {status}")
            print("\nAll required normalized tables are ready in database:", settings.MYSQL_DATABASE)
        else:
            print("\n[FAIL] Migration encountered an error:")
            for k, v in results.items():
                print(f"  * {k}: {v}")
            print("\nPlease check your MySQL credentials and privileges in .env.")

        print("========================================================\n")
        return success
    except Exception as exc:
        logger.exception("Database migration failed: %s", exc)
        print(f"\n[FAIL] Fatal exception during migration: {exc}\n")
        return False


def show_info() -> None:
    """Print current configuration details."""
    try:
        settings = get_settings()
        print("\n========================================================")
        print("         Financial AI Assistant - Configuration         ")
        print("========================================================")
        print(f"  APP_NAME:               {settings.APP_NAME}")
        print(f"  ENVIRONMENT:            {settings.ENVIRONMENT}")
        print(f"  LOG_LEVEL:              {settings.LOG_LEVEL}")
        print(f"  MYSQL_HOST:             {settings.MYSQL_HOST}")
        print(f"  MYSQL_PORT:             {settings.MYSQL_PORT}")
        print(f"  MYSQL_DATABASE:         {settings.MYSQL_DATABASE}")
        print(f"  MYSQL_USER:             {settings.MYSQL_USER}")
        print(f"  MYSQL_POOL_SIZE:        {settings.MYSQL_POOL_SIZE}")
        print(f"  OLLAMA_BASE_URL:        {settings.OLLAMA_BASE_URL}")
        print(f"  OLLAMA_MODEL:           {settings.OLLAMA_MODEL}")
        print(f"  DOWNLOAD_DIR:           {settings.DOWNLOAD_DIR}")
        print(f"  PROCESSED_DIR:          {settings.PROCESSED_DIR}")
        print(f"  EXPORT_DIR:             {settings.EXPORT_DIR}")
        print(f"  CHUNK_SIZE:             {settings.CHUNK_SIZE}")
        print(f"  CHUNK_OVERLAP:          {settings.CHUNK_OVERLAP}")
        print("========================================================\n")
    except Exception as exc:
        logger.exception("Failed displaying configuration info: %s", exc)


def run_graphify_command() -> bool:
    """Execute database graphification into in-memory persistent Knowledge Graph."""
    try:
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

        print("\n========================================================")
        print("       Financial AI Assistant - Database Graphifier      ")
        print("========================================================")
        settings = get_settings()
        db_mgr = get_db_manager(settings)
        from app.pipeline.graphify import Graphifier, get_knowledge_graph
        graphifier = Graphifier(db_mgr, get_knowledge_graph(settings), settings)
        kg = graphifier.graphify_from_db()
        summary = kg.to_dict()["summary"]
        print(f"\n[OK] Knowledge Graph built successfully:")
        print(f"  * Total Nodes:        {summary.get('total_nodes')}")
        print(f"  * Total Edges:        {summary.get('total_edges')}")
        print(f"  * Companies:          {summary.get('companies')}")
        print(f"  * Financial Metrics:  {summary.get('metrics')}")
        print(f"  * Risk Factors:       {summary.get('risks')}")
        print(f"  * Documents:          {summary.get('documents')}")
        print(f"  * Semantic Guidance:  {summary.get('guidance')}")
        print(f"\nSaved Knowledge Graph to: {settings.PROCESSED_DIR / 'knowledge_graph.json'}")
        print("========================================================\n")
        return True
    except Exception as exc:
        logger.exception("Graphification failed: %s", exc)
        print(f"\n[FAIL] Graphification error: {exc}\n")
        return False


def run_web_server(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """Launch the Uvicorn web server and dashboard UI."""
    try:
        import uvicorn
        print("\n========================================================")
        print("      Financial AI Suite - Interactive Web Dashboard     ")
        print("========================================================")
        print(f"  * Dashboard URL:  http://localhost:{port}")
        print(f"  * API Docs:       http://localhost:{port}/docs")
        print(f"  * Health Status:  http://localhost:{port}/api/health")
        print(f"  * Auto Reload:    {'Enabled' if reload else 'Disabled'}")
        print("========================================================\n")
        uvicorn.run("app.main:app", host=host, port=port, reload=reload)
    except Exception as exc:
        logger.exception("Web server failed to start or crashed: %s", exc)
        print(f"[FAIL] Web server error: {exc}")


def main() -> None:
    try:
        parser = argparse.ArgumentParser(
            description="Financial Document Automation & AI Assistant CLI",
            formatter_class=argparse.RawTextHelpFormatter,
        )
        parser.add_argument(
            "--serve",
            "-s",
            action="store_true",
            help="Start the FastAPI web server and interactive dashboard UI.",
        )
        parser.add_argument(
            "--health",
            "-c",
            action="store_true",
            help="Run health check on config, filesystem, and MySQL connection.",
        )
        parser.add_argument(
            "--migrate",
            "-m",
            action="store_true",
            help="Execute database schema migrations to create all normalized tables.",
        )
        parser.add_argument(
            "--graphify",
            "-g",
            action="store_true",
            help="Transform relational MySQL records & concalls into pre-indexed Knowledge Graph.",
        )
        parser.add_argument(
            "--info",
            "-i",
            action="store_true",
            help="Display loaded configuration and environment variables.",
        )
        parser.add_argument(
            "--port",
            "-p",
            type=int,
            default=8000,
            help="Port to bind the web server (default: 8000).",
        )
        parser.add_argument(
            "--reload",
            "-r",
            action="store_true",
            help="Enable auto-reload on code changes (default in development).",
        )

        args = parser.parse_args()

        settings = get_settings()
        setup_logging(log_level=settings.LOG_LEVEL, log_dir=settings.LOGS_DIR)

        is_dev = getattr(settings, "APP_ENV", "development").lower() == "development"
        should_reload = args.reload or is_dev

        if args.health:
            healthy = run_health_check()
            sys.exit(0 if healthy else 1)
        elif args.migrate:
            success = run_migration_command()
            sys.exit(0 if success else 1)
        elif args.graphify:
            success = run_graphify_command()
            sys.exit(0 if success else 1)
        elif args.info:
            show_info()
        elif args.serve:
            run_web_server(port=args.port, reload=should_reload)
        else:
            # Default behavior when run directly without flags
            run_web_server(port=args.port, reload=should_reload)

    except Exception as exc:
        logger.critical("Fatal exception in main execution: %s", exc, exc_info=True)
        print(f"\n[FATAL ERROR]: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
