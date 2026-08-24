import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
import requests
from datetime import datetime
import pytz
import re
import io
import plotly.graph_objects as go
import plotly.express as px

# Configuração da página
st.set_page_config(page_title="Gestão de Manutenção", page_icon="🛠️", layout="wide")

# Estilo Escuro Fixo (Midnight Slate - Alto Contraste)
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}

    .stApp {
        background-color: #0F172A;
        color: #F8FAFC;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    }

    h1, h2, h3, h4, h5, h6, label {
        color: #F8FAFC !important;
        font-weight: 700 !important;
    }

    div[data-testid="stMetric"] {
        background-color: #1E293B;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 4px 20px -2px rgba(56, 189, 248, 0.05);
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.85rem !important;
        color: #94A3B8 !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
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

    section[data-testid="stSidebar"] {
        background-color: #0B0F19;
        border-right: 1px solid #1E293B;
    }

    hr {
        border-color: #334155 !important;
        margin: 1.5rem 0 !important;
    }

    div[data-testid="stDataFrame"] {
        background-color: #1E293B;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 8px;
    }

    .badge-prioridade-alta {
        background-color: #7F1D1D;
        color: #FECACA;
        padding: 4px 8px;
        border-radius: 6px;
        font-weight: bold;
    }
    .badge-prioridade-media {
        background-color: #78350F;
        color: #FDE68A;
        padding: 4px 8px;
        border-radius: 6px;
        font-weight: bold;
    }
    .badge-prioridade-baixa {
        background-color: #064E3B;
        color: #A7F3D0;
        padding: 4px 8px;
        border-radius: 6px;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

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
    return creds, gspread.authorize(creds)

def load_data():
    creds, client = get_gspread_client()
    sheet = client.open_by_url(st.secrets["spreadsheet"]["url"]).worksheet("CHAMADOS")
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    return creds, sheet, df

# Validação de e-mail por regex
def validar_email(email):
    padrao = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return re.match(padrao, email) is not None

# Upload de anexo para o Google Drive
def upload_para_drive(creds, file_obj):
    try:
        if not creds.valid:
            creds.refresh(Request())
        access_token = creds.token
        
        metadata = {"name": file_obj.name}
        files = {
            'data': ('metadata', str(metadata).encode('utf-8'), 'application/json; charset=UTF-8'),
            'file': (file_obj.name, file_obj.getvalue(), file_obj.type)
        }
        headers = {"Authorization": f"Bearer {access_token}"}
        r = requests.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            headers=headers,
            files=files
        )
        if r.status_code == 200:
            file_id = r.json().get("id")
            return f"https://drive.google.com/file/d/{file_id}/view"
        return f"Arquivo carregado: {file_obj.name}"
    except Exception:
        return f"Anexo registrado: {file_obj.name}"

# Formatador de tempo amigável
def formatar_tempo_legivel(horas):
    if pd.isna(horas) or horas is None or horas <= 0:
        return "0h"
    if horas < 24:
        return f"{horas:.1f}h"
    dias = int(horas // 24)
    hrs_restantes = int(horas % 24)
    return f"{dias}d {hrs_restantes}h"

# Gerador de Pareto Escuro e Futurista
def criar_grafico_pareto_limpo(df_input, coluna, titulo, top_n=10):
    if coluna not in df_input.columns or df_input[coluna].dropna().empty:
        return None
    
    s = df_input[coluna].astype(str).str.strip()
    s = s[s != ""]
    if s.empty:
        return None
        
    counts = s.value_counts().reset_index()
    counts.columns = [coluna, 'Ocorrências']
    
    if len(counts) > top_n:
        top_counts = counts.head(top_n).copy()
        outros_qtd = counts.iloc[top_n:]['Ocorrências'].sum()
        outros_df = pd.DataFrame([{coluna: 'Outros (Diversos)', 'Ocorrências': outros_qtd}])
        counts = pd.concat([top_counts, outros_df], ignore_index=True)
    
    counts[coluna] = counts[coluna].apply(lambda x: x[:22] + "..." if len(x) > 22 else x)
    
    counts['Acumulado'] = counts['Ocorrências'].cumsum()
    total = counts['Ocorrências'].sum()
    counts['Percentual_Acumulado'] = (counts['Acumulado'] / total) * 100 if total > 0 else 0
    
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=counts[coluna],
            y=counts['Ocorrências'],
            name="Qtd Chamados",
            marker_color="#38BDF8",
            text=counts['Ocorrências'],
            textposition="outside",
            textfont=dict(size=12, color="#F8FAFC")
        )
    )
    fig.add_trace(
        go.Scatter(
            x=counts[coluna],
            y=counts['Percentual_Acumulado'],
            name="% Acumulado",
            yaxis="y2",
            mode="lines+markers",
            line=dict(color="#F43F5E", width=3),
            marker=dict(size=8, color="#F43F5E")
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
        title=dict(text=f"<b>{titulo}</b>", font=dict(size=16, color="#F8FAFC")),
        xaxis=dict(tickfont=dict(size=11, color="#CBD5E1"), tickangle=-15, showgrid=False),
        yaxis=dict(
            title=dict(text="<b>Qtd Chamados</b>", font=dict(size=12, color="#94A3B8")),
            tickfont=dict(size=11, color="#CBD5E1"),
            gridcolor="#334155",
            showgrid=True
        ),
        yaxis2=dict(
            title=dict(text="<b>% Acumulado</b>", font=dict(size=12, color="#94A3B8")),
            tickfont=dict(size=11, color="#CBD5E1"),
            overlaying="y",
            side="right",
            range=[0, 105],
            showgrid=False
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1, font=dict(size=11, color="#F8FAFC")),
        margin=dict(l=20, r=20, t=50, b=50),
        height=420,
        paper_bgcolor="#1E293B",
        plot_bgcolor="#1E293B"
    )
    return fig

try:
    creds, sheet, df = load_data()
except Exception as e:
    st.error(f"Erro ao conectar com a planilha: {e}")
    st.stop()

# Navegação lateral
st.sidebar.title("Sistema de Manutenção")
menu = st.sidebar.radio("Navegação", ["Abrir Chamado", "Gestão Operacional", "Dashboard & SLA"])

SENHA_CORRETA = st.secrets.get("SENHA_GESTAO", "manutencao123")

if menu == "Gestão Operacional":
    st.sidebar.markdown("---")
    senha_digitada = st.sidebar.text_input("Chave de Acesso Operacional", type="password")
    if senha_digitada != SENHA_CORRETA:
        st.warning("🔒 Área restrita à equipe de manutenção. Insira a chave de acesso na barra lateral para continuar.")
        st.stop()
    st.sidebar.success("Sessão ativa: Técnico Autenticado")

# MODULO 1: ABERTURA DE CHAMADO
if menu == "Abrir Chamado":
    st.title("📌 Abertura de Chamado de Manutenção")
    
    proximo_num = len(df) + 1
    st.info(f"🆔 **Pré-visualização do Número do Chamado:** #{proximo_num}")

    with st.form("form_abertura", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            nome_setor = st.text_input("Nome e Setor Solicitante *", placeholder="Ex: Guilherme (Surfaçagem)")
            email = st.text_input("E-mail para Notificação *", placeholder="exemplo@empresa.com.br")
            area = st.selectbox("Área do Chamado", ["Surfaçagem", "AR", "Montagem", "Estoque", "Expedição", "Atendimento", "TI", "Diretoria", "Geral"])
            equipamento = st.text_input("Equipamento / Sistema / Local *", placeholder="Ex: Satisloh SL-501")
        
        with col2:
            impacto = st.selectbox("Impacto na Operação", ["Parada total", "Parada parcial", "Sem impacto"])
            prioridade = st.selectbox("Prioridade Sugerida", ["Alta", "Média", "Baixa"])
            arquivo_anexo = st.file_uploader("Anexar Foto ou Documento (Opcional)", type=["png", "jpg", "jpeg", "pdf"])

        problema = st.text_input("Qual é o problema? *", placeholder="Resumo em uma frase")
        observado = st.text_area("O que foi observado?", placeholder="Detalhes do comportamento do equipamento")
        testado = st.text_area("O que já foi feito/testado?", placeholder="Ações iniciais tentadas antes do chamado")

        st.markdown("---")
        submitted = st.form_submit_button("🚀 Enviar Chamado de Manutenção", use_container_width=True)

        if submitted:
            if not nome_setor or not email or not problema or not equipamento:
                st.error("⚠️ Preencha todos os campos obrigatórios assinalados com (*).")
            elif not validar_email(email):
                st.error("⚠️ O e-mail informado é inválido. Verifique o formato inserido.")
            else:
                fuso_br = pytz.timezone("America/Sao_Paulo")
                agora = datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M:%S")

                link_anexo = ""
                if arquivo_anexo is not None:
                    with st.spinner("Enviando anexo para o repositório..."):
                        link_anexo = upload_para_drive(creds, arquivo_anexo)

                nova_linha = [
                    proximo_num, agora, email, nome_setor, area, equipamento,
                    problema, observado, testado, impacto, prioridade,
                    link_anexo, "Aberto", "", "", ""
                ]

                sheet.append_row(nova_linha)
                st.cache_resource.clear()

                st.success(f"✅ **Chamado #{proximo_num} aberto com sucesso!**")
                st.markdown(f"""
                <div style="background-color:#1E293B; border:1px solid #38BDF8; padding:20px; border-radius:12px; margin-top:10px;">
                    <h4 style="color:#38BDF8; margin:0 0 10px 0;">Resumo da Solicitação</h4>
                    <p><b>Número:</b> #{proximo_num}</p>
                    <p><b>Solicitante:</b> {nome_setor} ({email})</p>
                    <p><b>Equipamento:</b> {equipamento} ({area})</p>
                    <p><b>Problema:</b> {problema}</p>
                    <p><b>Prioridade/Impacto:</b> {prioridade} / {impacto}</p>
                </div>
                """, unsafe_allow_html=True)

# MODULO 2: GESTÃO OPERACIONAL
elif menu == "Gestão Operacional":
    st.title("⚙️ Gestão Operacional de Chamados")
    
    lista_status = ["Aberto", "Em análise", "Em execução", "Aguardando peça", "Concluído", "Cancelado"]
    
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        status_filtro = st.multiselect("Filtrar por Status", lista_status, default=["Aberto", "Em análise", "Em execução", "Aguardando peça"])
    with col_f2:
        areas_disponiveis = list(df["Área do chamado"].astype(str).unique()) if "Área do chamado" in df.columns else []
        area_filtro = st.multiselect("Filtrar por Área", areas_disponiveis)
    with col_f3:
        prio_filtro = st.multiselect("Filtrar por Prioridade", ["Alta", "Média", "Baixa"])

    df_filtrado = df.copy()
    if status_filtro:
        df_filtrado = df_filtrado[df_filtrado["Status"].isin(status_filtro)]
    if area_filtro:
        df_filtrado = df_filtrado[df_filtrado["Área do chamado"].isin(area_filtro)]
    if prio_filtro:
        df_filtrado = df_filtrado[df_filtrado["Prioridade"].isin(prio_filtro)]

    colunas_visiveis = [c for c in ["Nº Chamado", "Carimbo de data/hora", "Área do chamado", "Equipamento/Sistema/Local", "Prioridade", "Impacto na operação", "Status", "Técnico Responsável"] if c in df_filtrado.columns]
    st.dataframe(df_filtrado[colunas_visiveis], use_container_width=True)

    # Exportação de relatório
    csv_data = df_filtrado.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Exportar Chamados Filtrados (CSV)", data=csv_data, file_name="relatorio_chamados.csv", mime="text/csv")

    st.markdown("---")
    st.subheader("Atualizar e Processar Chamado")

    num_chamado = st.number_input("Informe o Nº do Chamado para atualizar", min_value=1, step=1)
    
    if num_chamado in df["Nº Chamado"].values:
        idx_linha = df[df["Nº Chamado"] == num_chamado].index[0]
        linha_atual = df.iloc[idx_linha]

        st.info(f"**Chamado #{num_chamado}:** {linha_atual.get('Equipamento/Sistema/Local', '')} | **Solicitante:** {linha_atual.get('Nome e Setor Solicitante', '')}")
        st.write(f"**Problema:** {linha_atual.get('Qual é o problema?', '')}")

        with st.form("form_atualizacao"):
            col_a, col_b = st.columns(2)
            with col_a:
                status_atual = str(linha_atual.get("Status", "Aberto")).strip()
                idx_st = lista_status.index(status_atual) if status_atual in lista_status else 0
                novo_status = st.selectbox("Status Operacional", lista_status, index=idx_st)
                
                nova_prio = st.selectbox("Ajustar Prioridade", ["Alta", "Média", "Baixa"], index=["Alta", "Média", "Baixa"].index(str(linha_atual.get("Prioridade", "Média"))) if str(linha_atual.get("Prioridade", "Média")) in ["Alta", "Média", "Baixa"] else 1)
                novo_impacto = st.selectbox("Ajustar Impacto", ["Parada total", "Parada parcial", "Sem impacto"], index=["Parada total", "Parada parcial", "Sem impacto"].index(str(linha_atual.get("Impacto na operação", "Sem impacto"))) if str(linha_atual.get("Impacto na operação", "Sem impacto")) in ["Parada total", "Parada parcial", "Sem impacto"] else 2)

            with col_b:
                tec_atual = str(linha_atual.get("Técnico Responsável", "Eric"))
                opcoes_tec = ["Eric", "Felipe", "Outro"]
                idx_tec = opcoes_tec.index(tec_atual) if tec_atual in opcoes_tec else 0
                tecnico = st.selectbox("Técnico Responsável", opcoes_tec, index=idx_tec)

                obs_interna = st.text_area("Histórico / Diagnóstico Técnico", value=str(linha_atual.get("Observação Interna", "")))

            btn_salvar = st.form_submit_button("Salvar Alterações do Chamado")

            if btn_salvar:
                linha_excel = idx_linha + 2
                
                sheet.update_cell(linha_excel, 10, novo_impacto)
                sheet.update_cell(linha_excel, 11, nova_prio)
                sheet.update_cell(linha_excel, 13, novo_status)
                sheet.update_cell(linha_excel, 14, tecnico)
                
                if novo_status == "Concluído":
                    fuso_br = pytz.timezone("America/Sao_Paulo")
                    agora_conc = datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M:%S")
                    sheet.update_cell(linha_excel, 15, agora_conc)
                
                sheet.update_cell(linha_excel, 16, obs_interna)
                st.success(f"Chamado #{num_chamado} atualizado para '{novo_status}' com sucesso!")
                st.cache_resource.clear()

# MODULO 3: DASHBOARD & SLA
elif menu == "Dashboard & SLA":
    st.title("📊 Painel Gerencial & Indicadores de SLA")

    if df.empty:
        st.info("Nenhum dado registrado na planilha até o momento.")
        st.stop()

    fuso_br = pytz.timezone("America/Sao_Paulo")
    agora_br = datetime.now(fuso_br)

    df_calc = df.copy()
    df_calc["dt_abertura"] = pd.to_datetime(df_calc["Carimbo de data/hora"].astype(str), errors="coerce", dayfirst=True)
    df_calc["dt_conclusao"] = pd.to_datetime(df_calc["Data de conclusão"].astype(str), errors="coerce", dayfirst=True)

    # Filtro Temporal de Período
    st.sidebar.markdown("---")
    filtro_periodo = st.sidebar.selectbox("Período do Dashboard", ["Tudo", "Últimos 7 dias", "Últimos 30 dias", "Últimos 90 dias"])

    agora_naive = agora_br.replace(tzinfo=None)
    if filtro_periodo == "Últimos 7 dias":
        df_calc = df_calc[df_calc["dt_abertura"] >= (agora_naive - pd.Timedelta(days=7))]
    elif filtro_periodo == "Últimos 30 dias":
        df_calc = df_calc[df_calc["dt_abertura"] >= (agora_naive - pd.Timedelta(days=30))]
    elif filtro_periodo == "Últimos 90 dias":
        df_calc = df_calc[df_calc["dt_abertura"] >= (agora_naive - pd.Timedelta(days=90))]

    total_chamados = len(df_calc)
    em_aberto = len(df_calc[df_calc["Status"].astype(str).str.strip().isin(["Aberto", "Em análise", "Em execução", "Aguardando peça", "Pendente", "Atuando"])])

    METAS_SLA = {"alta": 4.0, "media": 8.0, "baixa": 78.0}
    def get_sla_target(prioridade):
        p = str(prioridade).strip().lower().replace("é", "e")
        for chave, meta in METAS_SLA.items():
            if chave in p:
                return meta
        return 8.0

    df_calc["Meta_SLA_Horas"] = df_calc["Prioridade"].apply(get_sla_target)

    # Avaliação de Atrasos
    chamados_em_atraso = 0
    for _, row in df_calc.iterrows():
        st_str = str(row.get("Status", "Aberto")).strip()
        dt_ab = row.get("dt_abertura")
        dt_conc = row.get("dt_conclusao")
        meta = row.get("Meta_SLA_Horas", 8.0)
        
        if pd.isna(dt_ab):
            continue
            
        if st_str == "Concluído":
            if pd.notna(dt_conc) and ((dt_conc - dt_ab).total_seconds() / 3600.0) > meta:
                chamados_em_atraso += 1
        elif st_str != "Cancelado":
            if ((agora_naive - dt_ab).total_seconds() / 3600.0) > meta:
                chamados_em_atraso += 1

    df_concluidos = df_calc.dropna(subset=["dt_conclusao", "dt_abertura"]).copy()
    if not df_concluidos.empty:
        df_concluidos["Tempo_Resolucao_Horas"] = (
            df_concluidos["dt_conclusao"] - df_concluidos["dt_abertura"]
        ).dt.total_seconds() / 3600.0
        df_concluidos = df_concluidos[df_concluidos["Tempo_Resolucao_Horas"] >= 0]
        df_concluidos["SLA_Cumprido"] = df_concluidos["Tempo_Resolucao_Horas"] <= df_concluidos["Meta_SLA_Horas"]
        
        df_tmr_operacional = df_concluidos[df_concluidos["Tempo_Resolucao_Horas"] <= 720]
        tmr_geral_num = df_tmr_operacional["Tempo_Resolucao_Horas"].mean() if not df_tmr_operacional.empty else df_concluidos["Tempo_Resolucao_Horas"].median()
    else:
        df_concluidos["Tempo_Resolucao_Horas"] = []
        df_concluidos["SLA_Cumprido"] = []
        tmr_geral_num = 0.0

    total_concluidos = len(df_concluidos)
    sla_cumprido_pct = ((df_concluidos["SLA_Cumprido"].sum() / total_concluidos) * 100) if total_concluidos > 0 else 100.0

    # LINHA 1: KPIs Solicitados
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Chamados Abertos / Ativos", em_aberto)
    c2.metric("Fora do SLA (Em Atraso)", chamados_em_atraso)
    c3.metric("Tempo Médio (TMR)", formatar_tempo_legivel(tmr_geral_num))
    c4.metric("% Dentro do SLA", f"{sla_cumprido_pct:.0f}%")

    st.markdown("---")

    # LINHA 2: Gráficos de Distribuição
    col_g1, col_g2, col_g3 = st.columns(3)
    
    with col_g1:
        if "Área do chamado" in df_calc.columns and not df_calc.empty:
            fig_area = px.pie(df_calc, names="Área do chamado", title="<b>Chamados por Área</b>", hole=0.4, template="plotly_dark")
            fig_area.update_layout(height=350, paper_bgcolor="#1E293B", plot_bgcolor="#1E293B")
            st.plotly_chart(fig_area, use_container_width=True)

    with col_g2:
        if "Prioridade" in df_calc.columns and not df_calc.empty:
            fig_prio = px.bar(df_calc["Prioridade"].value_counts().reset_index(), x="Prioridade", y="count", title="<b>Distribuição de Prioridade</b>", text="count", template="plotly_dark")
            fig_prio.update_traces(marker_color="#38BDF8", textposition="outside")
            fig_prio.update_layout(height=350, paper_bgcolor="#1E293B", plot_bgcolor="#1E293B")
            st.plotly_chart(fig_prio, use_container_width=True)

    with col_g3:
        if not df_concluidos.empty and "Impacto na operação" in df_concluidos.columns:
            tmr_impacto = df_concluidos.groupby("Impacto na operação")["Tempo_Resolucao_Horas"].mean().reset_index()
            fig_imp = px.bar(tmr_impacto, x="Impacto na operação", y="Tempo_Resolucao_Horas", title="<b>Tempo Médio por Impacto (h)</b>", text_auto=".1f", template="plotly_dark")
            fig_imp.update_traces(marker_color="#F43F5E", textposition="outside")
            fig_imp.update_layout(height=350, paper_bgcolor="#1E293B", plot_bgcolor="#1E293B")
            st.plotly_chart(fig_imp, use_container_width=True)

    st.markdown("---")

    # LINHA 3: Pareto Equipamentos
    fig_equip = criar_grafico_pareto_limpo(df_calc, "Equipamento/Sistema/Local", "Top Equipamentos Críticos (Pareto 80/20)", top_n=10)
    if fig_equip:
        st.plotly_chart(fig_equip, use_container_width=True)

    st.markdown("---")

    # LINHA 4: Tabelas de Desempenho
    col_t1, col_t2 = st.columns(2)
    
    with col_t1:
        st.markdown("##### 👷 Desempenho por Técnico")
        if "Técnico Responsável" in df_calc.columns and not df_concluidos.empty:
            tec_stats = df_concluidos.groupby("Técnico Responsável").agg(
                Atendidos=("Nº Chamado", "count"),
                Tempo_Medio_Horas=("Tempo_Resolucao_Horas", lambda x: x[x <= 720].mean() if not x[x <= 720].empty else x.median()),
                SLA_OK_Pct=("SLA_Cumprido", lambda x: (x.sum() / len(x)) * 100),
            ).reset_index()
            tec_stats["TMR Formatado"] = tec_stats["Tempo_Medio_Horas"].apply(formatar_tempo_legivel)
            tec_stats["SLA_OK_Pct"] = tec_stats["SLA_OK_Pct"].round(1)
            
            tec_exibicao = tec_stats[["Técnico Responsável", "Atendidos", "TMR Formatado", "SLA_OK_Pct"]].rename(
                columns={"TMR Formatado": "TMR Médio", "SLA_OK_Pct": "SLA OK (%)"}
            )
            st.dataframe(tec_exibicao, use_container_width=True, hide_index=True)

    with col_t2:
        st.markdown("##### 🔍 Alertas de Estouro de SLA")
        
        lista_fora = []
        for _, row in df_calc.iterrows():
            st_str = str(row.get("Status", "Aberto")).strip()
            dt_ab = row.get("dt_abertura")
            dt_conc = row.get("dt_conclusao")
            meta = row.get("Meta_SLA_Horas", 8.0)
            
            if pd.isna(dt_ab):
                continue
                
            if st_str == "Concluído":
                if pd.notna(dt_conc):
                    tempo = (dt_conc - dt_ab).total_seconds() / 3600.0
                    if tempo > meta:
                        lista_fora.append({
                            "Nº Chamado": row.get("Nº Chamado"),
                            "Área": row.get("Área do chamado"),
                            "Equipamento": row.get("Equipamento/Sistema/Local"),
                            "Status": "Concluído",
                            "Tempo": formatar_tempo_legivel(tempo),
                            "Atraso": formatar_tempo_legivel(tempo - meta),
                            "Atraso_Num": tempo - meta,
                            "Técnico": row.get("Técnico Responsável")
                        })
            elif st_str != "Cancelado":
                tempo = (agora_naive - dt_ab).total_seconds() / 3600.0
                if tempo > meta:
                    lista_fora.append({
                        "Nº Chamado": row.get("Nº Chamado"),
                        "Área": row.get("Área do chamado"),
                        "Equipamento": row.get("Equipamento/Sistema/Local"),
                        "Status": st_str,
                        "Tempo": formatar_tempo_legivel(tempo),
                        "Atraso": formatar_tempo_legivel(tempo - meta),
                        "Atraso_Num": tempo - meta,
                        "Técnico": row.get("Técnico Responsável")
                    })
                    
        if lista_fora:
            df_fora_sla = pd.DataFrame(lista_fora).sort_values("Atraso_Num", ascending=False)
            df_display = df_fora_sla[["Nº Chamado", "Área", "Equipamento", "Status", "Tempo", "Atraso", "Técnico"]]
            
            def colorir_status_dark(val):
                v = str(val).strip()
                if v == "Concluído":
                    return "background-color: #065F46; color: #34D399; font-weight: 700;"
                elif v in ["Aberto", "Em análise"]:
                    return "background-color: #78350F; color: #FBBF24; font-weight: 700;"
                else:
                    return "background-color: #075985; color: #38BDF8; font-weight: 700;"
            
            styled_df = df_display.style.map(colorir_status_dark, subset=["Status"])
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
        else:
            st.success("✅ Operação 100% em conformidade: nenhum chamado fora do prazo registrado.")
