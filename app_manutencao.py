import streamlit as st
import pandas as pd
import gspread
from gspread.utils import rowcol_to_a1
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz
import re
import textwrap
import plotly.express as px
import plotly.graph_objects as go

# Configuração da página
st.set_page_config(page_title="Gestão de Manutenção", page_icon="🛠️", layout="wide")

# CSS: Design System Escuro Futurista
st.markdown("""
   <style>
   #MainMenu {visibility: hidden;}
   footer {visibility: hidden;}

   .stApp {
       background-color: #0F172A;
       color: #F8FAFC;
       font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
   }

   h1, h2, h3, h4, h5, h6, label {
       color: #F8FAFC !important;
       font-weight: 700 !important;
   }

   div[data-baseweb="tab-list"] {
       gap: 8px;
       background-color: #0F172A;
   }

   button[data-baseweb="tab"] {
       background-color: #1E293B !important;
       color: #94A3B8 !important;
       border-radius: 8px !important;
       padding: 12px 16px !important;
       font-weight: 600 !important;
       border: 1px solid #334155 !important;
   }

   button[aria-selected="true"] {
       background-color: #38BDF8 !important;
       color: #0F172A !important;
       font-weight: 800 !important;
       border: 1px solid #38BDF8 !important;
   }

   div[data-testid="stMetric"] {
       background-color: #1E293B;
       border: 1px solid #334155;
       border-radius: 12px;
       padding: 12px 16px;
   }

   .stTextInput > div > div > input, 
   .stSelectbox > div > div, 
   .stTextArea textarea {
       background-color: #1E293B !important;
       color: #F8FAFC !important;
       border: 1px solid #334155 !important;
       border-radius: 8px !important;
   }

   hr {
       border-color: #334155 !important;
       margin: 1rem 0 !important;
   }
   </style>
""", unsafe_allow_html=True)

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

def get_sheet(nome_aba="CHAMADOS"):
    client = get_gspread_client()
    sh = client.open_by_url(st.secrets["spreadsheet"]["url"])
    try:
        return sh.worksheet(nome_aba)
    except Exception:
        ws = sh.add_worksheet(title=nome_aba, rows=1000, cols=15)
        if nome_aba == "CHECKLISTS":
            ws.append_row(["Data/Hora", "Equipamento", "Operador", "Turno", "Status Geral", "Itens Conformidade", "Observações"])
        elif nome_aba == "MAQUINAS":
            ws.append_row(["TAG", "Setor", "Máquina", "Tipo", "Ano", "Nº de Série", "Criticidade", "Status", "Garantia", "Última Preventiva", "Próxima Preventiva", "Motivo"])
        return ws

def extrair_campo(row, candidatos, padrao=""):
    for c in candidatos:
        if c in row.index and pd.notna(row[c]) and str(row[c]).strip() != "":
            return str(row[c]).strip()
    return padrao

