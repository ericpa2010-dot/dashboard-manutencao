import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
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

# CSS: Design System Escuro Futurista Idêntico ao Preview
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

   /* Botões Principais */
   div.stButton > button {
       background-color: #38BDF8 !important;
       color: #0F172A !important;
       font-weight: 800 !important;
       border-radius: 8px !important;
       padding: 10px 20px !important;
       border: none !important;
       transition: all 0.2s ease;
   }
   div.stButton > button:hover {
       background-color: #7DD3FC !important;
       color: #0F172A !important;
       transform: scale(1.01);
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

# Estado global para regras de turno
if "hora_inicio_turno" not in st.session_state:
    st.session_state["hora_inicio_turno"] = 8
if "hora_fim_turno" not in st.session_state:
    st.session_state["hora_fim_turno"] = 19

@st.cache_resource(ttl=60)
def get_gspread_client():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace(r"\n", "\n")
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)

def get_sheet():
    client = get_gspread_client()
    return client.open_by_url(st.secrets["spreadsheet"]["url"]).worksheet("CHAMADOS")

def extrair_campo_flexivel(row, candidatos, padrao=""):
    for c in candidatos:
        c_clean = str(c).strip().lower()
        for col_name in row.index:
            col_clean = str(col_name).strip().lower()
            if col_clean == c_clean:
                val = str(row[col_name]).replace('\xa0', ' ').strip()
                if val != "" and val.lower() not in ["nan", "none", "null"]:
                    return val

    for c in candidatos:
        c_alnum = re.sub(r'[^a-z0-9]', '', str(c).lower())
        for col_name in row.index:
            col_alnum = re.sub(r'[^a-z0-9]', '', str(col_name).lower())
            if col_alnum == c_alnum and c_alnum != "":
                val = str(row[col_name]).replace('\xa0', ' ').strip()
                if val != "" and val.lower() not in ["nan", "none", "null"]:
                    return val

    for c in candidatos:
        c_clean = str(c).strip().lower()
        if len(c_clean) > 3:
            for col_name in row.index:
                col_clean = str(col_name).strip().lower()
                if c_clean in col_clean:
                    val = str(row[col_name]).replace('\xa0', ' ').strip()
                    if val != "" and val.lower() not in ["nan", "none", "null"]:
                        return val
    return padrao

def encontrar_coluna(headers, candidatos):
    for c in candidatos:
        c_alnum = re.sub(r'[^a-z0-9]', '', str(c).lower())
        for idx, h in enumerate(headers):
            h_alnum = re.sub(r'[^a-z0-9]', '', str(h).lower())
            if h_alnum == c_alnum and c_alnum != "":
                return idx, h
    return None, None

def dentro_do_expediente(dt, hora_inicio=None, hora_fim=None):
    if hora_inicio is None: hora_inicio = st.session_state.get("hora_inicio_turno", 8)
    if hora_fim is None: hora_fim = st.session_state.get("hora_fim_turno", 19)
    if pd.isna(dt): return False
    if dt.weekday() >= 5: return False
    return hora_inicio <= dt.hour < hora_fim

