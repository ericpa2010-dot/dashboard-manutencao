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

def dentro_do_expediente(dt, hora_inicio=8, hora_fim=19):
    if pd.isna(dt): return False
    if dt.weekday() >= 5: return False
    return hora_inicio <= dt.hour < hora_fim

def calcular_horas_uteis(dt_inicio, dt_fim, hora_inicio=8, hora_fim=19):
    if pd.isna(dt_inicio): return 0.0
    if pd.isna(dt_fim):
        dt_fim = datetime.now(pytz.timezone("America/Sao_Paulo")).replace(tzinfo=None)
    
    if hasattr(dt_inicio, 'tzinfo') and dt_inicio.tzinfo is not None:
        dt_inicio = dt_inicio.tz_convert(None)
    if hasattr(dt_fim, 'tzinfo') and dt_fim.tzinfo is not None:
        dt_fim = dt_fim.tz_convert(None)
        
    if dt_inicio >= dt_fim: return 0.0

    total_segundos = 0.0
    curr = dt_inicio
    
    while curr < dt_fim:
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
        try: return datetime(y, m, d, h, mi, sec)
        except ValueError: pass

    return pd.to_datetime(s, errors="coerce", dayfirst=True)

def extrair_dt_abertura(row):
    val = extrair_campo(row, ["Carimbo de data/hora", "Carimbo de Data/Hora", "Data/Hora", "Data de Abertura", "Data"], "")
    return parse_data_infalivel(val)

def extrair_dt_conclusao(row):
    val = extrair_campo(row, ["Data de conclusão", "Data de Conclusão"], "")
    return parse_data_infalivel(val)

def formatar_dt_exibicao(dt, val_raw=""):
    if pd.notna(dt): return dt.strftime("%d/%m/%Y %H:%M:%S")
    s = str(val_raw).replace('\xa0', ' ').strip()
    return s if s not in ["", "nan", "None"] else "-"

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
    dt_conc = extrair_campo(r, ["Data de conclusão", "Data de Conclusão"], "")
    if dt_conc != "" and dt_conc != "nan" and dt_conc != "None": return "Concluído"
    
    st_raw = str(extrair_campo(r, ["Status"], "")).strip().upper()
    if "ATUAND" in st_raw or "ANDAMENTO" in st_raw: return "Atuando"
    if "CONCLU" in st_raw: return "Concluído"
    if "PENDENT" in st_raw or "ABERTO" in st_raw: return "Pendente"
    return "Pendente"

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

# ABA 2: DASHBOARD & SLA
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
        status_expediente_str = "▶️ Ativo (Em Turno)" if em_turno else "⏸️ Pausado (Fora do Expediente)"

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Chamados", total_chamados_geral)
        c2.metric("Em Aberto", em_aberto)
        c3.metric("Taxa Resolução", f"{taxa_conclusao_geral:.1f}%")
        c4.metric("SLA / Expediente", status_expediente_str)

        st.markdown("---")
        st.markdown(f"##### ⏳ Barra de Vida & Saúde do SLA por Fila (Regime: Horário Comercial 08:00 - 19:00)")

        def cartao_prioridade_jornada(col, nome, meta_horas):
            sub_prio_ativos = df_calc[(df_calc["Prioridade_Clean"] == nome) & (df_calc["Status_Clean"].isin(["Pendente", "Atuando"]))]
            qtd_ativos = len(sub_prio_ativos)
            
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
                    else:
                        somas_saude.append(100.0)
                
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
                    prefixo_turno = "▶️" if em_turno else "⏸️ Pausado:"
                    tempo_dec_str = f"{prefixo_turno} {formatar_tempo_legivel(tempo_restante_util)} restantes"
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

# ABA 3: GESTÃO OPERACIONAL DE CHAMADOS
with tab_gestao:
    st.title("⚙️ Gestão Operacional de Chamados")
    senha_digitada = st.text_input("Chave de Acesso Operacional", type="password", key="pwd_gestao")
    
    if senha_digitada == SENHA_CORRETA and not df_calc.empty:
        st.subheader("🛠️ Tratar Chamados em Aberto")
        
        df_abertos_gestao = df_calc[df_calc["Status_Clean"].isin(["Pendente", "Atuando"])].sort_values("Num_Chamado_Num", ascending=False)
        
        if not df_abertos_gestao.empty:
            opcoes_chamados = [
                f"#{r['Num_Chamado_Num']} - {r['Equipamento_Norm']} ({r['Solicitante_Norm']}) | Status: {r['Status_Clean']}"
                for _, r in df_abertos_gestao.iterrows()
            ]
            chamado_sel_str = st.selectbox("Selecione um chamado em aberto para atualizar:", opcoes_chamados)
            num_chamado_sel = int(chamado_sel_str.split(" - ")[0].replace("#", ""))
        else:
            st.info("Nenhum chamado pendente na fila no momento. Digite um número abaixo para editar um histórico encerrado:")
            num_chamado_sel = st.number_input("Informe o Nº do Chamado", min_value=1, step=1)

        mask_num = df_calc["Num_Chamado_Num"] == num_chamado_sel
        if mask_num.any():
            idx_linha = df_calc[mask_num].index[0]
            linha_atual = df_raw.iloc[idx_linha]

            st.info(f"Editando Chamado #{num_chamado_sel}: {extrair_campo(linha_atual, ['Equipamento / Sistema / Local', 'Máquina ou Equipamento'])}")

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
                    if novo_status == "Concluído" and "Data de conclusão" in headers:
                        data_conc = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")
                        updates_lote.append({'range': rowcol_to_a1(linha_excel, headers.index("Data de conclusão") + 1), 'values': [[data_conc]]})

                    if updates_lote:
                        sheet.batch_update(updates_lote)

                    st.success(f"Chamado Nº {num_chamado_sel} atualizado com sucesso!")
                    st.cache_data.clear()
                    st.rerun()