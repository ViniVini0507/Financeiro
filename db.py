import sqlite3

DB_NAME = "financeiro_cache.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        # Cria as tabelas utilizando o DDL definido na Seção 3
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            notion_id TEXT PRIMARY KEY, name TEXT NOT NULL, initial_balance REAL DEFAULT 0,
            currency TEXT, type TEXT, due_day INTEGER, closing_day INTEGER, credit_limit REAL DEFAULT 0
        );""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            notion_id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT, monthly_budget REAL DEFAULT 0
        );""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            notion_id TEXT PRIMARY KEY, name TEXT NOT NULL, account_id TEXT,
            reference_month TEXT, closing_date TEXT, due_date TEXT, status TEXT
        );""")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            notion_id TEXT PRIMARY KEY, description TEXT NOT NULL, type TEXT,
            purchase_date TEXT, effective_date TEXT, amount REAL, installments_count INTEGER,
            movement_type TEXT, context TEXT, account_id TEXT, invoice_id TEXT
        );""")
        conn.commit()