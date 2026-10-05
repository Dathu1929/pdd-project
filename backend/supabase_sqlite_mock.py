import re
import sqlite3
import logging
import psycopg2
import supabase_db

logger = logging.getLogger("supabase_sqlite_mock")

class PostgresRow:
    """Wrapper that mimics sqlite3.Row for dict conversion and dual key/index indexing."""
    def __init__(self, description_or_cursor, row_tuple):
        if hasattr(description_or_cursor, "description"):
            description = description_or_cursor.description
        else:
            description = description_or_cursor
            
        self._keys = [desc[0] for desc in description] if description else []
        self._data = dict(zip(self._keys, row_tuple)) if description else {}
        self._tuple = row_tuple

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._tuple[key]
        return self._data[key]

    def keys(self) -> list:
        return self._keys

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __repr__(self):
        return f"PostgresRow({self._data})"

Row = PostgresRow

class PostgresMockCursor:
    def __init__(self, pg_cursor):
        self._cursor = pg_cursor
        self.lastrowid = None

    def execute(self, sql: str, params: tuple = ()):
        sql_clean = sql.strip().lower()
        if "pragma " in sql_clean:
            return self
        
        # 1. Translate SQLite ? parameter syntax to PostgreSQL %s parameter syntax
        sql_postgres = sql.replace("?", "%s")
        
        # 2. Translate SQLite PRINTF('%08d', expr) to PostgreSQL LPAD(expr::text, 8, '0')
        sql_postgres = re.sub(
            r"printf\(\s*'([^']+)'\s*,\s*([^)]+)\)", 
            r"lpad(\2::text, 8, '0')", 
            sql_postgres, 
            flags=re.IGNORECASE
        )
        
        # 3. Handle lastrowid emulation: append RETURNING id to INSERT statements
        is_insert = sql_postgres.strip().lower().startswith("insert into")
        if is_insert and "returning" not in sql_postgres.lower():
            sql_postgres += " RETURNING id"
            
        logger.debug(f"SQL Translated: {sql} -> {sql_postgres} | Params: {params}")
        
        # 4. Execute the query
        self._cursor.execute(sql_postgres, params)
        
        # If it was an insert, fetch the returned ID to populate lastrowid
        if is_insert:
            try:
                row = self._cursor.fetchone()
                if row:
                    self.lastrowid = row[0]
            except Exception:
                pass
                
        return self

    def fetchone(self) -> PostgresRow:
        row = self._cursor.fetchone()
        if row is None:
            return None
        return PostgresRow(self._cursor.description, row)

    def fetchall(self) -> list:
        rows = self._cursor.fetchall()
        desc = self._cursor.description
        return [PostgresRow(desc, r) for r in rows]

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

class PostgresMockConnection:
    def __init__(self, pg_conn):
        self._conn = pg_conn
        self.row_factory = None

    def cursor(self) -> PostgresMockCursor:
        return PostgresMockCursor(self._conn.cursor())

    def execute(self, sql: str, params: tuple = ()) -> PostgresMockCursor:
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

def connect(database: str, *args, **kwargs):
    conn = supabase_db.get_connection()
    if not supabase_db.is_postgres(conn):
        # Fallback SQLite connection
        return conn
    return PostgresMockConnection(conn)

IntegrityError = (sqlite3.IntegrityError, psycopg2.IntegrityError)
OperationalError = (sqlite3.OperationalError, psycopg2.OperationalError)
DatabaseError = (sqlite3.DatabaseError, psycopg2.DatabaseError)
Error = (sqlite3.Error, psycopg2.Error)

