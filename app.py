import streamlit as st
import pandas as pd
import plotly.express as px
import db
import sync

st.set_page_config(layout="wide", page_title="Financeiro Inteligente")

# Inicialização do banco local de forma invisível
db.init_db()

with st.sidebar:
    st.title("⚙️ Controle")
    if st.button("🔄 Sincronizar com Notion", use_container_width=True):
        with st.spinner("Puxando dados brutos do Notion..."):
            sync.run_sync()
            st.success("Cache Local Atualizado!")

# Ingestão para Dataframes
conn = db.get_connection()
df_tx = pd.read_sql_query("SELECT * FROM transactions", conn)
df_acc = pd.read_sql_query("SELECT * FROM accounts", conn)
df_cat = pd.read_sql_query("SELECT * FROM categories", conn)
conn.close()

st.title("📊 Painel de Análise Financeira")

if df_tx.empty:
    st.warning("Banco de dados local vazio. Clique em Sincronizar com Notion na barra lateral.")
else:
    # Barra de Filtros Globais Pragmáticos
    df_tx['effective_month'] = df_tx['effective_date'].str[:7]
    months = sorted(df_tx['effective_month'].unique(), reverse=True)
    
    c1, c2, c3 = st.columns(3)
    with c1:
        selected_month = st.selectbox("Mês de Referência (Competência)", months)
    with c2:
        selected_context = st.selectbox("Contexto", ["Todos"] + list(df_tx['context'].unique()))
    with c3:
        selected_currency = st.selectbox("Moeda", ["BRL", "EUR"])

    # Filtros nos Dataframes
    filtered_tx = df_tx[df_tx['effective_month'] == selected_month]
    if selected_context != "Todos":
        filtered_tx = filtered_tx[filtered_tx['context'] == selected_context]
        
    # Resolver filtro de conta baseado na moeda escolhida
    valid_accounts = df_acc[df_acc['currency'] == selected_currency]['notion_id'].tolist()
    filtered_tx = filtered_tx[filtered_tx['account_id'].isin(valid_accounts)]

    # 4.2 Cálculos de KPIs Dinâmicos de Tela
    receitas = filtered_tx[filtered_tx['type'] == 'Receita']['amount'].sum()
    despesas = filtered_tx[filtered_tx['type'] == 'Despesa']['amount'].sum()
    saldo_liquido = receitas - despesas

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Faturamento Mensal", f"{selected_currency} {receitas:,.2f}")
    kpi2.metric("Gastos Consolidados", f"{selected_currency} {despesas:,.2f}", delta=f"-{despesas:,.2f}", delta_color="inverse")
    kpi3.metric("Resultado Líquido", f"{selected_currency} {saldo_liquido:,.2f}", delta=f"{saldo_liquido:,.2f}")

    # Renderização Gráfica Avançada
    st.markdown("---")
    g1, g2 = st.columns([2, 1])
    
    with g1:
        st.subheader("Evolução de Gastos por Dia da Compra")
        df_line = filtered_tx[filtered_tx['type'] == 'Despesa'].groupby('purchase_date')['amount'].sum().reset_index()
        if not df_line.empty:
            fig_line = px.line(df_line, x='purchase_date', y='amount', markers=True, color_discrete_sequence=['#e74c3c'])
            st.plotly_chart(fig_line, use_container_width=True)
            
    with g2:
        st.subheader("Distribuição por Tipo de Movimento")
        df_pie = filtered_tx.groupby('movement_type')['amount'].sum().reset_index()
        fig_pie = px.pie(df_pie, names='movement_type', values='amount', hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)