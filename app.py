import streamlit as st
import pandas as pd
import plotly.express as px
import db
import sync


db.init_db()

with st.sidebar:
    st.title("⚙️ Controle")
    if st.button("🔄 Sincronizar Notion", use_container_width=True):
        with st.spinner("Puxando e normalizando dados..."):
            sync.run_sync()
            st.success("Dados Atualizados!")

# Carregar dados fazendo um JOIN para trazer o nome da categoria para a UI
conn = db.get_connection()
query = """
    SELECT t.*, c.name as category_name 
    FROM transactions t
    LEFT JOIN categories c ON t.category_id = c.notion_id
"""
df_tx = pd.read_sql_query(query, conn)
conn.close()

st.title("📊 Visão Consolidada")

if df_tx.empty:
    st.warning("Banco de dados vazio. Sincronize com o Notion na barra lateral.")
else:
    # Cria coluna no formato YYYY-MM para o filtro
    df_tx['effective_month'] = df_tx['effective_date'].str[:7]
    months = sorted(df_tx['effective_month'].unique(), reverse=True)
    
    c1, c2 = st.columns(2)
    with c1:
        selected_month = st.selectbox("Mês de Competência", months)
    with c2:
        selected_context = st.selectbox("Contexto", ["Todos"] + list(df_tx['context'].dropna().unique()))

    # Filtros base
    filtered_tx = df_tx[df_tx['effective_month'] == selected_month]
    if selected_context != "Todos":
        filtered_tx = filtered_tx[filtered_tx['context'] == selected_context]
        
    # REGRA 2: Isolar transferências dos KPIs globais
    df_kpi = filtered_tx[filtered_tx['type'] != 'Transferência']

    receitas = df_kpi[df_kpi['type'] == 'Receita']['amount'].sum()
    despesas = df_kpi[df_kpi['type'] == 'Despesa']['amount'].sum()
    saldo_liquido = receitas - despesas

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Entradas", f"R$ {receitas:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    kpi2.metric("Saídas", f"R$ {despesas:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    kpi3.metric("Líquido", f"R$ {saldo_liquido:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    st.markdown("---")
    g1, g2 = st.columns([2, 1])
    
    with g1:
        st.subheader("Evolução Diária (Despesas)")
        df_line = df_kpi[df_kpi['type'] == 'Despesa'].groupby('purchase_date')['amount'].sum().reset_index()
        if not df_line.empty:
            fig_line = px.line(df_line, x='purchase_date', y='amount', markers=True, color_discrete_sequence=['#e74c3c'])
            fig_line.update_layout(xaxis_title="Data da Compra", yaxis_title="Valor (R$)")
            st.plotly_chart(fig_line, use_container_width=True)
            
    with g2:
        st.subheader("Gastos por Categoria")
        # REGRA 4: Remover "Pagamento de fatura" para o gráfico de categorias
        df_despesas_reais = df_kpi[
            (df_kpi['type'] == 'Despesa') & 
            (df_kpi['movement_type'] != 'Pagamento de fatura')
        ]
        
        if not df_despesas_reais.empty:
            df_pie = df_despesas_reais.groupby('category_name')['amount'].sum().reset_index()
            fig_pie = px.pie(df_pie, names='category_name', values='amount', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Sem despesas para categorizar neste mês.")