def parse_data_infalivel(val):
    if not val or pd.isna(val):
        return pd.NaT
    s = str(val).replace('\xa0', ' ').strip()
    if s.lower() in ["nan", "none", "", "-", "null"]:
        return pd.NaT
    m_br = re.search(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?:\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?', s)
    if m_br:
        d, m, y = int(m_br.group(1)), int(m_br.group(2)), int(m_br.group(3))
        h = int(m_br.group(4)) if m_br.group(4) is not None else 0
        mi = int(m_br.group(5)) if m_br.group(5) is not None else 0
        sec = int(m_br.group(6)) if m_br.group(6) is not None else 0
        try:
            return datetime(y, m, d, h, mi, sec)
        except ValueError:
            pass
    return pd.to_datetime(s, errors="coerce", dayfirst=True)

def extrair_dt_abertura(row):
    val = extrair_campo(row, ["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora", "Data de Abertura", "Data"], "")
    return parse_data_infalivel(val)

def extrair_dt_conclusao(row):
    val = extrair_campo(row, ["Data de conclusão", "Data de Conclusão"], "")
    return parse_data_infalivel(val)

def formatar_dt_exibicao(dt, val_raw=""):
    if pd.notna(dt):
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    s = str(val_raw).replace('\xa0', ' ').strip()
    return s if s not in ["", "nan", "None"] else "-"

def formatar_tempo_legivel(horas):
    if pd.isna(horas) or horas is None or horas < 0:
        return "0s"
    total_sec = int(round(horas * 3600))
    dias = total_sec // (24 * 3600)
    sec_restantes = total_sec % (24 * 3600)
    hrs = sec_restantes // 3600
    sec_restantes %= 3600
    mins = sec_restantes // 60
    secs = sec_restantes % 60
    partes = []
    if dias > 0: partes.append(f"{dias}d")
    if hrs > 0: partes.append(f"{hrs}h")
    if mins > 0: partes.append(f"{mins}m")
    if secs > 0 or not partes: partes.append(f"{secs}s")
    return " ".join(partes)

def sanitizar_prioridade_universal(r):
    p_raw = str(extrair_campo(r, ["Prioridade", "Prioridade Sugerida"], "")).strip().lower()
    if "alt" in p_raw: return "Alta"
    elif "med" in p_raw or "méd" in p_raw: return "Média"
    elif "baix" in p_raw: return "Baixa"
    return "Média"

def obter_status_sanitizado(r):
    dt_conc = extrair_campo(r, ["Data de conclusão", "Data de Conclusão"], "")
    if dt_conc != "" and dt_conc != "nan" and dt_conc != "None": return "Concluído"
    st_raw = str(extrair_campo(r, ["Status"], "")).strip().upper()
    if "ATUAND" in st_raw or "ANDAMENTO" in st_raw: return "Atuando"
    if "CONCLU" in st_raw: return "Concluído"
    if "PENDENT" in st_raw or "ABERTO" in st_raw: return "Pendente"
    return "Pendente"

@st.cache_data(ttl=30)
def load_and_process_data():
    sheet = get_sheet("CHAMADOS")
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    if df.empty: return df, df
    df.columns = [str(col).strip() for col in df.columns]
    df_calc = df.copy()
    
    df_calc["Num_Chamado_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["N*Chamado", "Nº Chamado", "N° Chamado"], "0"), axis=1)
    df_calc["Num_Chamado_Num"] = pd.to_numeric(df_calc["Num_Chamado_Norm"], errors="coerce").fillna(0).astype(int)
    df_calc["Solicitante_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Nome e Setor", "Nome e Setor Solicitante", "Solicitante", "Nome"], "Não informado"), axis=1)
    df_calc["Equipamento_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Equipamento / Sistema / Local", "Equipamento/Sistema/Local", "Máquina ou Equipamento"], "Não informado"), axis=1)
    df_calc["Problema_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Qual é o problema?", "Descrição do chamado", "Tipo de problema"], "Sem descrição"), axis=1)
    df_calc["Impacto_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Qual é o impacto na operação?", "Impacto na operação", "Impacto"], "Não informado"), axis=1)
    df_calc["Area_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Área do chamado", "Nome e Setor"], "Geral"), axis=1)
    
    DATA_CORTE_TECNICO = pd.Timestamp(2026, 8, 23, 0, 0, 0)
    def sanitizar_tecnico(r):
        tec_raw = str(r.get("Técnico Responsável", "")).strip()
        dt_ab = extrair_dt_abertura(r)
        if tec_raw == "" or tec_raw.lower() in ["nan", "none", "não atribuído", "-"]:
            if pd.notna(dt_ab) and dt_ab < DATA_CORTE_TECNICO: return "Eric (Histórico Geral)"
            return "Não atribuído"
        return tec_raw

    df_calc["Tecnico_Clean"] = df_calc.apply(sanitizar_tecnico, axis=1)
    df_calc["Prioridade_Clean"] = df_calc.apply(sanitizar_prioridade_universal, axis=1)
    df_calc["Status_Clean"] = df_calc.apply(obter_status_sanitizado, axis=1)
    df_calc["dt_abertura"] = df_calc.apply(extrair_dt_abertura, axis=1)
    df_calc["dt_conclusao"] = df_calc.apply(extrair_dt_conclusao, axis=1)

    METAS_SLA = {"Alta": 4.0, "Média": 8.0, "Baixa": 48.0}
    df_calc["Meta_SLA_Horas"] = df_calc["Prioridade_Clean"].map(METAS_SLA).fillna(8.0)
    
    return df, df_calc

