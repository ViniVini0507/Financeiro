import os
from datetime import datetime
from dateutil.relativedelta import relativedelta
import db
import notion_client

def run_sync():
    db.init_db()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # 1. Sync Contas
    account_pages = notion_client.fetch_database_pages(os.getenv("DB_CONTAS_ID", ""))
    for p in account_pages:
        nid = p["id"]
        name = notion_client.extract_property(p, "Conta", "title")
        init_bal = notion_client.extract_property(p, "Saldo Inicial", "number")
        curr = notion_client.extract_property(p, "Moeda Principal", "select") or "BRL"
        tp = notion_client.extract_property(p, "Tipo", "select") or "Conta Corrente"
        due = notion_client.extract_property(p, "Dia do vencimento", "number")
        close = notion_client.extract_property(p, "Dia do fechamento", "number")
        lim = notion_client.extract_property(p, "Limite", "number")
        
        cursor.execute("""
            INSERT OR REPLACE INTO accounts (notion_id, name, initial_balance, currency, type, due_day, closing_day, credit_limit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (nid, name, init_bal, curr, tp, due, close, lim))
        
    # 2. Sync Categorias
    cat_pages = notion_client.fetch_database_pages(os.getenv("DB_CATEGORIAS_ID", ""))
    for p in cat_pages:
        cursor.execute("INSERT OR REPLACE INTO categories VALUES (?, ?, ?, ?)", (
            p["id"],
            notion_client.extract_property(p, "Categoria", "title"),
            notion_client.extract_property(p, "Tipo", "select"),
            notion_client.extract_property(p, "Orçamento Mensal", "number")
        ))

    # 3. Sync Transações (Com expansão de parcelas nativa em memória de cache)
    tx_pages = notion_client.fetch_database_pages(os.getenv("DB_TRANSACOES_ID", ""))
    for p in tx_pages:
        nid = p["id"]
        desc = notion_client.extract_property(p, "Descrição", "title")
        txtype = notion_client.extract_property(p, "Tipo de Transação", "select") or "Despesa"
        p_date_str = notion_client.extract_property(p, "Data da compra", "date") or datetime.now().strftime("%Y-%m-%d")
        p_date = datetime.strptime(p_date_str[:10], "%Y-%m-%d").date()
        amt = notion_client.extract_property(p, "Valor", "number") or 0.0
        inst_count = int(notion_client.extract_property(p, "Parcelas (Qtd)", "number") or 1)
        gen_inst = notion_client.extract_property(p, "Gerar Parcelas", "checkbox")
        mov = notion_client.extract_property(p, "Movimento", "select") or "Compra"
        ctx = notion_client.extract_property(p, "Contexto", "select") or "Dia a dia"
        acc_id = notion_client.extract_property(p, "Contas", "relation")
        inv_id = notion_client.extract_property(p, "Faturas", "relation")

        # Buscar dados de fechamento da conta para a competência
        cursor.execute("SELECT closing_day FROM accounts WHERE notion_id = ?", (acc_id,))
        acc_row = cursor.fetchone()
        closing_day = acc_row["closing_day"] if acc_row else None
        
        # Algoritmo de Ingestão de Parcelas Virtualizadas
        loops = inst_count if gen_inst else 1
        for i in range(loops):
            current_p_date = p_date + relativedelta(months=i)
            # Calcular competência efetiva (Regra 4.1)
            if closing_day and current_p_date.day >= closing_day:
                eff_date = (current_p_date + relativedelta(months=1)).replace(day=1)
            else:
                eff_date = current_p_date.replace(day=1)
                
            unique_id = f"{nid}_p{i+1}" if i > 0 else nid
            display_desc = f"{desc} ({i+1}/{inst_count})" if i > 0 else desc
            
            cursor.execute("""
                INSERT OR REPLACE INTO transactions (notion_id, description, type, purchase_date, effective_date, amount, installments_count, movement_type, context, account_id, invoice_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (unique_id, display_desc, txtype, current_p_date.strftime("%Y-%m-%d"), eff_date.strftime("%Y-%m-%d"), amt/loops if gen_inst else amt, inst_count, mov, ctx, acc_id, inv_id))

    conn.commit()
    conn.close()