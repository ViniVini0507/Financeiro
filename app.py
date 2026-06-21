import streamlit as st
import pandas as pd
import plotly.express as px
import db
import sync

# --- 1. CONFIGURAÇÃO PREMIUM (Estilo Notion Dark Mode) ---
st.set_page_config(layout="wide", page_title="Financeiro", page_icon="💰")

st.markdown("""
<style>
    /* Estilização dos Cards de Contas (Topo) */
    [data-testid="metric-container"] {
        background-color: #1a1a1a;
        border: 1px solid #333;
        padding: 1.2rem;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    [data-testid="metric-container"] label {
        font-size: 15px !important;
        font-weight: 500 !important;
        color: #a0a0a0 !important;
    }
    [data-testid="metric-container"] div {
        font-weight: 700 !important;
        color: #e0e0e0 !important;
    }
    /* Arredondamento e estilo das tabelas nativas */
    [data-testid="stDataFrame"] {
        border-radius: 8px;
        border: 1px solid #333;
    }
</style>
""", unsafe_allow_html=True)

db.init_db()

with st.sidebar:
    st.title("⚙️ Controle")
    if st.button("🔄 Sincronizar Notion", use_container_width=True):
        with st.spinner("Sincronizando com a fonte da verdade..."):
            sync.run_sync()
            st.success("Dados Atualizados!")
            st.rerun()

# --- 2. INGESTÃO DE DADOS ---
conn = db.get_connection()
query_tx = """
    SELECT t.*, c.name as category_name 
    FROM transactions t
    LEFT JOIN categories c ON t.category_id = c.notion_id
"""
df_tx = pd.read_sql_query(query_tx, conn)
df_cat = pd.read_sql_query("SELECT * FROM categories", conn)
df_acc = pd.read_sql_query("SELECT * FROM accounts", conn)
conn.close()

if df_tx.empty:
    st.info("👋 Banco de dados vazio. Clique em 'Sincronizar Notion' na barra lateral.")
    st.stop()

# --- 3. FILTRO EUR (A BLACKLIST) ---
# Identifica contas Euro e exclui as transações e as próprias contas do cache em memória
eur_acc_ids = df_acc[df_acc['name'].str.contains('EUR', case=False, na=False)]['notion_id'].dropna().tolist()
df_acc = df_acc[~df_acc['notion_id'].isin(eur_acc_ids)]
df_tx = df_tx[~df_tx['account_id'].isin(eur_acc_ids)]

# --- PREPARAÇÃO ---
df_tx['category_name'] = df_tx['category_name'].fillna("Sem Categoria")
df_tx['effective_month'] = df_tx['effective_date'].str[:7]
months = sorted(df_tx['effective_month'].dropna().unique(), reverse=True)

# --- 4. CABEÇALHO E FILTROS GLOBAIS ---
col_title, col_f1, col_f2 = st.columns([2, 1, 1])
with col_title:
    st.title("Financeiro")
with col_f1:
    selected_month = st.selectbox("📅 Competência", months if len(months) > 0 else ["Atual"], label_visibility="collapsed")
with col_f2:
    context_list = []
    for ctx in ["Dia a dia", "Todos os Contextos"] + list(df_tx['context'].dropna().unique()):
        if ctx not in context_list: context_list.append(ctx)
    selected_context = st.selectbox("Contexto", context_list, label_visibility="collapsed")

# Aplica filtros de competência
filtered_tx = df_tx[df_tx['effective_month'] == selected_month]
if selected_context != "Todos os Contextos":
    filtered_tx = filtered_tx[filtered_tx['context'] == selected_context]

df_kpi = filtered_tx[filtered_tx['type'] != 'Transferência']


# =========================================================
# MASTER DASHBOARD (ESPELHAMENTO NOTION)
# =========================================================

# --- SESSÃO 1: CONTAS (Na ordem solicitada) ---
st.markdown("### 🏦 Contas")

def get_saldo_conta(substring):
    acc = df_acc[df_acc['name'].str.contains(substring, case=False, na=False)]
    if acc.empty: return 0.0
    acc_id = acc.iloc[0]['notion_id']
    tx_conta = df_tx[df_tx['account_id'] == acc_id] # Pega o histórico total (ignora filtro de mês)
    rec = tx_conta[tx_conta['type'] == 'Receita']['amount'].sum()
    desp = tx_conta[tx_conta['type'] == 'Despesa']['amount'].sum()
    return acc.iloc[0]['initial_balance'] + rec - desp

