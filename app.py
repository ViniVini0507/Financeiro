import streamlit as st
import pandas as pd
import plotly.express as px
import db
import sync

# 1. Configuração da Página e Injeção de CSS Premium (Estilo Notion Dark Mode)
st.set_page_config(layout="wide", page_title="Financeiro", page_icon="💰")

st.markdown("""
<style>
    /* Estilização dos Cards de KPI (Simulando os cards de contas do Notion) */
    div[data-testid="metric-container"] {
        background-color: #202020;
        border: 1px solid #363636;
        padding: 15px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    div[data-testid="metric-container"] > div {
        color: #e0e0e0;
    }
    /* Estilização das abas */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: transparent;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# 2. Inicialização e Sidebar
db.init_db()

with st.sidebar:
    st.title("⚙️ Controle")
    if st.button("🔄 Sincronizar Notion", use_container_width=True):
        with st.spinner("Sincronizando com a fonte da verdade..."):
            sync.run_sync()
            st.success("Dados Atualizados!")
            st.rerun()

# 3. Ingestão de Dados e Filtro EUR
conn = db.get_connection()

query_tx = """
    SELECT t.*, c.name as category_name 
    FROM transactions t
    LEFT JOIN categories c ON t.category_id = c.notion_id
"""
df_tx = pd.read_sql_query(query_tx, conn)
df_cat = pd.read_sql_query("SELECT * FROM categories", conn)
df_acc = pd.read_sql_query("SELECT * FROM accounts", conn)
df_faturas = pd.read_sql_query("SELECT * FROM invoices", conn)
conn.close()

if df_tx.empty:
    st.info("👋 Banco de dados vazio. Sincronize com o Notion para começar.")
    st.stop()

# --- FILTRO ESTRITO BRL (Remover EUR) ---
# Filtra contas que NÃO contenham 'EUR' no nome (case insensitive)
df_acc = df_acc[~df_acc['name'].str.contains('EUR', case=False, na=False)]
valid_acc_ids = df_acc['notion_id'].tolist()
# Remove das transações qualquer coisa ligada a contas EUR
df_tx = df_tx[df_tx['account_id'].isin(valid_acc_ids)]

# --- PREPARAÇÃO DOS DADOS ---
df_tx['category_name'] = df_tx['category_name'].fillna("Sem Categoria")
df_tx['effective_month'] = df_tx['effective_date'].str[:7]
months = sorted(df_tx['effective_month'].dropna().unique(), reverse=True)

# Cabeçalho da página
st.title("Financeiro")

# Filtros Globais Modernos
col_f1, col_f2 = st.columns([1, 3])
with col_f1:
    selected_month = st.selectbox("📅 Competência", months if len(months) > 0 else ["Atual"], label_visibility="collapsed")
with col_f2:
    contextos = ["Todos os Contextos"] + list(df_tx['context'].dropna().unique())
    selected_context = st.selectbox("Contexto", contextos, label_visibility="collapsed")

# Aplicação dos Filtros de Tela
filtered_tx = df_tx[df_tx['effective_month'] == selected_month]
if selected_context != "Todos os Contextos":
    filtered_tx = filtered_tx[filtered_tx['context'] == selected_context]

df_kpi = filtered_tx[filtered_tx['type'] != 'Transferência']

# --- NAVEGAÇÃO ---
tab_home, tab_orcamento, tab_tx_list, tab_contas = st.tabs([
    "📊 Gastos & Entradas", "🎯 Categorias e Orçamentos", "💸 Transações", "🏦 Contas e Faturas"
])

with tab_home:
    # --- CARDS HORIZONTAIS DE RESUMO ---
    receitas = df_kpi[df_kpi['type'] == 'Receita']['amount'].sum()
    despesas = df_kpi[df_kpi['type'] == 'Despesa']['amount'].sum()
    saldo_liquido = receitas - despesas

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("⬇️ Entradas", f"R$ {receitas:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    k2.metric("⬆️ Saídas", f"R$ {despesas:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    k3.metric("💳 Faturas (Mês)", f"R$ {df_tx[df_tx['movement_type'] == 'Pagamento de fatura']['amount'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    k4.metric("💰 Resultado Líquido", f"R$ {saldo_liquido:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    st.markdown("<br>", unsafe_allow_html=True)

    # --- GRÁFICOS (Layout Idêntico ao seu Notion) ---
    st.markdown("#### Gastos gerais por categoria")
    
    df_despesas_reais = df_kpi[(df_kpi['type'] == 'Despesa') & (df_kpi['movement_type'] != 'Pagamento de fatura')]
    df_pie = df_despesas_reais.groupby('category_name')['amount'].sum().reset_index()
    df_pie = df_pie[df_pie['amount'] > 0].sort_values('amount', ascending=False)
    
    if not df_pie.empty:
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            # Gráfico Donut com Valor Central
            total_gasto_str = f"R$ {df_pie['amount'].sum():,.0f}".replace(",", ".")
            fig_pie = px.pie(df_pie, names='category_name', values='amount', hole=0.65)
            fig_pie.update_traces(textposition='outside', textinfo='percent+label')
            fig_pie.update_layout(
                showlegend=False, 
                margin=dict(t=0, b=0, l=0, r=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                annotations=[dict(text=f"<b>{total_gasto_str}</b>", x=0.5, y=0.5, font_size=24, showarrow=False)]
            )
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with col_g2:
            # Gráfico de Barras Horizontais (Ranking)
            fig_bar = px.bar(
                df_pie.sort_values('amount', ascending=True), # Sort asc for horizontal top-down
                x='amount', y='category_name', orientation='h', text_auto='.2s'
            )
            fig_bar.update_traces(textfont_size=12, textangle=0, textposition="outside", cliponaxis=False)
            fig_bar.update_layout(
                xaxis_title="", yaxis_title="", 
                showlegend=False,
                margin=dict(t=0, b=0, l=0, r=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=True, gridcolor='#333', zeroline=False)
            )
            st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("Sem dados de gastos para exibir neste mês.")

with tab_orcamento:
    st.markdown("#### Progresso dos Orçamentos")
    
    if not df_cat.empty:
        gastos_por_cat = df_despesas_reais.groupby('category_id')['amount'].sum().reset_index()
        df_orc = pd.merge(df_cat, gastos_por_cat, left_on='notion_id', right_on='category_id', how='left')
        df_orc['amount'] = df_orc['amount'].fillna(0)
        
        # Filtra apenas categorias que possuem orçamento definido
        df_orc = df_orc[df_orc['monthly_budget'] > 0].copy()
        
        if not df_orc.empty:
            df_orc['progresso'] = df_orc['amount'] / df_orc['monthly_budget']
            
            # Prepara o dataframe final de visualização
            view_orc = df_orc[['name', 'monthly_budget', 'amount', 'progresso']].copy()
            view_orc.columns = ['Categoria', 'Orçamento', 'Gasto', 'Progresso']
            
            # A MÁGICA DE UI: Tabela interativa com barra de progresso nativa!
            st.dataframe(
                view_orc.sort_values('Progresso', ascending=False),
                column_config={
                    "Categoria": st.column_config.TextColumn("Aa Categoria"),
                    "Orçamento": st.column_config.NumberColumn("# Orçamento", format="R$ %.2f"),
                    "Gasto": st.column_config.NumberColumn("Σ Gastos", format="R$ %.2f"),
                    "Progresso": st.column_config.ProgressColumn(
                        "Σ Progresso",
                        help="Uso do orçamento no mês",
                        format="%.0%",
                        min_value=0,
                        max_value=1.0,
                    ),
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("Você não definiu 'Orçamento Mensal' para nenhuma categoria.")

with tab_tx_list:
    st.markdown("#### Histórico do Mês")
    view_df = filtered_tx[['purchase_date', 'description', 'category_name', 'amount', 'account_id']].copy()
    
    # Substitui o account_id pelo nome da conta
    acc_map = df_acc.set_index('notion_id')['name'].to_dict()
    view_df['account_id'] = view_df['account_id'].map(acc_map)
    
    view_df.columns = ['Data', 'Descrição', 'Categoria', 'Valor', 'Conta']
    
    st.dataframe(
        view_df.sort_values('Data', ascending=False),
        column_config={
            "Data": st.column_config.DateColumn("🗓️ Data", format="DD/MM/YYYY"),
            "Descrição": st.column_config.TextColumn("Aa Descrição"),
            "Categoria": st.column_config.TextColumn("🏷️ Categoria"),
            "Valor": st.column_config.NumberColumn("# Valor", format="R$ %.2f"),
            "Conta": st.column_config.TextColumn("🏦 Conta")
        },
        use_container_width=True, 
        hide_index=True
    )

with tab_contas:
    col_c1, col_c2 = st.columns(2)
    
    with col_c1:
        st.markdown("#### 🏦 Saldos das Contas")
        for _, acc in df_acc.iterrows():
            tx_conta = df_tx[df_tx['account_id'] == acc['notion_id']]
            receitas_conta = tx_conta[tx_conta['type'] == 'Receita']['amount'].sum()
            despesas_conta = tx_conta[tx_conta['type'] == 'Despesa']['amount'].sum()
            
            saldo_atual = acc['initial_balance'] + receitas_conta - despesas_conta
            st.metric(f"{acc['name']} ({acc['type']})", f"R$ {saldo_atual:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            st.divider()

    with col_c2:
        st.markdown("#### 💳 Faturas em Aberto")
        if not df_faturas.empty:
            df_faturas_view = pd.merge(df_faturas, df_acc[['notion_id', 'name']], left_on='account_id', right_on='notion_id', how='inner', suffixes=('', '_acc'))
            
            for _, fatura in df_faturas_view.iterrows():
                tx_fatura = df_tx[df_tx['invoice_id'] == fatura['notion_id']]
                total_compras = tx_fatura[tx_fatura['movement_type'] == 'Compra']['amount'].sum()
                total_pagos = tx_fatura[tx_fatura['movement_type'] == 'Pagamento de fatura']['amount'].sum()
                em_aberto = total_compras - total_pagos
                
                status = fatura['status'] if pd.notna(fatura['status']) and fatura['status'] != "" else "Aberta"
                
                st.metric(f"{fatura['name']} ({fatura.get('name_acc', '')}) - {status}", f"R$ {em_aberto:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                st.caption(f"Compras: R$ {total_compras:,.2f} | Pagos: R$ {total_pagos:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                st.divider()
