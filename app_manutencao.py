import streamlit as st
import pandas as pd

# Configuração da página inteira
st.set_page_config(page_title="Gestão de SLA - Manutenção", layout="wide")

st.title("🛠️ Painel Interativo de Manutenção & SLA")

# 1. Conexão direta com a planilha do Google Drive
URL_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRgqjurSWlFiWjsy3V2cpz9vju85d1-mGNB0wIucZm9Rx_Af0cweCNbXvlEIblD9TlY2bmiYVY5T4N0/pub?gid=1559301826&single=true&output=csv"

@st.cache_data(ttl=60)
def carregar_dados():
    df = pd.read_csv(URL_CSV)
    # Limpa espaços em branco extras nos nomes das colunas
    df.columns = df.columns.str.strip()
    
    # Tratamento de Data/Hora se existir
    col_data = [c for c in df.columns if 'Carimbo' in c or 'Data' in c]
    if col_data:
        df[col_data[0]] = pd.to_datetime(df[col_data[0]], dayfirst=True, errors='coerce')
        
    return df

df = carregar_dados()

# Mapeia colunas dinamicamente para evitar novos erros de KeyError
col_maquina = next((c for c in df.columns if 'Máquina' in c or 'Maquina' in c or 'Equipamento' in c), None)
col_prioridade = next((c for c in df.columns if 'Prioridade' in c), None)
col_chamado = next((c for c in df.columns if 'N°' in c or 'Chamado' in c), df.columns[0])

# Botão de atualização manual no painel
if st.sidebar.button("🔄 Atualizar Dados Agora"):
    st.cache_data.clear()
    st.rerun()

# 2. Filtros Interativos na Barra Lateral
st.sidebar.header("Filtros da Operação")

if col_maquina:
    opcoes_maquinas = df[col_maquina].dropna().unique()
    maquinas = st.sidebar.multiselect(
        "Filtrar por Máquina/Equipamento:",
        options=opcoes_maquinas,
        default=opcoes_maquinas
    )
    df_filtrado = df[df[col_maquina].isin(maquinas)]
else:
    df_filtrado = df

# 3. Indicadores Gerais em Cartões
col1, col2, col3 = st.columns(3)
col1.metric("Total de Chamados Registrados", len(df_filtrado))

# Configuração de SLA por Prioridade
st.markdown("---")
st.subheader("⏱️ Metas e Média de SLA por Prioridade")

col_alta, col_media, col_baixa = st.columns(3)

if col_prioridade:
    qtd_alta = len(df_filtrado[df_filtrado[col_prioridade].astype(str).str.contains('Alta|Urgente', case=False, na=False)])
    qtd_media = len(df_filtrado[df_filtrado[col_prioridade].astype(str).str.contains('Med|Média', case=False, na=False)])
    qtd_baixa = len(df_filtrado[df_filtrado[col_prioridade].astype(str).str.contains('Baixa', case=False, na=False)])
else:
    qtd_alta = qtd_media = qtd_baixa = 0

with col_alta:
    st.error("🚨 URGENTE / ALTA")
    st.write("**Meta de SLA:** até 2 horas")
    st.metric("Chamados na Fila", qtd_alta)

with col_media:
    st.warning("⚠️ MÉDIA")
    st.write("**Meta de SLA:** até 8 horas")
    st.metric("Chamados na Fila", qtd_media)

with col_baixa:
    st.info("🟢 BAIXA")
    st.write("**Meta de SLA:** até 24 horas")
    st.metric("Chamados na Fila", qtd_baixa)

# 4. Tabela Interativa de Pesquisa
st.markdown("---")
st.subheader("📋 Tabela Dinâmica de Chamados (Pesquisável)")

busca = st.text_input("🔍 Digite para pesquisar (Nome, Máquina ou Defeito):")

if busca:
    df_exibicao = df_filtrado[
        df_filtrado.astype(str).apply(lambda x: x.str.contains(busca, case=False)).any(axis=1)
    ]
else:
    df_exibicao = df_filtrado

st.dataframe(df_exibicao, use_container_width=True)
