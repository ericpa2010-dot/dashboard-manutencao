import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz

# Configuração da página
st.set_page_config(page_title="Gestão de Manutenção", page_icon="🛠️", layout="wide")

# Conexão com Google Sheets via gspread (Secrets)
@st.cache_resource(ttl=60)
def get_gspread_client():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)

def load_data():
    client = get_gspread_client()
    sheet = client.open_by_url(st.secrets["spreadsheet"]["url"]).worksheet("CHAMADOS")
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    return sheet, df

try:
    sheet, df = load_data()
except Exception as e:
    st.error(f"Erro ao conectar com a planilha: {e}")
    st.stop()

# Navegação lateral
st.sidebar.title("Sistema de Manutenção")
menu = st.sidebar.radio("Navegação", ["Abrir Chamado", "Gestão Operacional", "Dashboard & SLA"])

# --- MODULO 1: ABERTURA DE CHAMADO ---
if menu == "Abrir Chamado":
    st.title("📌 Abertura de Chamado de Manutenção")
    
    with st.form("form_abertura", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nome_setor = st.text_input("Nome e Setor Solicitante", placeholder="Ex: Guilherme (Surfaçagem)")
            email = st.text_input("E-mail para Notificação")
            area = st.selectbox("Área do Chamado", ["Surfaçagem", "AR", "Montagem", "Estoque", "Expedição", "Atendimento", "TI", "Diretoria", "Geral"])
            equipamento = st.text_input("Equipamento / Sistema / Local", placeholder="Ex: Satisloh SL-501")
        
        with col2:
            impacto = st.selectbox("Impacto na Operação", ["Parada total", "Parada parcial", "Sem impacto"])
            prioridade = st.selectbox("Prioridade Sugerida", ["Alta", "Média", "Baixa"])
            info_adicional = st.text_input("Link de Foto/Anexo (opcional)")

        problema = st.text_input("Qual é o problema?", placeholder="Resumo em uma frase")
        observado = st.text_area("O que foi observado?", placeholder="Detalhes do comportamento do equipamento")
        testado = st.text_area("O que já foi feito/testado?", placeholder="Ações iniciais tentadas antes do chamado")

        submitted = st.form_submit_button("Enviar Chamado")

        if submitted:
            if not nome_setor or not problema or not equipamento:
                st.warning("Por favor, preencha os campos obrigatórios.")
            else:
                fuso_br = pytz.timezone("America/Sao_Paulo")
                agora = datetime.now(fuso_br).strftime("%Y-%m-%d %H:%M:%S")
                proximo_num = len(df) + 1

                nova_linha = [
                    proximo_num,          # Nº Chamado
                    agora,                # Carimbo de data/hora
                    email,                # Endereço de e-mail
                    nome_setor,           # Nome e Setor
                    area,                 # Área do chamado
                    equipamento,          # Equipamento/Sistema/Local
                    problema,             # Qual é o problema?
                    observado,            # O que foi observado?
                    testado,              # O que já foi feito/testado?
                    impacto,              # Impacto na operação
                    prioridade,           # Prioridade
                    info_adicional,       # Informação adicional
                    "Pendente",           # Status inicial
                    "",                   # Técnico Responsável
                    "",                   # Data de conclusão
                    ""                    # Observação Interna
                ]

                sheet.append_row(nova_linha)
                st.success(f"Chamado Nº {proximo_num} registrado com sucesso!")
                st.cache_resource.clear()

# --- MODULO 2: GESTÃO OPERACIONAL ---
elif menu == "Gestão Operacional":
    st.title("⚙️ Gestão Operacional de Chamados")
    
    status_filtro = st.multiselect("Filtrar por Status", ["Pendente", "Atuando", "Concluído"], default=["Pendente", "Atuando"])
    
    df_filtrado = df[df["Status"].isin(status_filtro)] if status_filtro else df
    
    colunas_visiveis = [c for c in ["Nº Chamado", "Carimbo de data/hora", "Área do chamado", "Equipamento/Sistema/Local", "Prioridade", "Status", "Técnico Responsável"] if c in df_filtrado.columns]
    st.dataframe(df_filtrado[colunas_visiveis], use_container_width=True)

    st.markdown("---")
    st.subheader("Atualizar Status de Chamado")

    num_chamado = st.number_input("Informe o Nº do Chamado para atualizar", min_value=1, step=1)
    
    if num_chamado in df["Nº Chamado"].values:
        idx_linha = df[df["Nº Chamado"] == num_chamado].index[0]
        linha_atual = df.iloc[idx_linha]

        st.info(f"Chamado {num_chamado}: {linha_atual.get('Equipamento/Sistema/Local', '')} (Problema: {linha_atual.get('Qual é o problema?', '')})")

        with st.form("form_atualizacao"):
            col_a, col_b = st.columns(2)
            with col_a:
                status_atual = str(linha_atual.get("Status", "Pendente"))
                opcoes_status = ["Pendente", "Atuando", "Concluído"]
                idx_st = opcoes_status.index(status_atual) if status_atual in opcoes_status else 0
                
                novo_status = st.selectbox("Status", opcoes_status, index=idx_st)
                
                tec_atual = str(linha_atual.get("Técnico Responsável", "Eric"))
                opcoes_tec = ["Eric", "Felipe", "Outro"]
                idx_tec = opcoes_tec.index(tec_atual) if tec_atual in opcoes_tec else 0
                tecnico = st.selectbox("Técnico Responsável", opcoes_tec, index=idx_tec)
            
            with col_b:
                obs_interna = st.text_area("Observação Interna / Diagnóstico", value=str(linha_atual.get("Observação Interna", "")))

            btn_salvar = st.form_submit_button("Salvar Alterações")

            if btn_salvar:
                linha_excel = idx_linha + 2
                
                sheet.update_cell(linha_excel, 13, novo_status)
                sheet.update_cell(linha_excel, 14, tecnico)
                sheet.update_cell(linha_excel, 16, obs_interna)

                st.success(f"Chamado {num_chamado} atualizado para '{novo_status}'. A planilha formatará a linha e inserirá a data automaticamente.")
                st.cache_resource.clear()

# --- MODULO 3: DASHBOARD & SLA ---
elif menu == "Dashboard & SLA":
    st.title("📊 Painel Gerencial & Indicadores SLA")
    
    df_calc = df.copy()
    df_calc["Carimbo de data/hora"] = pd.to_datetime(df_calc["Carimbo de data/hora"], errors="coerce")
    df_calc["Data de conclusão"] = pd.to_datetime(df_calc["Data de conclusão"], errors="coerce")

    df_concluidos = df_calc.dropna(subset=["Data de conclusão"]).copy()
    df_concluidos["Tempo_Resolucao_Horas"] = (df_concluidos["Data de conclusão"] - df_concluidos["Carimbo de data/hora"]).dt.total_seconds() / 3600.0
    df_concluidos = df_concluidos[df_concluidos["Tempo_Resolucao_Horas"] >= 0]

    mttr = df_concluidos["Tempo_Resolucao_Horas"].mean() if not df_concluidos.empty else 0
    mediana = df_concluidos["Tempo_Resolucao_Horas"].median() if not df_concluidos.empty else 0

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Total de Chamados", len(df))
    col_m2.metric("Em Aberto / Atuando", len(df[df["Status"].isin(["Pendente", "Atuando"])]))
    col_m3.metric("MTTR (Média Horas)", f"{mttr:.1f}h")
    col_m4.metric("Mediana de Resolução", f"{mediana:.1f}h")

    st.markdown("---")
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        st.subheader("Chamados por Setor")
        if "Área do chamado" in df.columns:
            st.bar_chart(df["Área do chamado"].value_counts())

    with col_g2:
        st.subheader("Distribuição por Prioridade")
        if "Prioridade" in df.columns:
            st.bar_chart(df["Prioridade"].value_counts())
