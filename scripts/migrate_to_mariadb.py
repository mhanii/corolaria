#!/usr/bin/env python3
"""
SQLite to MariaDB Migration Script.

Migrates all data from SQLite (data/coloraria.db) to MariaDB.
Creates a backup of the SQLite database before migration.

Usage:
    python scripts/migrate_to_mariadb.py [--dry-run]
"""
import os
import sys
import shutil
import argparse
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.logger import step_logger


def create_backup(sqlite_path: str) -> str:
    """Create backup of SQLite database."""
    backup_path = f"{sqlite_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(sqlite_path, backup_path)
    print(f"✓ Created backup: {backup_path}")
    return backup_path


def get_sqlite_connection():
    """Get SQLite connection."""
    import sqlite3
    db_path = "data/coloraria.db"
    
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"SQLite database not found: {db_path}")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_mariadb_connection(max_retries: int = 5, retry_delay: int = 3):
    """
    Get MariaDB connection with retry logic.
    
    Args:
        max_retries: Maximum connection attempts
        retry_delay: Seconds between retries
    """
    import time
    from src.infrastructure.database.mariadb_connection import MariaDBConnection
    
    # Use environment variables
    uri = os.getenv("MARIADB_URI")
    if not uri:
        host = os.getenv("MARIADB_HOST", "localhost")
        port = os.getenv("MARIADB_PORT", "3306")
        db = os.getenv("MARIADB_DATABASE", "coloraria")
        user = os.getenv("MARIADB_USER", "coloraria_user")
        password = os.getenv("MARIADB_PASSWORD", "coloraria_pass")
        uri = f"mariadb+pymysql://{user}:{password}@{host}:{port}/{db}"
    
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        try:
            conn = MariaDBConnection(uri=uri)
            
            # Test connection with simple query
            result = conn.fetchone("SELECT 1 as test", ())
            if result and result.get('test') == 1:
                print(f"✓ MariaDB connection verified (attempt {attempt}/{max_retries})")
                return conn
            else:
                raise Exception("Connection test query returned unexpected result")
                
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                print(f"  Connection attempt {attempt}/{max_retries} failed: {e}")
                print(f"  Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print(f"  Connection attempt {attempt}/{max_retries} failed: {e}")
    
    raise Exception(f"Failed to connect after {max_retries} attempts. Last error: {last_error}")


def migrate_table(sqlite_conn, mariadb_conn, table: str, columns: list, dry_run: bool = False) -> tuple:
    """
    Migrate a single table from SQLite to MariaDB.
    
    Returns:
        tuple: (migrated_count, error_count, total_rows)
    """
    import time
    
    cursor = sqlite_conn.cursor()
    cursor.execute(f"SELECT * FROM {table}")
    rows = cursor.fetchall()
    
    if not rows:
        print(f"  {table}: 0 rows (empty)")
        return (0, 0, 0)
    
    if dry_run:
        print(f"  {table}: {len(rows)} rows (dry run)")
        return (len(rows), 0, len(rows))
    
    # Build parameterized insert
    placeholders = ", ".join([f":p{i}" for i in range(len(columns))])
    column_list = ", ".join(columns)
    insert_sql = f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})"
    
    migrated = 0
    errors = 0
    max_retries = 3
    
    for row in rows:
        values = tuple(dict(row)[col] for col in columns)
        
        # Retry loop for each row
        for attempt in range(1, max_retries + 1):
            try:
                mariadb_conn.execute(insert_sql, values)
                migrated += 1
                break  # Success, move to next row
            except Exception as e:
                error_str = str(e)
                if "Duplicate entry" in error_str:
                    # Already exists, count as migrated (idempotent)
                    migrated += 1
                    break
                elif "Lost connection" in error_str or "Connection refused" in error_str:
                    if attempt < max_retries:
                        time.sleep(1)  # Brief pause before retry
                        continue
                    else:
                        errors += 1
                        if errors <= 3:
                            print(f"    Error in {table} (after {max_retries} retries): {e}")
                        break
                else:
                    errors += 1
                    if errors <= 3:
                        print(f"    Error in {table}: {e}")
                    break
    
    status = "✓" if errors == 0 else "✗"
    print(f"  {table}: {migrated}/{len(rows)} rows migrated" + (f" ({errors} errors)" if errors else "") + f" {status}")
    return (migrated, errors, len(rows))


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite to MariaDB")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without actually migrating")
    parser.add_argument("--no-backup", action="store_true", help="Skip creating backup (use with caution)")
    args = parser.parse_args()
    
    print("=" * 60)
    print("SQLite to MariaDB Migration")
    print("=" * 60)
    
    # Check SQLite exists
    sqlite_path = "data/coloraria.db"
    if not os.path.exists(sqlite_path):
        print(f"✗ SQLite database not found: {sqlite_path}")
        print("  Nothing to migrate.")
        sys.exit(0)
    
    # Create backup
    if not args.no_backup and not args.dry_run:
        create_backup(sqlite_path)
    
    # Connect to databases
    print("\nConnecting to databases...")
    try:
        sqlite_conn = get_sqlite_connection()
        print("✓ SQLite connected")
    except Exception as e:
        print(f"✗ SQLite connection failed: {e}")
        sys.exit(1)
    
    if not args.dry_run:
        try:
            mariadb_conn = get_mariadb_connection()
        except Exception as e:
            print(f"✗ MariaDB connection failed: {e}")
            print("  Make sure MariaDB is running: docker compose -f docker-compose.api.dev.yml up -d mariadb")
            sys.exit(1)
        
        # Initialize schema separately to get better error messages
        print("\nInitializing MariaDB schema...")
        try:
            from src.infrastructure.database.mariadb_schema import init_mariadb_schema
            init_mariadb_schema(mariadb_conn)
            print("✓ MariaDB schema initialized")
        except Exception as e:
            print(f"✗ Schema initialization failed: {e}")
            sys.exit(1)
    else:
        mariadb_conn = None
        print("  (Dry run - skipping MariaDB connection)")
    
    # Define tables and columns to migrate
    tables = {
        "users": [
            "id", "username", "password_hash", "available_tokens", 
            "created_at", "is_active"
        ],
        "conversations": [
            "id", "user_id", "created_at", "updated_at", "metadata"
        ],
        "messages": [
            "id", "conversation_id", "role", "content", "timestamp",
            "metadata", "context_json"
        ],
        "message_citations": [
            "id", "message_id", "citation_index", "cite_key", "display_text",
            "article_id", "article_number", "article_text", "normativa_title",
            "article_path", "score"
        ],
        "feedback": [
            "id", "user_id", "message_id", "conversation_id",
            "feedback_type", "comment", "config_matrix", "created_at"
        ],
        "surveys": [
            "id", "user_id", "responses", "tokens_granted", "submitted_at"
        ]
    }
    
    # Migrate each table
    print("\nMigrating tables...")
    total_migrated = 0
    total_errors = 0
    total_expected = 0
    
    for table, columns in tables.items():
        try:
            migrated, errors, expected = migrate_table(sqlite_conn, mariadb_conn, table, columns, args.dry_run)
            total_migrated += migrated
            total_errors += errors
            total_expected += expected
        except Exception as e:
            print(f"  {table}: ✗ Error - {e}")
            total_errors += 1
    
    # Summary
    print("\n" + "=" * 60)
    if args.dry_run:
        print(f"DRY RUN COMPLETE: Would migrate {total_migrated} total rows")
        print("=" * 60)
        print("\n✓ Dry run finished successfully!")
        sys.exit(0)
    
    # Check if migration had errors
    if total_errors > 0:
        print(f"MIGRATION FAILED: {total_migrated}/{total_expected} rows migrated, {total_errors} errors")
        print("=" * 60)
        print("\n✗ Migration encountered errors. Please check the output above.")
        print("  Make sure MariaDB is running and accessible.")
        sys.exit(1)
    
    print(f"MIGRATION COMPLETE: {total_migrated} total rows migrated successfully")
    print("=" * 60)
    
    # Verification
    print("\nVerifying migration...")
    verification_failed = False
    
    for table in tables.keys():
        try:
            sqlite_cursor = sqlite_conn.cursor()
            sqlite_cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
            sqlite_count = sqlite_cursor.fetchone()['count']
            
            mariadb_row = mariadb_conn.fetchone(f"SELECT COUNT(*) as count FROM {table}", ())
            mariadb_count = mariadb_row['count'] if mariadb_row else 0
            
            if sqlite_count == mariadb_count:
                print(f"  {table}: SQLite={sqlite_count}, MariaDB={mariadb_count} ✓")
            else:
                print(f"  {table}: SQLite={sqlite_count}, MariaDB={mariadb_count} ✗ MISMATCH")
                verification_failed = True
        except Exception as e:
            print(f"  {table}: ✗ Verification error - {e}")
            verification_failed = True
    
    if verification_failed:
        print("\n✗ Verification failed! Some data may not have migrated correctly.")
        sys.exit(1)
    
    print("\n✓ Migration completed successfully!")


if __name__ == "__main__":
    main()

