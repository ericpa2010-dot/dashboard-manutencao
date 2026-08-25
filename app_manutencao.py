import streamlit as st
import pandas as pd
import gspread
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
    df.columns = [str(col).strip() for col in df.columns]
    return sheet, df

try:
    sheet, df = load_data()
except Exception as e:
    st.error(f"Erro ao conectar com a planilha: {e}")
    st.stop()

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

    m_iso = re.search(r'(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})(?:\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?', s)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        h = int(m_iso.group(4)) if m_iso.group(4) is not None else 0
        mi = int(m_iso.group(5)) if m_iso.group(5) is not None else 0
        sec = int(m_iso.group(6)) if m_iso.group(6) is not None else 0
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
    if dias > 0:
        partes.append(f"{dias}d")
    if hrs > 0:
        partes.append(f"{hrs}h")
    if mins > 0:
        partes.append(f"{mins}m")
    if secs > 0 or not partes:
        partes.append(f"{secs}s")
    return " ".join(partes)

def criar_grafico_pareto_limpo(df_input, coluna, titulo, top_n=10):
    if coluna not in df_input.columns or df_input[coluna].dropna().empty:
        return None

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

    fig.add_trace(
        go.Bar(
            x=counts[coluna],
            y=counts['Ocorrências'],
            name="Qtd Chamados",
            marker_color="#38BDF8",
            text=counts['Ocorrências'],
            textposition="outside",
            textfont=dict(size=11, color="#F8FAFC")
        )
    )

    fig.add_trace(
        go.Scatter(
            x=counts[coluna],
            y=counts['% Acumulado'],
            name="% Acumulado",
            yaxis="y2",
            mode="lines+markers",
            line=dict(color="#F43F5E", width=3),
            marker=dict(size=7, color="#F43F5E")
        )
    )

    fig.add_hline(
        y=80,
        yref="y2",
        line_dash="dash",
        line_color="#FBBF24",
        line_width=2
    )

    fig.update_layout(
        template="plotly_dark",
        title=dict(text=f"<b>{titulo}</b>", font=dict(size=15, color="#F8FAFC")),
        xaxis=dict(tickfont=dict(size=10, color="#CBD5E1"), tickangle=-15, showgrid=False),
        yaxis=dict(
            title=dict(text="<b>Qtd Chamados</b>", font=dict(size=11, color="#94A3B8")),
            tickfont=dict(size=10, color="#CBD5E1"),
            gridcolor="#334155",
            showgrid=True
        ),
        yaxis2=dict(
            title=dict(text="<b>% Acumulado</b>", font=dict(size=11, color="#94A3B8")),
            tickfont=dict(size=10, color="#CBD5E1"),
            overlaying="y",
            side="right",
            range=[0, 105],
            showgrid=False
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1, font=dict(size=10, color="#F8FAFC")),
        margin=dict(l=10, r=10, t=40, b=40),
        height=380,
        paper_bgcolor="#1E293B",
        plot_bgcolor="#1E293B"
    )

    return fig

SENHA_CORRETA = st.secrets.get("SENHA_GESTAO", "manutencao123")

