import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz
import plotly.graph_objects as go
import plotly.express as px

# Configuração da página
st.set_page_config(page_title="Gestão de Manutenção", page_icon="🛠️", layout="wide")

# CSS: Design System Minimalista Corporativo
st.markdown("""
    <style>
    /* Oculta elementos nativos */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}

    /* Fundo da aplicação e tipografia */
    .stApp {
        background-color: #F8FAFC;
        color: #0F172A;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }

    /* Cartões de métricas customizados */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        padding: 16px 20px;
        border-radius: 12px;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.02);
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.85rem !important;
        color: #64748B !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.025em;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        color: #0F172A !important;
        font-weight: 700 !important;
    }

    /* Ajuste de abas e divisores */
    hr {
        border-color: #E2E8F0 !important;
        margin: 1.5rem 0 !important;
    }

    /* Tabelas limpas */
    div[data-testid="stDataFrame"] {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 8px;
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
    return gspread.authorize(creds)

def load_data():
    client = get_gspread_client()
    sheet = client.open_by_url(st.secrets["spreadsheet"]["url"]).worksheet("CHAMADOS")
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    return sheet, df

# Formatador de tempo amigável
def formatar_tempo_legivel(horas):
    if pd.isna(horas) or horas is None or horas <= 0:
        return "0h"
    if horas < 24:
        return f"{horas:.1f}h"
    dias = int(horas // 24)
    hrs_restantes = int(horas % 24)
    return f"{dias}d {hrs_restantes}h"

# Gerador de Pareto Minimalista
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
            marker_color="#334155",
            text=counts['Ocorrências'],
            textposition="outside",
            textfont=dict(size=12, color="#0F172A")
        )
    )
    
    fig.add_trace(
        go.Scatter(
            x=counts[coluna],
            y=counts['Percentual_Acumulado'],
            name="% Acumulado",
            yaxis="y2",
            mode="lines+markers",
            line=dict(color="#0284C7", width=2.5),
            marker=dict(size=7, color="#0284C7")
        )
    )
    
    fig.add_hline(
        y=80,
        yref="y2",
        line_dash="dash",
        line_color="#E11D48",
        line_width=1.5
    )
    
    fig.update_layout(
        template="plotly_white",
        title=dict(text=f"<b>{titulo}</b>", font=dict(size=15, color="#0F172A")),
        xaxis=dict(tickfont=dict(size=11, color="#475569"), tickangle=-15, showgrid=False),
        yaxis=dict(
            title=dict(text="<b>Qtd Chamados</b>", font=dict(size=12, color="#475569")),
            tickfont=dict(size=11, color="#475569"),
            gridcolor="#F1F5F9",
            showgrid=True
        ),
        yaxis2=dict(
            title=dict(text="<b>% Acumulado</b>", font=dict(size=12, color="#475569")),
            tickfont=dict(size=11, color="#475569"),
            overlaying="y",
            side="right",
            range=[0, 105],
            showgrid=False
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1, font=dict(size=11)),
        margin=dict(l=20, r=20, t=50, b=50),
        height=420,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    
    return fig

try:
    sheet, df = load_data()
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

# MODULO 1: ABERTURA DE CHAMADO
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
                agora = datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M:%S")
                proximo_num = len(df) + 1

                nova_linha = [
                    proximo_num, agora, email, nome_setor, area, equipamento,
                    problema, observado, testado, impacto, prioridade,
                    info_adicional, "Pendente", "", "", ""
                ]

                sheet.append_row(nova_linha)
                st.success(f"Chamado Nº {proximo_num} registrado com sucesso!")
                st.cache_resource.clear()

# MODULO 2: GESTÃO OPERACIONAL
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
                st.success(f"Chamado {num_chamado} atualizado com sucesso!")
                st.cache_resource.clear()

# MODULO 3: DASHBOARD MINIMALISTA
elif menu == "Dashboard & SLA":
    st.title("📊 Painel Gerencial & Indicadores de SLA")

    if df.empty:
        st.info("Nenhum dado registrado na planilha até o momento.")
        st.stop()

    fuso_br = pytz.timezone("America/Sao_Paulo")
    agora_br = datetime.now(fuso_br)

    total_chamados = len(df)
    em_aberto = len(df[df["Status"].astype(str).str.strip().isin(["Pendente", "Atuando"])])

    df_calc = df.copy()
    
    df_calc["dt_abertura"] = pd.to_datetime(df_calc["Carimbo de data/hora"].astype(str), errors="coerce", dayfirst=True)
    df_calc["dt_conclusao"] = pd.to_datetime(df_calc["Data de conclusão"].astype(str), errors="coerce", dayfirst=True)

    df_temp_validos = df_calc.dropna(subset=["dt_abertura"]).copy()
    
    agora_naive = agora_br.replace(tzinfo=None)
    inicio_hoje = agora_naive.replace(hour=0, minute=0, second=0, microsecond=0)
    inicio_semana = inicio_hoje - pd.Timedelta(days=agora_naive.weekday())
    inicio_mes = agora_naive.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    inicio_ano = agora_naive.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    qtd_hoje = len(df_temp_validos[df_temp_validos["dt_abertura"] >= inicio_hoje])
    qtd_semana = len(df_temp_validos[df_temp_validos["dt_abertura"] >= inicio_semana])
    qtd_mes = len(df_temp_validos[df_temp_validos["dt_abertura"] >= inicio_mes])
    qtd_ano = len(df_temp_validos[df_temp_validos["dt_abertura"] >= inicio_ano])

    METAS_SLA = {"alta": 4.0, "media": 8.0, "baixa": 78.0}

    def get_sla_target(prioridade):
        p = str(prioridade).strip().lower().replace("é", "e")
        for chave, meta in METAS_SLA.items():
            if chave in p:
                return meta
        return 8.0

    df_calc["Meta_SLA_Horas"] = df_calc["Prioridade"].apply(get_sla_target)

    df_concluidos = df_calc.dropna(subset=["dt_conclusao", "dt_abertura"]).copy()
    if not df_concluidos.empty:
        df_concluidos["Tempo_Resolucao_Horas"] = (
            df_concluidos["dt_conclusao"] - df_concluidos["dt_abertura"]
        ).dt.total_seconds() / 3600.0
        df_concluidos = df_concluidos[df_concluidos["Tempo_Resolucao_Horas"] >= 0]
        df_concluidos["SLA_Cumprido"] = df_concluidos["Tempo_Resolucao_Horas"] <= df_concluidos["Meta_SLA_Horas"]
        
        df_tmr_operacional = df_concluidos[df_concluidos["Tempo_Resolucao_Horas"] <= 720]
        if not df_tmr_operacional.empty:
            tmr_geral_num = df_tmr_operacional["Tempo_Resolucao_Horas"].mean()
        else:
            tmr_geral_num = df_concluidos["Tempo_Resolucao_Horas"].median()
    else:
        df_concluidos["Tempo_Resolucao_Horas"] = []
        df_concluidos["SLA_Cumprido"] = []
        tmr_geral_num = 0.0

    total_concluidos = len(df_concluidos)
    taxa_conclusao = (total_concluidos / total_chamados * 100) if total_chamados > 0 else 0.0
    sla_cumprido_pct = (
        (df_concluidos["SLA_Cumprido"].sum() / total_concluidos * 100) if total_concluidos > 0 else 100.0
    )

    # LINHA 1: KPIs Globais
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Chamados", total_chamados)
    c2.metric("Em Aberto", em_aberto)
    c3.metric("Taxa Resolução", f"{taxa_conclusao:.0f}%")
    c4.metric("Tempo Médio (TMR)", formatar_tempo_legivel(tmr_geral_num))
    c5.metric("Conformidade SLA", f"{sla_cumprido_pct:.0f}%")

    st.markdown("---")

    # LINHA 2: Volumetria por Período
    st.markdown("##### 📅 Volumetria por Período de Abertura")
    ct1, ct2, ct3, ct4 = st.columns(4)
    ct1.metric("Hoje", qtd_hoje)
    ct2.metric("Esta Semana", qtd_semana)
    ct3.metric("Este Mês", qtd_mes)
    ct4.metric("Este Ano", qtd_ano)

    st.markdown("---")

    # LINHA 3: Cartões de SLA por Prioridade
    st.markdown("##### 🎯 Cumprimento de SLA por Prioridade")

    def cartao_prioridade_clean(col, nome, meta_horas):
        subset = df_concluidos[
            df_concluidos["Prioridade"].astype(str).str.lower().str.replace("é", "e", regex=False).str.contains(nome.lower())
        ]
        total = len(subset)
        cumpridos = int(subset["SLA_Cumprido"].sum()) if total else 0
        estourados = total - cumpridos
        pct = (cumpridos / total * 100) if total else 100.0
        
        subset_tmr = subset[subset["Tempo_Resolucao_Horas"] <= 720]
        tmr_num = subset_tmr["Tempo_Resolucao_Horas"].mean() if not subset_tmr.empty else (subset["Tempo_Resolucao_Horas"].median() if total else 0.0)

        # Paleta limpa com fundos suaves e bordas elegantes
        if pct >= 90:
            bg_card, border_card, text_color = "#F0FDF4", "#BBF7D0", "#166534"
        elif pct >= 70:
            bg_card, border_card, text_color = "#FEFCE8", "#FEF08A", "#854D0E"
        else:
            bg_card, border_card, text_color = "#FEF2F2", "#FECACA", "#991B1B"

        with col:
            st.markdown(
                f"""
                <div style="background-color:{bg_card}; border:1px solid {border_card}; padding:20px; border-radius:12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:700; color:{text_color}; font-size:1rem;">{nome}</span>
                        <span style="font-size:0.8rem; color:{text_color}; opacity:0.8;">Meta: {formatar_tempo_legivel(meta_horas)}</span>
                    </div>
                    <div style="font-size:2.2rem; font-weight:800; color:{text_color}; margin:12px 0 4px 0;">{pct:.0f}%</div>
                    <div style="font-size:0.85rem; color:{text_color}; font-weight:500;">Conformidade operacional</div>
                    <div style="margin-top:14px; pt-12px; border-top:1px solid {border_card}; font-size:0.8rem; color:{text_color}; display:flex; justify-content:space-between;">
                        <span>✅ {cumpridos} OK &nbsp;·&nbsp; 🔴 {estourados} Fora</span>
                        <span>TMR: <b>{formatar_tempo_legivel(tmr_num)}</b></span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    col_alta, col_media, col_baixa = st.columns(3)
    cartao_prioridade_clean(col_alta, "Alta", 4.0)
    cartao_prioridade_clean(col_media, "Média", 8.0)
    cartao_prioridade_clean(col_baixa, "Baixa", 78.0)

    st.markdown("---")

    # LINHA 4: Pareto Equipamentos
    fig_equip = criar_grafico_pareto_limpo(df_calc, "Equipamento/Sistema/Local", "Top Equipamentos Críticos (Pareto 80/20)", top_n=10)
    if fig_equip:
        st.plotly_chart(fig_equip, use_container_width=True)

    st.markdown("---")

    # LINHA 5: Pareto Setores e Evolução Mensal
    col_p1, col_p2 = st.columns(2)
    
    with col_p1:
        fig_setor = criar_grafico_pareto_limpo(df_calc, "Área do chamado", "Top Setores Solicitantes", top_n=8)
        if fig_setor:
            st.plotly_chart(fig_setor, use_container_width=True)

    with col_p2:
        df_tempo = df_calc.dropna(subset=["dt_abertura"]).copy()
        df_tempo = df_tempo[df_tempo["dt_abertura"] >= pd.Timestamp("2024-01-01")]
        
        if not df_tempo.empty:
            df_tempo["Ano_Mês"] = df_tempo["dt_abertura"].dt.strftime("%Y-%m")
            evolucao = df_tempo.groupby("Ano_Mês").size().reset_index(name="Volume")
            evolucao = evolucao.sort_values("Ano_Mês")
            
            fig_evol = px.bar(evolucao, x="Ano_Mês", y="Volume", text="Volume", title="<b>Evolução Mensal de Chamados (2024+)</b>")
            fig_evol.update_traces(marker_color="#0284C7", textposition="outside", textfont=dict(size=11, color="#0F172A"))
            fig_evol.update_layout(
                template="plotly_white",
                height=420,
                title=dict(text="<b>Evolução Mensal de Chamados (2024+)</b>", font=dict(size=15, color="#0F172A")),
                xaxis=dict(title=dict(text="<b>Mês/Ano</b>", font=dict(size=12, color="#475569")), tickfont=dict(size=11, color="#475569"), showgrid=False),
                yaxis=dict(title=dict(text="<b>Qtd Chamados</b>", font=dict(size=12, color="#475569")), tickfont=dict(size=11, color="#475569"), gridcolor="#F1F5F9", showgrid=True),
                margin=dict(l=20, r=20, t=50, b=50),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_evol, use_container_width=True)

    st.markdown("---")

    # LINHA 6: Tabelas
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
        else:
            st.caption("Aguardando finalização de chamados para consolidação de métricas.")

    with col_t2:
        st.markdown("##### 🔍 Chamados Fora do SLA (Ativos e Concluídos)")
        
        lista_fora = []
        for _, row in df_calc.iterrows():
            st_str = str(row.get("Status", "Pendente")).strip()
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
                            "Prioridade": row.get("Prioridade"),
                            "Status": "Concluído",
                            "Tempo Decorrido": formatar_tempo_legivel(tempo),
                            "Atraso": formatar_tempo_legivel(tempo - meta),
                            "Atraso_Horas_Num": tempo - meta,
                            "Técnico": row.get("Técnico Responsável")
                        })
            else:
                tempo = (agora_naive - dt_ab).total_seconds() / 3600.0
                if tempo > meta:
                    lista_fora.append({
                        "Nº Chamado": row.get("Nº Chamado"),
                        "Área": row.get("Área do chamado"),
                        "Equipamento": row.get("Equipamento/Sistema/Local"),
                        "Prioridade": row.get("Prioridade"),
                        "Status": st_str if st_str in ["Pendente", "Atuando"] else "Pendente",
                        "Tempo Decorrido": formatar_tempo_legivel(tempo),
                        "Atraso": formatar_tempo_legivel(tempo - meta),
                        "Atraso_Horas_Num": tempo - meta,
                        "Técnico": row.get("Técnico Responsável")
                    })
                    
        if lista_fora:
            df_fora_sla = pd.DataFrame(lista_fora).sort_values("Atraso_Horas_Num", ascending=False)
            df_display = df_fora_sla[["Nº Chamado", "Área", "Equipamento", "Prioridade", "Status", "Tempo Decorrido", "Atraso", "Técnico"]]
            
            # Estilo discreto e de alto contraste para a tabela
            def colorir_status_clean(val):
                v = str(val).strip()
                if v == "Concluído":
                    return "background-color: #DCFCE7; color: #15803D; font-weight: 600;"
                elif v == "Pendente":
                    return "background-color: #FEE2E2; color: #B91C1C; font-weight: 600;"
                elif v == "Atuando":
                    return "background-color: #E0F2FE; color: #0369A1; font-weight: 600;"
                return ""
            
            styled_df = df_display.style.map(colorir_status_clean, subset=["Status"])
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
        else:
            st.success("✅ Operação 100% em conformidade: nenhum chamado fora do prazo registrado.")
