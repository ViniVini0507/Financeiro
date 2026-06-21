import streamlit as st
import pandas as pd
import plotly.express as px
import db
import sync

# Configuração de página mais limpa
st.set_page_config(layout="wide", page_title="Financeiro SSOT", page_icon="💸")

db.init_db()

with st.sidebar:
    st.title("⚙️ Controle")
    if st.button("🔄 Sincronizar Notion", use_container_width=True):
        with st.spinner("Puxando e normalizando dados..."):
            sync.run_sync()
            st.success("Dados Atualizados!")
            st.rerun() # Força a tela a piscar e mostrar os dados novos na hora

# Ingestão de dados com JOIN
conn = db.get_connection()
query = """
    SELECT t.*, c.name as category_name 
    FROM transactions t
    LEFT JOIN categories c ON t.category_id = c.notion_id
"""
df_tx = pd.read_sql_query(query, conn)
df_cat = pd.read_sql_query("SELECT * FROM categories", conn)
df_acc = pd.read_sql_query("SELECT * FROM accounts", conn)
conn.close()

if df_tx.empty:
    st.info("👋 Bem-vindo! Clique em 'Sincronizar Notion' na barra lateral para carregar seus dados.")
    st.stop()

# TRATAMENTO DE ERROS: Garante que categorias vazias não quebrem o app
df_tx['category_name'] = df_tx['category_name'].fillna("Sem Categoria")
df_tx['effective_month'] = df_tx['effective_date'].str[:7]
months = sorted(df_tx['effective_month'].dropna().unique(), reverse=True)

st.title("📊 Visão Financeira")

# Filtros Globais Preservados
c1, c2 = st.columns(2)
with c1:
    selected_month = st.selectbox("Mês de Competência", months if len(months) > 0 else ["Atual"])
with c2:
    contextos = ["Todos"] + list(df_tx['context'].dropna().unique())
    selected_context = st.selectbox("Contexto", contextos)

# Aplicação dos Filtros
filtered_tx = df_tx[df_tx['effective_month'] == selected_month]
if selected_context != "Todos":
    filtered_tx = filtered_tx[filtered_tx['context'] == selected_context]

# Remover transferências da visão de lucro/prejuízo
df_kpi = filtered_tx[filtered_tx['type'] != 'Transferência']

# --- NAVEGAÇÃO POR ABAS (FASE 2) ---
tab_home, tab_tx, tab_orcamento, tab_contas = st.tabs([
    "📈 Dashboard", "📝 Transações", "🎯 Orçamentos", "🏦 Contas"
])

with tab_home:
    # KPIs Modernizados
    receitas = df_kpi[df_kpi['type'] == 'Receita']['amount'].sum()
    despesas = df_kpi[df_kpi['type'] == 'Despesa']['amount'].sum()
    saldo_liquido = receitas - despesas

    k1, k2, k3 = st.columns(3)
    k1.metric("Entradas do Mês", f"R$ {receitas:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    k2.metric("Saídas do Mês", f"R$ {despesas:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    k3.metric("Líquido", f"R$ {saldo_liquido:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    st.markdown("---")
    g1, g2 = st.columns([2, 1])
    
    with g1:
        st.subheader("Evolução Diária (Despesas)")
        df_line = df_kpi[df_kpi['type'] == 'Despesa'].groupby('purchase_date')['amount'].sum().reset_index()
        if not df_line.empty:
            fig_line = px.line(df_line, x='purchase_date', y='amount', markers=True, color_discrete_sequence=['#e74c3c'])
            fig_line.update_layout(xaxis_title="Data", yaxis_title="Valor (R$)")
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("Sem despesas registradas para exibir no gráfico.")
            
    with g2:
        st.subheader("Gastos por Categoria")
        # Regra: Remover "Pagamento de fatura" para não duplicar
        df_despesas_reais = df_kpi[
            (df_kpi['type'] == 'Despesa') & 
            (df_kpi['movement_type'] != 'Pagamento de fatura')
        ]
        
        df_pie = df_despesas_reais.groupby('category_name')['amount'].sum().reset_index()
        df_pie = df_pie[df_pie['amount'] > 0] # Filtra zerados
        
        if not df_pie.empty:
            fig_pie = px.pie(df_pie, names='category_name', values='amount', hole=0.4)
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            fig_pie.update_layout(showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Sem dados suficientes para o gráfico de categorias.")

with tab_tx:
    st.subheader("Extrato de Transações")
    # Tabela nativa do Streamlit com ordenação
    view_df = filtered_tx[['purchase_date', 'description', 'category_name', 'type', 'amount', 'context']].copy()
    view_df.columns = ['Data', 'Descrição', 'Categoria', 'Tipo', 'Valor', 'Contexto']
    st.dataframe(view_df.sort_values('Data', ascending=False), use_container_width=True, hide_index=True)

with tab_orcamento:
    st.subheader("Progresso dos Orçamentos")
    if not df_cat.empty:
        # Pega as despesas reais e cruza com a tabela de categorias
        gastos_por_cat = df_despesas_reais.groupby('category_id')['amount'].sum().reset_index()
        df_orc = pd.merge(df_cat, gastos_por_cat, left_on='notion_id', right_on='category_id', how='left')
        df_orc['amount'] = df_orc['amount'].fillna(0)
        
        tem_orcamento = False
        for _, row in df_orc[df_orc['monthly_budget'] > 0].iterrows():
            tem_orcamento = True
            orcamento = row['monthly_budget']
            gasto = row['amount']
            progresso = min(gasto / orcamento, 1.0)
            
            st.markdown(f"**{row['name']}** (R$ {gasto:,.2f} / R$ {orcamento:,.2f})")
            
            # Muda a cor da barra dependendo de quão perto está de estourar
            if progresso < 0.8:
                st.progress(progresso)
            else:
                # Streamlit não tem barra vermelha nativa fácil, então usamos um truque de emoji/aviso
                st.progress(progresso)
                if progresso >= 1.0:
                    st.error("Orçamento Estourado!")
                else:
                    st.warning("Atenção: Próximo do limite.")
        
        if not tem_orcamento:
            st.info("Você não definiu 'Orçamento Mensal' para nenhuma categoria no Notion.")
    else:
        st.info("Nenhuma categoria carregada.")

with tab_contas:
    st.subheader("Saldos das Contas (Visão Simplificada)")
    st.markdown("*(Nota: Na Fase 3 implementaremos a transferência intra-contas. Por enquanto é um cálculo direto de Entradas vs Saídas por conta).*")
    
    # Para saldo, olhamos a vida inteira da conta, não só o mês atual
    for _, acc in df_acc.iterrows():
        tx_conta = df_tx[df_tx['account_id'] == acc['notion_id']]
        receitas_conta = tx_conta[tx_conta['type'] == 'Receita']['amount'].sum()
        despesas_conta = tx_conta[tx_conta['type'] == 'Despesa']['amount'].sum()
        
        saldo_atual = acc['initial_balance'] + receitas_conta - despesas_conta
        st.metric(f"🏦 {acc['name']} ({acc['type']})", f"R$ {saldo_atual:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        