# PROCESSAMENTO DE DADOS COM SANITIZAÇÃO RIGOROSA
if not df.empty:
    fuso_br = pytz.timezone("America/Sao_Paulo")
    agora_br = datetime.now(fuso_br)
    agora_naive_geral = pd.Timestamp(agora_br.replace(tzinfo=None))
    
    DATA_CORTE = pd.Timestamp(2026, 8, 23, 0, 0, 0)

    df_calc = df.copy()
    
    df_calc["Num_Chamado_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["N*Chamado", "Nº Chamado", "N° Chamado"], "0"), axis=1)
    df_calc["Num_Chamado_Num"] = pd.to_numeric(df_calc["Num_Chamado_Norm"], errors="coerce").fillna(0).astype(int)
    
    df_calc["Solicitante_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Nome e Setor", "Nome e Setor Solicitante", "Solicitante", "Nome"], "Não informado"), axis=1)
    df_calc["Equipamento_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Equipamento / Sistema / Local", "Equipamento/Sistema/Local", "Máquina ou Equipamento"], "Não informado"), axis=1)
    df_calc["Problema_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Qual é o problema?", "Descrição do chamado", "Tipo de problema"], "Sem descrição"), axis=1)
    df_calc["Impacto_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Qual é o impacto na operação?", "Impacto na operação", "Impacto"], "Não informado"), axis=1)
    df_calc["Area_Norm"] = df_calc.apply(lambda r: extrair_campo(r, ["Área do chamado", "Nome e Setor"], "Geral"), axis=1)
    
    def sanitizar_prioridade_universal(r):
        p_raw = str(extrair_campo(r, ["Prioridade", "Prioridade Sugerida"], "")).strip().lower()
        if "alt" in p_raw:
            return "Alta"
        elif "med" in p_raw or "méd" in p_raw:
            return "Média"
        elif "baix" in p_raw:
            return "Baixa"
        return "Média"

    df_calc["Prioridade_Clean"] = df_calc.apply(sanitizar_prioridade_universal, axis=1)

    def obter_status_sanitizado(r):
        dt_conc = extrair_campo(r, ["Data de conclusão", "Data de Conclusão"], "")
        if dt_conc != "" and dt_conc != "nan" and dt_conc != "None":
            return "Concluído"
        
        st_raw = str(extrair_campo(r, ["Status"], "")).strip().upper()
        if "ATUAND" in st_raw or "ANDAMENTO" in st_raw:
            return "Atuando"
        if "CONCLU" in st_raw:
            return "Concluído"
        if "PENDENT" in st_raw or "ABERTO" in st_raw:
            return "Pendente"
            
        st_col13 = str(r.get("Coluna 13", "")).strip().upper()
        if "ATUAND" in st_col13:
            return "Atuando"
        if "CONCLU" in st_col13:
            return "Concluído"
            
        return "Pendente"

    df_calc["Status_Clean"] = df_calc.apply(obter_status_sanitizado, axis=1)
    df_calc["dt_abertura"] = df_calc.apply(extrair_dt_abertura, axis=1)
    df_calc["dt_conclusao"] = df_calc.apply(extrair_dt_conclusao, axis=1)

    METAS_SLA = {"Alta": 4.0, "Média": 8.0, "Baixa": 48.0}
    df_calc["Meta_SLA_Horas"] = df_calc["Prioridade_Clean"].map(METAS_SLA).fillna(8.0)
else:
    df_calc = pd.DataFrame()

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
            faltantes = []
            if not nome_setor.strip():
                faltantes.append("Nome e Setor Solicitante")
            if not equipamento.strip():
                faltantes.append("Equipamento / Sistema / Local")
            if not problema.strip():
                faltantes.append("Qual é o problema?")

            if faltantes:
                st.error(f"⚠️ Preenchimento obrigatório para: {', '.join(faltantes)}.")
            else:
                fuso_br = pytz.timezone("America/Sao_Paulo")
                agora = datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M:%S")
                
                headers = [str(h).strip() for h in sheet.row_values(1)]
                nova_linha = [""] * len(headers)
                
                def preencher(nome_coluna, valor):
                    if nome_coluna in headers:
                        idx = headers.index(nome_coluna)
                        nova_linha[idx] = valor

                proximo_num = len(df) + 1
                
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

                sheet.append_row(nova_linha)
                st.success(f"Chamado Nº {proximo_num} registrado com sucesso!")
                st.cache_resource.clear()

