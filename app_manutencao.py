import streamlit as st
import pandas as pd
import time
import streamlit.components.v1 as components

st.set_page_config(page_title="Painel de Manutenção", layout="wide")

# Recarrega a página automaticamente a cada 15 segundos sem dependência externa
components.html(
    """
    <script>
        setTimeout(function(){
            window.location.reload();
        }, 15000);
    </script>
    """,
    height=0,
    width=0
)

st.title("Painel de Manutenção")

URL_BASE = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRgqjurSWlFiWjsy3V2cpz9vju85d1-mGNB0wIucZm9Rx_Af0cweCNbXvlEIblD9TlY2bmiYVY5T4N0/pub?gid=1559301826&single=true&output=csv"

@st.cache_data(ttl=0)
def carregar_dados():
    # Bypass no cache do Google Sheets adicionando o timestamp atual na requisicao
    url_dinamica = f"{URL_BASE}&_nocache={int(time.time())}"
    df = pd.read_csv(url_dinamica)
    df.columns = df.columns.str.strip()
    
    # Mapeamento da coluna de abertura e conclusao da planilha
    col_abertura = next((c for c in df.columns if 'Carimbo' in c or 'Abertura' in c), None)
    col_conclusao = next((c for c in df.columns if 'Data de conclusão' in c or 'conclusão' in c.lower()), None)

    # Conversão das datas respeitando o formato brasileiro (dia primeiro)
    if col_abertura:
        df['Data_Abertura_dt'] = pd.to_datetime(df[col_abertura], dayfirst=True, errors='coerce')
    else:
        df['Data_Abertura_dt'] = pd.NaT

    if col_conclusao:
        df['Data_Conclusao_dt'] = pd.to_datetime(df[col_conclusao], dayfirst=True, errors='coerce')
    else:
        df['Data_Conclusao_dt'] = pd.NaT

    # Cálculo exato do tempo decorrido em horas
    def calcular_tempo_resolucao(row):
        status_str = str(row.get('Status', '')).lower()
        if pd.notnull(row['Data_Abertura_dt']) and pd.notnull(row['Data_Conclusao_dt']):
            diff_segundos = (row['Data_Conclusao_dt'] - row['Data_Abertura_dt']).total_seconds()
            if diff_segundos >= 0:
                horas = diff_segundos / 3600
                if horas < 24:
                    return f"{horas:.1f}h"
                else:
                    dias = horas / 24
                    return f"{dias:.1f} dias ({horas:.0f}h)"
        
        # Para chamados em aberto (Pendente ou Atuando), calcula o tempo decorrido ate o momento atual
        if pd.notnull(row['Data_Abertura_dt']) and 'conclu' not in status_str:
            tempo_aberto_horas = (pd.Timestamp.now() - row['Data_Abertura_dt']).total_seconds() / 3600
            return f"{tempo_aberto_horas:.1f}h (Em aberto)"
            
        return "-"

    df['Tempo Decorrido'] = df.apply(calcular_tempo_resolucao, axis=1)
    
    # Formatação amigável das datas para exibição na tabela
    df['Abertura Exibição'] = df['Data_Abertura_dt'].dt.strftime('%d/%m/%Y %H:%M').fillna('-')
    df['Conclusão Exibição'] = df['Data_Conclusao_dt'].dt.strftime('%d/%m/%Y').fillna('-')
    
    return df

df = carregar_dados()

col_status = next((c for c in df.columns if 'Status' in c or 'Situacao' in c or 'Situação' in c), None)
col_setor = next((c for c in df.columns if 'Setor' in c or 'Nome e Setor' in c), None)
col_maquina = next((c for c in df.columns if 'Máquina' in c or 'Equipamento' in c), None)
col_prioridade = next((c for c in df.columns if 'Prioridade' in c), None)
col_chamado = next((c for c in df.columns if 'N°' in c or 'Chamado' in c), df.columns[0])

if not col_status:
    df['Status'] = 'Pendente'
    col_status = 'Status'

def normalizar_status(val):
    val_str = str(val).lower()
    if 'conclu' in val_str or 'finaliz' in val_str or 'fechado' in val_str:
        return 'Concluído'
    elif 'atuando' in val_str or 'andamento' in val_str or 'em ' in val_str:
        return 'Atuando'
    else:
        return 'Pendente'

df['Status_Padrao'] = df[col_status].apply(normalizar_status)

st.sidebar.header("Filtros por Operação")

setores_padrao = [
    "Manutenção", "Expedição", "Estoque", "Montagem", 
    "Sala de Reunião", "Atendimento", "Sala de Treinamento", 
    "Diretoria", "TI", "Antireflexo"
]

