import unicodedata
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Painel de Manutenção", layout="wide", initial_sidebar_state="expanded")

# CSS Customizado - Dark Premium
st.markdown("""
<style>
    .stApp {
        background-color: #0F172A;
        color: #F8FAFC;
    }
    h1 {
        color: #F8FAFC !important;
        font-weight: 800 !important;
        letter-spacing: -0.5px !important;
        padding-bottom: 15px !important;
    }
    h3 {
        color: #94A3B8 !important;
        font-weight: 600 !important;
        font-size: 1.1rem !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 20px !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 2.2rem !important;
        font-weight: 800 !important;
        color: #38BDF8 !important;
    }
    div[data-testid="stMetric"] {
        background: #1E293B;
        border: 1px solid #334155;
        padding: 16px 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    }
    .card-status {
        padding: 20px;
        border-radius: 12px;
        border-left: 6px solid;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.25);
    }
    .card-status h4 {
        margin: 0;
        font-size: 0.9rem;
        font-weight: 700;
        letter-spacing: 1px;
    }
    .card-status h2 {
        margin: 8px 0 0 0;
        font-size: 2.5rem;
        font-weight: 800;
    }
    .card-sla {
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #334155;
        background-color: #1E293B;
        margin-bottom: 10px;
    }
    .stDataFrame {
        border: 1px solid #334155;
        border-radius: 12px;
        overflow: hidden;
    }
    section[data-testid="stSidebar"] {
        background-color: #1E293B !important;
        border-right: 1px solid #334155;
    }
</style>
""", unsafe_allow_html=True)

URL_BASE = (
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vRgqjurSWlFiWjsy3V2cpz9vju85"
    "d1-mGNB0wIucZm9Rx_Af0cweCNbXvlEIblD9TlY2bmiYVY5T4N0/pub"
    "?gid=1559301826&single=true&output=csv"
)

INTERVALO_ATUALIZACAO_SEG = 60

SETORES_PADRAO = [
    "Manutenção", "Expedição", "Estoque", "Montagem",
    "Sala de Reunião", "Atendimento", "Sala de Treinamento",
    "Diretoria", "TI", "Antireflexo",
]

PRIORIDADE_SLA_HORAS = {
    "urgente": 2,
    "alta": 2,
    "medio": 6,
    "media": 6,
    "baixo": 24,
    "baixa": 24,
}
SLA_PADRAO_HORAS = 24
LIMIAR_ATENCAO = 0.7

SETORES_CRITICOS = {"Produção", "Montagem", "Expedição", "Antireflexo"}
MAQUINAS_CRITICAS = {"FORNO 1", "LINHA 3", "MÁQUINA X"}

def normalizar_texto(valor: str) -> str:
    if not isinstance(valor, str):
        return ""
    return (
        unicodedata.normalize("NFKD", valor)
        .encode("ascii", "ignore")
        .decode("ascii")
        .strip()
        .lower()
    )

def identificar_colunas(df: pd.DataFrame) -> dict:
    mapeamento = {
        "abertura": ["Carimbo", "Abertura"],
        "conclusao": ["conclusao", "conclusão"],
        "status": ["Status", "Situação", "Situacao"],
        "setor": ["Setor", "Nome e Setor"],
        "maquina": ["Máquina", "Equipamento"],
        "prioridade": ["Prioridade"],
        "chamado": ["N°", "Chamado", "N"],
    }
    colunas = {}
    avisos = []
    for chave, termos in mapeamento.items():
        encontrada = next(
            (c for c in df.columns if any(normalizar_texto(t) in normalizar_texto(c) for t in termos)),
            None,
        )
        colunas[chave] = encontrada
        if encontrada is None and chave in ("abertura", "setor", "maquina"):
            avisos.append(chave)

    if colunas.get("chamado") is None:
        colunas["chamado"] = df.columns[0]

    colunas["_avisos"] = avisos
    return colunas

def classificar_status(df: pd.DataFrame) -> pd.Series:
    tem_conclusao = pd.notnull(df["Data_Conclusao_dt"])
    status_norm = df["Status_Origem"].astype(str).map(normalizar_texto)
    atuando = status_norm.str.contains("atu", na=False)

    status_final = pd.Series("Pendente", index=df.index)
    status_final = status_final.mask((~tem_conclusao) & atuando, "Atuando")
    status_final = status_final.mask(tem_conclusao, "Concluído")
    return status_final

def obter_multiplicador_critico(setor: str, maquina: str) -> int:
    crit_setores = {normalizar_texto(x) for x in SETORES_CRITICOS}
    crit_maquinas = {normalizar_texto(x) for x in MAQUINAS_CRITICAS}
    if normalizar_texto(setor) in crit_setores or normalizar_texto(maquina) in crit_maquinas:
        return 2
    return 1