c1, c2, c3, c4 = st.columns(4)
c1.metric("🟠 Itaú BRL", f"R$ {get_saldo_conta('Itaú BRL'):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
c2.metric("🟢 VR Pluxee", f"R$ {get_saldo_conta('VR'):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
c3.metric("🔴 VA Sodexo", f"R$ {get_saldo_conta('VA'):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
c4.metric("🔸 Cartão Itaú", f"R$ {get_saldo_conta('Cartão'):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

st.markdown("<br>", unsafe_allow_html=True)


# --- SESSÃO 2: GASTOS GERAIS ---
st.markdown("### 📊 Gastos gerais por categoria")

# Isola despesas e remove pagamento de fatura para não duplicar
df_despesas_reais = df_kpi[(df_kpi['type'] == 'Despesa') & (df_kpi['movement_type'] != 'Pagamento de fatura')]
df_pie = df_despesas_reais.groupby('category_name')['amount'].sum().reset_index()
df_pie = df_pie[df_pie['amount'] > 0].sort_values('amount', ascending=False)

col_g1, col_g2 = st.columns(2)

with col_g1:
    if not df_pie.empty:
        total_gasto_str = f"R$ {df_pie['amount'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        fig_pie = px.pie(
            df_pie, names='category_name', values='amount', hole=0.75,
            color_discrete_sequence=px.colors.qualitative.Bold
        )
        # Traz as linhas para fora, replicando a estética exata da sua imagem
        fig_pie.update_traces(textposition='outside', textinfo='percent+label', textfont_size=13)
        fig_pie.update_layout(
            showlegend=False, 
            margin=dict(t=20, b=20, l=20, r=20),
            paper_bgcolor="rgba(0,0,0,0)", 
            plot_bgcolor="rgba(0,0,0,0)",
            annotations=[dict(text=f"<b>{total_gasto_str}</b>", x=0.5, y=0.5, font_size=24, font_color="white", showarrow=False)]
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("Nenhuma despesa para consolidar neste mês.")

with col_g2:
    if not df_pie.empty:
        # Tabela simplificada replicando a visão em lista do Notion
        st.dataframe(
            df_pie,
            column_config={
                "category_name": st.column_config.TextColumn("Categoria"),
                "amount": st.column_config.NumberColumn("Total", format="R$ %.2f")
            },
            hide_index=True, use_container_width=True
        )

st.markdown("<br>", unsafe_allow_html=True)


# --- SESSÃO 3: ORÇAMENTOS & TRANSAÇÕES LADO A LADO ---
col_orc, col_tx = st.columns(2)

with col_orc:
    st.markdown("### 🏷️ Categorias e Orçamentos")
    if not df_cat.empty:
        gastos_por_cat = df_despesas_reais.groupby('category_id')['amount'].sum().reset_index()
        df_orc = pd.merge(df_cat, gastos_por_cat, left_on='notion_id', right_on='category_id', how='left')
        df_orc['amount'] = df_orc['amount'].fillna(0)
        df_orc = df_orc[df_orc['monthly_budget'] > 0].copy()
        
        if not df_orc.empty:
            df_orc['progresso'] = df_orc['amount'] / df_orc['monthly_budget']
            view_orc = df_orc[['name', 'monthly_budget', 'amount', 'progresso']].copy()
            
            # DataFrame com Progress Bar Nativo
            st.dataframe(
                view_orc.sort_values('progresso', ascending=False),
                column_config={
                    "name": st.column_config.TextColumn("Aa Categoria"),
                    "monthly_budget": st.column_config.NumberColumn("# Orçamento", format="R$ %.2f"),
                    "amount": st.column_config.NumberColumn("Σ Gastos", format="R$ %.2f"),
                    "progresso": st.column_config.ProgressColumn("Σ Progresso", format="%.0%", min_value=0, max_value=1.0)
                },
                hide_index=True, use_container_width=True
            )
        else:
            st.info("Nenhum orçamento configurado.")

with col_tx:
    st.markdown("### 💸 Transações")
    view_tx = filtered_tx[['purchase_date', 'description', 'category_name', 'amount', 'account_id']].copy()
    
    # Resolve IDs das contas para os nomes de exibição reais
    acc_map = df_acc.set_index('notion_id')['name'].to_dict()
    view_tx['account_id'] = view_tx['account_id'].map(acc_map).fillna('-')
    
    st.dataframe(
        view_tx.sort_values('purchase_date', ascending=False),
        column_config={
            "purchase_date": st.column_config.DateColumn("Data", format="DD/MM"),
            "description": st.column_config.TextColumn("Aa Descrição"),
            "category_name": st.column_config.TextColumn("Categoria"),
            "amount": st.column_config.NumberColumn("# Valor", format="R$ %.2f"),
            "account_id": st.column_config.TextColumn("Conta")
        },
        hide_index=True, use_container_width=True
    )
    