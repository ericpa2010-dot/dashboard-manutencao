import streamlit as st
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
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)

def get_sheet():
    client = get_gspread_client()
    return client.open_by_url(st.secrets["spreadsheet"]["url"]).worksheet("CHAMADOS")

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

def extrair_campo(row, candidatos, padrao=""):
    for c in candidatos:
        if c in row.index and pd.notna(row[c]):
            val = str(row[c]).replace('\xa0', ' ').strip()
            if val != "" and val.lower() not in ["nan", "none", "null"]:
                return val
    return padrao

def parse_data_infalivel(val):
    if not val or pd.isna(val):
        return pd.NaT
    s = str(val).replace('\xa0', ' ').strip()
    if s.lower() in ["nan", "none", "", "-", "null", "0"]:
        return pd.NaT
    
    m_br = re.search(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?:\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?', s)
    if m_br:
        d, m, y = int(m_br.group(1)), int(m_br.group(2)), int(m_br.group(3))
        h = int(m_br.group(4)) if m_br.group(4) is not None else 0
        mi = int(m_br.group(5)) if m_br.group(5) is not None else 0
        sec = int(m_br.group(6)) if m_br.group(6) is not None else 0
        try: return pd.Timestamp(y, m, d, h, mi, sec)
        except ValueError: pass

    return pd.to_datetime(s, errors="coerce", dayfirst=True)

def extrair_dt_abertura(row):
    val = extrair_campo(row, ["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora", "Data de Abertura", "Data"], "")
    return parse_data_infalivel(val)

def extrair_dt_conclusao(row):
    val = extrair_campo(row, ["Data de conclusão", "Data de Conclusão", "Data Conclusão"], "")
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
    p_raw = str(extrair_campo(r, ["Prioridade", "Prioridade Sugerida"], "")).strip().lower()
    if "alt" in p_raw: return "Alta"
    elif "med" in p_raw or "méd" in p_raw: return "Média"
    elif "baix" in p_raw: return "Baixa"
    return "Média"

def obter_status_sanitizado(r):
    dt_conc_raw = extrair_campo(r, ["Data de conclusão", "Data de Conclusão", "Data Conclusão"], "")
    dt_conc_parsed = parse_data_infalivel(dt_conc_raw)
    
    if pd.notna(dt_conc_parsed):
        return "Concluído"
    
    st_raw = extrair_campo(r, ["Status", "STATUS", "Situação", "Situacao"], "").upper()
    if any(k in st_raw for k in ["CONCLU", "RESOLV", "FECHAD", "FINALIZAD"]):
        return "Concluído"
    if any(k in st_raw for k in ["ATUAND", "ANDAMENTO", "EM ATENDIMENTO", "EM ANDAMENTO"]):
        return "Atuando"
    return "Pendente"

def sanitizar_tecnico(r):
    tec_raw = extrair_campo(r, ["Técnico Responsável", "Técnico", "Tecnico", "Técnico Responsavel", "Responsável", "Técnico Atribuído", "Atribuído a"], "")
    tec_clean = tec_raw.strip().title()
    if tec_clean == "" or tec_clean.lower() in ["nan", "none", "não atribuído", "nao atribuido", "-", "null", "eric (histórico geral)", "eric (historico geral)"]:
        return "Eric"
    if "Eric" in tec_clean:
        return "Eric"
    if "Felipe" in tec_clean:
        return "Felipe"
    return tec_clean

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
    df_calc["Equipamento_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Equipamento / Sistema / Local", "Equipamento/Sistema/Local", "Máquina ou Equipamento"], "Não informado"), axis=1)
    df_calc["Problema_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Qual é o problema?", "Descrição do chamado", "Tipo de problema"], "Sem descrição"), axis=1)
    df_calc["Impacto_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Qual é o impacto na operação?", "Impacto na operação", "Impacto"], "Não informado"), axis=1)
    df_calc["Area_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Área do chamado", "Nome e Setor"], "Geral"), axis=1)
    
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
    DATA_CORTE = pd.Timestamp(2026, 8, 23, 0, 0, 0)

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
                st.error("🛑 **Abertura Bloqueada!** Preencha os campos obrigatórios:\n\n" + "\n".join([f"• **{campo}**" for campo in campos_faltantes]))
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
                preencher("Prioridade", prioridade)
                preencher("Status", "Pendente")
                preencher("Técnico Responsável", "Eric")

                sheet.append_row(nova_linha)
                st.success(f"Chamado Nº {proximo_num} registrado!")
                st.cache_data.clear()
                st.rerun()