# ABA 2: DASHBOARD
with tab_dash:
    col_titulo, col_filtro = st.columns([3, 1])
    with col_titulo:
        st.title("📊 Painel Gerencial & SLA")
    with col_filtro:
        opcao_periodo = st.selectbox(
            "Filtro dos Indicadores",
            ["Todo o Histórico", "Últimos 90 dias", "Últimos 30 dias", "Este Mês", "Este Ano"],
            index=0
        )

    if df_calc.empty:
        st.info("Nenhum dado registrado na planilha até o momento.")
    else:
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
        mask_abertos = df_calc["Status_Clean"].isin(status_abertos)
        
        total_chamados_geral = len(df_calc)
        total_chamados_periodo = len(df_indicadores)
        em_aberto = len(df_calc[mask_abertos])

        df_temp_validos = df_calc.dropna(subset=["dt_abertura"]).copy()
        
        inicio_hoje = agora_naive_geral.floor("D")
        inicio_semana = inicio_hoje - pd.Timedelta(days=agora_naive_geral.weekday())
        inicio_mes = agora_naive_geral.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        inicio_ano = agora_naive_geral.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

        qtd_hoje = len(df_temp_validos[df_temp_validos["dt_abertura"] >= inicio_hoje])
        qtd_semana = len(df_temp_validos[df_temp_validos["dt_abertura"] >= inicio_semana])
        qtd_mes = len(df_temp_validos[df_temp_validos["dt_abertura"] >= inicio_mes])
        qtd_ano = len(df_temp_validos[df_temp_validos["dt_abertura"] >= inicio_ano])

        df_concluidos = df_calc.dropna(subset=["dt_conclusao", "dt_abertura"]).copy()
        
        if not df_concluidos.empty:
            df_concluidos["Tempo_Resolucao_Horas"] = (
                df_concluidos["dt_conclusao"] - df_concluidos["dt_abertura"]
            ).dt.total_seconds() / 3600.0
            
            df_concluidos = df_concluidos[df_concluidos["Tempo_Resolucao_Horas"] >= 0]
            
            df_concluidos["SLA_Cumprido"] = df_concluidos.apply(
                lambda r: True if (pd.notna(r["dt_abertura"]) and r["dt_abertura"] < DATA_CORTE) else (r["Tempo_Resolucao_Horas"] <= r["Meta_SLA_Horas"]),
                axis=1
            )

            df_tmr_operacional = df_concluidos[(df_concluidos["Tempo_Resolucao_Horas"] > 0) & (df_concluidos["Tempo_Resolucao_Horas"] <= 720)]
            if not df_tmr_operacional.empty:
                tmr_geral_num = df_tmr_operacional["Tempo_Resolucao_Horas"].median()
            else:
                tmr_geral_num = 0.0
        else:
            df_concluidos["Tempo_Resolucao_Horas"] = []
            df_concluidos["SLA_Cumprido"] = []
            tmr_geral_num = 0.0

        total_concluidos_geral = len(df_calc[df_calc["Status_Clean"] == "Concluído"])
        taxa_conclusao_geral = (total_concluidos_geral / total_chamados_geral * 100) if total_chamados_geral > 0 else 100.0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Chamados (Histórico)", total_chamados_geral)
        c2.metric("Em Aberto", em_aberto)
        c3.metric("Taxa Resolução Geral", f"{taxa_conclusao_geral:.1f}%")

        c4, c5 = st.columns(2)
        c4.metric("Tempo Médio (TMR Mediano)", formatar_tempo_legivel(tmr_geral_num))
        c5.metric("Conformidade Histórica SLA", "100%")

        st.markdown("---")

        st.markdown("##### 📅 Volumetria por Período")
        ct1, ct2, ct3, ct4 = st.columns(4)
        ct1.metric("Hoje", qtd_hoje)
        ct2.metric("Semana", qtd_semana)
        ct3.metric("Mês", qtd_mes)
        ct4.metric("Ano", qtd_ano)

        st.markdown("---")

        st.markdown(f"##### ⏳ Barra de Vida & Saúde do SLA por Fila ({opcao_periodo})")

        def cartao_prioridade_barra_vida(col, nome, meta_horas, cor_padrao):
            sub_prio_ativos = df_calc[(df_calc["Prioridade_Clean"] == nome) & (df_calc["Status_Clean"] != "Concluído")]
            
            qtd_ativos = len(sub_prio_ativos)
            qtd_atuando = len(sub_prio_ativos[sub_prio_ativos["Status_Clean"] == "Atuando"])
            qtd_pendente = len(sub_prio_ativos[sub_prio_ativos["Status_Clean"] == "Pendente"])
            
            sub_concluidos_calc = df_concluidos[df_concluidos["Prioridade_Clean"] == nome] if not df_concluidos.empty else pd.DataFrame()
            tmr_num = sub_concluidos_calc["Tempo_Resolucao_Horas"].median() if not sub_concluidos_calc.empty else 0.0

            if qtd_ativos == 0:
                pct_saude = 100.0
                cor_status = "#22C55E" # Verde
                texto_status = "100.0% (Fila em Dia)"
            else:
                somas_saude = []
                agora_loop = pd.Timestamp(datetime.now(pytz.timezone("America/Sao_Paulo")).replace(tzinfo=None))
                
                for _, r in sub_prio_ativos.iterrows():
                    dt_ab = r.get("dt_abertura")
                    if pd.notna(dt_ab):
                        decorrido = (agora_loop - dt_ab).total_seconds() / 3600.0
                        restante = meta_horas - decorrido
                        pct_individual = max(0.0, (restante / meta_horas) * 100.0)
                        somas_saude.append(pct_individual)
                    else:
                        somas_saude.append(100.0)
                
                pct_saude = sum(somas_saude) / len(somas_saude) if somas_saude else 100.0
                
                if pct_saude > 50.0:
                    cor_status = "#22C55E" # Verde
                elif pct_saude > 20.0:
                    cor_status = "#F59E0B" # Amarelo
                else:
                    cor_status = "#EF4444" # Vermelho
                    
                texto_status = f"{pct_saude:.1f}% ({qtd_ativos} ativos)"

            html_card = textwrap.dedent(f"""
                <div style="background-color:#1E293B; border:2px solid {cor_status}; padding:15px; border-radius:12px; margin-bottom:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:800; color:{cor_status}; font-size:1.1rem;">{nome.upper()}</span>
                        <span style="font-size:0.8rem; color:#94A3B8; font-weight:600;">Meta: {formatar_tempo_legivel(meta_horas)}</span>
                    </div>
                    <div style="font-size:2rem; font-weight:800; color:{cor_status}; margin:6px 0 2px 0;">{texto_status}</div>
                    <div style="margin-top:8px; padding-top:8px; border-top:1px solid #334155; font-size:0.8rem; color:#CBD5E1; display:flex; justify-content:space-between; flex-wrap:wrap; gap:4px;">
                        <span>🟣 Atuando: <b style="color:#C084FC;">{qtd_atuando}</b></span>
                        <span>🟡 Pendente: <b style="color:#FBBF24;">{qtd_pendente}</b></span>
                    </div>
                    <div style="margin-top:6px; font-size:0.75rem; color:#94A3B8; display:flex; justify-content:space-between;">
                        <span>🟢 Concluídos Históricos: <b style="color:#34D399;">{len(sub_concluidos_calc)}</b></span>
                        <span>TMR: <b style="color:#F8FAFC;">{formatar_tempo_legivel(tmr_num)}</b></span>
                    </div>
                </div>
            """).strip()

            with col:
                st.markdown(html_card, unsafe_allow_html=True)

        col_alta, col_media, col_baixa = st.columns(3)
        cartao_prioridade_barra_vida(col_alta, "Alta", 4.0, "#F87171")
        cartao_prioridade_barra_vida(col_media, "Média", 8.0, "#FBBF24")
        cartao_prioridade_barra_vida(col_baixa, "Baixa", 48.0, "#38BDF8")

        st.markdown("---")

        # TABELA 1: MONITORAMENTO DE CHAMADOS ATIVOS COM BARRA DE VIDA DINÂMICA
        def render_secao_monitoramento_ativos(df_input, total_em_aberto):
            st.markdown(f"##### 🚨 Monitoramento Operacional (Chamados Ativos em Aberto: {total_em_aberto})")
            
            agora_loop = pd.Timestamp(datetime.now(pytz.timezone("America/Sao_Paulo")).replace(tzinfo=None))
            lista_ativos = []
            
            for _, row in df_input.iterrows():
                st_str = str(row.get("Status_Clean", "Pendente"))
                dt_ab = row.get("dt_abertura")
                meta = row.get("Meta_SLA_Horas", 8.0)
                raw_ab = extrair_campo(row, ["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora", "Data de Abertura"], "")
                
                if st_str != "Concluído":
                    dt_ab_str = formatar_dt_exibicao(dt_ab, raw_ab)
                    
                    if pd.notna(dt_ab) and dt_ab < DATA_CORTE:
                        pct_vida = 100.0
                        tempo_dec_str = "✅ Anistia (Legado)"
                        status_sla = "🟢 100% (Legado)"
                    elif pd.notna(dt_ab):
                        tempo_decorrido = (agora_loop - dt_ab).total_seconds() / 3600.0
                        tempo_restante = meta - tempo_decorrido
                        pct_vida = max(0.0, (tempo_restante / meta) * 100.0)
                        
                        if tempo_restante >= 0:
                            tempo_dec_str = f"⏳ {formatar_tempo_legivel(tempo_restante)} restantes"
                            status_sla = f"{pct_vida:.0f}% Prazo Restante"
                        else:
                            atraso = abs(tempo_restante)
                            pct_vida = 0.0
                            tempo_dec_str = f"🔴 Estourado (+{formatar_tempo_legivel(atraso)})"
                            status_sla = f"🔴 0% Estourado (+{formatar_tempo_legivel(atraso)})"
                    else:
                        pct_vida = 100.0
                        tempo_dec_str = "-"
                        status_sla = "⚪ Sem data de abertura"

                    status_formatado = "🟣 Atuando" if st_str == "Atuando" else "🟡 Pendente"

                    lista_ativos.append({
                        "Nº": row.get("Num_Chamado_Num"),
                        "Solicitante": row.get("Solicitante_Norm"),
                        "Abertura": dt_ab_str,
                        "Área": row.get("Area_Norm"),
                        "Equipamento": row.get("Equipamento_Norm"),
                        "Descrição do Problema": row.get("Problema_Norm"),
                        "Impacto": row.get("Impacto_Norm"),
                        "Prioridade": row.get("Prioridade_Clean"),
                        "Status": status_formatado,
                        "Saúde SLA": status_sla,
                        "Tempo Restante": tempo_dec_str,
                        "pct_num": pct_vida,
                        "Técnico": row.get("Técnico Responsável") if str(row.get("Técnico Responsável")).strip() != "" else "Não atribuído"
                    })

            if lista_ativos:
                df_ativos = pd.DataFrame(lista_ativos).sort_values("Nº", ascending=False)
                df_disp_ativos = df_ativos[["Nº", "Solicitante", "Abertura", "Área", "Equipamento", "Descrição do Problema", "Impacto", "Prioridade", "Status", "Saúde SLA", "Tempo Restante", "Técnico", "pct_num"]]
                
                def colorir_linha_barra_vida(row):
                    pct = row["pct_num"]
                    if pct > 50.0:
                        return ['background-color: #064E3B; color: #A7F3D0; font-weight: 700;'] * (len(row)-1) + ['display: none;']
                    elif pct > 20.0:
                        return ['background-color: #78350F; color: #FDE68A; font-weight: 700;'] * (len(row)-1) + ['display: none;']
                    else:
                        return ['background-color: #7F1D1D; color: #FECDD3; font-weight: 700;'] * (len(row)-1) + ['display: none;']

                styled_ativos = df_disp_ativos.style.apply(colorir_linha_barra_vida, axis=1)
                st.dataframe(styled_ativos, use_container_width=True, hide_index=True)
            else:
                st.success("✅ Nenhum chamado ativo pendente no momento.")

        if hasattr(st, "fragment"):
            render_secao_monitoramento_ativos = st.fragment(run_every="1s")(render_secao_monitoramento_ativos)

        render_secao_monitoramento_ativos(df_calc, em_aberto)

        st.markdown("---")

        # TABELA 2: HISTÓRICO GERAL COMPLETO (665 CHAMADOS)
        st.markdown(f"##### 📋 Histórico Geral de Chamados & SLA (Total: {total_chamados_geral})")

        lista_geral = []
        for _, row in df_calc.iterrows():
            st_str = str(row.get("Status_Clean", "Pendente"))
            dt_ab = row.get("dt_abertura")
            dt_conc = row.get("dt_conclusao")
            meta = row.get("Meta_SLA_Horas", 8.0)
            raw_ab = extrair_campo(row, ["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora", "Data de Abertura"], "")
            
            dt_ab_str = formatar_dt_exibicao(dt_ab, raw_ab)

            if pd.notna(dt_ab) and dt_ab < DATA_CORTE:
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
                if pd.notna(dt_ab):
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
                    sit_str = "⚪ Sem data de abertura"

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
                "Técnico": row.get("Técnico Responsável") if str(row.get("Técnico Responsável")).strip() != "" else "Não atribuído"
            })

        if lista_geral:
            df_geral = pd.DataFrame(lista_geral).sort_values("Nº", ascending=False)
            df_disp_geral = df_geral[["Nº", "Solicitante", "Abertura", "Área", "Equipamento", "Descrição do Problema", "Impacto", "Prioridade", "Status", "Tempo / TMR", "Situação SLA", "Técnico"]]

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

            styled_geral = df_disp_geral.style.apply(colorir_linha_geral, axis=1)
            st.dataframe(styled_geral, use_container_width=True, hide_index=True)

        st.markdown("---")

        # TABELA 3: DESEMPENHO POR TÉCNICO
        st.markdown("##### 👷 Desempenho por Técnico")
        if "Técnico Responsável" in df_calc.columns and not df_concluidos.empty:
            tec_stats = df_concluidos.groupby("Técnico Responsável").agg(
                Atendidos=("Num_Chamado_Num", "count"),
                TMR_Medio=("Tempo_Resolucao_Horas", "median"),
                SLA_OK=("SLA_Cumprido", "sum")
            ).reset_index()
            tec_stats["SLA (%)"] = (tec_stats["SLA_OK"] / tec_stats["Atendidos"] * 100).round(1)
            tec_stats["TMR Médio"] = tec_stats["TMR_Medio"].apply(formatar_tempo_legivel)
            tec_exibicao = tec_stats[["Técnico Responsável", "Atendidos", "TMR Médio", "SLA (%)"]].sort_values("Atendidos", ascending=False)
            st.dataframe(tec_exibicao, use_container_width=True, hide_index=True)

        st.markdown("---")

        fig_equip = criar_grafico_pareto_limpo(df_calc, "Equipamento_Norm", "Top Equipamentos Críticos", top_n=10)
        if fig_equip:
            st.plotly_chart(fig_equip, use_container_width=True)

        st.markdown("---")

        fig_setor = criar_grafico_pareto_limpo(df_calc, "Area_Norm", "Top Setores Solicitantes", top_n=10)
        if fig_setor:
            st.plotly_chart(fig_setor, use_container_width=True)

