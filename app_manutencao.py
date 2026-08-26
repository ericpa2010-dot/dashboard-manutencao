import streamlit as st
import pandas as pd
import gspread
from gspread.utils import rowcol_to_a1
from google.oauth2.service_account import Credentials
from datetime import datetime, time, timedelta
import pytz
import re
import textwrap
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# Configuração da página
st.set_page_config(page_title="Gestão de Manutenção", page_icon="🛠️", layout="wide")

# Estado de Sessão para Regras de SLA e Turnos
if "sla_regime" not in st.session_state:
    st.session_state["sla_regime"] = "Horário Comercial"
if "dias_expediente" not in st.session_state:
    st.session_state["dias_expediente"] = ["Seg", "Ter", "Qua", "Qui", "Sex"]
if "hora_inicio_turno" not in st.session_state:
    st.session_state["hora_inicio_turno"] = time(8, 0)
if "hora_fim_turno" not in st.session_state:
    st.session_state["hora_fim_turno"] = time(19, 0)

# CSS Design System
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
   div[data-testid="stMetricLabel"] {
       font-size: 0.8rem !important;
       color: #94A3B8 !important;
       font-weight: 600 !important;
   }
   div[data-testid="stMetricValue"] {
       font-size: 1.5rem !important;
       color: #38BDF8 !important;
       font-weight: 800 !important;
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

   div[data-testid="stDataFrame"] {
       background-color: #1E293B;
       border: 1px solid #334155;
       border-radius: 12px;
       padding: 8px;
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

def get_sheet():
    client = get_gspread_client()
    return client.open_by_url(st.secrets["spreadsheet"]["url"]).worksheet("CHAMADOS")

def extrair_campo(row, candidatos, padrao=""):
    for c in candidatos:
        if c in row.index and pd.notna(row[c]) and str(row[c]).strip() != "":
            return str(row[c]).strip()
    return padrao

def extrair_equipamento_infalivel(row):
    candidatos = [
        "Equipamento / Sistema / Local", "Equipamento/Sistema/Local", 
        "Máquina ou Equipamento", "Equipamento", "Máquina", "Maquina", 
        "Equipamento / Sistema", "Equipamento/Sistema", "Sistema / Equipamento", 
        "Qual o equipamento?", "Qual é o equipamento?", "Local / Equipamento",
        "Equipamento / Local", "Máquina / Equipamento", "Equipamento / Máquina",
        "Nome do Equipamento", "Aparelho"
    ]
    for c in candidatos:
        if c in row.index and pd.notna(row[c]) and str(row[c]).strip() != "":
            return str(row[c]).strip()
            
    candidatos_kw = ["equip", "maquin", "máquin", "aparelho", "sistema"]
    for col in row.index:
        col_clean = str(col).strip().lower()
        if any(kw in col_clean for kw in candidatos_kw):
            val = str(row[col]).strip()
            if val != "" and val.lower() not in ["nan", "none", "null", "não informado", "nao informado", "-"]:
                return val

    desc = ""
    for col in row.index:
        c_lower = str(col).lower()
        if any(k in c_lower for k in ["problema", "descri", "observa", "chamado"]):
            desc += " " + str(row[col])
            
    desc_lower = desc.lower()
    equip_keywords = [
        ("forno", "Forno AR"),
        ("campanula", "Campânula AR"),
        ("campânula", "Campânula AR"),
        ("satisloh", "Satisloh"),
        ("ultra", "Ultra Ópticos"),
        ("polidora", "Polidora"),
        ("biseladora", "Biseladora"),
        ("gerador", "Gerador"),
        ("spin", "Spin AR"),
        ("darter", "Darter"),
        ("nidek", "Nidek"),
        ("lensometro", "Lensômetro"),
        ("lensômetro", "Lensômetro"),
        ("compressor", "Compressor"),
        ("ultrassom", "Ultrassom")
    ]
    
    for kw, label in equip_keywords:
        if kw in desc_lower:
            return f"{label} (Inferido)"
            
    return "Não informado"

def parse_data_infalivel(val):
    if val is None or pd.isna(val):
        return pd.NaT
    if isinstance(val, (pd.Timestamp, datetime)):
        ts = pd.Timestamp(val)
        if getattr(ts, 'tz', None) is not None:
            ts = ts.tz_localize(None)
        return ts
        
    s = str(val).strip().lstrip("'").replace('\xa0', ' ')
    if s.lower() in ["nan", "none", "", "-", "null", "undefined"]:
        return pd.NaT

    s_clean = re.sub(r'\s+', ' ', s)

    try:
        val_float = float(s_clean)
        if 30000 <= val_float <= 70000:
            return pd.to_datetime(val_float, unit='D', origin='1899-12-30')
    except:
        pass

    try:
        dt = pd.to_datetime(s_clean, dayfirst=True, errors='coerce')
        if pd.notna(dt):
            if getattr(dt, 'tz', None) is not None:
                dt = dt.tz_localize(None)
            return dt
    except:
        pass

    try:
        dt = pd.to_datetime(s_clean, dayfirst=False, errors='coerce')
        if pd.notna(dt):
            if getattr(dt, 'tz', None) is not None:
                dt = dt.tz_localize(None)
            return dt
    except:
        pass

    return pd.NaT

def extrair_dt_abertura(row):
    candidatos = [
        "Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora", 
        "Data de Abertura", "Data", "Timestamp", "Carimbo de data / hora",
        "Data/Hora Abertura", "Data Abertura"
    ]
    val = extrair_campo(row, candidatos, "")
    if val != "":
        dt = parse_data_infalivel(val)
        if pd.notna(dt):
            return dt
            
    for col in row.index:
        col_lower = str(col).lower()
        if any(k in col_lower for k in ["carimbo", "data", "abertura", "timestamp"]):
            val_raw = str(row[col]).strip()
            dt = parse_data_infalivel(val_raw)
            if pd.notna(dt):
                return dt
                
    return pd.NaT

def extrair_dt_conclusao(row):
    candidatos = ["Data de conclusão", "Data de Conclusão", "Data Conclusão", "Data Fechamento"]
    val = extrair_campo(row, candidatos, "")
    if val != "":
        dt = parse_data_infalivel(val)
        if pd.notna(dt):
            return dt
            
    for col in row.index:
        col_lower = str(col).lower()
        if "conclu" in col_lower or "encerra" in col_lower or "fecha" in col_lower:
            val_raw = str(row[col]).strip()
            dt = parse_data_infalivel(val_raw)
            if pd.notna(dt):
                return dt
                
    return pd.NaT

def formatar_dt_exibicao(dt, val_raw=""):
    if pd.notna(dt):
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    s = str(val_raw).replace('\xa0', ' ').strip()
    return s if s not in ["", "nan", "None"] else "-"

def formatar_tempo_legivel(horas):
    if pd.isna(horas) or horas is None or horas < 0:
        return "-"
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

def formatar_tempo_curto(horas):
    if pd.isna(horas) or horas is None or horas < 0:
        return "-"
    total_min = int(round(horas * 60))
    h = total_min // 60
    m = total_min % 60
    if h > 0 and m > 0:
        return f"{h}h {m}m"
    elif h > 0:
        return f"{h}h"
    else:
        return f"{m}m"

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

def esta_no_expediente(dt_check):
    if st.session_state["sla_regime"] == "Regime 24/7":
        return True
    
    dias_map = {0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex", 5: "Sáb", 6: "Dom"}
    dia_str = dias_map.get(dt_check.weekday())
    
    if dia_str not in st.session_state["dias_expediente"]:
        return False
        
    hora_atual = dt_check.time()
    return st.session_state["hora_inicio_turno"] <= hora_atual <= st.session_state["hora_fim_turno"]

@st.cache_data(ttl=30)
def load_and_process_data():
    sheet = get_sheet()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    if df.empty: return df, df
    
    df.columns = [str(col).strip() for col in df.columns]
    df_calc = df.copy()
    
    df_calc["Num_Chamado_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["N*Chamado", "Nº Chamado", "N° Chamado"], "0"), axis=1)
    df_calc["Num_Chamado_Num"] = pd.to_numeric(df_calc["Num_Chamado_Norm"], errors="coerce").fillna(0).astype(int)
    df_calc["Solicitante_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Nome e Setor", "Nome e Setor Solicitante", "Solicitante", "Nome"], "Não informado"), axis=1)
    df_calc["Equipamento_Norm"] = df_calc.apply(extrair_equipamento_infalivel, axis=1)
    df_calc["Problema_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Qual é o problema?", "Descrição do chamado", "Tipo de problema"], "Sem descrição"), axis=1)
    df_calc["Impacto_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Qual é o impacto na operação?", "Impacto na operação", "Impacto"], "Não informado"), axis=1)
    df_calc["Area_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Área do chamado", "Nome e Setor"], "Geral"), axis=1)
    
    def sanitizar_tecnico(r):
        tec_raw = extrair_campo(r, ["Técnico Responsável", "Técnico", "Tecnico", "Responsável", "Responsavel"], "").strip()
        if tec_raw == "" or tec_raw.lower() in ["nan", "none", "não atribuído", "-"]:
            return "Não atribuído"
        return tec_raw

    def extrair_hh(r):
        for col in r.index:
            col_str = str(col).lower()
            if any(k in col_str for k in ["horas", "hora", "hh", "tempo"]):
                val_raw = str(r[col]).replace(",", ".").replace("h", "").replace("H", "").strip()
                try:
                    v = float(val_raw)
                    if v >= 0:
                        return v
                except:
                    pass
        return 0.0

    df_calc["Tecnico_Clean"] = df_calc.apply(sanitizar_tecnico, axis=1)
    df_calc["Horas_Homem"] = df_calc.apply(extrair_hh, axis=1)
    df_calc["Prioridade_Clean"] = df_calc.apply(sanitizar_prioridade_universal, axis=1)
    df_calc["Status_Clean"] = df_calc.apply(obter_status_sanitizado, axis=1)
    
    # Extração de datas direta e segura
    df_calc["dt_abertura"] = df_calc.apply(extrair_dt_abertura, axis=1)
    df_calc["dt_conclusao"] = df_calc.apply(extrair_dt_conclusao, axis=1)

    METAS_SLA = {"Alta": 4.0, "Média": 8.0, "Baixa": 48.0}
    df_calc["Meta_SLA_Horas"] = df_calc["Prioridade_Clean"].map(METAS_SLA).fillna(8.0)
    
    return df, df_calc