def obter_sla_horas(prioridade: str) -> float:
    return PRIORIDADE_SLA_HORAS.get(normalizar_texto(prioridade), SLA_PADRAO_HORAS)

def formatar_horas(h: float) -> str:
    if pd.isna(h):
        return "-"
    return f"{h:.1f}h" if h < 24 else f"{h / 24:.1f}d ({h:.0f}h)"

def classificar_urgencia(row) -> tuple:
    status = row["Status_Final"]
    sla = obter_sla_horas(row["Prioridade"])

    if status == "Concluído":
        return ("OK", "#1E293B", "#10B981", "#10B981", sla)

    mult = obter_multiplicador_critico(row["Setor"], row["Máquina"])
    sla_efetivo = sla / mult
    horas = row["Horas_em_aberto"]

    if horas > sla_efetivo:
        return ("ESTOUROU SLA", "#451A03", "#EF4444", "#FCA5A5", sla)
    if horas > sla_efetivo * LIMIAR_ATENCAO:
        return ("QUASE ESTOURANDO", "#451A03", "#F59E0B", "#FCD34D", sla)

    cor = ("#1E293B", "#F97316", "#FFEDD5") if status == "Pendente" else ("#1E293B", "#EF4444", "#FECACA")
    return ("DENTRO DO PRAZO", *cor, sla)

@st.cache_data(ttl=INTERVALO_ATUALIZACAO_SEG, show_spinner=False)
def carregar_dados() -> pd.DataFrame:
    df = pd.read_csv(URL_BASE)
    df.columns = df.columns.astype(str).str.strip()
    col = identificar_colunas(df)

    df["Data_Abertura_dt"] = (
        pd.to_datetime(df[col["abertura"]], dayfirst=True, errors="coerce")
        if col["abertura"] else pd.NaT
    )
    df = df.dropna(subset=["Data_Abertura_dt"])

    df["Data_Conclusao_dt"] = (
        pd.to_datetime(df[col["conclusao"]], dayfirst=True, errors="coerce")
        if col["conclusao"] else pd.NaT
    )

    df["Status_Origem"] = df[col["status"]] if col["status"] else ""
    df["Setor"] = (df[col["setor"]].astype(str) if col["setor"] else "").fillna("")
    df["Máquina"] = (df[col["maquina"]].astype(str) if col["maquina"] else "").fillna("")
    df["Prioridade"] = (df[col["prioridade"]].astype(str) if col["prioridade"] else "").fillna("")
    df["Chamado"] = df[col["chamado"]]

    df["Status_Final"] = classificar_status(df)
    df["Data Abertura"] = df["Data_Abertura_dt"].dt.strftime("%d/%m/%Y %H:%M")
    df["Data Conclusão"] = df["Data_Conclusao_dt"].dt.strftime("%d/%m/%Y").fillna("-")

    agora = pd.Timestamp.now()
    df["Horas_em_aberto"] = (agora - df["Data_Abertura_dt"]).dt.total_seconds() / 3600.0
    df["Tempo Decorrido"] = df["Horas_em_aberto"].apply(formatar_horas)

    urg = df.apply(classificar_urgencia, axis=1, result_type="expand")
    df["Urgência"] = urg[0]
    df["Urgencia_Fundo"] = urg[1]
    df["Urgencia_Borda"] = urg[2]
    df["Urgencia_Texto"] = urg[3]
    df["SLA"] = urg[4].apply(lambda h: f"{h:.0f}h")

    df.attrs["avisos_colunas"] = col["_avisos"]
    return df

def montar_estilizador(df_com_cores: pd.DataFrame):
    def _style(row):
        info = df_com_cores.loc[row.name]
        estilo = (
            f"background-color: {info['Urgencia_Fundo']}; "
            f"color: {info['Urgencia_Texto']}; "
            f"font-weight: 600; "
            f"border-left: 4px solid {info['Urgencia_Borda']};"
        )
        return [estilo] * len(row)
    return _style

def filtrar_por_setor(df: pd.DataFrame, setores: list) -> pd.DataFrame:
    if not setores:
        return df
    return df[df["Setor"].isin(setores)]

st.title("🛠️ Painel de Controle da Manutenção")

df_inicial = carregar_dados()
setores_presentes = df_inicial["Setor"].dropna().unique().tolist()
setores_finais = sorted(set(SETORES_PADRAO + setores_presentes))

with st.sidebar:
    st.header("⚙️ Filtros Operacionais")
    setor_selecionado = st.multiselect("Setores da Empresa", options=setores_finais, default=setores_finais)
    status_selecionado = st.multiselect(
        "Status do Chamado",
        options=["Pendente", "Atuando", "Concluído"],
        default=["Pendente", "Atuando", "Concluído"],
    )
    st.markdown("---")
    st.caption(f"🔄 Auto-refresh ativo: {INTERVALO_ATUALIZACAO_SEG}s")