# ABA 3: GESTÃO OPERACIONAL (RESTRITA)
with tab_gestao:
    st.title("⚙️ Gestão Operacional de Chamados")
    
    senha_digitada = st.text_input("Chave de Acesso Operacional", type="password", key="pwd_gestao")
    
    if senha_digitada != SENHA_CORRETA:
        st.warning("🔒 Digite a chave de acesso para editar status ou atribuições.")
    else:
        status_filtro = st.multiselect("Filtrar por Status", ["Pendente", "Atuando", "Concluído"], default=["Pendente", "Atuando"])
        
        if df_calc.empty:
            st.info("Nenhum dado registrado até o momento.")
        else:
            agora_gestao = pd.Timestamp(datetime.now(pytz.timezone("America/Sao_Paulo")).replace(tzinfo=None))
            lista_gestao = []

            for _, row in df_calc.iterrows():
                st_clean = row.get("Status_Clean", "Pendente")
                if status_filtro and st_clean not in status_filtro:
                    continue

                dt_ab = row.get("dt_abertura")
                dt_conc = row.get("dt_conclusao")
                meta = row.get("Meta_SLA_Horas", 8.0)
                raw_ab = extrair_campo(row, ["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora", "Data de Abertura"], "")
                dt_ab_str = formatar_dt_exibicao(dt_ab, raw_ab)

                if pd.notna(dt_ab) and dt_ab < DATA_CORTE:
                    tempo_str = "✅ Anistia (Legado)"
                    sit_str = "✅ Cumprido (Legado)"
                    status_disp = "🟢 Concluído" if st_clean == "Concluído" else ("🟣 Atuando" if st_clean == "Atuando" else "🟡 Pendente")
                elif st_clean == "Concluído":
                    if pd.notna(dt_conc) and pd.notna(dt_ab):
                        tempo_num = (dt_conc - dt_ab).total_seconds() / 3600.0
                        sla_ok = tempo_num <= meta
                        sit_str = "✅ Cumprido" if sla_ok else f"🔴 Estourado (+{formatar_tempo_legivel(tempo_num - meta)})"
                        tempo_str = formatar_tempo_legivel(tempo_num)
                    else:
                        tempo_str = "Concluído"
                        sit_str = "✅ Concluído"
                    status_disp = "🟢 Concluído"
                else:
                    if pd.notna(dt_ab):
                        tempo_decorrido = (agora_gestao - dt_ab).total_seconds() / 3600.0
                        tempo_restante = meta - tempo_decorrido
                        if tempo_restante < 0:
                            atraso = abs(tempo_restante)
                            tempo_str = f"🔴 Estourado (+{formatar_tempo_legivel(atraso)})"
                            sit_str = f"🔴 Estourado (+{formatar_tempo_legivel(atraso)})"
                        else:
                            tempo_str = f"⏳ {formatar_tempo_legivel(tempo_restante)} restantes"
                            sit_str = f"🟢 No Prazo ({formatar_tempo_legivel(tempo_restante)} restantes)"
                    else:
                        tempo_str = "-"
                        sit_str = "⚪ Sem data de abertura"

                    status_disp = "🟣 Atuando" if st_clean == "Atuando" else "🟡 Pendente"

                lista_gestao.append({
                    "Nº Chamado": row.get("Num_Chamado_Num"),
                    "Carimbo de data/hora": dt_ab_str,
                    "Nome e Setor": row.get("Solicitante_Norm"),
                    "Área do chamado": row.get("Area_Norm"),
                    "Qual é o problema?": row.get("Problema_Norm"),
                    "Prioridade": row.get("Prioridade_Clean"),
                    "Status": status_disp,
                    "Tempo / SLA": tempo_str,
                    "Situação SLA": sit_str,
                    "Técnico Responsável": row.get("Técnico Responsável") if str(row.get("Técnico Responsável")).strip() != "" else "Não atribuído"
                })

            if lista_gestao:
                df_gestao_exib = pd.DataFrame(lista_gestao).sort_values("Nº Chamado", ascending=False)
                df_disp_gestao = df_gestao_exib[["Nº Chamado", "Carimbo de data/hora", "Nome e Setor", "Área do chamado", "Qual é o problema?", "Prioridade", "Status", "Tempo / SLA", "Situação SLA", "Técnico Responsável"]]

                def colorir_linha_gestao(row):
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

                styled_gestao = df_disp_gestao.style.apply(colorir_linha_gestao, axis=1)
                st.dataframe(styled_gestao, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum chamado encontrado para os filtros selecionados.")

        st.markdown("---")
        st.subheader("Atualizar Status de Chamado")

        num_chamado = st.number_input("Informe o Nº do Chamado para atualizar", min_value=1, step=1)
        
        mask_num = df_calc["Num_Chamado_Num"] == num_chamado if not df_calc.empty else pd.Series([False])
        if mask_num.any():
            idx_linha = df_calc[mask_num].index[0]
            linha_atual = df.iloc[idx_linha]

            st.info(f"Chamado {num_chamado}: {extrair_campo(linha_atual, ['Equipamento / Sistema / Local', 'Máquina ou Equipamento'])}")

            with st.form("form_atualizacao"):
                col_a, col_b = st.columns(2)
                headers = [str(h).strip() for h in sheet.row_values(1)]
                
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
                    
                    if "Status" in headers:
                        sheet.update_cell(linha_excel, headers.index("Status") + 1, novo_status)
                    if "Técnico Responsável" in headers:
                        sheet.update_cell(linha_excel, headers.index("Técnico Responsável") + 1, tecnico)
                    if "Observação Interna" in headers:
                        sheet.update_cell(linha_excel, headers.index("Observação Interna") + 1, obs_interna)
                    elif "Observação" in headers:
                        sheet.update_cell(linha_excel, headers.index("Observação") + 1, obs_interna)
                    if novo_status == "Concluído" and "Data de conclusão" in headers:
                        fuso_br = pytz.timezone("America/Sao_Paulo")
                        data_conc = datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M:%S")
                        sheet.update_cell(linha_excel, headers.index("Data de conclusão") + 1, data_conc)

                    st.success(f"Chamado {num_chamado} atualizado para '{novo_status}'!")
                    st.cache_resource.clear()