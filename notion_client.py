import sqlite3

DB_NAME = "financeiro_cache.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    # Permite acessar as colunas pelo nome (ex: row['amount'])
    conn.row_factory = sqlite3.Row 
    return conn

def init_db():
    """Inicializa as tabelas no SQLite. Este é o seu Schema SQL físico."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Tabela de Contas
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            notion_id TEXT PRIMARY KEY, 
            name TEXT NOT NULL, 
            initial_balance REAL DEFAULT 0,
            type TEXT, 
            due_day INTEGER, 
            closing_day INTEGER, 
            credit_limit REAL DEFAULT 0
        );""")
        
        # Tabela de Categorias
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            notion_id TEXT PRIMARY KEY, 
            name TEXT NOT NULL, 
            type TEXT, 
            monthly_budget REAL DEFAULT 0
        );""")
        
        # Tabela de Transações
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            notion_id TEXT PRIMARY KEY, 
            description TEXT NOT NULL, 
            type TEXT,
            purchase_date TEXT, 
            effective_date TEXT, 
            amount REAL, 
            installments_count INTEGER,
            movement_type TEXT, 
            context TEXT, 
            account_id TEXT, 
            category_id TEXT,
            FOREIGN KEY(account_id) REFERENCES accounts(notion_id),
            FOREIGN KEY(category_id) REFERENCES categories(notion_id)
        );""")
        
        conn.commit()