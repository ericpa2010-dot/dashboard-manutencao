import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz
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

   /* Abas Nativas Responsivas */
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

def formatar_tempo_legivel(horas):
    if pd.isna(horas) or horas is None or horas <= 0:
        return "0h"
    dias = int(horas // 24)
    hrs_restantes = round(horas % 24, 1)
    if hrs_restantes == int(hrs_restantes):
        hrs_restantes = int(hrs_restantes)
    if dias > 0:
        return f"{dias}d {hrs_restantes}h"
    return f"{horas:.1f}h" if isinstance(horas, float) and horas % 1 != 0 else f"{int(horas)}h"

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

tab_abertura, tab_dash, tab_gestao = st.tabs(["📌 Abrir Chamado", "📊 Dashboard & SLA", "⚙️ Gestão Operacional"])

# ABA 1: ABERTURA DE CHAMADO
with tab_abertura:
    st.title("📌 Abertura de Chamado")
    
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
                    proximo_num, agora, email, nome_setor, area, equipamento,
                    problema, observado, testado, impacto, prioridade,
                    info_adicional, "Pendente", "", "", ""
                ]

                sheet.append_row(nova_linha)
                st.success(f"Chamado Nº {proximo_num} registrado com sucesso!")
                st.cache_resource.clear()

# ABA 2: DASHBOARD
with tab_dash:
    st.title("📊 Painel Gerencial & SLA")

    if df.empty:
        st.info("Nenhum dado registrado na planilha até o momento.")
    else:
        fuso_br = pytz.timezone("America/Sao_Paulo")
        agora_br = datetime.now(fuso_br)

        df_calc = df.copy()
        
        # Tratamento de Datas sem conflito de parametros no Pandas 2.x/Python 3.14
        df_calc["dt_abertura"] = pd.to_datetime(df_calc["Carimbo de data/hora"].astype(str).str.strip(), errors="coerce", dayfirst=True)
        df_calc["dt_conclusao"] = pd.to_datetime(df_calc["Data de conclusão"].astype(str).str.strip(), errors="coerce", dayfirst=True)

        df_calc["Status_Clean"] = df_calc["Status"].astype(str).str.strip().str.capitalize()
        
        status_abertos = ["Pendente", "Atuando", "Aberto", "Em andamento"]
        mask_abertos = df_calc["Status_Clean"].isin(status_abertos)
        
        total_chamados = len(df_calc)
        em_aberto = len(df_calc[mask_abertos])

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

            df_concluidos["Meta_SLA_Horas"] = df_concluidos["Prioridade"].apply(get_sla_target)
            df_concluidos["SLA_Cumprido"] = df_concluidos["Tempo_Resolucao_Horas"] <= df_concluidos["Meta_SLA_Horas"]

            df_tmr_operacional = df_concluidos[df_concluidos["Tempo_Resolucao_Horas"] <= 720]
            if not df_tmr_operacional.empty:
                tmr_geral_num = df_tmr_operacional["Tempo_Resolucao_Horas"].median()
            else:
                tmr_geral_num = df_concluidos["Tempo_Resolucao_Horas"].median()
        else:
            df_concluidos["Tempo_Resolucao_Horas"] = []
            df_concluidos["Meta_SLA_Horas"] = []
            df_concluidos["SLA_Cumprido"] = []
            tmr_geral_num = 0.0

        total_concluidos = len(df_concluidos)
        taxa_conclusao = (total_concluidos / total_chamados * 100) if total_chamados > 0 else 0.0
        sla_cumprido_pct = (
            (df_concluidos["SLA_Cumprido"].sum() / total_concluidos * 100) if total_concluidos > 0 else 100.0
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Chamados", total_chamados)
        c2.metric("Em Aberto", em_aberto)
        c3.metric("Taxa Resolução", f"{taxa_conclusao:.0f}%")

        c4, c5 = st.columns(2)
        c4.metric("Tempo Médio (TMR Mediano)", formatar_tempo_legivel(tmr_geral_num))
        c5.metric("Conformidade SLA", f"{sla_cumprido_pct:.0f}%")

        st.markdown("---")

        st.markdown("##### 📅 Volumetria por Período")
        ct1, ct2, ct3, ct4 = st.columns(4)
        ct1.metric("Hoje", qtd_hoje)
        ct2.metric("Semana", qtd_semana)
        ct3.metric("Mês", qtd_mes)
        ct4.metric("Ano", qtd_ano)

        st.markdown("---")

        st.markdown("##### 🎯 SLA por Prioridade")

        def cartao_prioridade_neon(col, nome, meta_horas):
            subset = df_concluidos[
                df_concluidos["Prioridade"].astype(str).str.lower().str.replace("é", "e", regex=False).str.contains(nome.lower())
            ]
            total = len(subset)
            cumpridos = len(subset[subset["SLA_Cumprido"] == True])
            estourados = total - cumpridos
            pct = (cumpridos / total * 100) if total > 0 else 100.0

            tmr_num = subset["Tempo_Resolucao_Horas"].median() if total > 0 else 0.0

            if pct >= 90:
                border_card, text_glow = "#34D399", "#34D399"
            elif pct >= 70:
                border_card, text_glow = "#FBBF24", "#FBBF24"
            else:
                border_card, text_glow = "#F87171", "#F87171"

            with col:
                st.markdown(
                    f"""
                    <div style="background-color:#1E293B; border:1px solid {border_card}; padding:15px; border-radius:12px; margin-bottom:10px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-weight:700; color:#F8FAFC; font-size:0.9rem;">{nome}</span>
                            <span style="font-size:0.75rem; color:#94A3B8;">Meta: {formatar_tempo_legivel(meta_horas)}</span>
                        </div>
                        <div style="font-size:1.8rem; font-weight:800; color:{text_glow}; margin:8px 0 2px 0;">{pct:.0f}%</div>
                        <div style="font-size:0.75rem; color:#CBD5E1;">Conformidade</div>
                        <div style="margin-top:10px; padding-top:8px; border-top:1px solid #334155; font-size:0.75rem; color:#94A3B8; display:flex; justify-content:space-between;">
                            <span>✅ {cumpridos} OK · 🔴 {estourados} Fora</span>
                            <span>TMR: <b style="color:#F8FAFC;">{formatar_tempo_legivel(tmr_num)}</b></span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        col_alta, col_media, col_baixa = st.columns(3)
        cartao_prioridade_neon(col_alta, "Alta", 4.0)
        cartao_prioridade_neon(col_media, "Média", 8.0)
        cartao_prioridade_neon(col_baixa, "Baixa", 78.0)

        st.markdown("---")

        fig_equip = criar_grafico_pareto_limpo(df_calc, "Equipamento/Sistema/Local", "Top Equipamentos Críticos", top_n=10)
        if fig_equip:
            st.plotly_chart(fig_equip, use_container_width=True)

        st.markdown("---")

        fig_setor = criar_grafico_pareto_limpo(df_calc, "Área do chamado", "Top Setores Solicitantes", top_n=10)
        if fig_setor:
            st.plotly_chart(fig_setor, use_container_width=True)

        st.markdown("---")

        col_t1, col_t2 = st.columns(2)

        with col_t1:
            st.markdown("##### 👷 Desempenho por Técnico")
            if "Técnico Responsável" in df_calc.columns and not df_concluidos.empty:
                tec_stats = df_concluidos.groupby("Técnico Responsável").agg(
                    Atendidos=("Nº Chamado", "count"),
                    TMR_Medio=("Tempo_Resolucao_Horas", "median"),
                    SLA_OK=("SLA_Cumprido", "sum")
                ).reset_index()
                tec_stats["SLA (%)"] = (tec_stats["SLA_OK"] / tec_stats["Atendidos"] * 100).round(1)
                tec_stats["TMR Médio"] = tec_stats["TMR_Medio"].apply(formatar_tempo_legivel)
                tec_exibicao = tec_stats[["Técnico Responsável", "Atendidos", "TMR Médio", "SLA (%)"]].sort_values("Atendidos", ascending=False)
                st.dataframe(tec_exibicao, use_container_width=True, hide_index=True)
            else:
                st.caption("Aguardando finalização de chamados para consolidação de métricas.")

        with col_t2:
            st.markdown("##### 🔍 Chamados Ativos e Atrasados (Fora do SLA)")
            lista_fora = []
            for _, row in df_calc.iterrows():
                st_str = str(row.get("Status_Clean", "Pendente"))
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
                            "Status": st_str,
                            "Tempo Decorrido": formatar_tempo_legivel(tempo),
                            "Atraso": formatar_tempo_legivel(tempo - meta),
                            "Atraso_Horas_Num": tempo - meta,
                            "Técnico": row.get("Técnico Responsável")
                        })
                        
            if lista_fora:
                df_fora_sla = pd.DataFrame(lista_fora).sort_values("Atraso_Horas_Num", ascending=False)
                df_display = df_fora_sla[["Nº Chamado", "Área", "Equipamento", "Prioridade", "Status", "Tempo Decorrido", "Atraso", "Técnico"]]
                
                def colorir_status_dark(val):
                    v = str(val).strip()
                    if v == "Concluído":
                        return "background-color: #065F46; color: #34D399; font-weight: 700;"
                    elif v in ["Pendente", "Aberto"]:
                        return "background-color: #78350F; color: #FBBF24; font-weight: 700;"
                    elif v in ["Atuando", "Em andamento"]:
                        return "background-color: #075985; color: #38BDF8; font-weight: 700;"
                    return ""
                
                styled_df = df_display.style.map(colorir_status_dark, subset=["Status"])
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
            else:
                st.success("✅ Operação em conformidade: nenhum chamado fora do prazo registrado.")

# ABA 3: GESTÃO OPERACIONAL (RESTRITA)
with tab_gestao:
    st.title("⚙️ Gestão Operacional de Chamados")
    
    senha_digitada = st.text_input("Chave de Acesso Operacional", type="password", key="pwd_gestao")
    
    if senha_digitada != SENHA_CORRETA:
        st.warning("🔒 Digite a chave de acesso para editar status ou atribuições.")
    else:
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

            st.info(f"Chamado {num_chamado}: {linha_atual.get('Equipamento/Sistema/Local', '')}")

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

                    st.success(f"Chamado {num_chamado} atualizado!")
                    st.cache_resource.clear()