def calcular_horas_uteis(dt_inicio, dt_fim, hora_inicio=None, hora_fim=None):
    if hora_inicio is None: hora_inicio = st.session_state.get("hora_inicio_turno", 8)
    if hora_fim is None: hora_fim = st.session_state.get("hora_fim_turno", 19)
    
    if pd.isna(dt_inicio) or pd.isna(dt_fim): return 0.0
    
    if hasattr(dt_inicio, 'tzinfo') and dt_inicio.tzinfo is not None:
        dt_inicio = dt_inicio.tz_convert(None)
    if hasattr(dt_fim, 'tzinfo') and dt_fim.tzinfo is not None:
        dt_fim = dt_fim.tz_convert(None)
        
    dt_inicio = pd.Timestamp(dt_inicio)
    dt_fim = pd.Timestamp(dt_fim)
    
    if dt_inicio >= dt_fim: return 0.0

    total_segundos = 0.0
    curr = dt_inicio
    max_dias = 1000
    contador = 0
    
    while curr < dt_fim and contador < max_dias:
        contador += 1
        if curr.weekday() < 5:
            inicio_turno = curr.replace(hour=hora_inicio, minute=0, second=0, microsecond=0)
            fim_turno = curr.replace(hour=hora_fim, minute=0, second=0, microsecond=0)
            
            win_start = max(curr, inicio_turno)
            win_end = min(dt_fim, fim_turno)
            
            if win_start < win_end:
                total_segundos += (win_end - win_start).total_seconds()
        
        proximo_dia = (curr + pd.Timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        curr = proximo_dia
        
    return total_segundos / 3600.0

def parse_data_infalivel(val):
    if not val or pd.isna(val):
        return pd.NaT
    s = str(val).replace('\xa0', ' ').strip()
    if s.lower() in ["nan", "none", "", "-", "null", "0"]:
        return pd.NaT
    
    try:
        val_float = float(s)
        if val_float > 30000:
            return pd.to_datetime(val_float, unit='D', origin='1899-12-30')
    except (ValueError, TypeError):
        pass

    m_br = re.search(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?:\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?', s)
    if m_br:
        d, m, y = int(m_br.group(1)), int(m_br.group(2)), int(m_br.group(3))
        h = int(m_br.group(4)) if m_br.group(4) is not None else 0
        mi = int(m_br.group(5)) if m_br.group(5) is not None else 0
        sec = int(m_br.group(6)) if m_br.group(6) is not None else 0
        try: return pd.Timestamp(y, m, d, h, mi, sec)
        except ValueError: pass

    m_iso = re.search(r'(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})(?:\s+|T)?(\d{1,2})?:?(\d{1,2})?:?(\d{1,2})?', s)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        h = int(m_iso.group(4)) if m_iso.group(4) is not None else 0
        mi = int(m_iso.group(5)) if m_iso.group(5) is not None else 0
        sec = int(m_iso.group(6)) if m_iso.group(6) is not None else 0
        try: return pd.Timestamp(y, m, d, h, mi, sec)
        except ValueError: pass

    return pd.to_datetime(s, errors="coerce", dayfirst=True)

def extrair_dt_abertura(row):
    val = extrair_campo_flexivel(row, ["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora", "Data de Abertura", "Data", "Timestamp"], "")
    return parse_data_infalivel(val)

def extrair_dt_conclusao(row):
    val = extrair_campo_flexivel(row, ["Data de conclusão", "Data de Conclusão", "Data Conclusão"], "")
    return parse_data_infalivel(val)

def formatar_dt_exibicao(dt, val_raw=""):
    if pd.notna(dt): return dt.strftime("%d/%m/%Y %H:%M:%S")
    s = str(val_raw).replace('\xa0', ' ').strip()
    return s if s not in ["", "nan", "None", "-"] else "-"

def formatar_tempo_legivel(horas):
    if pd.isna(horas) or horas is None or horas < 0: return "0s"
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
    p_raw = str(extrair_campo_flexivel(r, ["Prioridade", "Prioridade Sugerida"], "")).strip().lower()
    if "alt" in p_raw: return "Alta"
    elif "med" in p_raw or "méd" in p_raw: return "Média"
    elif "baix" in p_raw: return "Baixa"
    return "Média"

def obter_status_sanitizado(r):
    dt_conc_raw = extrair_campo_flexivel(r, ["Data de conclusão", "Data de Conclusão", "Data Conclusão"], "")
    dt_conc_parsed = parse_data_infalivel(dt_conc_raw)
    
    if pd.notna(dt_conc_parsed):
        return "Concluído"
    
    st_raw = extrair_campo_flexivel(r, ["Status", "STATUS", "Situação", "Situacao"], "").upper()
    if any(k in st_raw for k in ["CONCLU", "RESOLV", "FECHAD", "FINALIZAD"]):
        return "Concluído"
    if any(k in st_raw for k in ["ATUAND", "ANDAMENTO", "EM ATENDIMENTO", "EM ANDAMENTO"]):
        return "Atuando"
    return "Pendente"

def sanitizar_tecnico(r):
    tec_raw = extrair_campo_flexivel(r, ["Técnico Responsável", "Técnico", "Tecnico", "Técnico Responsavel", "Responsável", "Técnico Atribuído", "Atribuído a"], "")
    tec_clean = tec_raw.strip().title()
    if tec_clean == "" or tec_clean.lower() in ["nan", "none", "não atribuído", "nao atribuido", "-", "null", "eric (histórico geral)", "eric (historico geral)"]:
        return "Eric"
    if "Felipe" in tec_clean:
        return "Felipe"
    if "Eric" in tec_clean:
        return "Eric"
    return tec_clean

@st.cache_data(ttl=30)
def load_and_process_data():
    sheet = get_sheet()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    if df.empty: return df, df
    
    df.columns = [str(col).strip() for col in df.columns]
    df_calc = df.copy()
    
    df_calc["Num_Chamado_Norm"] = df_calc.apply(lambda r: extrair_campo_flexivel(r, ["N*Chamado", "Nº Chamado", "N° Chamado", "Chamado"], "0"), axis=1)
    df_calc["Num_Chamado_Num"] = pd.to_numeric(df_calc["Num_Chamado_Norm"], errors="coerce").fillna(0).astype(int)
    
    df_calc["Solicitante_Norm"] = df_calc.apply(lambda r: extrair_campo_flexivel(r, ["Nome e Setor", "Nome e Setor Solicitante", "Solicitante", "Nome"], "Não informado"), axis=1)
    df_calc["Equipamento_Norm"] = df_calc.apply(lambda r: extrair_campo_flexivel(r, ["Equipamento / Sistema / Local", "Equipamento/Sistema/Local", "Máquina ou Equipamento", "Equipamento"], "Não informado"), axis=1)
    df_calc["Problema_Norm"] = df_calc.apply(lambda r: extrair_campo_flexivel(r, ["Qual é o problema?", "Descrição do chamado", "Tipo de problema", "Problema"], "Sem descrição"), axis=1)
    df_calc["Impacto_Norm"] = df_calc.apply(lambda r: extrair_campo_flexivel(r, ["Qual é o impacto na operação?", "Impacto na operação", "Impacto"], "Não informado"), axis=1)
    df_calc["Area_Norm"] = df_calc.apply(lambda r: extrair_campo_flexivel(r, ["Área do chamado", "Área", "Setor"], "Geral"), axis=1)
    
    df_calc["Tecnico_Clean"] = df_calc.apply(sanitizar_tecnico, axis=1)
    df_calc["Prioridade_Clean"] = df_calc.apply(sanitizar_prioridade_universal, axis=1)
    df_calc["Status_Clean"] = df_calc.apply(obter_status_sanitizado, axis=1)
    
    list_ab = [extrair_dt_abertura(r) for _, r in df_calc.iterrows()]
    list_conc = [extrair_dt_conclusao(r) for _, r in df_calc.iterrows()]
    
    df_calc["dt_abertura"] = pd.to_datetime(list_ab, errors="coerce")
    df_calc["dt_conclusao"] = pd.to_datetime(list_conc, errors="coerce")

    METAS_SLA = {"Alta": 4.0, "Média": 8.0, "Baixa": 48.0}
    df_calc["Meta_SLA_Horas"] = df_calc["Prioridade_Clean"].map(METAS_SLA).fillna(8.0)
    
    return df, df_calc

def calcular_tempo_resolucao_concluido(row):
    dt_ab = row.get("dt_abertura")
    dt_conc = row.get("dt_conclusao")
    if pd.notna(dt_ab) and pd.notna(dt_conc) and dt_conc >= dt_ab:
        return calcular_horas_uteis(dt_ab, dt_conc)
    
    hh_raw = str(extrair_campo_flexivel(row, ["Horas-Homem Aplicadas (ex: 1.5)", "Horas-Homem", "Horas Homem", "Horas"], "")).replace(",", ".").strip()
    try:
        v = float(hh_raw)
        if v > 0: return v
    except ValueError:
        pass
    
    return 1.0

def criar_grafico_pareto_limpo(df_input, coluna, titulo, top_n=10):
    if coluna not in df_input.columns or df_input[coluna].dropna().empty: return None

    counts = df_input[coluna].value_counts().reset_index()
    counts.columns = [coluna, 'Ocorrências']

    if len(counts) > top_n:
        df_top = counts.iloc[:top_n].copy()
        outros_total = counts.iloc[top_n:]['Ocorrências'].sum()
        df_outros = pd.DataFrame([{coluna: 'Outros', 'Ocorrências': outros_total}])
        counts = pd.concat([df_top, df_outros], ignore_index=True)

    counts['Acumulado'] = counts['Ocorrências'].cumsum()
    counts['% Acumulado'] = (counts['Acumulado'] / counts['Ocorrências'].sum()) * 100

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=counts[coluna], y=counts['Ocorrências'], name="Qtd Chamados",
        marker_color="#38BDF8", text=counts['Ocorrências'], textposition="outside",
        textfont=dict(size=11, color="#F8FAFC")
    ))
    fig.add_trace(go.Scatter(
        x=counts[coluna], y=counts['% Acumulado'], name="% Acumulado", yaxis="y2",
        mode="lines+markers", line=dict(color="#F43F5E", width=3), marker=dict(size=7, color="#F43F5E")
    ))
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

tab_abertura, tab_dash, tab_gestao = st.tabs(["📌 Abrir Chamado", "📊 Dashboard & SLA", "⚙️ Gestão Operacional"])

