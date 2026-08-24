import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz

# Configuração da página
st.set_page_config(page_title="Gestão de Manutenção", page_icon="🛠️", layout="wide")

# Conexão com Google Sheets via gspread (Secrets)
@st.cache_resource(ttl=30)
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

# Navegação Lateral Original
st.sidebar.title("Sistema de Manutenção")
menu = st.sidebar.radio("Navegação", ["Abrir Chamado", "Gestão Operacional", "Dashboard & SLA"])

SENHA_CORRETA = st.secrets.get("SENHA_GESTAO", "manutencao123")

# Trava de Segurança
if menu == "Gestão Operacional":
    st.sidebar.markdown("---")
    senha_digitada = st.sidebar.text_input("Chave de Acesso Operacional", type="password")
    
    if senha_digitada != SENHA_CORRETA:
        st.warning("🔒 Área restrita à equipe de manutenção. Insira a chave de acesso na barra lateral para continuar.")
        st.stop()

# --- MÓDULO 1: ABERTURA DE CHAMADO ---
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
            prioridade = st.selectbox("Prioridade Sugerida", ["Urgente", "Alta", "Média", "Baixa"])
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

# --- MÓDULO 2: GESTÃO OPERACIONAL ---
elif menu == "Gestão Operacional":
    st.title("⚙️ Gestão Operacional de Chamados")
    
    status_filtro = st.multiselect("Filtrar por Status", ["Pendente", "Atuando", "Concluído"], default=["Pendente", "Atuando"])
    
    df_filtrado = df[df["Status"].isin(status_filtro)] if ("Status" in df.columns and status_filtro) else df
    
    colunas_visiveis = [c for c in ["Nº Chamado", "Carimbo de data/hora", "Área do chamado", "Equipamento/Sistema/Local", "Prioridade", "Status", "Técnico Responsável"] if c in df_filtrado.columns]
    st.dataframe(df_filtrado[colunas_visiveis], use_container_width=True)

    st.markdown("---")
    st.subheader("Atualizar Status de Chamado")

    if "Nº Chamado" in df.columns and not df.empty:
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

# --- MÓDULO 3: DASHBOARD & SLA (RESTAURADO) ---
elif menu == "Dashboard & SLA":
    st.title("📊 Painel Gerencial & Indicadores SLA")
    
    if df.empty:
        st.info("Nenhum chamado registrado na planilha ainda.")
    else:
        df_calc = df.copy()
        
        # Conversão estrita dos nomes de colunas
        col_abertura = "Carimbo de data/hora"
        col_conclusao = "Data de conclusão"
        
        df_calc[col_abertura] = pd.to_datetime(df_calc[col_abertura], errors="coerce")
        df_calc[col_conclusao] = pd.to_datetime(df_calc[col_conclusao], errors="coerce")

        df_concluidos = df_calc.dropna(subset=[col_conclusao]).copy()
        df_concluidos["Tempo_Resolucao_Horas"] = (df_concluidos[col_conclusao] - df_concluidos[col_abertura]).dt.total_seconds() / 3600.0
        df_concluidos = df_concluidos[df_concluidos["Tempo_Resolucao_Horas"] >= 0]

        mttr = df_concluidos["Tempo_Resolucao_Horas"].mean() if not df_concluidos.empty else 0.0
        mediana = df_concluidos["Tempo_Resolucao_Horas"].median() if not df_concluidos.empty else 0.0

        # Cards de topo
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Total de Chamados", len(df_calc))
        col_m2.metric("Em Aberto / Atuando", len(df_calc[df_calc["Status"].isin(["Pendente", "Atuando"])]))
        col_m3.metric("MTTR (Média Horas)", f"{mttr:.1f}h")
        col_m4.metric("Mediana de Resolução", f"{mediana:.1f}h")

        st.markdown("---")
        st.subheader("⏱️ Indicadores de Cumprimento de SLA")

        metas_sla = {
            "Urgente": 4,
            "Alta": 12,
            "Média": 24,
            "Baixa": 48
        }

        # Cards de SLA por prioridade
        cols_sla = st.columns(4)
        idx = 0
        for prio, meta in metas_sla.items():
            df_prio = concluidos[concluidos["Prioridade"] == prio] if "Prioridade" in concluidos.columns else pd.DataFrame()
            tot = len(df_prio)
            no_prazo = len(df_prio[df_prio["Tempo_Resolucao_Horas"] <= meta]) if tot > 0 else 0
            pct = (no_prazo / tot * 100) if tot > 0 else 100.0
            
            with cols_sla[idx]:
                st.metric(label=f"SLA {prio} (Meta {meta}h)", value=f"{pct:.0f}%", delta=f"{no_prazo}/{tot} no prazo")
            idx += 1

        st.markdown("---")
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.subheader("Chamados por Setor")
            if "Área do chamado" in df_calc.columns:
                st.bar_chart(df_calc["Área do chamado"].value_counts())

        with col_g2:
            st.subheader("Distribuição por Prioridade")
            if "Prioridade" in df_calc.columns:
                st.bar_chart(df_calc["Prioridade"].value_counts())