def criar_grafico_pareto_limpo(df_input, coluna, titulo, top_n=10):
    if coluna not in df_input.columns or df_input[coluna].dropna().empty: return None
    counts = df_input[coluna].value_counts().reset_index()
    counts.columns = [coluna, 'Ocorrências']

    if len(counts) > top_n:
        df_top = counts.iloc[:top_n].copy()
        outros_total = counts.iloc[top_n:]['Ocorrências'].sum()
        counts = pd.concat([df_top, pd.DataFrame([{coluna: 'Outros', 'Ocorrências': outros_total}])], ignore_index=True)

    counts['Acumulado'] = counts['Ocorrências'].cumsum()
    counts['% Acumulado'] = (counts['Acumulado'] / counts['Ocorrências'].sum()) * 100

    fig = go.Figure()
    fig.add_trace(go.Bar(x=counts[coluna], y=counts['Ocorrências'], name="Qtd Chamados", marker_color="#38BDF8", text=counts['Ocorrências'], textposition="outside", textfont=dict(size=11, color="#F8FAFC")))
    fig.add_trace(go.Scatter(x=counts[coluna], y=counts['% Acumulado'], name="% Acumulado", yaxis="y2", mode="lines+markers", line=dict(color="#F43F5E", width=3), marker=dict(size=7, color="#F43F5E")))
    fig.add_hline(y=80, yref="y2", line_dash="dash", line_color="#FBBF24", line_width=2)

    fig.update_layout(
        template="plotly_dark",
        title=dict(text=f"<b>{titulo}</b>", font=dict(size=15, color="#F8FAFC")),
        xaxis=dict(tickfont=dict(size=10, color="#CBD5E1"), tickangle=-15, showgrid=False),
        yaxis=dict(title=dict(text="<b>Qtd Chamados</b>", font=dict(size=11, color="#94A3B8")), tickfont=dict(size=10, color="#CBD5E1"), gridcolor="#334155", showgrid=True),
        yaxis2=dict(title=dict(text="<b>% Acumulado</b>", font=dict(size=11, color="#94A3B8")), tickfont=dict(size=10, color="#CBD5E1"), overlaying="y", side="right", range=[0, 105], showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1, font=dict(size=10, color="#F8FAFC")),
        margin=dict(l=10, r=10, t=40, b=40), height=380, paper_bgcolor="#1E293B", plot_bgcolor="#1E293B"
    )
    return fig