# ABA 2: DASHBOARD & SLA COMPLETO
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

        df_concluidos = df_calc.dropna(subset=["dt_conclusao", "dt_abertura"]).copy()
        if not df_concluidos.empty:
            df_concluidos["Tempo_Resolucao_Horas"] = df_concluidos.apply(
                lambda r: calcular_horas_uteis(r["dt_abertura"], r["dt_conclusao"]), axis=1
            )
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
        st.markdown("##### 📅 Volumetria por Período")
        
        df_temp_validos = df_calc.dropna(subset=["dt_abertura"]).copy()
        inicio_hoje = agora_naive_geral.floor("D")
        inicio_semana = inicio_hoje - pd.Timedelta(days=agora_naive_geral.weekday())
        inicio_mes = agora_naive_geral.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        inicio_ano = agora_naive_geral.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

        ct1, ct2, ct3, ct4 = st.columns(4)
        ct1.metric("Hoje", len(df_temp_validos[df_temp_validos["dt_abertura"] >= inicio_hoje]))
        ct2.metric("Semana", len(df_temp_validos[df_temp_validos["dt_abertura"] >= inicio_semana]))
        ct3.metric("Mês", len(df_temp_validos[df_temp_validos["dt_abertura"] >= inicio_mes]))
        ct4.metric("Ano", len(df_temp_validos[df_temp_validos["dt_abertura"] >= inicio_ano]))

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
            raw_ab = extrair_campo(row, ["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora"], "")
            
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
                "Técnico": row.get("Tecnico_Clean", "Eric"),
                "pct_num": pct_vida
            })

        if lista_ativos:
            df_ativos = pd.DataFrame(lista_ativos).sort_values("Nº", ascending=False)
            
            def colorir_linha_ativos(row):
                pct = row["pct_num"]
                if pct > 50.0: return ['background-color: #064E3B; color: #A7F3D0; font-weight: 700;'] * len(row)
                elif pct > 20.0: return ['background-color: #78350F; color: #FDE68A; font-weight: 700;'] * len(row)
                else: return ['background-color: #7F1D1D; color: #FECDD3; font-weight: 700;'] * len(row)

            styled_ativos = df_ativos.drop(columns=["pct_num"]).style.apply(colorir_linha_ativos, axis=1)
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
            raw_ab = extrair_campo(row, ["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora"], "")
            
            dt_ab_str = formatar_dt_exibicao(dt_ab, raw_ab)

            if pd.notna(dt_ab) and dt_ab < DATA_CORTE:
                tmr_str = formatar_tempo_legivel((dt_conc - dt_ab).total_seconds() / 3600.0) if pd.notna(dt_conc) else "Legado"
                sit_str = "✅ Cumprido (Legado)"
                status_disp = "🟢 Concluído" if st_str == "Concluído" else ("🟣 Atuando" if st_str == "Atuando" else "🟡 Pendente")
            elif st_str == "Concluído":
                if pd.notna(dt_conc) and pd.notna(dt_ab):
                    tempo_num = calcular_horas_uteis(dt_ab, dt_conc)
                    sla_ok = tempo_num <= meta
                    sit_str = "✅ Cumprido" if sla_ok else f"🔴 Estourado (+{formatar_tempo_legivel(tempo_num - meta)})"
                    tmr_str = formatar_tempo_legivel(tempo_num)
                else:
                    tmr_str = "Concluído"
                    sit_str = "✅ Concluído"
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
        
        df_tec_full = df_calc.copy()
        if not df_tec_full.empty:
            df_concl_tec = df_tec_full[df_tec_full["Status_Clean"] == "Concluído"].dropna(subset=["dt_abertura", "dt_conclusao"]).copy()
            if not df_concl_tec.empty:
                df_concl_tec["Tempo_Horas"] = df_concl_tec.apply(lambda r: calcular_horas_uteis(r["dt_abertura"], r["dt_conclusao"]), axis=1)
                df_concl_tec["SLA_OK"] = df_concl_tec["Tempo_Horas"] <= df_concl_tec["Meta_SLA_Horas"]
            
            linhas_tec = []
            tecnicos_unicos = ["Eric", "Felipe"]
            
            for tec in tecnicos_unicos:
                sub_tec_all = df_tec_full[df_tec_full["Tecnico_Clean"] == tec]
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