@st.cache_data(ttl=30)
def load_and_process_maquinas():
    sheet = get_sheet("MAQUINAS")
    headers_esperados = ["TAG", "Setor", "Máquina", "Tipo", "Ano", "Nº de Série", "Criticidade", "Status", "Garantia", "Última Preventiva", "Próxima Preventiva", "Motivo"]
    try:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
    except Exception:
        df = pd.DataFrame()
    
    if df.empty or not any(c in df.columns for c in ["TAG", "Máquina"]):
        sheet.clear()
        sheet.append_row(headers_esperados)
        seed_maquinas = [
            ["SURF-GER-001", "Surfaçagem", "Orbit 2", "Gerador", "2023", "—", "Classe A", "Operando", "Não", "—", "—", "—"],
            ["SURF-GER-002", "Surfaçagem", "Orbit 2 E", "Gerador", "2024", "—", "Classe A", "Operando", "Não", "—", "—", "—"],
            ["SURF-POL-001", "Surfaçagem", "Toro-Flex", "Polimento", "2023", "—", "Classe B", "Operando", "Não", "—", "—", "—"],
            ["SURF-VER-001", "Surfaçagem", "Verniz + Forno", "Verniz", "2020", "—", "Classe B", "Parada", "Não", "—", "—", "Ajuste de temperatura"],
            ["MONT-COR-001", "Montagem", "Mr Blue", "Corte", "2023", "623160", "Classe A", "Operando", "Sim", "—", "—", "—"],
            ["MONT-COR-002", "Montagem", "Neksia 500", "Corte", "2023", "0223189", "Classe B", "Quebrada", "Não", "—", "—", "Aguardando peças"],
            ["MONT-COR-003", "Montagem", "Neksia 600", "Corte", "2025", "0525128", "Classe B", "Operando", "Sim", "—", "—", "—"],
            ["AR-REV-001", "Anti-Reflexo", "MC 380 X2", "Revestimento a vácuo", "2025", "—", "Classe A", "Operando", "Sim", "—", "—", "—"],
            ["AR-HARD-001", "Anti-Reflexo", "SL-501", "Hardcoating / Dip coating", "2008", "—", "Classe A", "Operando", "Sim", "—", "—", "—"],
            ["UTIL-COMP-001", "Compressor", "Compressor GA11VSD+FF", "Ar Comprimido", "2023", "—", "Classe A", "Operando", "Não", "31/07/2023", "30/11/2026", "—"]
        ]
        for row in seed_maquinas:
            sheet.append_row(row)
        df = pd.DataFrame(seed_maquinas, columns=headers_esperados)

    df.columns = [str(col).strip() for col in df.columns]
    for h in headers_esperados:
        if h not in df.columns: df[h] = ""
            
    df["Criticidade"] = df["Criticidade"].fillna("Classe B").replace("", "Classe B")
    df["Status"] = df["Status"].fillna("Operando").replace("", "Operando")
    return sheet, df

SENHA_CORRETA = st.secrets.get("SENHA_GESTAO", "manutencao123")

try:
    df_raw, df_calc = load_and_process_data()
    sheet_maq, df_maq = load_and_process_maquinas()
except Exception as e:
    st.error(f"Erro ao conectar com a planilha: {e}")
    st.stop()

if not df_calc.empty:
    fuso_br = pytz.timezone("America/Sao_Paulo")
    agora_br = datetime.now(fuso_br)
    agora_naive_geral = pd.Timestamp(agora_br.replace(tzinfo=None))
    DATA_CORTE = pd.Timestamp(2026, 8, 23, 0, 0, 0)

tab_abertura, tab_checklist, tab_maquinas, tab_dash, tab_gestao = st.tabs([
    "📌 Abrir Chamado", "📋 Checklist Diário", "🏭 Gestão de Ativos", "📊 Dashboard & SLA", "⚙️ Gestão Operacional"
])

