import os
import sqlite3
import logging
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("supabase_db")

SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL", "")
LOCAL_DB_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "electricity.db"))

_use_local_sqlite = False

def get_connection():
    global _use_local_sqlite
    
    # Check if Supabase URL is configured
    if not SUPABASE_DB_URL or "your-project-ref" in SUPABASE_DB_URL:
        if not _use_local_sqlite:
            logger.warning("SUPABASE_DB_URL not configured in .env. Falling back to local SQLite database.")
            _use_local_sqlite = True
        conn = sqlite3.connect(LOCAL_DB_FILE, timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
        except Exception:
            pass
        return conn

    try:
        conn = psycopg2.connect(SUPABASE_DB_URL)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to Supabase PostgreSQL: {e}")
        if not _use_local_sqlite:
            logger.warning("Falling back to local SQLite database.")
            _use_local_sqlite = True
        return sqlite3.connect(LOCAL_DB_FILE, timeout=30.0)

def is_postgres(conn) -> bool:
    # psycopg2 connections have a cursor method that behaves differently or we can check the class
    return not isinstance(conn, sqlite3.Connection)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    if not is_postgres(conn):
        # Run local SQLite table initialization directly to avoid circular imports
        cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, phone TEXT, alternate_phone TEXT, sms_reminders INTEGER DEFAULT 1, email_reminders INTEGER DEFAULT 1, whatsapp_reminders INTEGER DEFAULT 1, phone_reminders INTEGER DEFAULT 1, sms_recipient_phone TEXT, email_recipient_email TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS meters (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, service_number TEXT UNIQUE NOT NULL, board_name TEXT NOT NULL, consumer_name TEXT NOT NULL, address TEXT NOT NULL, prediction_reminder_enabled INTEGER DEFAULT 1, FOREIGN KEY(user_id) REFERENCES users(id))")
        cursor.execute("CREATE TABLE IF NOT EXISTS bills (id INTEGER PRIMARY KEY AUTOINCREMENT, meter_id INTEGER NOT NULL, consumer_id TEXT, consumer_name TEXT, mobile_number TEXT, email_address TEXT, billing_month TEXT NOT NULL, units_consumed REAL DEFAULT 0.0, amount REAL NOT NULL, bill_amount REAL NOT NULL, amount_paid REAL DEFAULT 0.0, remaining_amount REAL NOT NULL, bill_issue_date TEXT, due_date TEXT NOT NULL, payment_status TEXT DEFAULT 'Unpaid', transaction_ref TEXT, FOREIGN KEY(meter_id) REFERENCES meters(id))")
        cursor.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, bill_id INTEGER NOT NULL, amount REAL NOT NULL, payment_method TEXT NOT NULL, transaction_ref TEXT NOT NULL, paid_at TEXT NOT NULL, verification_status TEXT DEFAULT 'VERIFIED', FOREIGN KEY(bill_id) REFERENCES bills(id))")
        cursor.execute("CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, days_before INTEGER NOT NULL, enabled INTEGER DEFAULT 1, FOREIGN KEY(user_id) REFERENCES users(id))")
        cursor.execute("CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL, is_read INTEGER DEFAULT 0, FOREIGN KEY(user_id) REFERENCES users(id))")
        cursor.execute("CREATE TABLE IF NOT EXISTS notification_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, bill_id INTEGER, type TEXT NOT NULL, recipient TEXT NOT NULL, title TEXT, message TEXT NOT NULL, status TEXT NOT NULL, provider_response TEXT, error_message TEXT, sent_at TEXT NOT NULL, retry_count INTEGER DEFAULT 0, FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(bill_id) REFERENCES bills(id))")
        conn.commit()
        conn.close()
        return

    logger.info("Initializing Supabase PostgreSQL database tables...")
    try:
        # 1. Users Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            phone TEXT,
            alternate_phone TEXT,
            sms_reminders INTEGER DEFAULT 1,
            email_reminders INTEGER DEFAULT 1,
            whatsapp_reminders INTEGER DEFAULT 1,
            phone_reminders INTEGER DEFAULT 1,
            sms_recipient_phone TEXT,
            email_recipient_email TEXT
        )""")

        # Add missing columns if tables already existed
        cols_to_add = [
            ("alternate_phone", "TEXT"),
            ("sms_recipient_phone", "TEXT"),
            ("email_recipient_email", "TEXT"),
            ("sms_reminders", "INTEGER DEFAULT 1"),
            ("email_reminders", "INTEGER DEFAULT 1"),
            ("whatsapp_reminders", "INTEGER DEFAULT 1"),
            ("phone_reminders", "INTEGER DEFAULT 1")
        ]
        for col, col_type in cols_to_add:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
            except psycopg2.DatabaseError:
                conn.rollback()

        # 2. Meters Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS meters (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            service_number TEXT UNIQUE NOT NULL,
            board_name TEXT NOT NULL,
            consumer_name TEXT NOT NULL,
            address TEXT NOT NULL,
            prediction_reminder_enabled INTEGER DEFAULT 1,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )""")
        
        try:
            cursor.execute("ALTER TABLE meters ADD COLUMN prediction_reminder_enabled INTEGER DEFAULT 1")
        except psycopg2.DatabaseError:
            conn.rollback()

        # 3. Bills Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id SERIAL PRIMARY KEY,
            meter_id INTEGER NOT NULL,
            consumer_id TEXT,
            consumer_name TEXT,
            mobile_number TEXT,
            email_address TEXT,
            billing_month TEXT NOT NULL,
            units_consumed DOUBLE PRECISION DEFAULT 0.0,
            amount DOUBLE PRECISION NOT NULL,
            bill_amount DOUBLE PRECISION NOT NULL,
            amount_paid DOUBLE PRECISION DEFAULT 0.0,
            remaining_amount DOUBLE PRECISION NOT NULL,
            bill_issue_date TEXT,
            due_date TEXT NOT NULL,
            payment_status TEXT DEFAULT 'Unpaid',
            transaction_ref TEXT,
            FOREIGN KEY(meter_id) REFERENCES meters(id) ON DELETE CASCADE
        )""")

        bills_cols = [
            ("consumer_id", "TEXT"),
            ("consumer_name", "TEXT"),
            ("mobile_number", "TEXT"),
            ("email_address", "TEXT"),
            ("bill_amount", "DOUBLE PRECISION DEFAULT 0.0"),
            ("amount_paid", "DOUBLE PRECISION DEFAULT 0.0"),
            ("remaining_amount", "DOUBLE PRECISION DEFAULT 0.0"),
            ("bill_issue_date", "TEXT"),
            ("transaction_ref", "TEXT")
        ]
        for col, col_type in bills_cols:
            try:
                cursor.execute(f"ALTER TABLE bills ADD COLUMN {col} {col_type}")
            except psycopg2.DatabaseError:
                conn.rollback()

        # Update default amounts if necessary
        cursor.execute("UPDATE bills SET bill_amount = amount WHERE bill_amount IS NULL OR bill_amount = 0.0")
        cursor.execute("UPDATE bills SET remaining_amount = CASE WHEN payment_status = 'Paid' THEN 0.0 ELSE (bill_amount - COALESCE(amount_paid, 0.0)) END WHERE remaining_amount IS NULL OR remaining_amount = 0.0 AND payment_status != 'Paid'")
        cursor.execute("UPDATE bills SET amount_paid = CASE WHEN payment_status = 'Paid' THEN bill_amount ELSE 0.0 END WHERE amount_paid IS NULL")

        # 4. Payments Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            bill_id INTEGER NOT NULL,
            amount DOUBLE PRECISION NOT NULL,
            payment_method TEXT NOT NULL,
            transaction_ref TEXT NOT NULL,
            paid_at TEXT NOT NULL,
            verification_status TEXT DEFAULT 'VERIFIED',
            FOREIGN KEY(bill_id) REFERENCES bills(id) ON DELETE CASCADE
        )""")

        try:
            cursor.execute("ALTER TABLE payments ADD COLUMN verification_status TEXT DEFAULT 'VERIFIED'")
        except psycopg2.DatabaseError:
            conn.rollback()

        # 5. Reminders Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            days_before INTEGER NOT NULL,
            enabled INTEGER DEFAULT 1,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )""")

        # 6. Notifications Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )""")

        # 7. Notification History Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_history (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            bill_id INTEGER,
            type TEXT NOT NULL,
            recipient TEXT NOT NULL,
            title TEXT,
            message TEXT NOT NULL,
            status TEXT NOT NULL,
            provider_response TEXT,
            error_message TEXT,
            sent_at TEXT NOT NULL,
            retry_count INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(bill_id) REFERENCES bills(id) ON DELETE SET NULL
        )""")

        conn.commit()
        logger.info("Supabase PostgreSQL tables initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        conn.rollback()
    finally:
        conn.close()