SENHA_CORRETA = st.secrets.get("SENHA_GESTAO", "manutencao123")

try:
    df_raw, df_calc = load_and_process_data()
except Exception as e:
    st.error(f"Erro ao conectar com a planilha: {e}")
    st.stop()

if not df_calc.empty:
    fuso_br = pytz.timezone("America/Sao_Paulo")
    agora_br = datetime.now(fuso_br)
    agora_naive_geral = pd.Timestamp(agora_br.replace(tzinfo=None))
    DATA_CORTE_TECNICA = pd.Timestamp(2026, 8, 23, 0, 0, 0)

tab_abertura, tab_dash, tab_gestao = st.tabs(["📌 Abrir Chamado", "📊 Dashboard & SLA", "⚙️ Gestão Operacional"])

# ABA 1: ABERTURA DE CHAMADO
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
            if not nome_setor or not nome_setor.strip(): campos_faltantes.append("Nome e Setor Solicitante")
            if not area or not area.strip(): campos_faltantes.append("Área do Chamado")
            if not equipamento or not equipamento.strip(): campos_faltantes.append("Equipamento / Sistema / Local")
            if not problema or not problema.strip(): campos_faltantes.append("Qual é o problema?")

            if campos_faltantes:
                st.error("🛑 **Abertura Bloqueada!** Preencha os campos obrigatórios:\n\n" + "\n".join([f"• **{c}**" for c in campos_faltantes]))
            else:
                sheet = get_sheet()
                agora = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")
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
                preencher("Descrição do chamado", problema)
                preencher("Tipo de problema", problema)
                preencher("O que foi observado?", observado)
                preencher("O que já foi feito / testado?", testado)
                preencher("Qual é o impacto na operação?", impacto)
                preencher("Prioridade", prioridade)
                preencher("Informação adicional", info_adicional)
                preencher("Status", "Pendente")
                preencher("Técnico Responsável", "Não atribuído")

                sheet.append_row(nova_linha)
                st.success(f"Chamado Nº {proximo_num} registrado com sucesso!")
                st.cache_data.clear()

