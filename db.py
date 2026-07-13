import sqlite3

DB_NAME = "financeiro_cache.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row 
    return conn

def init_db():
    """Inicializa as tabelas no SQLite, garantindo a modelagem correta."""
    with get_connection() as conn:
        cursor = conn.cursor()
               
        # 1. TABELA DE CONTAS
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
        
        # 2. TABELA DE CATEGORIAS
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            notion_id TEXT PRIMARY KEY, 
            name TEXT NOT NULL, 
            type TEXT, 
            monthly_budget REAL DEFAULT 0
        );""")
        
        # 3. TABELA DE TRANSAÇÕES (Corrigida)
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

        # 4. TABELA DE SNAPSHOTS / FP&A (Agora isolada corretamente)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS monthly_snapshots (
            month TEXT PRIMARY KEY,
            total_income REAL,
            total_expense REAL,
            net_balance REAL,
            closed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );""")

        # 5. TABELA DE PLANEJAMENTO CONJUNTO (FP&A)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS fpa_planning (
            notion_id TEXT PRIMARY KEY,
            item TEXT NOT NULL,
            data_prevista TEXT,
            valor REAL,
            status TEXT,
            tipo_movimento TEXT,
            tipo_transacao TEXT
        );""")
        
        conn.commit()
        