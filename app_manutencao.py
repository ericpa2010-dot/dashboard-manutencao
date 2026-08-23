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
    
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
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

# Trava de Segurança exclusiva para a Gestão Operacional
SENHA_CORRETA = st.secrets.get("SENHA_GESTAO", "manutencao123")

if menu == "Gestão Operacional":
    st.sidebar.markdown("---")
    senha_digitada = st.sidebar.text_input("Chave de Acesso Operacional", type="password")
    
    if senha_digitada != SENHA_CORRETA:
        st.warning("🔒 Área restrita à equipe de manutenção. Insira a chave de acesso na barra lateral para continuar.")
        st.stop()

# --- MODULO 1: ABERTURA DE CHAMADO (PÚBLICO) ---
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

# --- MODULO 2: GESTÃO OPERACIONAL (RESTRITO) ---
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

# --- MODULO 3: DASHBOARD COMPLETO & SLA (PÚBLICO) ---
elif menu == "Dashboard & SLA":
    st.title("📊 Painel Gerencial & Indicadores Avançados de SLA")
    
    if df.empty:
        st.info("Nenhum dado registrado na planilha até o momento.")
    else:
        df_calc = df.copy()
        df_calc["Carimbo de data/hora"] = pd.to_datetime(df_calc["Carimbo de data/hora"], errors="coerce")
        df_calc["Data de conclusão"] = pd.to_datetime(df_calc["Data de conclusão"], errors="coerce")
        
        # Processamento de resolvidos e regras de SLA
        df_concluidos = df_calc.dropna(subset=["Data de conclusão"]).copy()
        if not df_concluidos.empty:
            df_concluidos["Tempo_Resolucao_Horas"] = (
                df_concluidos["Data de conclusão"] - df_concluidos["Carimbo de data/hora"]
            ).dt.total_seconds() / 3600.0
            df_concluidos = df_concluidos[df_concluidos["Tempo_Resolucao_Horas"] >= 0]
            
            def get_sla_target(prioridade):
                p = str(prioridade).strip().lower()
                if "alta" in p:
                    return 4.0
                elif "média" in p or "media" in p:
                    return 24.0
                elif "baixa" in p:
                    return 48.0
                return 24.0

            df_concluidos["Meta_SLA_Horas"] = df_concluidos["Prioridade"].apply(get_sla_target)
            df_concluidos["SLA_Cumprido"] = df_concluidos["Tempo_Resolucao_Horas"] <= df_concluidos["Meta_SLA_Horas"]
        else:
            df_concluidos["Tempo_Resolucao_Horas"] = []
            df_concluidos["Meta_SLA_Horas"] = []
            df_concluidos["SLA_Cumprido"] = []

        # Métricas Globais
        total_chamados = len(df_calc)
        em_aberto = len(df_calc[df_calc["Status"].isin(["Pendente", "Atuando"])])
        total_concluidos = len(df_concluidos)
        taxa_conclusao = (total_concluidos / total_chamados * 100) if total_chamados > 0 else 0.0
        
        mttr_geral = df_concluidos["Tempo_Resolucao_Horas"].mean() if not df_concluidos.empty else 0.0
        sla_cumprido_pct = (df_concluidos["SLA_Cumprido"].sum() / total_concluidos * 100) if total_concluidos > 0 else 0.0

        # Cards de Indicadores
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Chamados", total_chamados)
        c2.metric("Em Aberto / Atuando", em_aberto)
        c3.metric("Taxa de Resolução", f"{taxa_conclusao:.1f}%")
        c4.metric("MTTR Geral", f"{mttr_geral:.1f}h")
        c5.metric("Conformidade SLA", f"{sla_cumprido_pct:.1f}%")

        st.markdown("---")

        # Visões analíticas por abas
        aba1, aba2, aba3 = st.tabs(["📌 Volumetria & Gargalos", "👥 Desempenho Técnico", "🚨 Análise de SLA & Reincidência"])

        with aba1:
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("Chamados por Setor / Área")
                if "Área do chamado" in df_calc.columns:
                    st.bar_chart(df_calc["Área do chamado"].value_counts())
            
            with col_b:
                st.subheader("Distribuição por Prioridade")
                if "Prioridade" in df_calc.columns:
                    st.bar_chart(df_calc["Prioridade"].value_counts())

            st.subheader("Evolução Temporal de Aberturas")
            df_tempo = df_calc.dropna(subset=["Carimbo de data/hora"]).copy()
            if not df_tempo.empty:
                df_tempo["Data_Dia"] = df_tempo["Carimbo de data/hora"].dt.date
                evolucao = df_tempo.groupby("Data_Dia").size()
                st.line_chart(evolucao)

        with aba2:
            st.subheader("Desempenho por Técnico Responsável")
            if "Técnico Responsável" in df_calc.columns and not df_concluidos.empty:
                tec_stats = df_concluidos.groupby("Técnico Responsável").agg(
                    Total_Atendidos=("Nº Chamado", "count"),
                    MTTR_Medio_Horas=("Tempo_Resolucao_Horas", "mean"),
                    Percentual_SLA_OK=("SLA_Cumprido", lambda x: (x.sum() / len(x)) * 100)
                ).reset_index()
                tec_stats["MTTR_Medio_Horas"] = tec_stats["MTTR_Medio_Horas"].round(1)
                tec_stats["Percentual_SLA_OK"] = tec_stats["Percentual_SLA_OK"].round(1)
                st.dataframe(tec_stats, use_container_width=True)
            else:
                st.info("Aguardando conclusão de chamados para gerar histórico do time técnico.")

        with aba3:
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                st.subheader("Top Equipamentos Reincidentes")
                if "Equipamento/Sistema/Local" in df_calc.columns:
                    top_eq = df_calc["Equipamento/Sistema/Local"].value_counts().head(10)
                    st.bar_chart(top_eq)
            
            with col_r2:
                st.subheader("Cumprimento do SLA")
                if not df_concluidos.empty:
                    sla_counts = df_concluidos["SLA_Cumprido"].map({True: "Dentro do SLA", False: "Fora do SLA (Estourado)"}).value_counts()
                    st.bar_chart(sla_counts)
            
            st.subheader("Detalhamento de Chamados com SLA Estourado")
            if not df_concluidos.empty:
                fora_sla = df_concluidos[df_concluidos["SLA_Cumprido"] == False]
                if not fora_sla.empty:
                    colunas_sla = [c for c in ["Nº Chamado", "Área do chamado", "Equipamento/Sistema/Local", "Prioridade", "Tempo_Resolucao_Horas", "Meta_SLA_Horas", "Técnico Responsável"] if c in fora_sla.columns]
                    st.dataframe(fora_sla[colunas_sla], use_container_width=True)
                else:
                    st.success("Operação eficiente: 100% dos chamados concluídos dentro da meta de SLA.")