# ==========================================
# ABA 1: ABERTURA DE CHAMADO (LAYOUT VISUAL DO PREVIEW)
# ==========================================
with tab_abertura:
    
    # Header estilizado
    st.markdown("""
        <div style="border-bottom: 1px solid #334155; padding-bottom: 12px; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h2 style="margin: 0; color: #F8FAFC; font-size: 1.4rem;">📌 Abertura de Chamado & Diagnóstico</h2>
                <p style="margin: 4px 0 0 0; color: #94A3B8; font-size: 0.85rem;">Escolha como prefere registrar o chamado de manutenção:</p>
            </div>
            <span style="background: rgba(56, 189, 248, 0.15); color: #38BDF8; padding: 4px 12px; border-radius: 9999px; font-size: 0.75rem; font-weight: 700; border: 1px solid rgba(56, 189, 248, 0.3);">
                ⚡ Rápido e Seguro
            </span>
        </div>
    """, unsafe_allow_html=True)

    # 2 Cards Visuais de Escolha (Voz vs Manual)
    col_card_v, col_card_m = st.columns(2)
    
    with col_card_v:
        btn_modo_voz = st.button("🎙️ Abertura por Voz (Áudio IA)", use_container_width=True)
    with col_card_m:
        btn_modo_manual = st.button("✍️ Escrita Manual Completa", use_container_width=True)

    if "modo_selecionado" not in st.session_state:
        st.session_state["modo_selecionado"] = "manual"

    if btn_modo_voz:
        st.session_state["modo_selecionado"] = "voz"
    if btn_modo_manual:
        st.session_state["modo_selecionado"] = "manual"

    st.markdown("---")

    # MODO 1: GRAVADOR DE VOZ NATIVO (HTML5 Web Speech API + Extração)
    if st.session_state["modo_selecionado"] == "voz":
        st.markdown("""
            <div style="background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%); border: 1px solid #334155; border-radius: 16px; padding: 20px; text-align: center; margin-bottom: 20px;">
                <h4 style="color: #F8FAFC; margin: 0 0 6px 0;">🎙️ Gravador de Áudio & Reconhecimento de Voz</h4>
                <p style="color: #94A3B8; font-size: 0.8rem; margin: 0;">Clique no microfone abaixo e fale: <b>Seu Nome, Setor, Máquina e o Defeito</b>.</p>
            </div>
        """, unsafe_allow_html=True)

        # Microfone HTML5 nativo do navegador
        html_mic = """
        <!DOCTYPE html>
        <html>
        <head>
          <style>
            body { margin: 0; background: transparent; font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; }
            .mic-btn { width: 70px; height: 70px; border-radius: 50%; background: #38BDF8; color: #0F172A; font-size: 28px; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 15px rgba(56, 189, 248, 0.4); transition: all 0.2s; }
            .mic-btn:hover { background: #7DD3FC; transform: scale(1.05); }
            .recording { background: #EF4444 !important; color: white !important; animation: pulse 1.5s infinite; }
            @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); } 70% { box-shadow: 0 0 0 15px rgba(239, 68, 68, 0); } 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); } }
            #status-text { color: #38BDF8; font-size: 13px; font-weight: 700; margin-top: 10px; }
            #transcript-box { background: #1E293B; border: 1px solid #334155; color: #F8FAFC; border-radius: 8px; padding: 10px; font-size: 13px; width: 90%; max-width: 500px; margin-top: 12px; min-height: 40px; text-align: left; }
          </style>
        </head>
        <body>
          <button id="mic" class="mic-btn" onclick="toggleRecord()">🎙️</button>
          <div id="status-text">Clique no microfone para falar</div>
          <div id="transcript-box"><i>O que você falar aparecerá aqui em tempo real...</i></div>

          <script>
            let rec;
            let isRecording = false;
            if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
              const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
              rec = new SpeechRec();
              rec.lang = 'pt-BR';
              rec.continuous = false;
              rec.interimResults = true;

              rec.onstart = function() {
                isRecording = true;
                document.getElementById('mic').classList.add('recording');
                document.getElementById('status-text').innerHTML = '<span style="color: #EF4444;">🔴 Ouvindo... Fale agora!</span>';
              };

              rec.onresult = function(e) {
                let text = '';
                for (let i = e.resultIndex; i < e.results.length; ++i) {
                  text += e.results[i][0].transcript;
                }
                document.getElementById('transcript-box').innerText = text;
              };

              rec.onend = function() {
                isRecording = false;
                document.getElementById('mic').classList.remove('recording');
                document.getElementById('status-text').innerText = '✅ Fala capturada! Copie ou ajuste abaixo para confirmar.';
              };

              rec.onerror = function() {
                isRecording = false;
                document.getElementById('mic').classList.remove('recording');
                document.getElementById('status-text').innerText = 'Microfone finalizado.';
              };
            }

            function toggleRecord() {
              if (!rec) {
                alert('Seu navegador não liberou o microfone. Use a caixa de texto abaixo.');
                return;
              }
              if (isRecording) { rec.stop(); } else { rec.start(); }
            }
          </script>
        </body>
        </html>
        """
        components.html(html_mic, height=200)

        st.markdown("##### 📝 Confirmar Relato de Voz")
        texto_voz_input = st.text_area(
            "Relato Capturado (você pode editar ou complementar):",
            placeholder="Ex: Sou o Carlos da Coloração, a Polidora 2 travou a manta e está parada total.",
            height=80
        )

        col_ex1, col_ex2 = st.columns(2)
        with col_ex1:
            if st.button("💬 Exemplo 1: Polidora 2 Parada"):
                texto_voz_input = "Sou o Carlos da Coloração, a Polidora 2 travou a manta e está parada total."
        with col_ex2:
            if st.button("💬 Exemplo 2: Torno SL-501 com Ruído"):
                texto_voz_input = "Aqui é o Marcos da Surfaçagem, o torno SL-501 está com ruído estranho no eixo mas continua rodando."

        if st.button("🚀 Processar e Registrar Chamado por Voz"):
            if not texto_voz_input or len(texto_voz_input.strip()) < 8:
                st.error("🛑 Forneça o relato com seu nome, máquina e o defeito.")
            else:
                t = texto_voz_input.lower()
                nome_auto = "Operador"
                if "carlos" in t: nome_auto = "Carlos Silva"
                elif "marcos" in t: nome_auto = "Marcos Oliveira"
                elif "guilherme" in t: nome_auto = "Guilherme Santos"
                elif "eric" in t: nome_auto = "Eric"

                setor_auto = "Geral"
                if any(k in t for k in ["surfaçagem", "surfacagem"]): setor_auto = "Surfaçagem"
                elif any(k in t for k in ["coloração", "coloracao"]): setor_auto = "Coloração"
                elif "montagem" in t: setor_auto = "Montagem"
                elif "ar" in t: setor_auto = "AR"

                equip_auto = "Máquina"
                if "polidora 1" in t: equip_auto = "Polidora 1"
                elif "polidora 2" in t: equip_auto = "Polidora 2"
                elif "polidora 3" in t: equip_auto = "Polidora 3"
                elif any(k in t for k in ["sl-501", "sl501", "satisloh"]): equip_auto = "Satisloh SL-501"

                if any(k in t for k in ["parada total", "parou total", "travou total", "parada"]):
                    prio_auto = "Alta"
                    impacto_auto = "Parada total"
                elif any(k in t for k in ["lentid", "falha", "ruido", "barulho", "vazamento"]):
                    prio_auto = "Média"
                    impacto_auto = "Parada parcial"
                else:
                    prio_auto = "Baixa"
                    impacto_auto = "Sem impacto"

                sheet = get_sheet()
                agora = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")
                headers = [str(h).strip() for h in sheet.row_values(1)]
                nova_linha = [""] * len(headers)
                
                def preencher(col_cands, val):
                    idx, col_encontrada = encontrar_coluna(headers, col_cands)
                    if idx is not None: nova_linha[idx] = val

                proximo_num = len(df_calc) + 1
                solicitante_str = f"{nome_auto} ({setor_auto})"
                
                preencher(["N*Chamado", "Nº Chamado", "N° Chamado"], proximo_num)
                preencher(["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora"], agora)
                preencher(["Nome e Setor", "Nome e Setor Solicitante"], solicitante_str)
                preencher(["Área do chamado", "Área"], setor_auto)
                preencher(["Equipamento / Sistema / Local", "Máquina ou Equipamento"], equip_auto)
                preencher(["Qual é o problema?", "Descrição do problema"], texto_voz_input.strip())
                preencher(["Impacto na operação", "Impacto"], impacto_auto)
                preencher(["Prioridade", "Prioridade Sugerida"], prio_auto)
                preencher(["Status"], "Pendente")
                preencher(["Técnico Responsável", "Técnico", "Tecnico"], "Eric")

                sheet.append_row(nova_linha)
                st.success(f"✅ **Chamado Nº {proximo_num} registrado com sucesso para {nome_auto}!** (SLA: {prio_auto} | Máquina: {equip_auto})")
                st.cache_data.clear()
                st.rerun()

    # MODO 2: FORMULÁRIO MANUAL COM DESIGN IDÊNTICO AO PREVIEW
    else:
        st.markdown("""
            <div style="background-color: #1E293B; border: 1px solid #334155; border-radius: 16px; padding: 24px; margin-bottom: 20px;">
                <div style="color: #38BDF8; font-size: 0.8rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px;">
                    1. Identificação do Solicitante
                </div>
            </div>
        """, unsafe_allow_html=True)

        with st.form("form_abertura_manual_preview", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                nome_solicitante = st.text_input("Seu Nome Completo (Pessoa) *", placeholder="Ex: Carlos Silva")
                st.caption("🔒 *Obrigatório: digite seu nome pessoal, não apenas o setor.*")
            with col2:
                area = st.selectbox("Seu Setor / Área *", ["Surfaçagem", "Coloração", "Tratamento AR", "Montagem", "Estoque", "Expedição", "TI", "Geral"])

            st.markdown("---")
            st.markdown("""
                <div style="color: #38BDF8; font-size: 0.8rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; margin: 16px 0 10px 0;">
                    2. Diagnóstico Técnico Inicial
                </div>
            """, unsafe_allow_html=True)

            col3, col4 = st.columns(2)
            with col3:
                equipamento = st.text_input("Equipamento / Máquina / Local *", placeholder="Ex: Polidora 2, Satisloh SL-501...")
            with col4:
                sintoma = st.selectbox("Sintoma Principal da Falha *", [
                    "⚡ Elétrica / Painel (Não liga, disjuntor, sensor)",
                    "⚙️ Mecânica / Ruído (Travamento, vibração, folga)",
                    "💧 Pneumática / Hidráulica (Vácuo, ar, vazamento)",
                    "🔬 Qualidade / Descalibração (Riscando, descentrado)",
                    "🖥️ Software / CNC (Tela travada, erro de leitura)",
                    "❓ Outro Sintoma"
                ])
                
            codigo_alarme = st.text_input("Código ou Mensagem de Erro no Painel (se houver)", placeholder="Ex: Erro E-104 / Alarme Pressão Baixa / Não tem código")

            st.markdown("---")
            st.markdown("""
                <div style="color: #38BDF8; font-size: 0.8rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; margin: 16px 0 10px 0;">
                    3. Situação Real da Máquina & Gravidade
                </div>
            """, unsafe_allow_html=True)

            # Os 3 Cards Explicativos de Situação
            st.markdown("""
                <div style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px;">
                    <div style="background-color: #0F172A; border: 2px solid #EF4444; border-radius: 10px; padding: 12px;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <b style="color: #F87171; font-size: 0.9rem;">🔴 1. MÁQUINA TOTALMENTE PARADA</b>
                            <span style="background: rgba(239, 68, 68, 0.2); color: #FCA5A5; padding: 2px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: 800;">SLA: Até 4 Horas</span>
                        </div>
                        <div style="color: #CBD5E1; font-size: 0.75rem; margin-top: 4px;">A máquina <b>não funciona 100%</b> e a produção do setor está <b>bloqueada sem máquina reserva</b>.</div>
                    </div>
                    <div style="background-color: #0F172A; border: 1px solid #F59E0B; border-radius: 10px; padding: 12px;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <b style="color: #FBBF24; font-size: 0.9rem;">🟡 2. OPERANDO COM FALHA / LENTIDÃO</b>
                            <span style="background: rgba(245, 158, 11, 0.2); color: #FDE68A; padding: 2px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: 800;">SLA: Até 8 Horas</span>
                        </div>
                        <div style="color: #CBD5E1; font-size: 0.75rem; margin-top: 4px;">A máquina continua rodando com ruído, lentidão ou há outra máquina absorvendo a produção.</div>
                    </div>
                    <div style="background-color: #0F172A; border: 1px solid #10B981; border-radius: 10px; padding: 12px;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <b style="color: #34D399; font-size: 0.9rem;">🟢 3. AJUSTE / PREVENTIVA / SEM PARADA</b>
                            <span style="background: rgba(16, 185, 129, 0.2); color: #A7F3D0; padding: 2px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: 800;">SLA: Até 48 Horas (2 Dias)</span>
                        </div>
                        <div style="color: #CBD5E1; font-size: 0.75rem; margin-top: 4px;">Troca de manta, lâmpada, lubrificação, reaperto ou melhoria programada sem impacto imediato.</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            condicao_escolhida = st.selectbox(
                "Selecione a Situação Correspondente *",
                [
                    "🔴 MÁQUINA TOTALMENTE PARADA (SLA: Até 4 Horas)",
                    "🟡 OPERANDO COM FALHA / LENTIDÃO (SLA: Até 8 Horas)",
                    "🟢 AJUSTE / PREVENTIVA / SEM PARADA (SLA: Até 48 Horas - 2 Dias)"
                ]
            )

            problema_detalhe = st.text_area(
                "O que a máquina está fazendo? (Breve resumo) *",
                placeholder="Ex: Ao iniciar o ciclo de polimento, o braço não desce e o display aponta erro de vácuo...",
                height=90
            )

            submitted_manual = st.form_submit_button("🚀 Registrar Chamado de Manutenção")

            if submitted_manual:
                campos_faltantes = []
                nome_clean = nome_solicitante.strip()
                setores_bloqueados = ["surfaçagem", "surfacagem", "coloração", "coloracao", "ar", "montagem", "estoque", "expedição", "expedicao", "ti", "diretoria", "geral"]

                if not nome_clean or len(nome_clean) < 3:
                    campos_faltantes.append("Seu Nome Completo (informe seu nome pessoal)")
                elif nome_clean.lower() in setores_bloqueados:
                    campos_faltantes.append(f"Você digitou '{nome_clean}' no campo de nome. Digite seu nome de pessoa, pois o setor já está selecionado ao lado.")

                if not equipamento or not equipamento.strip():
                    campos_faltantes.append("Equipamento / Máquina / Local")

                if not problema_detalhe or len(problema_detalhe.strip()) < 5:
                    campos_faltantes.append("O que a máquina está fazendo? (Descreva brevemente)")

                if campos_faltantes:
                    st.error("🛑 **Abertura Bloqueada!** Corrija os seguintes itens:\n\n" + "\n".join([f"• **{campo}**" for campo in campos_faltantes]))
                else:
                    if "🔴" in condicao_escolhida:
                        prio_final = "Alta"
                        impacto_final = "Parada total"
                    elif "🟡" in condicao_escolhida:
                        prio_final = "Média"
                        impacto_final = "Parada parcial"
                    else:
                        prio_final = "Baixa"
                        impacto_final = "Sem impacto"

                    desc_completa = f"[{sintoma.split(' (')[0]}] {problema_detalhe.strip()}"
                    if codigo_alarme.strip():
                        desc_completa += f" (Código no Painel: {codigo_alarme.strip()})"

                    sheet = get_sheet()
                    agora = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")
                    headers = [str(h).strip() for h in sheet.row_values(1)]
                    nova_linha = [""] * len(headers)
                    
                    def preencher(col_cands, val):
                        idx, col_encontrada = encontrar_coluna(headers, col_cands)
                        if idx is not None: nova_linha[idx] = val

                    proximo_num = len(df_calc) + 1
                    solicitante_formatado = f"{nome_clean} ({area})"

                    preencher(["N*Chamado", "Nº Chamado", "N° Chamado"], proximo_num)
                    preencher(["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora"], agora)
                    preencher(["Nome e Setor", "Nome e Setor Solicitante"], solicitante_formatado)
                    preencher(["Área do chamado", "Área"], area)
                    preencher(["Equipamento / Sistema / Local", "Máquina ou Equipamento"], equipamento.strip())
                    preencher(["Qual é o problema?", "Descrição do problema"], desc_completa)
                    preencher(["Impacto na operação", "Impacto"], impacto_final)
                    preencher(["Prioridade", "Prioridade Sugerida"], prio_final)
                    preencher(["Status"], "Pendente")
                    preencher(["Técnico Responsável", "Técnico", "Tecnico"], "Eric")

                    sheet.append_row(nova_linha)
                    st.success(f"✅ **Chamado Nº {proximo_num} registrado com sucesso para {nome_clean}!** (SLA: {prio_final})")
                    st.cache_data.clear()
                    st.rerun()

# ==========================================
# ABA 2: DASHBOARD & SLA COMPLETO
# ==========================================
with tab_dash:
    col_titulo, col_filtro = st.columns([3, 1])
    with col_titulo:
        st.title("📊 Painel Gerencial & SLA")
    with col_filtro:
        opcao_periodo = st.selectbox("Filtro dos Indicadores", ["Todo o Histórico", "Últimos 90 dias", "Últimos 30 dias", "Este Mês", "Este Ano"], index=0)

    if not df_calc.empty:
        status_abertos = ["Pendente", "Atuando"]
        em_aberto = len(df_calc[df_calc["Status_Clean"].isin(status_abertos)])
        total_chamados_geral = len(df_calc)
        total_concluidos_geral = len(df_calc[df_calc["Status_Clean"] == "Concluído"])
        taxa_conclusao_geral = (total_concluidos_geral / total_chamados_geral * 100) if total_chamados_geral > 0 else 100.0

        em_turno = dentro_do_expediente(agora_naive_geral)
        status_expediente_str = "▶️ Ativo" if em_turno else "⏸️ Pausado (Fora do Expediente)"

        df_concluidos = df_calc[df_calc["Status_Clean"] == "Concluído"].copy()
        if not df_concluidos.empty:
            df_concluidos["Tempo_Resolucao_Horas"] = df_concluidos.apply(calcular_tempo_resolucao_concluido, axis=1)
            tmr_geral_num = df_concluidos["Tempo_Resolucao_Horas"].median() if not df_concluidos.empty else 0.0
        else:
            tmr_geral_num = 0.0

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Chamados", total_chamados_geral)
        c2.metric("Em Aberto", em_aberto)
        c3.metric("Taxa Resolução", f"{taxa_conclusao_geral:.1f}%")
        c4.metric("TMR Mediano", formatar_tempo_legivel(tmr_geral_num))
        c5.metric("SLA / Expediente", status_expediente_str)

        st.markdown("---")
        st.markdown("##### 📅 Volumetria de Chamados por Período (Abertos vs. Concluídos)")
        
        df_validos = df_calc.dropna(subset=["dt_abertura"]).copy()
        if df_validos.empty: df_validos = df_calc.copy()

        inicio_hoje = agora_naive_geral.floor("D")
        inicio_semana = inicio_hoje - pd.Timedelta(days=agora_naive_geral.weekday())
        inicio_mes = agora_naive_geral.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        inicio_ano = agora_naive_geral.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

        def render_card_periodo(titulo, dt_limite):
            if "dt_abertura" in df_validos.columns and df_validos["dt_abertura"].notna().any():
                sub = df_validos[df_validos["dt_abertura"] >= dt_limite]
            else:
                sub = df_validos
                
            total_periodo = len(sub)
            abertos_periodo = len(sub[sub["Status_Clean"].isin(["Pendente", "Atuando"])])
            concluidos_periodo = total_periodo - abertos_periodo
            cor_aberto = "#FBBF24" if abertos_periodo > 0 else "#94A3B8"
            
            return textwrap.dedent(f"""
                <div style="background-color:#1E293B; border:1px solid #334155; padding:14px; border-radius:12px; text-align:center;">
                    <div style="color:#94A3B8; font-size:0.85rem; font-weight:700; text-transform:uppercase;">{titulo}</div>
                    <div style="color:#38BDF8; font-size:2rem; font-weight:800; margin:4px 0;">{total_periodo}</div>
                    <div style="margin-top:8px; font-size:0.8rem; font-weight:600; display:flex; justify-content:space-around; border-top:1px solid #334155; padding-top:8px;">
                        <span style="color:{cor_aberto};">🟡 <b>{abertos_periodo}</b> em aberto</span>
                        <span style="color:#22C55E;">🟢 <b>{concluidos_periodo}</b> concluídos</span>
                    </div>
                </div>
            """).strip()

        col_vh, col_vs, col_vm, col_va = st.columns(4)
        with col_vh: st.markdown(render_card_periodo("Hoje", inicio_hoje), unsafe_allow_html=True)
        with col_vs: st.markdown(render_card_periodo("Esta Semana", inicio_semana), unsafe_allow_html=True)
        with col_vm: st.markdown(render_card_periodo("Este Mês", inicio_mes), unsafe_allow_html=True)
        with col_va: st.markdown(render_card_periodo("Este Ano", inicio_ano), unsafe_allow_html=True)

        st.markdown("---")
        st.markdown(f"##### ⏳ Barra de Vida & Saúde do SLA por Fila (Regime: Horário Comercial {st.session_state['hora_inicio_turno']:02d}:00 - {st.session_state['hora_fim_turno']:02d}:00)")

        def cartao_prioridade_jornada(col, nome, meta_horas):
            sub_prio_ativos = df_calc[(df_calc["Prioridade_Clean"] == nome) & (df_calc["Status_Clean"].isin(["Pendente", "Atuando"]))]
            qtd_ativos = len(sub_prio_ativos)
            qtd_atuando = len(sub_prio_ativos[sub_prio_ativos["Status_Clean"] == "Atuando"])
            qtd_pendente = len(sub_prio_ativos[sub_prio_ativos["Status_Clean"] == "Pendente"])
            
            if qtd_ativos == 0:
                pct_saude = 100.0
                cor_status = "#22C55E"
                texto_status = "100.0% (Fila em Dia)"
            else:
                somas_saude = []
                for _, r in sub_prio_ativos.iterrows():
                    dt_ab = r.get("dt_abertura")
                    if pd.notna(dt_ab):
                        decorrido_util = calcular_horas_uteis(dt_ab, agora_naive_geral)
                        restante = meta_horas - decorrido_util
                        pct_individual = max(0.0, (restante / meta_horas) * 100.0)
                        somas_saude.append(pct_individual)
                    else: somas_saude.append(100.0)
                
                pct_saude = sum(somas_saude) / len(somas_saude) if somas_saude else 100.0
                if pct_saude > 50.0: cor_status = "#22C55E"
                elif pct_saude > 20.0: cor_status = "#F59E0B"
                else: cor_status = "#EF4444"
                texto_status = f"{pct_saude:.1f}% ({qtd_ativos} ativos)"

            html_card = textwrap.dedent(f"""
                <div style="background-color:#1E293B; border:2px solid {cor_status}; padding:15px; border-radius:12px; margin-bottom:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:800; color:{cor_status}; font-size:1.1rem;">{nome.upper()}</span>
                        <span style="font-size:0.8rem; color:#94A3B8; font-weight:600;">Meta: {formatar_tempo_legivel(meta_horas)}</span>
                    </div>
                    <div style="font-size:1.8rem; font-weight:800; color:{cor_status}; margin:6px 0;">{texto_status}</div>
                    <div style="background-color:#334155; border-radius:6px; height:12px; width:100%; margin:10px 0; overflow:hidden;">
                        <div style="background-color:{cor_status}; width:{pct_saude:.1f}%; height:100%; border-radius:6px; transition: width 0.5s ease;"></div>
                    </div>
                    <div style="margin-top:8px; padding-top:8px; border-top:1px solid #334155; font-size:0.8rem; color:#CBD5E1; display:flex; justify-content:space-between;">
                        <span>🟣 Atuando: <b style="color:#C084FC;">{qtd_atuando}</b></span>
                        <span>🟡 Pendente: <b style="color:#FBBF24;">{qtd_pendente}</b></span>
                    </div>
                </div>
            """).strip()
            with col: st.markdown(html_card, unsafe_allow_html=True)

        col_a, col_m, col_b = st.columns(3)
        cartao_prioridade_jornada(col_a, "Alta", 4.0)
        cartao_prioridade_jornada(col_m, "Média", 8.0)
        cartao_prioridade_jornada(col_b, "Baixa", 48.0)

        st.markdown("---")
        st.markdown(f"##### 🚨 Monitoramento Operacional (Chamados Ativos em Aberto: {em_aberto})")

        lista_ativos = []
        for _, row in df_calc[df_calc["Status_Clean"].isin(["Pendente", "Atuando"])].iterrows():
            dt_ab = row.get("dt_abertura")
            meta = row.get("Meta_SLA_Horas", 8.0)
            raw_ab = extrair_campo_flexivel(row, ["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora"], "")
            
            if pd.notna(dt_ab):
                horas_decorridas_uteis = calcular_horas_uteis(dt_ab, agora_naive_geral)
                tempo_restante_util = meta - horas_decorridas_uteis
                pct_vida = max(0.0, (tempo_restante_util / meta) * 100.0)
                
                if tempo_restante_util >= 0:
                    prefixo = "▶️" if em_turno else "⏸️ Pausado:"
                    tempo_dec_str = f"{prefixo} {formatar_tempo_legivel(tempo_restante_util)} restantes"
                    status_sla = f"{pct_vida:.0f}% Prazo Útil"
                else:
                    tempo_dec_str = f"🔴 Estourado (+{formatar_tempo_legivel(abs(tempo_restante_util))})"
                    status_sla = f"🔴 0% Estourado"
            else:
                pct_vida = 100.0
                tempo_dec_str = "-"
                status_sla = "⚪ Sem data"

            lista_ativos.append({
                "Nº": row.get("Num_Chamado_Num"),
                "Solicitante": row.get("Solicitante_Norm"),
                "Abertura": formatar_dt_exibicao(dt_ab, raw_ab),
                "Área": row.get("Area_Norm"),
                "Equipamento": row.get("Equipamento_Norm"),
                "Descrição do Problema": row.get("Problema_Norm"),
                "Prioridade": row.get("Prioridade_Clean"),
                "Status": "🟣 Atuando" if row.get("Status_Clean") == "Atuando" else "🟡 Pendente",
                "Saúde SLA": status_sla,
                "Tempo Restante (Útil)": tempo_dec_str,
                "Técnico": row.get("Tecnico_Clean", "Eric")
            })

        if lista_ativos:
            df_ativos = pd.DataFrame(lista_ativos).sort_values("Nº", ascending=False)
            
            def colorir_linha_ativos(row):
                saude_str = str(row.get("Saúde SLA", ""))
                if "Estourado" in saude_str:
                    return ['background-color: #7F1D1D; color: #FECDD3; font-weight: 700;'] * len(row)
                
                m = re.search(r'(\d+)%', saude_str)
                pct = int(m.group(1)) if m else 100
                
                if pct > 50:
                    return ['background-color: #064E3B; color: #A7F3D0; font-weight: 700;'] * len(row)
                elif pct > 20:
                    return ['background-color: #78350F; color: #FDE68A; font-weight: 700;'] * len(row)
                else:
                    return ['background-color: #7F1D1D; color: #FECDD3; font-weight: 700;'] * len(row)

            styled_ativos = df_ativos.style.apply(colorir_linha_ativos, axis=1)
            st.dataframe(styled_ativos, use_container_width=True, hide_index=True)
        else:
            st.success("✅ Nenhum chamado ativo pendente no momento.")

        st.markdown("---")
        col_hist_tit, col_hist_lim = st.columns([3, 1])
        with col_hist_tit:
            st.markdown(f"##### 📋 Histórico Geral de Chamados & SLA (Total: {total_chamados_geral})")
        with col_hist_lim:
            limite_exibicao = st.selectbox("Exibir no histórico:", [50, 100, 200, "Todos"], index=0)

        lista_geral = []
        for _, row in df_calc.iterrows():
            st_str = str(row.get("Status_Clean", "Pendente"))
            dt_ab = row.get("dt_abertura")
            dt_conc = row.get("dt_conclusao")
            meta = row.get("Meta_SLA_Horas", 8.0)
            raw_ab = extrair_campo_flexivel(row, ["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora"], "")
            
            dt_ab_str = formatar_dt_exibicao(dt_ab, raw_ab)

            if st_str == "Concluído":
                tempo_num = calcular_tempo_resolucao_concluido(row)
                sla_ok = tempo_num <= meta
                sit_str = "✅ Cumprido" if sla_ok else f"🔴 Estourado (+{formatar_tempo_legivel(tempo_num - meta)})"
                tmr_str = formatar_tempo_legivel(tempo_num)
                status_disp = "🟢 Concluído"
            else:
                if pd.notna(dt_ab):
                    tempo_decorrido = calcular_horas_uteis(dt_ab, agora_naive_geral)
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
                "Tempo Útil": tmr_str,
                "Situação SLA": sit_str,
                "Técnico": row.get("Tecnico_Clean", "Eric")
            })

        if lista_geral:
            df_geral = pd.DataFrame(lista_geral).sort_values("Nº", ascending=False)
            if limite_exibicao != "Todos": df_geral = df_geral.head(int(limite_exibicao))

            def colorir_linha_geral(row):
                st_val = str(row["Status"])
                prio = str(row["Prioridade"]).strip().lower()
                if "Concluído" in st_val: return ['background-color: #064E3B; color: #A7F3D0; font-weight: 700;'] * len(row)
                else:
                    if "alta" in prio: return ['background-color: #7F1D1D; color: #FECDD3; font-weight: 700;'] * len(row)
                    elif "media" in prio: return ['background-color: #78350F; color: #FDE68A; font-weight: 700;'] * len(row)
                    else: return ['background-color: #1E3A8A; color: #F0F9FF; font-weight: 700;'] * len(row)

            styled_geral = df_geral.style.apply(colorir_linha_geral, axis=1)
            st.dataframe(styled_geral, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown(f"##### 👷 Desempenho por Técnico & Prioridade (SLA por Nível)")
        
        if not df_calc.empty:
            df_concl_tec = df_calc[df_calc["Status_Clean"] == "Concluído"].copy()
            if not df_concl_tec.empty:
                df_concl_tec["Tempo_Horas"] = df_concl_tec.apply(calcular_tempo_resolucao_concluido, axis=1)
                df_concl_tec["SLA_OK"] = df_concl_tec["Tempo_Horas"] <= df_concl_tec["Meta_SLA_Horas"]
            
            linhas_tec = []
            tecnicos_unicos = ["Eric", "Felipe"]
            
            for tec in tecnicos_unicos:
                sub_tec_conc = df_concl_tec[df_concl_tec["Tecnico_Clean"] == tec] if not df_concl_tec.empty else pd.DataFrame()
                
                total_atend = len(sub_tec_conc)
                tmr_geral = formatar_tempo_legivel(sub_tec_conc["Tempo_Horas"].median()) if total_atend > 0 else "-"
                sla_geral_pct = f"{(sub_tec_conc['SLA_OK'].sum() / total_atend * 100):.1f}%" if total_atend > 0 else "-"

                # Prioridade Alta
                conc_alta = sub_tec_conc[sub_tec_conc["Prioridade_Clean"] == "Alta"] if not sub_tec_conc.empty else pd.DataFrame()
                qtd_alta = len(conc_alta)
                tmr_alta = formatar_tempo_legivel(conc_alta["Tempo_Horas"].median()) if qtd_alta > 0 else "-"
                sla_alta = f"{(conc_alta['SLA_OK'].sum() / qtd_alta * 100):.1f}%" if qtd_alta > 0 else "-"

                # Prioridade Média
                conc_med = sub_tec_conc[sub_tec_conc["Prioridade_Clean"] == "Média"] if not sub_tec_conc.empty else pd.DataFrame()
                qtd_med = len(conc_med)
                tmr_med = formatar_tempo_legivel(conc_med["Tempo_Horas"].median()) if qtd_med > 0 else "-"
                sla_med = f"{(conc_med['SLA_OK'].sum() / qtd_med * 100):.1f}%" if qtd_med > 0 else "-"

                # Prioridade Baixa
                conc_baix = sub_tec_conc[sub_tec_conc["Prioridade_Clean"] == "Baixa"] if not sub_tec_conc.empty else pd.DataFrame()
                qtd_baix = len(conc_baix)
                tmr_baix = formatar_tempo_legivel(conc_baix["Tempo_Horas"].median()) if qtd_baix > 0 else "-"
                sla_baix = f"{(conc_baix['SLA_OK'].sum() / qtd_baix * 100):.1f}%" if qtd_baix > 0 else "-"

                linhas_tec.append({
                    "Técnico Responsável": tec,
                    "Total Concluídos": total_atend,
                    "TMR Geral (Útil)": tmr_geral,
                    "SLA Geral (%)": sla_geral_pct,
                    "Qtd Alta": qtd_alta,
                    "TMR Alta": tmr_alta,
                    "SLA Alta": sla_alta,
                    "Qtd Média": qtd_med,
                    "TMR Média": tmr_med,
                    "SLA Média": sla_med,
                    "Qtd Baixa": qtd_baix,
                    "TMR Baixa": tmr_baix,
                    "SLA Baixa": sla_baix
                })

            if linhas_tec:
                df_tec_exibicao = pd.DataFrame(linhas_tec)
                st.dataframe(df_tec_exibicao, use_container_width=True, hide_index=True)

        st.markdown("---")
        fig_equip = criar_grafico_pareto_limpo(df_calc, "Equipamento_Norm", "Top Equipamentos Críticos", top_n=10)
        if fig_equip: st.plotly_chart(fig_equip, use_container_width=True)

        st.markdown("---")
        fig_setor = criar_grafico_pareto_limpo(df_calc, "Area_Norm", "Top Setores Solicitantes", top_n=10)
        if fig_setor: st.plotly_chart(fig_setor, use_container_width=True)

# ==========================================
# ABA 3: GESTÃO OPERACIONAL DE CHAMADOS
# ==========================================
with tab_gestao:
    st.title("⚙️ Gestão Operacional de Chamados")
    senha_digitada = st.text_input("Chave de Acesso Operacional", type="password", key="pwd_gestao")
    
    if senha_digitada == SENHA_CORRETA:
        st.markdown("##### ⏱️ Configuração de Jornada & Expediente (Pausa Automática do SLA)")
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            h_ini_sel = st.number_input("Início do Turno (Hora)", min_value=0, max_value=23, value=int(st.session_state["hora_inicio_turno"]))
        with col_t2:
            h_fim_sel = st.number_input("Fim do Turno (Hora)", min_value=0, max_value=23, value=int(st.session_state["hora_fim_turno"]))
            
        if st.button("Salvar Regras de Turno"):
            st.session_state["hora_inicio_turno"] = h_ini_sel
            st.session_state["hora_fim_turno"] = h_fim_sel
            st.success("Regras de turno salvas com sucesso!")
            st.rerun()

        st.markdown("---")
        col_tit_g, col_flt_g = st.columns([2, 2])
        with col_tit_g:
            st.markdown("##### 📋 Monitoramento & Planilha de Chamados")
        with col_flt_g:
            opcao_filtro_gestao = st.radio("Filtro de Exibição:", ["🟡 Apenas Em Aberto (Pendente / Atuando)", "📋 Planilha Completa (Todos os Chamados)"], horizontal=True)

        if "Apenas Em Aberto" in opcao_filtro_gestao:
            df_gestao_view = df_calc[df_calc["Status_Clean"].isin(["Pendente", "Atuando"])].sort_values("Num_Chamado_Num", ascending=False)
        else:
            df_gestao_view = df_calc.sort_values("Num_Chamado_Num", ascending=False)

        if not df_gestao_view.empty:
            lista_gestao_tabela = []
            for _, r in df_gestao_view.iterrows():
                dt_ab = r.get("dt_abertura")
                raw_ab = extrair_campo_flexivel(r, ["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora"], "")
                lista_gestao_tabela.append({
                    "Nº": r.get("Num_Chamado_Num"),
                    "Abertura": formatar_dt_exibicao(dt_ab, raw_ab),
                    "Solicitante": r.get("Solicitante_Norm"),
                    "Área": r.get("Area_Norm"),
                    "Equipamento": r.get("Equipamento_Norm"),
                    "Problema": r.get("Problema_Norm"),
                    "Prioridade": r.get("Prioridade_Clean"),
                    "Status": r.get("Status_Clean"),
                    "Técnico": r.get("Tecnico_Clean")
                })
            df_view_table = pd.DataFrame(lista_gestao_tabela)
            st.dataframe(df_view_table, use_container_width=True, hide_index=True)
        else:
            st.info("ℹ️ Nenhum chamado encontrado para o filtro selecionado.")

        st.markdown("---")
        st.subheader("Atualizar Status de Chamado & Apontamento Técnico")
        
        df_para_selecao = df_gestao_view if not df_gestao_view.empty else df_calc.sort_values("Num_Chamado_Num", ascending=False)
        
        if not df_para_selecao.empty:
            opcoes_chamados = [f"#{r['Num_Chamado_Num']} - {r['Equipamento_Norm']} ({r['Solicitante_Norm']}) | Status: {r['Status_Clean']} | Tec: {r['Tecnico_Clean']}" for _, r in df_para_selecao.iterrows()]
            chamado_sel_str = st.selectbox("Selecione o chamado para editar:", opcoes_chamados)
            num_chamado_sel = int(chamado_sel_str.split(" - ")[0].replace("#", ""))
        else:
            num_chamado_sel = st.number_input("Informe o Nº do Chamado do Histórico", min_value=1, step=1)

        mask_num = df_calc["Num_Chamado_Num"] == num_chamado_sel if not df_calc.empty else pd.Series([False])
        if mask_num.any():
            idx_linha = df_calc[mask_num].index[0]
            linha_atual = df_raw.iloc[idx_linha]

            st.info(f"Editando Chamado #{num_chamado_sel}: {extrair_campo_flexivel(linha_atual, ['Equipamento / Sistema / Local', 'Máquina ou Equipamento', 'Equipamento'])}")

            with st.form("form_atualizacao"):
                col_a, col_b = st.columns(2)
                sheet = get_sheet()
                headers = [str(h).strip() for h in sheet.row_values(1)]
                
                with col_a:
                    status_atual = str(linha_atual.get("Status", "Pendente"))
                    opcoes_status = ["Pendente", "Atuando", "Concluído"]
                    novo_status = st.selectbox("Status", opcoes_status, index=opcoes_status.index(status_atual) if status_atual in opcoes_status else 0)
                    
                    tec_atual = str(linha_atual.get("Técnico Responsável", "Eric"))
                    opcoes_tec = ["Eric", "Felipe", "Outro"]
                    tecnico = st.selectbox("Técnico Responsável", opcoes_tec, index=opcoes_tec.index(tec_atual) if tec_atual in opcoes_tec else 0)
                    horas_aplicadas = st.text_input("Horas-Homem Aplicadas (ex: 1.5)", value=str(linha_atual.get("Horas-Homem", "1.0")))
                
                with col_b:
                    obs_interna = st.text_area("Diagnóstico / Ação Executada", value=str(linha_atual.get("Observação Interna", "")))

                btn_salvar = st.form_submit_button("Salvar Alterações")

                if btn_salvar:
                    linha_excel = idx_linha + 2
                    updates_lote = []
                    
                    idx_st, col_st = encontrar_coluna(headers, ["Status", "Situação"])
                    idx_tc, col_tc = encontrar_coluna(headers, ["Técnico Responsável", "Técnico", "Tecnico", "Responsável"])
                    idx_ob, col_ob = encontrar_coluna(headers, ["Observação Interna", "Diagnóstico / Ação Executada", "Observações"])
                    idx_hh, col_hh = encontrar_coluna(headers, ["Horas-Homem Aplicadas (ex: 1.5)", "Horas-Homem", "Horas Homem", "Horas"])
                    idx_dt, col_dt = encontrar_coluna(headers, ["Data de conclusão", "Data de Conclusão", "Data Conclusão"])

                    if idx_st is not None:
                        updates_lote.append({'range': rowcol_to_a1(linha_excel, idx_st + 1), 'values': [[novo_status]]})
                    if idx_tc is not None:
                        updates_lote.append({'range': rowcol_to_a1(linha_excel, idx_tc + 1), 'values': [[tecnico]]})
                    if idx_ob is not None:
                        updates_lote.append({'range': rowcol_to_a1(linha_excel, idx_ob + 1), 'values': [[obs_interna]]})
                    if idx_hh is not None:
                        updates_lote.append({'range': rowcol_to_a1(linha_excel, idx_hh + 1), 'values': [[horas_aplicadas]]})
                    if novo_status == "Concluído" and idx_dt is not None:
                        data_conc = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")
                        updates_lote.append({'range': rowcol_to_a1(linha_excel, idx_dt + 1), 'values': [[data_conc]]})

                    if updates_lote:
                        sheet.batch_update(updates_lote)

                    st.success(f"Chamado Nº {num_chamado_sel} atualizado com sucesso!")
                    st.cache_data.clear()
                    st.rerun()