# ABA 3: GESTÃO OPERACIONAL DE CHAMADOS
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
        st.markdown("##### 📋 Chamados em Monitoramento (Pendente / Atuando)")
        
        df_abertos_gestao = df_calc[df_calc["Status_Clean"].isin(["Pendente", "Atuando"])].sort_values("Num_Chamado_Num", ascending=False)
        if not df_abertos_gestao.empty:
            cols_gestao_view = ["Num_Chamado_Num", "Solicitante_Norm", "Area_Norm", "Equipamento_Norm", "Problema_Norm", "Prioridade_Clean", "Status_Clean", "Tecnico_Clean"]
            df_view_table = df_abertos_gestao[cols_gestao_view].rename(columns={
                "Num_Chamado_Num": "Nº", "Solicitante_Norm": "Solicitante", "Area_Norm": "Área", 
                "Equipamento_Norm": "Equipamento", "Problema_Norm": "Problema", "Prioridade_Clean": "Prioridade",
                "Status_Clean": "Status", "Tecnico_Clean": "Técnico"
            })
            st.dataframe(df_view_table, use_container_width=True, hide_index=True)
        else:
            st.success("✅ Nenhum chamado pendente para tratamento no momento.")

        st.markdown("---")
        st.subheader("Atualizar Status de Chamado & Apontamento Técnico")
        
        if not df_abertos_gestao.empty:
            opcoes_chamados = [f"#{r['Num_Chamado_Num']} - {r['Equipamento_Norm']} ({r['Solicitante_Norm']}) | Status: {r['Status_Clean']}" for _, r in df_abertos_gestao.iterrows()]
            chamado_sel_str = st.selectbox("Selecione um chamado ativo para atualizar:", opcoes_chamados)
            num_chamado_sel = int(chamado_sel_str.split(" - ")[0].replace("#", ""))
        else:
            num_chamado_sel = st.number_input("Informe o Nº do Chamado do Histórico", min_value=1, step=1)

        mask_num = df_calc["Num_Chamado_Num"] == num_chamado_sel if not df_calc.empty else pd.Series([False])
        if mask_num.any():
            idx_linha = df_calc[mask_num].index[0]
            linha_atual = df_raw.iloc[idx_linha]

            st.info(f"Tratando Chamado #{num_chamado_sel}: {extrair_campo(linha_atual, ['Equipamento / Sistema / Local', 'Máquina ou Equipamento'])}")

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
                    
                    if "Status" in headers:
                        updates_lote.append({'range': rowcol_to_a1(linha_excel, headers.index("Status") + 1), 'values': [[novo_status]]})
                    if "Técnico Responsável" in headers:
                        updates_lote.append({'range': rowcol_to_a1(linha_excel, headers.index("Técnico Responsável") + 1), 'values': [[tecnico]]})
                    if "Observação Interna" in headers:
                        updates_lote.append({'range': rowcol_to_a1(linha_excel, headers.index("Observação Interna") + 1), 'values': [[obs_interna]]})
                    if "Horas-Homem" in headers:
                        updates_lote.append({'range': rowcol_to_a1(linha_excel, headers.index("Horas-Homem") + 1), 'values': [[horas_aplicadas]]})
                    if novo_status == "Concluído" and "Data de conclusão" in headers:
                        data_conc = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")
                        updates_lote.append({'range': rowcol_to_a1(linha_excel, headers.index("Data de conclusão") + 1), 'values': [[data_conc]]})

                    if updates_lote:
                        sheet.batch_update(updates_lote)

                    st.success(f"Chamado Nº {num_chamado_sel} atualizado com sucesso!")
                    st.cache_data.clear()
                    st.rerun()