@st.fragment(run_every=INTERVALO_ATUALIZACAO_SEG)
def render_painel(setores, status):
    df = carregar_dados()
    df = filtrar_por_setor(df, setores)
    if status:
        df = df[df["Status_Final"].isin(status)]

    agora = pd.Timestamp.now()
    df_validas = df.dropna(subset=["Data_Abertura_dt"])
    hoje = len(df_validas[df_validas["Data_Abertura_dt"].dt.date == agora.date()])
    semana = len(df_validas[df_validas["Data_Abertura_dt"].dt.isocalendar().week == agora.isocalendar().week])
    mes = len(df_validas[
        (df_validas["Data_Abertura_dt"].dt.month == agora.month)
        & (df_validas["Data_Abertura_dt"].dt.year == agora.year)
    ])

    st.markdown("### 📊 Volumetria de Atendimento")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Chamados Hoje", hoje)
    c2.metric("Nesta Semana", semana)
    c3.metric("Neste Mês", mes)
    c4.metric("Total Filtrado", len(df))

    st.markdown("---")
    st.markdown("### 🚦 Status da Fila")
    t1, t2, t3 = st.columns(3)

    def card(titulo, emoji, qtd, fundo, borda, texto):
        st.markdown(
            f"""
            <div class="card-status" style="background-color:{fundo}; border-color:{borda};">
                <h4 style="color:{texto};">{emoji} {titulo}</h4>
                <h2 style="color:{texto};">{qtd}</h2>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with t1:
        card("PENDENTES", "🟠", (df["Status_Final"] == "Pendente").sum(), "#1E293B", "#F97316", "#F97316")
    with t2:
        card("EM ATUAÇÃO", "🔴", (df["Status_Final"] == "Atuando").sum(), "#1E293B", "#EF4444", "#EF4444")
    with t3:
        card("CONCLUÍDOS", "🟢", (df["Status_Final"] == "Concluído").sum(), "#1E293B", "#10B981", "#10B981")

    st.markdown("---")
    
    # REESTRUTURAÇÃO COMPLETA DA SEÇÃO DE SLA POR PRIORIDADE
    st.markdown("### ⏱️ Monitoramento de SLA por Nível de Prioridade")
    
    df_aberto = df[df["Status_Final"] != "Concluído"]
    
    col_alta, col_media, col_baixa = st.columns(3)

    def montar_bloco_prioridade(col, titulo, emoji, prioridade_termos, meta_texto, cor_borda):
        df_p = df_aberto[df_aberto["Prioridade"].astype(str).str.lower().isin(prioridade_termos)]
        total = len(df_p)
        estourou = len(df_p[df_p["Urgência"] == "ESTOUROU SLA"])
        quase = len(df_p[df_p["Urgência"] == "QUASE ESTOURANDO"])
        
        with col:
            st.markdown(
                f"""
                <div class="card-sla" style="border-top: 4px solid {cor_borda};">
                    <h4 style="margin:0; color:#F8FAFC;">{emoji} {titulo}</h4>
                    <p style="margin:2px 0 10px 0; color:#94A3B8; font-size:0.8rem;"><b>Meta SLA:</b> {meta_texto}</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            sub1, sub2, sub3 = st.columns(3)
            sub1.metric("Em Fila", total)
            sub2.metric("Estourado", estourou)
            sub3.metric("Atenção", quase)

    montar_bloco_prioridade(col_alta, "URGENTE / ALTA", "🚨", ["alta", "urgente"], "Resolver em até 2h", "#EF4444")
    montar_bloco_prioridade(col_media, "MÉDIA", "⚠️", ["media", "medio"], "Resolver em até 6h", "#F59E0B")
    montar_bloco_prioridade(col_baixa, "BAIXA", "🟢", ["baixa", "baixo"], "Resolver em até 24h", "#10B981")

    st.markdown("---")
    st.markdown("### 📋 Fila Operacional Reordenada")

    colunas_exibir = [
        "Chamado", "Setor", "Máquina", "Prioridade",
        "Data Abertura", "Tempo Decorrido", "SLA", "Status_Final", "Urgência",
    ]
    colunas_exibir = [c for c in colunas_exibir if c in df.columns]

    ordem_urgencia = {"ESTOUROU SLA": 0, "QUASE ESTOURANDO": 1, "DENTRO DO PRAZO": 2, "OK": 2}
    df = df.assign(_ordem=df["Urgência"].map(ordem_urgencia).fillna(3))
    df = df.sort_values(["_ordem", "Horas_em_aberto"], ascending=[True, False])

    df_tabela = df[colunas_exibir].rename(columns={"Status_Final": "Status"})

    st.dataframe(
        df_tabela.style.apply(montar_estilizador(df), axis=1),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(f"Última sincronização: {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M:%S')}")

render_painel(setor_selecionado, status_selecionado)