# ABA 2: DASHBOARD & SLA
with tab_dash:
    col_titulo, col_filtro = st.columns([3, 1])
    with col_titulo:
        st.title("📊 Painel Gerencial & SLA")
    with col_filtro:
        opcao_periodo = st.selectbox("Filtro dos Indicadores", ["Últimos 30 dias", "Últimos 90 dias", "Este Mês", "Este Ano", "Todo o Histórico"], index=0)

    if df_calc.empty:
        st.info("Nenhum dado registrado na planilha até o momento.")
    else:
        em_expediente = esta_no_expediente(agora_naive_geral)

        # Filtro de período tolerante a datas válidas ou pendentes
        if opcao_periodo == "Últimos 30 dias":
            limite_dt = agora_naive_geral - pd.Timedelta(days=30)
            df_indicadores = df_calc[df_calc["dt_abertura"].isna() | (df_calc["dt_abertura"] >= limite_dt)].copy()
        elif opcao_periodo == "Últimos 90 dias":
            limite_dt = agora_naive_geral - pd.Timedelta(days=90)
            df_indicadores = df_calc[df_calc["dt_abertura"].isna() | (df_calc["dt_abertura"] >= limite_dt)].copy()
        elif opcao_periodo == "Este Mês":
            limite_dt = agora_naive_geral.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            df_indicadores = df_calc[df_calc["dt_abertura"].isna() | (df_calc["dt_abertura"] >= limite_dt)].copy()
        elif opcao_periodo == "Este Ano":
            limite_dt = agora_naive_geral.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            df_indicadores = df_calc[df_calc["dt_abertura"].isna() | (df_calc["dt_abertura"] >= limite_dt)].copy()
        else:
            df_indicadores = df_calc.copy()

        status_abertos = ["Pendente", "Atuando", "Aberto", "Em andamento"]
        em_aberto = len(df_calc[df_calc["Status_Clean"].isin(status_abertos)])
        total_chamados_geral = len(df_indicadores)
        total_concluidos_geral = len(df_indicadores[df_indicadores["Status_Clean"] == "Concluído"])
        taxa_conclusao_geral = (total_concluidos_geral / total_chamados_geral * 100) if total_chamados_geral > 0 else 100.0

        def calcular_tmr_mediano_geral(df_input):
            df_conc = df_input[df_input["Status_Clean"] == "Concluído"].copy()
            if df_conc.empty:
                return 0.0

            tempos = []
            for _, r in df_conc.iterrows():
                dt_ab = r.get("dt_abertura")
                dt_conc = r.get("dt_conclusao")
                hh = r.get("Horas_Homem", 0.0)

                if pd.notna(dt_ab) and pd.notna(dt_conc):
                    dur = (dt_conc - dt_ab).total_seconds() / 3600.0
                    if 0.01 <= dur <= 720:
                        tempos.append(dur)
                        continue

                if pd.notna(hh) and hh > 0:
                    tempos.append(hh)

            if tempos:
                return float(np.median(tempos))
            return 1.5

        tmr_geral_num = calcular_tmr_mediano_geral(df_indicadores)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Chamados", total_chamados_geral)
        c2.metric("Em Aberto", em_aberto)
        c3.metric("Taxa Resolução", f"{taxa_conclusao_geral:.1f}%")
        c4.metric("TMR Mediano", formatar_tempo_legivel(tmr_geral_num))
        c5.metric("SLA / Expediente", "▶️ Ativo" if em_expediente else "⏸️ Pausado")

        st.markdown("---")

        # Volumetria por Período
        df_temp_validos = df_calc.dropna(subset=["dt_abertura"]).copy()
        inicio_hoje = agora_naive_geral.floor("D")
        inicio_semana = inicio_hoje - pd.Timedelta(days=agora_naive_geral.weekday())
        inicio_mes = agora_naive_geral.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        inicio_ano = agora_naive_geral.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

        qtd_hoje = len(df_temp_validos[df_temp_validos["dt_abertura"] >= inicio_hoje])
        qtd_semana = len(df_temp_validos[df_temp_validos["dt_abertura"] >= inicio_semana])
        qtd_mes = len(df_temp_validos[df_temp_validos["dt_abertura"] >= inicio_mes])
        qtd_ano = len(df_temp_validos[df_temp_validos["dt_abertura"] >= inicio_ano])

        st.markdown("##### 📅 Volumetria por Período")
        ct1, ct2, ct3, ct4 = st.columns(4)
        ct1.metric("Hoje", qtd_hoje)
        ct2.metric("Semana", qtd_semana)
        ct3.metric("Mês", qtd_mes)
        ct4.metric("Ano", qtd_ano)

        st.markdown("---")

        # Barra de Vida & Saúde do SLA DENTRO DO CARD HTML
        st.markdown(f"##### ⏳ Barra de Vida & Saúde do SLA por Fila (Regime: `{st.session_state['sla_regime']}`)")
        if not em_expediente:
            st.info("⏸️ **Expediente Suspenso:** Fora do horário de trabalho configurado. O contador do SLA está congelado.")

        def cartao_barra_vida_interna(col, nome_prio, meta_horas):
            sub_prio = df_calc[(df_calc["Prioridade_Clean"] == nome_prio) & (df_calc["Status_Clean"] != "Concluído")]
            qtd_a = len(sub_prio)
            qtd_atuando = len(sub_prio[sub_prio["Status_Clean"] == "Atuando"])
            qtd_pendente = len(sub_prio[sub_prio["Status_Clean"] == "Pendente"])

            if qtd_a == 0:
                pct_saude = 100.0
                cor_status = "#22C55E"
                texto_status = "100% (Fila em Dia)"
            else:
                somas_saude = []
                agora_loop = pd.Timestamp(datetime.now(pytz.timezone("America/Sao_Paulo")).replace(tzinfo=None))
                for _, r in sub_prio.iterrows():
                    dt_ab = r.get("dt_abertura")
                    if pd.notna(dt_ab):
                        decorrido = (agora_loop - dt_ab).total_seconds() / 3600.0
                        restante = meta_horas - decorrido
                        pct_individual = max(0.0, (restante / meta_horas) * 100.0)
                        somas_saude.append(pct_individual)
                    else:
                        somas_saude.append(100.0)
                pct_saude = sum(somas_saude) / len(somas_saude) if somas_saude else 100.0
                cor_status = "#22C55E" if pct_saude > 50.0 else ("#F59E0B" if pct_saude > 20.0 else "#EF4444")
                if not em_expediente:
                    texto_status = f"{pct_saude:.1f}% (⏸️ Pausado)"
                else:
                    texto_status = f"{pct_saude:.1f}% ({qtd_a} ativos)"

            pct_bar = max(0.0, min(100.0, pct_saude))
            html_card = textwrap.dedent(f"""
                <div style="background-color:#1E293B; border:2px solid {cor_status}; padding:15px; border-radius:12px; margin-bottom:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:800; color:{cor_status}; font-size:1.1rem;">{nome_prio.upper()}</span>
                        <span style="font-size:0.8rem; color:#94A3B8; font-weight:600;">Meta: {formatar_tempo_legivel(meta_horas)}</span>
                    </div>
                    <div style="font-size:1.8rem; font-weight:800; color:{cor_status}; margin:6px 0 2px 0;">{texto_status}</div>
                    <div style="background-color: #334155; border-radius: 6px; height: 10px; width: 100%; margin: 8px 0; overflow: hidden;">
                        <div style="background-color: {cor_status}; height: 100%; width: {pct_bar:.1f}%;"></div>
                    </div>
                    <div style="margin-top:8px; padding-top:8px; border-top:1px solid #334155; font-size:0.8rem; color:#CBD5E1; display:flex; justify-content:space-between;">
                        <span>🟣 Atuando: <b style="color:#C084FC;">{qtd_atuando}</b></span>
                        <span>🟡 Pendente: <b style="color:#FBBF24;">{qtd_pendente}</b></span>
                    </div>
                </div>
            """).strip()

            with col:
                st.markdown(html_card, unsafe_allow_html=True)

        ca, cm, cb = st.columns(3)
        cartao_barra_vida_interna(ca, "Alta", 4.0)
        cartao_barra_vida_interna(cm, "Média", 8.0)
        cartao_barra_vida_interna(cb, "Baixa", 48.0)

        st.markdown("---")

        # Monitoramento Operacional de Chamados Ativos em Aberto COM CORES DINÂMICAS DE SLA
        st.markdown(f"##### 🚨 Monitoramento Operacional (Chamados Ativos em Aberto: {em_aberto})")
        df_abertos = df_calc[df_calc["Status_Clean"].isin(["Pendente", "Atuando"])].copy()
        if not df_abertos.empty:
            lista_ativos = []
            agora_loop = pd.Timestamp(datetime.now(pytz.timezone("America/Sao_Paulo")).replace(tzinfo=None))
            for _, row in df_abertos.iterrows():
                dt_ab = row.get("dt_abertura")
                meta = row.get("Meta_SLA_Horas", 8.0)
                raw_ab = extrair_campo(row, ["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora", "Data de Abertura", "Data", "Timestamp"], "")
                dt_ab_str = formatar_dt_exibicao(dt_ab, raw_ab)

                if pd.notna(dt_ab) and dt_ab < DATA_CORTE_TECNICA:
                    situacao = "100% (Legado)"
                    tempo_dec_str = "✅ Anistia (Legado)"
                elif pd.notna(dt_ab):
                    tempo_decorrido = (agora_loop - dt_ab).total_seconds() / 3600.0
                    tempo_restante = meta - tempo_decorrido
                    pct_v = max(0.0, (tempo_restante / meta) * 100.0)
                    
                    sufixo_exp = " (⏸️ Pausado)" if not em_expediente else ""
                    if tempo_restante >= 0:
                        situacao = f"{pct_v:.0f}% Prazo Restante{sufixo_exp}"
                        tempo_dec_str = f"⏳ {formatar_tempo_curto(tempo_restante)} restantes{sufixo_exp}"
                    else:
                        situacao = f"🔴 0% Estourado"
                        tempo_dec_str = f"🔴 Estourado (+{formatar_tempo_curto(abs(tempo_restante))})"
                else:
                    situacao = "100% (Sem data)"
                    tempo_dec_str = "-"

                lista_ativos.append({
                    "Nº": row.get("Num_Chamado_Num"),
                    "Solicitante": row.get("Solicitante_Norm"),
                    "Abertura": dt_ab_str,
                    "Área": row.get("Area_Norm"),
                    "Equipamento": row.get("Equipamento_Norm"),
                    "Descrição do Problema": row.get("Problema_Norm"),
                    "Impacto": row.get("Impacto_Norm"),
                    "Prioridade": row.get("Prioridade_Clean"),
                    "Status": "🟣 Atuando" if row.get("Status_Clean") == "Atuando" else "🟡 Pendente",
                    "Saúde SLA": situacao,
                    "Tempo Restante": tempo_dec_str,
                    "Técnico": row.get("Tecnico_Clean", "Não atribuído")
                })

            df_disp_ativos = pd.DataFrame(lista_ativos).sort_values("Nº", ascending=False)

            def colorir_linha_monitoramento(row):
                salud = str(row.get("Saúde SLA", ""))
                tempo = str(row.get("Tempo Restante", ""))
                prio = str(row.get("Prioridade", "")).lower()
                
                if "estourado" in salud.lower() or "estourado" in tempo.lower() or "🔴" in salud:
                    return ['background-color: #7F1D1D; color: #FECDD3; font-weight: 700;'] * len(row)
                
                m_pct = re.search(r'(\d+)%', salud)
                if m_pct:
                    pct_val = int(m_pct.group(1))
                    if pct_val > 50:
                        return ['background-color: #064E3B; color: #A7F3D0; font-weight: 700;'] * len(row)
                    elif pct_val > 20:
                        return ['background-color: #78350F; color: #FDE68A; font-weight: 700;'] * len(row)
                    else:
                        return ['background-color: #7F1D1D; color: #FECDD3; font-weight: 700;'] * len(row)

                if "alt" in prio:
                    return ['background-color: #7F1D1D; color: #FECDD3; font-weight: 700;'] * len(row)
                elif "med" in prio or "méd" in prio:
                    return ['background-color: #78350F; color: #FDE68A; font-weight: 700;'] * len(row)
                else:
                    return ['background-color: #064E3B; color: #A7F3D0; font-weight: 700;'] * len(row)

            styled_ativos = df_disp_ativos.style.apply(colorir_linha_monitoramento, axis=1)
            st.dataframe(styled_ativos, use_container_width=True, hide_index=True)
        else:
            st.success("✅ Nenhum chamado ativo pendente no momento.")

        st.markdown("---")

        # Histórico Geral de Chamados
        col_hist_tit, col_hist_lim = st.columns([3, 1])
        with col_hist_tit:
            st.markdown(f"##### 📋 Histórico Geral de Chamados & SLA (Exibindo: {len(df_indicadores)} de {total_chamados_geral})")
        with col_hist_lim:
            limite_exibicao = st.selectbox("Exibir no histórico:", [50, 100, 200, "Todos"], index=0)

        lista_geral = []
        for _, row in df_indicadores.iterrows():
            st_str = str(row.get("Status_Clean", "Pendente"))
            dt_ab = row.get("dt_abertura")
            dt_conc = row.get("dt_conclusao")
            meta = row.get("Meta_SLA_Horas", 8.0)
            raw_ab = extrair_campo(row, ["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora", "Data de Abertura"], "")
            dt_ab_str = formatar_dt_exibicao(dt_ab, raw_ab)

            if pd.notna(dt_ab) and dt_ab < DATA_CORTE_TECNICA:
                tmr_str = formatar_tempo_legivel((dt_conc - dt_ab).total_seconds() / 3600.0) if pd.notna(dt_conc) else "Legado"
                sit_str = "✅ Cumprido (Legado)"
                status_disp = "🟢 Concluído" if st_str == "Concluído" else ("🟣 Atuando" if st_str == "Atuando" else "🟡 Pendente")
            elif st_str == "Concluído":
                if pd.notna(dt_conc) and pd.notna(dt_ab):
                    tempo_num = (dt_conc - dt_ab).total_seconds() / 3600.0
                    sla_ok = tempo_num <= meta
                    sit_str = "✅ Cumprido" if sla_ok else f"🔴 Estourado (+{formatar_tempo_legivel(tempo_num - meta)})"
                    tmr_str = formatar_tempo_legivel(tempo_num)
                else:
                    tmr_str = "Concluído"
                    sit_str = "✅ Concluído"
                status_disp = "🟢 Concluído"
            else:
                if not em_expediente:
                    tmr_str = "⏸️ Pausado"
                    sit_str = "⏸️ Pausado (Fora de Turno)"
                elif pd.notna(dt_ab):
                    tempo_decorrido = (agora_naive_geral - dt_ab).total_seconds() / 3600.0
                    tempo_restante = meta - tempo_decorrido
                    if tempo_restante < 0:
                        sit_str = f"🔴 Estourado (+{formatar_tempo_legivel(abs(tempo_restante))})"
                        tmr_str = f"🔴 Estourado (+{formatar_tempo_legivel(abs(tempo_restante))})"
                    else:
                        sit_str = f"🟢 No Prazo ({formatar_tempo_legivel(tempo_restante)} restantes)"
                        tmr_str = f"⏳ {formatar_tempo_legivel(tempo_restante)} restantes"
                else:
                    tmr_str = "-"
                    sit_str = "⚪ Sem data"

                status_disp = "🟣 Atuando" if st_str == "Atuando" else "🟡 Pendente"

            lista_geral.append({
                "Nº": row.get("Num_Chamado_Num"),
                "Solicitante": row.get("Solicitante_Norm"),
                "Abertura": dt_ab_str,
                "Área": row.get("Area_Norm"),
                "Equipamento": row.get("Equipamento_Norm"),
                "Descrição do Problema": row.get("Problema_Norm"),
                "Impacto": row.get("Impacto_Norm"),
                "Prioridade": row.get("Prioridade_Clean"),
                "Status": status_disp,
                "Tempo / TMR": tmr_str,
                "Situação SLA": sit_str,
                "Técnico": row.get("Tecnico_Clean", "Não atribuído")
            })

        if lista_geral:
            df_geral = pd.DataFrame(lista_geral).sort_values("Nº", ascending=False)
            if limite_exibicao != "Todos":
                df_geral = df_geral.head(int(limite_exibicao))

            def colorir_linha_geral(row):
                st_val = str(row["Status"])
                prio = str(row["Prioridade"]).strip().lower()
                if "Concluído" in st_val:
                    return ['background-color: #064E3B; color: #A7F3D0; font-weight: 700;'] * len(row)
                else:
                    if "alta" in prio:
                        return ['background-color: #7F1D1D; color: #FECDD3; font-weight: 700;'] * len(row)
                    elif "media" in prio:
                        return ['background-color: #78350F; color: #FDE68A; font-weight: 700;'] * len(row)
                    else:
                        return ['background-color: #1E3A8A; color: #F0F9FF; font-weight: 700;'] * len(row)

            styled_geral = df_geral.style.apply(colorir_linha_geral, axis=1)
            st.dataframe(styled_geral, use_container_width=True, hide_index=True)

        st.markdown("---")

        # Desempenho por Técnico - DETALHAMENTO DE TMR POR PRIORIDADE (ALTA, MÉDIA, BAIXA) E HORAS
        st.markdown(f"##### 👷 Desempenho por Técnico & Tempo Médio por Prioridade ({opcao_periodo})")
        if not df_indicadores.empty:
            df_tec_analise = df_indicadores[df_indicadores["Tecnico_Clean"] != "Não atribuído"].copy()
            if not df_tec_analise.empty:
                METAS_SLA = {"Alta": 4.0, "Média": 8.0, "Baixa": 48.0}

                def calc_duracao_h(r):
                    st_val = r.get("Status_Clean", "")
                    dt_ab = r.get("dt_abertura")
                    dt_conc = r.get("dt_conclusao")
                    if st_val == "Concluído" and pd.notna(dt_ab) and pd.notna(dt_conc) and dt_ab >= DATA_CORTE_TECNICA:
                        dur = (dt_conc - dt_ab).total_seconds() / 3600.0
                        if 0 <= dur <= 720:
                            return dur
                    return np.nan

                def calc_sla_ok(r):
                    st_val = r.get("Status_Clean", "")
                    dt_ab = r.get("dt_abertura")
                    dt_conc = r.get("dt_conclusao")
                    prio = r.get("Prioridade_Clean", "Média")
                    meta = METAS_SLA.get(prio, 8.0)

                    if pd.isna(dt_ab) or dt_ab < DATA_CORTE_TECNICA:
                        return True

                    if st_val == "Concluído":
                        if pd.notna(dt_conc):
                            dur = (dt_conc - dt_ab).total_seconds() / 3600.0
                            return dur <= meta
                        return True
                    else:
                        agora = pd.Timestamp(datetime.now(pytz.timezone("America/Sao_Paulo")).replace(tzinfo=None))
                        dur = (agora - dt_ab).total_seconds() / 3600.0
                        return dur <= meta

                df_tec_analise["Duracao_H"] = df_tec_analise.apply(calc_duracao_h, axis=1)
                df_tec_analise["SLA_OK"] = df_tec_analise.apply(calc_sla_ok, axis=1)

                tecnicos_unicos = df_tec_analise["Tecnico_Clean"].unique()
                linhas_tec = []

                for tec in tecnicos_unicos:
                    sub = df_tec_analise[df_tec_analise["Tecnico_Clean"] == tec]
                    tot = len(sub)
                    conc = len(sub[sub["Status_Clean"] == "Concluído"])
                    hh_sum = sub["Horas_Homem"].sum()
                    sla_pct = (sub["SLA_OK"].sum() / tot * 100.0) if tot > 0 else 100.0

                    tmr_geral = sub["Duracao_H"].median()
                    sub_alta = sub[(sub["Prioridade_Clean"] == "Alta") & (sub["Duracao_H"].notna())]
                    sub_media = sub[(sub["Prioridade_Clean"] == "Média") & (sub["Duracao_H"].notna())]
                    sub_baixa = sub[(sub["Prioridade_Clean"] == "Baixa") & (sub["Duracao_H"].notna())]

                    tmr_alta = sub_alta["Duracao_H"].median() if not sub_alta.empty else np.nan
                    tmr_media = sub_media["Duracao_H"].median() if not sub_media.empty else np.nan
                    tmr_baixa = sub_baixa["Duracao_H"].median() if not sub_baixa.empty else np.nan

                    linhas_tec.append({
                        "Técnico Responsável": tec,
                        "Total Chamados": tot,
                        "Concluídos": conc,
                        "Horas-Homem": f"{hh_sum:.1f}h",
                        "TMR Geral": formatar_tempo_curto(tmr_geral),
                        "TMR Alta (Meta 4h)": formatar_tempo_curto(tmr_alta),
                        "TMR Média (Meta 8h)": formatar_tempo_curto(tmr_media),
                        "TMR Baixa (Meta 48h)": formatar_tempo_curto(tmr_baixa),
                        "SLA (%)": f"{sla_pct:.1f}%"
                    })

                df_exib_tec = pd.DataFrame(linhas_tec).sort_values("Total Chamados", ascending=False)
                st.dataframe(df_exib_tec, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum técnico atribuído nos chamados do período selecionado.")

        st.markdown("---")

        fig_equip = criar_grafico_pareto_limpo(df_indicadores, "Equipamento_Norm", "Top Equipamentos Críticos", top_n=10)
        if fig_equip: st.plotly_chart(fig_equip, use_container_width=True)

        st.markdown("---")

        fig_setor = criar_grafico_pareto_limpo(df_indicadores, "Area_Norm", "Top Setores Solicitantes", top_n=10)
        if fig_setor: st.plotly_chart(fig_setor, use_container_width=True)

# ABA 3: GESTÃO OPERACIONAL E CONFIGURAÇÃO RESTRITA DE TURNOS
with tab_gestao:
    st.title("⚙️ Gestão Operacional & Configurações de SLA")
    senha_digitada = st.text_input("Chave de Acesso Operacional", type="password", key="pwd_gestao_aba3")

    if senha_digitada != SENHA_CORRETA:
        st.warning("🔒 Digite a chave de acesso para alterar configurações de turnos ou editar chamados.")
    else:
        st.subheader("🕒 Configuração Restrita de Turnos & Regras SLA")
        with st.expander("Ajustar Horário de Expediente e Pausa de SLA", expanded=False):
            with st.form("form_config_turnos_gestao"):
                regime_sel = st.radio(
                    "REGRA DE CONTAGEM DE SLA",
                    ["Regime 24/7", "Horário Comercial"],
                    index=0 if st.session_state["sla_regime"] == "Regime 24/7" else 1
                )
                dias_sel = st.multiselect(
                    "Dias de Expediente da Fábrica:",
                    ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"],
                    default=st.session_state["dias_expediente"]
                )
                c_ini, c_fim = st.columns(2)
                with c_ini: h_ini = st.time_input("Início do Turno:", st.session_state["hora_inicio_turno"])
                with c_fim: h_fim = st.time_input("Fim do Turno:", st.session_state["hora_fim_turno"])

                if st.form_submit_button("Salvar Regras de Turno"):
                    st.session_state["sla_regime"] = regime_sel
                    st.session_state["dias_expediente"] = dias_sel
                    st.session_state["hora_inicio_turno"] = h_ini
                    st.session_state["hora_fim_turno"] = h_fim
                    st.success("Configurações de SLA atualizadas com sucesso!")
                    st.rerun()

        st.markdown("---")
        st.subheader("Atualizar Status de Chamado & Apontamento Técnico")

        num_chamado = st.number_input("Informe o Nº do Chamado para atualizar", min_value=1, step=1)
        mask_num = df_calc["Num_Chamado_Num"] == num_chamado

        if mask_num.any():
            idx_linha = df_calc[mask_num].index[0]
            linha_atual = df_raw.iloc[idx_linha]
            st.info(f"Chamado #{num_chamado}: {extrair_campo(linha_atual, ['Equipamento / Sistema / Local'])}")

            with st.form("form_atualizacao"):
                col_a, col_b = st.columns(2)
                sheet = get_sheet()
                headers = [str(h).strip() for h in sheet.row_values(1)]

                with col_a:
                    novo_status = st.selectbox("Status", ["Pendente", "Atuando", "Concluído"])
                    tecnico = st.selectbox("Técnico Responsável", ["Eric", "Felipe", "Outro"])
                    hh_in = st.text_input("Horas-Homem Aplicadas (ex: 1.5)", value=str(linha_atual.get("Horas-Homem", "1.0")))
                with col_b:
                    obs_interna = st.text_area("Diagnóstico / Ação Executada", value=str(linha_atual.get("Observação Interna", "")))

                if st.form_submit_button("Salvar Alterações"):
                    linha_excel = idx_linha + 2
                    updates_lote = []

                    if "Status" in headers: updates_lote.append({'range': rowcol_to_a1(linha_excel, headers.index("Status") + 1), 'values': [[novo_status]]})
                    if "Técnico Responsável" in headers: updates_lote.append({'range': rowcol_to_a1(linha_excel, headers.index("Técnico Responsável") + 1), 'values': [[tecnico]]})
                    if "Horas-Homem" in headers: updates_lote.append({'range': rowcol_to_a1(linha_excel, headers.index("Horas-Homem") + 1), 'values': [[hh_in]]})
                    if "Observação Interna" in headers: updates_lote.append({'range': rowcol_to_a1(linha_excel, headers.index("Observação Interna") + 1), 'values': [[obs_interna]]})

                    if novo_status == "Concluído" and "Data de conclusão" in headers:
                        data_conc = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")
                        updates_lote.append({'range': rowcol_to_a1(linha_excel, headers.index("Data de conclusão") + 1), 'values': [[data_conc]]})

                    if updates_lote: sheet.batch_update(updates_lote)
                    st.success(f"Chamado #{num_chamado} atualizado com sucesso!")
                    st.cache_data.clear()