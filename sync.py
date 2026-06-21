import os
from datetime import datetime
from dateutil.relativedelta import relativedelta
import db
import notion_client

def run_sync():
    db.init_db() # Garante que o banco existe
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # 1. Sync Categorias (Fazemos primeiro para podermos ler os nomes depois)
    cat_pages = notion_client.fetch_database_pages(os.getenv("DB_CATEGORIAS_ID", ""))
    categorias_map = {} # Cache em memória para olhar o nome da categoria rapidamente
    
    for p in cat_pages:
        cid = p["id"]
        cname = notion_client.extract_property(p, "Categoria", "title")
        ctype = notion_client.extract_property(p, "Tipo", "select")
        cbudget = notion_client.extract_property(p, "Orçamento Mensal", "number")
        
        categorias_map[cid] = cname
        cursor.execute(
            "INSERT OR REPLACE INTO categories VALUES (?, ?, ?, ?)", 
            (cid, cname, ctype, cbudget)
        )

    # 2. Sync Contas
    account_pages = notion_client.fetch_database_pages(os.getenv("DB_CONTAS_ID", ""))
    for p in account_pages:
        cursor.execute("""
            INSERT OR REPLACE INTO accounts (notion_id, name, initial_balance, type, due_day, closing_day, credit_limit)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            p["id"],
            notion_client.extract_property(p, "Conta", "title"),
            notion_client.extract_property(p, "Saldo Inicial", "number"),
            notion_client.extract_property(p, "Tipo", "select") or "Conta Corrente",
            notion_client.extract_property(p, "Dia do vencimento", "number"),
            notion_client.extract_property(p, "Dia do fechamento", "number"),
            notion_client.extract_property(p, "Limite", "number")
        ))
        
    # 3. Sync Transações (Com regras de parcelas e transferências)
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
        cat_id = notion_client.extract_property(p, "Categorias e Orçamentos", "relation")

        # REGRA 2: Transformar 'Transferência Interna' fisicamente no banco
        cat_name = categorias_map.get(cat_id, "")
        if cat_name == "Transferência Interna":
            txtype = "Transferência"

        # Buscar dia de fechamento para a competência
        cursor.execute("SELECT closing_day FROM accounts WHERE notion_id = ?", (acc_id,))
        acc_row = cursor.fetchone()
        closing_day = acc_row["closing_day"] if acc_row else None
        
        # Algoritmo de Ingestão de Parcelas Virtualizadas
        loops = inst_count if gen_inst else 1
        for i in range(loops):
            current_p_date = p_date + relativedelta(months=i)
            
            # Cálculo de competência
            if closing_day and current_p_date.day >= closing_day:
                eff_date = (current_p_date + relativedelta(months=1)).replace(day=1)
            else:
                eff_date = current_p_date.replace(day=1)
                
            unique_id = f"{nid}_p{i+1}" if i > 0 else nid
            display_desc = f"{desc} ({i+1}/{inst_count})" if i > 0 else desc
            
            cursor.execute("""
                INSERT OR REPLACE INTO transactions 
                (notion_id, description, type, purchase_date, effective_date, amount, installments_count, movement_type, context, account_id, category_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (unique_id, display_desc, txtype, current_p_date.strftime("%Y-%m-%d"), eff_date.strftime("%Y-%m-%d"), amt/loops if gen_inst else amt, inst_count, mov, ctx, acc_id, cat_id))

    conn.commit()
    conn.close()