# ABA 1: ABERTURA DE CHAMADO (COM TRAVA DE VALIDAÇÃO RÍGIDA)
with tab_abertura:
    st.title("📌 Abertura de Chamado")
    with st.form("form_abertura", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nome_setor = st.text_input("Nome e Setor Solicitante *", placeholder="Ex: Guilherme (Surfaçagem)")
            email = st.text_input("E-mail para Notificação")
            area = st.selectbox("Área do Chamado *", ["Surfaçagem", "AR", "Montagem", "Estoque", "Expedição", "Atendimento", "TI", "Diretoria", "Geral"])
            equipamento = st.text_input("Equipamento / Sistema / Local *", placeholder="Ex: Satisloh SL-501")
        with col2:
            impacto = st.selectbox("Impacto na Operação", ["Parada total", "Parada parcial", "Sem impacto"])
            prioridade = st.selectbox("Prioridade Sugerida", ["Alta", "Média", "Baixa"])
            info_adicional = st.text_input("Link de Foto/Anexo (opcional)")

        problema = st.text_input("Qual é o problema? *", placeholder="Resumo claro do problema")
        observado = st.text_area("O que foi observado?", placeholder="Detalhes do comportamento do equipamento")
        testado = st.text_area("O que já foi feito/testado?", placeholder="Ações iniciais tentadas antes do chamado")
        submitted = st.form_submit_button("Enviar Chamado")

        if submitted:
            campos_faltantes = []
            if not nome_setor or not nome_setor.strip():
                campos_faltantes.append("Nome e Setor Solicitante")
            if not area or not area.strip():
                campos_faltantes.append("Área do Chamado")
            if not equipamento or not equipamento.strip():
                campos_faltantes.append("Equipamento / Sistema / Local")
            if not problema or not problema.strip():
                campos_faltantes.append("Qual é o problema?")

            if campos_faltantes:
                st.error("🛑 **Abertura Bloqueada!** Os seguintes campos obrigatórios não foram preenchidos:\n\n" + "\n".join([f"• **{campo}**" for campo in campos_faltantes]))
            else:
                sheet = get_sheet("CHAMADOS")
                fuso_br = pytz.timezone("America/Sao_Paulo")
                agora = datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M:%S")
                headers = [str(h).strip() for h in sheet.row_values(1)]
                nova_linha = [""] * len(headers)
                
                def preencher(col, val):
                    if col in headers: nova_linha[headers.index(col)] = val

                proximo_num = len(df_calc) + 1
                preencher("N*Chamado", proximo_num)
                preencher("Nº Chamado", proximo_num)
                preencher("Carimbo de data/hora", agora)
                preencher("Endereço de e-mail", email)
                preencher("Nome e Setor", nome_setor)
                preencher("Área do chamado", area)
                preencher("Equipamento / Sistema / Local", equipamento)
                preencher("Máquina ou Equipamento", equipamento)
                preencher("Qual é o problema?", problema)
                preencher("Prioridade", prioridade)
                preencher("Status", "Pendente")
                preencher("Técnico Responsável", "Eric")

                sheet.append_row(nova_linha)
                st.success(f"Chamado Nº {proximo_num} registrado com sucesso!")
                st.cache_data.clear()

# ABA 2: CHECKLIST DIÁRIO
with tab_checklist:
    st.title("📋 Checklist de Inspeção Operacional (TPM)")
    with st.form("form_checklist", clear_on_submit=True):
        c_meta1, c_meta2, c_meta3 = st.columns(3)
        with c_meta1:
            eq_check = st.selectbox("Equipamento *", ["Satisloh SL-501", "Satisloh Orbit 2", "Ultra Ópticos", "Montagem Geral", "Gerador VFT", "Outro"])
        with c_meta2:
            op_check = st.text_input("Nome do Operador *", placeholder="Ex: Carlos")
        with c_meta3:
            turno_check = st.selectbox("Turno *", ["1º Turno", "2º Turno", "3º Turno", "Comercial"])

        col_chk1, col_chk2 = st.columns(2)
        with col_chk1:
            chk_seguranca = st.checkbox("1. Travas e botões de emergência operacionais", value=True)
            chk_pressao = st.checkbox("2. Pressão pneumática/hidráulica na faixa nominal", value=True)
            chk_vazamento = st.checkbox("3. Ausência de vazamentos visíveis de óleo/insumos", value=True)
        with col_chk2:
            chk_limpeza = st.checkbox("4. Área interna e sensores limpos e sem resíduos", value=True)
            chk_ruido = st.checkbox("5. Ruído e vibração normais durante o ciclo de teste", value=True)
            chk_insumo = st.checkbox("6. Nível de verniz/insumos adequado no reservatório", value=True)

        obs_check = st.text_area("Observações / Anomalias identificadas", placeholder="Descreva qualquer irregularidade notada durante a inspeção...")
        btn_salvar_check = st.form_submit_button("Salvar Inspeção")

        if btn_salvar_check:
            if not op_check or not op_check.strip():
                st.error("🛑 **Checklist Bloqueado!** Informe o nome do operador para validar a inspeção.")
            else:
                lista_itens = [chk_seguranca, chk_pressao, chk_vazamento, chk_limpeza, chk_ruido, chk_insumo]
                total_ok = sum(lista_itens)
                status_final = "Aprovado (100%)" if total_ok == 6 else f"Com Pendência ({total_ok}/6 OK)"
                agora_chk = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")

                sheet_chk = get_sheet("CHECKLISTS")
                sheet_chk.append_row([agora_chk, eq_check, op_check, turno_check, status_final, f"{total_ok}/6", obs_check])

                if total_ok < 6:
                    sheet_main = get_sheet("CHAMADOS")
                    headers_m = [str(h).strip() for h in sheet_main.row_values(1)]
                    nova_linha_m = [""] * len(headers_m)
                    
                    def preencher_m(col, val):
                        if col in headers_m: nova_linha_m[headers_m.index(col)] = val

                    proximo_num_m = len(df_calc) + 1
                    preencher_m("N*Chamado", proximo_num_m)
                    preencher_m("Nº Chamado", proximo_num_m)
                    preencher_m("Carimbo de data/hora", agora_chk)
                    preencher_m("Nome e Setor", f"{op_check} (Checklist Auto)")
                    preencher_m("Área do chamado", "Produção")
                    preencher_m("Equipamento / Sistema / Local", eq_check)
                    preencher_m("Máquina ou Equipamento", eq_check)
                    preencher_m("Qual é o problema?", f"Anomalia detectada no Checklist ({total_ok}/6 OK)")
                    preencher_m("Prioridade", "Média" if total_ok >= 4 else "Alta")
                    preencher_m("Status", "Pendente")
                    preencher_m("Técnico Responsável", "Eric")

                    sheet_main.append_row(nova_linha_m)
                    st.warning(f"Checklist registrado! Chamado automático Nº {proximo_num_m} criado.")
                else:
                    st.success(f"Checklist gravado com sucesso! Status: {status_final}")
                st.cache_data.clear()

# ABA 3: GESTÃO DE ATIVOS
with tab_maquinas:
    st.title("🏭 Gestão de Ativos & Parque Fabril")
    st.caption("Controle centralizado de máquinas, criticidade e preventiva.")

    if not df_maq.empty:
        total_maq = len(df_maq)
        operando_maq = len(df_maq[df_maq["Status"] == "Operando"])
        inativas_maq = len(df_maq[df_maq["Status"].isin(["Quebrada", "Parada"])])
        criticas_a_paradas = len(df_maq[(df_maq["Criticidade"] == "Classe A") & (df_maq["Status"].isin(["Quebrada", "Parada"]))])
        disp_pct = (operando_maq / total_maq * 100) if total_maq > 0 else 100.0

        cm1, cm2, cm3, cm4 = st.columns(4)
        cm1.metric("Total de Máquinas", total_maq)
        cm2.metric("Disponibilidade Operacional", f"{disp_pct:.1f}%")
        cm3.metric("Máquinas Inativas", inativas_maq)
        cm4.metric("Risco Crítico (Classe A)", criticas_a_paradas)

        st.markdown("---")
        st.markdown("##### 🔍 Filtro e Consulta de Equipamentos")

        cf1, cf2, cf3 = st.columns(3)
        with cf1:
            f_setor = st.selectbox("Filtrar por Setor", ["Todos"] + sorted(list(df_maq["Setor"].unique())))
        with cf2:
            f_status = st.selectbox("Filtrar por Status", ["Todos", "Operando", "Quebrada", "Parada", "Desativada"])
        with cf3:
            f_crit = st.selectbox("Filtrar por Criticidade", ["Todas", "Classe A", "Classe B", "Classe C"])

        df_disp_maq = df_maq.copy()
        if f_setor != "Todos": df_disp_maq = df_disp_maq[df_disp_maq["Setor"] == f_setor]
        if f_status != "Todos": df_disp_maq = df_disp_maq[df_disp_maq["Status"] == f_status]
        if f_crit != "Todas": df_disp_maq = df_disp_maq[df_disp_maq["Criticidade"] == f_crit]

        cols_view = ["TAG", "Setor", "Máquina", "Tipo", "Criticidade", "Status", "Nº de Série", "Próxima Preventiva", "Motivo"]
        
        def colorir_linha_maquina(row):
            st_m = str(row["Status"])
            if st_m == "Operando":
                return ['background-color: #064E3B; color: #A7F3D0; font-weight: 700;'] * len(row)
            elif st_m == "Quebrada":
                return ['background-color: #7F1D1D; color: #FECDD3; font-weight: 700;'] * len(row)
            elif st_m == "Parada":
                return ['background-color: #78350F; color: #FDE68A; font-weight: 700;'] * len(row)
            else:
                return ['background-color: #1E293B; color: #94A3B8; font-weight: 700;'] * len(row)

        styled_maq = df_disp_maq[cols_view].style.apply(colorir_linha_maquina, axis=1)
        st.dataframe(styled_maq, use_container_width=True, hide_index=True)

        st.markdown("---")
        col_m_edit, col_m_add = st.columns(2)
        
        with col_m_edit:
            st.subheader("🛠️ Atualizar Status de Máquina")
            lista_tags = df_maq["TAG"].tolist()
            
            if lista_tags:
                tag_sel = st.selectbox("Selecione a TAG do Equipamento", lista_tags)
                idx_m = df_maq[df_maq["TAG"] == tag_sel].index[0]
                row_m = df_maq.iloc[idx_m]

                with st.form("form_edit_maquina"):
                    n_status = st.selectbox("Novo Status", ["Operando", "Quebrada", "Parada", "Desativada"], index=["Operando", "Quebrada", "Parada", "Desativada"].index(row_m["Status"]) if row_m["Status"] in ["Operando", "Quebrada", "Parada", "Desativada"] else 0)
                    n_crit = st.selectbox("Criticidade", ["Classe A", "Classe B", "Classe C"], index=["Classe A", "Classe B", "Classe C"].index(row_m["Criticidade"]) if row_m["Criticidade"] in ["Classe A", "Classe B", "Classe C"] else 1)
                    n_prev = st.text_input("Data Próxima Preventiva", value=str(row_m["Próxima Preventiva"]))
                    n_motivo = st.text_area("Motivo / Causa Raiz", value=str(row_m["Motivo"]))
                    gerar_os = st.checkbox("Abrir chamado automático se marcado como Quebrada/Parada", value=True)
                    
                    btn_up_m = st.form_submit_button("Salvar Alterações da Máquina")

                    if btn_up_m:
                        headers_m = [str(h).strip() for h in sheet_maq.row_values(1)]
                        linha_m_excel = idx_m + 2
                        updates_m = []

                        if "Status" in headers_m: updates_m.append({'range': rowcol_to_a1(linha_m_excel, headers_m.index("Status") + 1), 'values': [[n_status]]})
                        if "Criticidade" in headers_m: updates_m.append({'range': rowcol_to_a1(linha_m_excel, headers_m.index("Criticidade") + 1), 'values': [[n_crit]]})
                        if "Próxima Preventiva" in headers_m: updates_m.append({'range': rowcol_to_a1(linha_m_excel, headers_m.index("Próxima Preventiva") + 1), 'values': [[n_prev]]})
                        if "Motivo" in headers_m: updates_m.append({'range': rowcol_to_a1(linha_m_excel, headers_m.index("Motivo") + 1), 'values': [[n_motivo]]})

                        if updates_m: sheet_maq.batch_update(updates_m)

                        if gerar_os and n_status in ["Quebrada", "Parada"]:
                            sheet_c = get_sheet("CHAMADOS")
                            headers_c = [str(h).strip() for h in sheet_c.row_values(1)]
                            nova_linha_c = [""] * len(headers_c)
                            
                            def preencher_c(col, val):
                                if col in headers_c: nova_linha_c[headers_c.index(col)] = val

                            agora_m = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")
                            proximo_num_c = len(df_calc) + 1
                            preencher_c("N*Chamado", proximo_num_c)
                            preencher_c("Nº Chamado", proximo_num_c)
                            preencher_c("Carimbo de data/hora", agora_m)
                            preencher_c("Nome e Setor", "Gestão de Ativos (Auto)")
                            preencher_c("Área do chamado", str(row_m["Setor"]))
                            preencher_c("Equipamento / Sistema / Local", f"{row_m['Máquina']} ({row_m['TAG']})")
                            preencher_c("Qual é o problema?", f"Máquina {n_status}: {n_motivo}")
                            preencher_c("Prioridade", "Alta" if n_crit == "Classe A" else "Média")
                            preencher_c("Status", "Pendente")
                            preencher_c("Técnico Responsável", "Eric")

                            sheet_c.append_row(nova_linha_c)
                            st.warning(f"Status atualizado e Chamado Nº {proximo_num_c} aberto automaticamente!")
                        else:
                            st.success(f"Máquina {tag_sel} atualizada com sucesso!")

                        st.cache_data.clear()

        with col_m_add:
            st.subheader("➕ Cadastrar Novo Ativo")
            with st.form("form_add_maquina", clear_on_submit=True):
                a_tag = st.text_input("TAG do Equipamento *", placeholder="Ex: SURF-GER-003")
                a_setor = st.selectbox("Setor *", ["Surfaçagem", "Montagem", "Anti-Reflexo", "Compressor", "Utilidades"])
                a_nome = st.text_input("Nome / Modelo da Máquina *", placeholder="Ex: Satisloh SL-501")
                a_tipo = st.text_input("Tipo / Função", placeholder="Ex: Gerador / Polidora")
                a_ano = st.text_input("Ano de Fabricação", placeholder="Ex: 2024")
                a_serie = st.text_input("Nº de Série", placeholder="Ex: 623160")
                a_crit = st.selectbox("Criticidade", ["Classe A", "Classe B", "Classe C"], index=1)
                a_status = st.selectbox("Status Inicial", ["Operando", "Quebrada", "Parada", "Desativada"])
                a_garantia = st.selectbox("Possui Garantia?", ["Não", "Sim"])

                btn_add_m = st.form_submit_button("Cadastrar Equipamento")

                if btn_add_m:
                    if not a_tag or not a_tag.strip() or not a_nome or not a_nome.strip():
                        st.error("🛑 **Cadastro Bloqueado!** TAG e Nome da Máquina são obrigatórios.")
                    else:
                        linha_nova_m = [a_tag, a_setor, a_nome, a_tipo, a_ano, a_serie, a_crit, a_status, a_garantia, "—", "—", "—"]
                        sheet_maq.append_row(linha_nova_m)
                        st.success(f"Equipamento {a_tag} cadastrado com sucesso!")
                        st.cache_data.clear()

# ABA 4: DASHBOARD
with tab_dash:
    st.title("📊 Painel Gerencial & SLA")
    opcao_periodo = st.selectbox("Filtro dos Indicadores", ["Todo o Histórico", "Últimos 90 dias", "Últimos 30 dias", "Este Mês", "Este Ano"], index=0)

    if not df_calc.empty:
        status_abertos = ["Pendente", "Atuando", "Aberto", "Em andamento"]
        em_aberto = len(df_calc[df_calc["Status_Clean"].isin(status_abertos)])
        total_chamados_geral = len(df_calc)
        total_concluidos_geral = len(df_calc[df_calc["Status_Clean"] == "Concluído"])
        taxa_conclusao_geral = (total_concluidos_geral / total_chamados_geral * 100) if total_chamados_geral > 0 else 100.0

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Chamados (Histórico)", total_chamados_geral)
        c2.metric("Em Aberto", em_aberto)
        c3.metric("Taxa Resolução Geral", f"{taxa_conclusao_geral:.1f}%")

        st.markdown("---")
        st.markdown(f"##### 📋 Histórico Geral de Chamados & SLA (Total: {total_chamados_geral})")
        
        lista_geral = []
        for _, row in df_calc.iterrows():
            st_str = str(row.get("Status_Clean", "Pendente"))
            dt_ab = row.get("dt_abertura")
            raw_ab = extrair_campo(row, ["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora", "Data de Abertura"], "")
            dt_ab_str = formatar_dt_exibicao(dt_ab, raw_ab)
            tec_val = row.get("Tecnico_Clean", "Eric")

            lista_geral.append({
                "Nº": row.get("Num_Chamado_Num"),
                "Solicitante": row.get("Solicitante_Norm"),
                "Abertura": dt_ab_str,
                "Área": row.get("Area_Norm"),
                "Equipamento": row.get("Equipamento_Norm"),
                "Descrição do Problema": row.get("Problema_Norm"),
                "Prioridade": row.get("Prioridade_Clean"),
                "Status": "🟢 Concluído" if st_str == "Concluído" else ("🟣 Atuando" if st_str == "Atuando" else "🟡 Pendente"),
                "Técnico": tec_val if tec_val != "Não atribuído" else "Eric"
            })

        if lista_geral:
            df_geral = pd.DataFrame(lista_geral).sort_values("Nº", ascending=False).head(50)
            st.dataframe(df_geral, use_container_width=True, hide_index=True)

# ABA 5: GESTÃO OPERACIONAL
with tab_gestao:
    st.title("⚙️ Gestão Operacional de Chamados")
    senha_digitada = st.text_input("Chave de Acesso Operacional", type="password", key="pwd_gestao")
    
    if senha_digitada == SENHA_CORRETA and not df_calc.empty:
        num_chamado = st.number_input("Informe o Nº do Chamado para atualizar", min_value=1, step=1)
        mask_num = df_calc["Num_Chamado_Num"] == num_chamado
        
        if mask_num.any():
            idx_linha = df_calc[mask_num].index[0]
            linha_atual = df_raw.iloc[idx_linha]
            st.info(f"Chamado {num_chamado}: {extrair_campo(linha_atual, ['Equipamento / Sistema / Local', 'Máquina ou Equipamento'])}")

            with st.form("form_atualizacao"):
                col_a, col_b = st.columns(2)
                sheet = get_sheet("CHAMADOS")
                headers = [str(h).strip() for h in sheet.row_values(1)]
                
                with col_a:
                    novo_status = st.selectbox("Status", ["Pendente", "Atuando", "Concluído"])
                    tecnico = st.selectbox("Técnico Responsável", ["Eric", "Felipe", "Outro"])
                with col_b:
                    obs_interna = st.text_area("Observação Interna / Diagnóstico", value=str(linha_atual.get("Observação Interna", "")))

                if st.form_submit_button("Salvar Alterações"):
                    linha_excel = idx_linha + 2
                    updates_lote = []
                    if "Status" in headers: updates_lote.append({'range': rowcol_to_a1(linha_excel, headers.index("Status") + 1), 'values': [[novo_status]]})
                    if "Técnico Responsável" in headers: updates_lote.append({'range': rowcol_to_a1(linha_excel, headers.index("Técnico Responsável") + 1), 'values': [[tecnico]]})
                    if "Observação Interna" in headers: updates_lote.append({'range': rowcol_to_a1(linha_excel, headers.index("Observação Interna") + 1), 'values': [[obs_interna]]})
                    
                    if updates_lote: sheet.batch_update(updates_lote)
                    st.success(f"Chamado Nº {num_chamado} atualizado!")
                    st.cache_data.clear()