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
    /* Estilo das abas principais */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# Garante a existência do banco base
db.init_db()

# --- ATUALIZAÇÃO SILENCIOSA DO SCHEMA (FP&A) ---
# Cria a tabela de fechamento de mês sem precisar alterar o db.py
conn = db.get_connection()
conn.cursor().execute("""
CREATE TABLE IF NOT EXISTS monthly_snapshots (
    month TEXT PRIMARY KEY,
    total_income REAL,
    total_expense REAL,
    net_balance REAL,
    closed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")
conn.commit()
conn.close()

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

# Variáveis globais para o Snapshot
receitas_globais = df_kpi[df_kpi['type'] == 'Receita']['amount'].sum()
despesas_globais = df_kpi[df_kpi['type'] == 'Despesa']['amount'].sum()
saldo_liquido_global = receitas_globais - despesas_globais

# =========================================================
# NAVEGAÇÃO PRINCIPAL (ABAS)
# =========================================================
tab_dash, tab_fpa = st.tabs(["📊 Master Dashboard", "🔮 FP&A & Simulações"])

with tab_dash:
    # --- SESSÃO 1: CONTAS (Na ordem solicitada) ---
    st.markdown("### 🏦 Contas")

    def get_saldo_conta(substring):
        acc = df_acc[df_acc['name'].str.contains(substring, case=False, na=False)]
        if acc.empty: return 0.0
        acc_id = acc.iloc[0]['notion_id']
        tx_conta = df_tx[df_tx['account_id'] == acc_id] # Histórico total
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

    df_despesas_reais = df_kpi[(df_kpi['type'] == 'Despesa') & (df_kpi['movement_type'] != 'Pagamento de fatura')]
    df_pie = df_despesas_reais.groupby('category_name')['amount'].sum().reset_index()
    df_pie = df_pie[df_pie['amount'] > 0].sort_values('amount', ascending=False)

    col_g1, col_g2 = st.columns(2)

    with col_g1:
        if not df_pie.empty:
            total_gasto_str = f"R$ {df_pie['amount'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            # Criação do gráfico com as variáveis mapeadas corretamente
            fig_pie = px.pie(
                df_pie, names='category_name', values='amount', hole=0.75,
                color_discrete_sequence=px.colors.qualitative.Bold,
                labels={'category_name': 'Categoria', 'amount': 'Total'}
            )
            # Limpeza do Tooltip (Hover) e das fatias externas
            fig_pie.update_traces(
                textposition='outside', 
                textinfo='percent+label', 
                textfont_size=13,
                hovertemplate="<b>%{label}</b><br>Gasto: R$ %{value:,.2f}<br>Fatia: %{percent}<extra></extra>"
            )
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
                # Calcula o progresso e trava visualmente em 1.0 (100%) para não quebrar a UI
                df_orc['progresso'] = (df_orc['amount'] / df_orc['monthly_budget']).clip(upper=1.0)
                view_orc = df_orc[['name', 'monthly_budget', 'amount', 'progresso']].copy()
                
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

with tab_fpa:
    st.markdown("### 🔮 Projeção de Fluxo de Caixa (O Fim do Excel)")
    st.markdown("Visão automática baseada na base 'Planejamento Conjunto' do Notion.")
    st.divider()

    # 1. Puxar os dados da nova tabela
    conn = db.get_connection()
    df_fpa = pd.read_sql_query("SELECT * FROM fpa_planning", conn)
    conn.close()

    if df_fpa.empty:
        st.info("Sincronize o Notion para carregar o seu Planejamento Conjunto.")
    else:
        # 2. Tratamento Matemático e de Tempo
        df_fpa['Data'] = pd.to_datetime(df_fpa['data_prevista']).dt.date
        df_fpa['Mês_Idx'] = pd.to_datetime(df_fpa['data_prevista']).dt.to_period('M')
        df_fpa['Mês_Label'] = df_fpa['Mês_Idx'].dt.strftime('%b/%Y')

        # Blindagem Matemática: Garante que toda 'Despesa' seja negativa no cálculo
        df_fpa['Valor Ajustado'] = df_fpa.apply(
            lambda x: -abs(x['valor']) if x['tipo_transacao'] == 'Despesa' else abs(x['valor']), axis=1
        )

        col_input, col_space = st.columns([1, 3])
        with col_input:
            # Você insere o saldo que tem no banco hoje para a cascata começar certa
            saldo_inicial_base = st.number_input("Saldo em Caixa Atual (R$)", value=4000.0, step=100.0)

        # 3. Lógica em Cascata (O motor do Saldo Acumulado)
        meses_ordenados = sorted(df_fpa['Mês_Idx'].unique())
        saldo_atual = saldo_inicial_base
        
        cascata_dados = []
        for mes in meses_ordenados:
            df_mes = df_fpa[df_fpa['Mês_Idx'] == mes]
            entradas = df_mes[df_mes['tipo_transacao'] == 'Receita']['Valor Ajustado'].sum()
            saidas = df_mes[df_mes['tipo_transacao'] == 'Despesa']['Valor Ajustado'].sum()
            geracao = entradas + saidas
            saldo_final = saldo_atual + geracao
            
            cascata_dados.append({
                'Mês': mes.strftime('%b/%Y'),
                '1. Saldo Inicial': saldo_atual,
                '2. Entradas': entradas,
                '3. Saídas': saidas,
                '4. Geração de Caixa': geracao,
                '5. Saldo Final': saldo_final
            })
            saldo_atual = saldo_final # Empurra o saldo para o mês seguinte

        df_cascata = pd.DataFrame(cascata_dados).set_index('Mês').T

        # 4. Renderização do Fechamento (O bloco inferior do seu Excel)
        st.markdown("#### 🎯 Fechamento Consolidado (Caixa)")
        st.dataframe(df_cascata.style.format("R$ {:,.2f}"), use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # 5. Renderização do Detalhe (O bloco superior do seu Excel)
        st.markdown("#### 📋 Detalhamento Previsto (Entradas e Saídas)")
        
        # Cria a Pivot Table (Tabela Dinâmica) igualzinha ao seu Excel
        pivot_fpa = pd.pivot_table(
            df_fpa,
            values='Valor Ajustado',
            index=['tipo_transacao', 'tipo_movimento', 'item'],
            columns='Mês_Label',
            aggfunc='sum',
            fill_value=0
        )
        
        # Ordena as colunas cronologicamente
        colunas_ordenadas = [m.strftime('%b/%Y') for m in meses_ordenados]
        pivot_fpa = pivot_fpa.reindex(columns=colunas_ordenadas)
        
        st.dataframe(pivot_fpa.style.format("R$ {:,.2f}"), use_container_width=True)