setores_presentes = df[col_setor].dropna().unique().tolist() if col_setor else []
setores_finais = list(set(setores_padrao + setores_presentes))

setor_selecionado = st.sidebar.multiselect(
    "Setores da Empresa:",
    options=setores_finais,
    default=setores_finais
)

status_opcoes = ["Pendente", "Atuando", "Concluído"]
status_selecionado = st.sidebar.multiselect(
    "Status do Chamado:",
    options=status_opcoes,
    default=status_opcoes
)

df_filtrado = df[df['Status_Padrao'].isin(status_selecionado)]
if col_setor and setor_selecionado:
    df_filtrado = df_filtrado[df_filtrado[col_setor].astype(str).str.contains('|'.join(setor_selecionado), case=False, na=False)]

agora = pd.Timestamp.now()
df_valid_data = df_filtrado.dropna(subset=['Data_Abertura_dt'])

chamados_dia = len(df_valid_data[df_valid_data['Data_Abertura_dt'].dt.date == agora.date()])
chamados_semana = len(df_valid_data[df_valid_data['Data_Abertura_dt'].dt.isocalendar().week == agora.isocalendar().week])
chamados_mes = len(df_valid_data[(df_valid_data['Data_Abertura_dt'].dt.month == agora.month) & (df_valid_data['Data_Abertura_dt'].dt.year == agora.year)])

st.markdown("### 📈 Volumetria de Chamados")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Chamados Hoje", chamados_dia)
m2.metric("Chamados Nesta Semana", chamados_semana)
m3.metric("Chamados Neste Mês", chamados_mes)
m4.metric("Total no Filtro", len(df_filtrado))

st.markdown("---")

st.markdown("### 🚦 Chamados na Fila")

qtd_pendente = len(df_filtrado[df_filtrado['Status_Padrao'] == 'Pendente'])
qtd_atuando = len(df_filtrado[df_filtrado['Status_Padrao'] == 'Atuando'])
qtd_concluido = len(df_filtrado[df_filtrado['Status_Padrao'] == 'Concluído'])

c1, c2, c3 = st.columns(3)

with c1:
    st.markdown(
        f"""
        <div style="background-color:#FFE8CC; padding:15px; border-radius:8px; border-left: 6px solid #FD7E14;">
            <h4 style="color:#D9480F; margin:0;">🟠 PENDENTE</h4>
            <h2 style="color:#D9480F; margin:0;">{qtd_pendente}</h2>
        </div>
        """, 
        unsafe_allow_html=True
    )

with c2:
    st.markdown(
        f"""
        <div style="background-color:#F8D7DA; padding:15px; border-radius:8px; border-left: 6px solid #DC3545;">
            <h4 style="color:#721C24; margin:0;">🔴 ATUANDO</h4>
            <h2 style="color:#721C24; margin:0;">{qtd_atuando}</h2>
        </div>
        """, 
        unsafe_allow_html=True
    )

with c3:
    st.markdown(
        f"""
        <div style="background-color:#D4EDDA; padding:15px; border-radius:8px; border-left: 6px solid #28A745;">
            <h4 style="color:#155724; margin:0;">🟢 CONCLUÍDO</h4>
            <h2 style="color:#155724; margin:0;">{qtd_concluido}</h2>
        </div>
        """, 
        unsafe_allow_html=True
    )

st.markdown("---")

st.markdown("### 📋 Fila Operacional de Chamados")

# Montagem das colunas incluindo Data de Conclusao e Tempo Decorrido
colunas_base = [col_chamado, 'Abertura Exibição', 'Conclusão Exibição', 'Tempo Decorrido', col_setor, col_maquina, col_prioridade, 'Status_Padrao']
colunas_exibir = [c for c in colunas_base if c in df_filtrado.columns]

df_tabela = df_filtrado[colunas_exibir].rename(columns={
    'Status_Padrao': 'Status Final', 
    'Abertura Exibição': 'Data Abertura',
    'Conclusão Exibição': 'Data Conclusão'
})

# Estilização por linha inteira
def estilar_linha_inteira(row):
    status = row['Status Final']
    if status == 'Concluído':
        return ['background-color: #D4EDDA; color: #155724; font-weight: bold;'] * len(row)
    elif status == 'Atuando':
        return ['background-color: #F8D7DA; color: #721C24; font-weight: bold;'] * len(row)
    elif status == 'Pendente':
        return ['background-color: #FFE8CC; color: #D9480F; font-weight: bold;'] * len(row)
    return [''] * len(row)

st.dataframe(
    df_tabela.style.apply(estilar_linha_inteira, axis=1),
    use_container_width=True,
    hide_index=True
)
