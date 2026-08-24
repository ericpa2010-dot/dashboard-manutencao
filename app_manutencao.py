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

# FUNÇÃO DE PARETO TOTALMENTE COMPATÍVEL COM PLOTLY MODERNO
def criar_grafico_pareto(df_input, coluna, titulo):
    if coluna not in df_input.columns or df_input[coluna].dropna().empty:
        return None
    
    counts = df_input[coluna].value_counts().reset_index()
    counts.columns = [coluna, 'Ocorrências']
    counts = counts.sort_values(by='Ocorrências', ascending=False)
    
    counts['Acumulado'] = counts['Ocorrências'].cumsum()
    total = counts['Ocorrências'].sum()
    counts['Percentual_Acumulado'] = (counts['Acumulado'] / total) * 100 if total > 0 else 0
    
    fig = go.Figure()
    
    fig.add_trace(
        go.Bar(
            x=counts[coluna],
            y=counts['Ocorrências'],
            name="Qtd Chamados",
            marker_color="#1D3557",
            text=counts['Ocorrências'],
            textposition="outside",
            textfont=dict(size=14, color="#1D3557")
        )
    )
    
    fig.add_trace(
        go.Scatter(
            x=counts[coluna],
            y=counts['Percentual_Acumulado'],
            name="% Acumulado (Pareto)",
            yaxis="y2",
            mode="lines+markers",
            line=dict(color="#E63946", width=4),
            marker=dict(size=10, color="#E63946")
        )
    )
    
    fig.add_hline(
        y=80,
        yref="y2",
        line_dash="dash",
        line_color="#FFB703",
        line_width=3
    )
    
    fig.update_layout(
        title=dict(text=f"<b>{titulo}</b>", font=dict(size=18, color="#1D3557")),
        xaxis=dict(tickfont=dict(size=12, color="#1D3557"), tickangle=-20),
        yaxis=dict(
            title=dict(text="<b>Número de Chamados</b>", font=dict(size=13, color="#1D3557")),
            tickfont=dict(size=12),
            showgrid=True
        ),
        yaxis2=dict(
            title=dict(text="<b>% Acumulado</b>", font=dict(size=13, color="#1D3557")),
            tickfont=dict(size=12),
            overlaying="y",
            side="right",
            range=[0, 105],
            showgrid=False
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1, font=dict(size=12)),
        margin=dict(l=30, r=30, t=60, b=80),
        height=500,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#F8F9FA"
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

# Trava de Segurança exclusiva para a Gestão Operacional
SENHA_CORRETA = st.secrets.get("SENHA_GESTAO", "manutencao123")

if menu == "Gestão Operacional":
    st.sidebar.markdown("---")
    senha_digitada = st.sidebar.text_input("Chave de Acesso Operacional", type="password")
    
    if senha_digitada != SENHA_CORRETA:
        st.warning("🔒 Área restrita à equipe de manutenção. Insira a chave de acesso na barra lateral para continuar.")
        st.stop()

# MODULO 1: ABERTURA DE CHAMADO (PÚBLICO)
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

# MODULO 2: GESTÃO OPERACIONAL (RESTRITO)
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

                st.success(f"Chamado {num_chamado} atualizado para '{novo_status}'. A planilha formatará a linha e inserirá a data automaticamente.")
                st.cache_resource.clear()

# MODULO 3: DASHBOARD
elif menu == "Dashboard & SLA":
    st.title("📊 Painel Gerencial & Indicadores de SLA")

    if df.empty:
        st.info("Nenhum dado registrado na planilha até o momento.")
        st.stop()

    df_calc = df.copy()
    
    # Tratamento robusto de datas para evitar exceções de tipos mistos
    df_calc["Carimbo de data/hora"] = pd.to_datetime(df_calc["Carimbo de data/hora"].astype(str), errors="coerce", dayfirst=True)
    df_calc["Data de conclusão"] = pd.to_datetime(df_calc["Data de conclusão"].astype(str), errors="coerce", dayfirst=True)
    
    # Remoção de fuso horário para comparação direta
    if hasattr(df_calc["Carimbo de data/hora"].dt, "tz_localize"):
        try:
            df_calc["Carimbo de data/hora"] = df_calc["Carimbo de data/hora"].dt.tz_localize(None)
        except TypeError:
            pass

    if hasattr(df_calc["Data de conclusão"].dt, "tz_localize"):
        try:
            df_calc["Data de conclusão"] = df_calc["Data de conclusão"].dt.tz_localize(None)
        except TypeError:
            pass

    # Corte temporal eliminando registros inconsistentes anteriores a 2024
    df_calc = df_calc[df_calc["Carimbo de data/hora"] >= pd.Timestamp("2024-01-01")]

    df_concluidos = df_calc.dropna(subset=["Data de conclusão"]).copy()
    if not df_concluidos.empty:
        df_concluidos["Tempo_Resolucao_Horas"] = (
            df_concluidos["Data de conclusão"] - df_concluidos["Carimbo de data/hora"]
        ).dt.total_seconds() / 3600.0
        df_concluidos = df_concluidos[df_concluidos["Tempo_Resolucao_Horas"] >= 0]

        METAS_SLA = {"alta": 4.0, "media": 8.0, "baixa": 78.0}

        def get_sla_target(prioridade):
            p = str(prioridade).strip().lower().replace("é", "e")
            for chave, meta in METAS_SLA.items():
                if chave in p:
                    return meta
            return 8.0

        df_concluidos["Meta_SLA_Horas"] = df_concluidos["Prioridade"].apply(get_sla_target)
        df_concluidos["SLA_Cumprido"] = df_concluidos["Tempo_Resolucao_Horas"] <= df_concluidos["Meta_SLA_Horas"]
    else:
        df_concluidos["Tempo_Resolucao_Horas"] = []
        df_concluidos["Meta_SLA_Horas"] = []
        df_concluidos["SLA_Cumprido"] = []

    # LINHA 1: RESUMO EXECUTIVO (KPIs)
    total_chamados = len(df_calc)
    em_aberto = len(df_calc[df_calc["Status"].isin(["Pendente", "Atuando"])])
    total_concluidos = len(df_concluidos)
    taxa_conclusao = (total_concluidos / total_chamados * 100) if total_chamados > 0 else 0.0
    tmr_geral = df_concluidos["Tempo_Resolucao_Horas"].mean() if not df_concluidos.empty else 0.0
    sla_cumprido_pct = (
        (df_concluidos["SLA_Cumprido"].sum() / total_concluidos * 100) if total_concluidos > 0 else 100.0
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total de Chamados", total_chamados)
    c2.metric("Em Aberto", em_aberto)
    c3.metric("Taxa de Resolução", f"{taxa_conclusao:.0f}%")
    c4.metric("Tempo Médio (TMR)", f"{tmr_geral:.1f}h")
    c5.metric("Conformidade SLA Geral", f"{sla_cumprido_pct:.0f}%")

    st.markdown("---")

    # LINHA 2: CARTÕES DE SLA POR PRIORIDADE
    st.subheader("🎯 Cumprimento de SLA por Prioridade")

    def cartao_prioridade(col, nome, meta_horas, cor_borda):
        subset = df_concluidos[
            df_concluidos["Prioridade"].astype(str).str.lower().str.replace("é", "e", regex=False).str.contains(nome.lower())
        ]
        total = len(subset)
        cumpridos = int(subset["SLA_Cumprido"].sum()) if total else 0
        estourados = total - cumpridos
        pct = (cumpridos / total * 100) if total else 100.0
        tmr = subset["Tempo_Resolucao_Horas"].mean() if total else 0.0

        if pct >= 90:
            cor_fundo, cor_texto = "#D4EDDA", "#155724"
        elif pct >= 70:
            cor_fundo, cor_texto = "#FFF3CD", "#856404"
        else:
            cor_fundo, cor_texto = "#F8D7DA", "#721C24"

        with col:
            st.markdown(
                f"""
                <div style="background-color:{cor_fundo}; padding:18px; border-radius:10px; border-left: 8px solid {cor_borda};">
                    <h4 style="color:{cor_texto}; margin:0 0 8px 0;">{nome} <span style="font-weight:normal; font-size:0.8em;">(meta: {meta_horas:.0f}h)</span></h4>
                    <h1 style="color:{cor_texto}; margin:0;">{pct:.0f}%</h1>
                    <p style="color:{cor_texto}; margin:4px 0 0 0;">dentro do prazo</p>
                    <hr style="border-color:{cor_texto}; opacity:0.3; margin:10px 0;">
                    <p style="color:{cor_texto}; margin:0; font-size:0.9em;">
                        ✅ {cumpridos} no prazo &nbsp;·&nbsp; 🔴 {estourados} estourados<br>
                        ⏱️ Tempo Médio (TMR): {tmr:.1f}h
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    col_alta, col_media, col_baixa = st.columns(3)
    cartao_prioridade(col_alta, "Alta", 4.0, "#DC3545")
    cartao_prioridade(col_media, "Média", 8.0, "#FFC107")
    cartao_prioridade(col_baixa, "Baixa", 78.0, "#28A745")

    st.markdown("---")

    # LINHA 3: PARETO DE EQUIPAMENTOS
    fig_equip = criar_grafico_pareto(df_calc, "Equipamento/Sistema/Local", "Diagrama de Pareto: Equipamentos Críticos (80/20)")
    if fig_equip:
        st.plotly_chart(fig_equip, use_container_width=True)

    st.markdown("---")

    # LINHA 4: PARETO DE SETORES E TENDÊNCIA TEMPORAL
    col_p1, col_p2 = st.columns(2)
    
    with col_p1:
        fig_setor = criar_grafico_pareto(df_calc, "Área do chamado", "Pareto por Setor Solicitante")
        if fig_setor:
            st.plotly_chart(fig_setor, use_container_width=True)

    with col_p2:
        df_tempo = df_calc.dropna(subset=["Carimbo de data/hora"]).copy()
        if not df_tempo.empty:
            df_tempo["Data_Dia"] = df_tempo["Carimbo de data/hora"].dt.date
            evolucao = df_tempo.groupby("Data_Dia").size().reset_index(name="Volume")
            
            fig_evol = px.line(evolucao, x="Data_Dia", y="Volume", markers=True)
            fig_evol.update_traces(line_color="#2A9D8F", line_width=4, marker=dict(size=8, color="#E76F51"))
            fig_evol.update_layout(
                height=500,
                title=dict(text="<b>Evolução Diária (2024 - Atual)</b>", font=dict(size=18, color="#1D3557")),
                xaxis=dict(title=dict(text="<b>Data</b>", font=dict(size=12)), tickfont=dict(size=12), showgrid=True),
                yaxis=dict(title=dict(text="<b>Qtd Chamados</b>", font=dict(size=12)), tickfont=dict(size=12), showgrid=True),
                margin=dict(l=30, r=30, t=60, b=40),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="#F8F9FA"
            )
            st.plotly_chart(fig_evol, use_container_width=True)

    st.markdown("---")

    # LINHA 5: TABELAS DE DESEMPENHO E ESTOURO DE SLA
    col_t1, col_t2 = st.columns(2)
    
    with col_t1:
        st.markdown("### 👷 Desempenho Técnico")
        if "Técnico Responsável" in df_calc.columns and not df_concluidos.empty:
            tec_stats = df_concluidos.groupby("Técnico Responsável").agg(
                Atendidos=("Nº Chamado", "count"),
                Tempo_Medio_Horas=("Tempo_Resolucao_Horas", "mean"),
                SLA_OK_Pct=("SLA_Cumprido", lambda x: (x.sum() / len(x)) * 100),
            ).reset_index()
            tec_stats["Tempo_Medio_Horas"] = tec_stats["Tempo_Medio_Horas"].round(1)
            tec_stats["SLA_OK_Pct"] = tec_stats["SLA_OK_Pct"].round(1)
            tec_stats.rename(columns={"Tempo_Medio_Horas": "TMR Médio (h)", "SLA_OK_Pct": "SLA OK (%)"}, inplace=True)
            st.dataframe(tec_stats, use_container_width=True, hide_index=True)
        else:
            st.caption("Aguardando finalização de chamados para consolidação de métricas por técnico.")

    with col_t2:
        st.markdown("### 🔍 Chamados Fora do SLA")
        if not df_concluidos.empty:
            fora_sla = df_concluidos[df_concluidos["SLA_Cumprido"] == False].copy()
            if not fora_sla.empty:
                fora_sla["Atraso_Horas"] = (fora_sla["Tempo_Resolucao_Horas"] - fora_sla["Meta_SLA_Horas"]).round(1)
                fora_sla = fora_sla.sort_values("Atraso_Horas", ascending=False)
                colunas_sla = [
                    c for c in [
                        "Nº Chamado", "Área do chamado", "Equipamento/Sistema/Local",
                        "Prioridade", "Tempo_Resolucao_Horas", "Meta_SLA_Horas",
                        "Atraso_Horas", "Técnico Responsável",
                    ] if c in fora_sla.columns
                ]
                st.dataframe(fora_sla[colunas_sla], use_container_width=True, hide_index=True)
            else:
                st.success("✅ Operação 100% em conformidade: nenhum chamado fora do prazo registrado.")
        else:
            st.info("Nenhum chamado concluído ainda para avaliar.")
