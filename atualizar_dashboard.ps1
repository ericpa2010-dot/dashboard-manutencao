Set-Location -Path "C:\Dashboard-Manutencao"

@'
"""
Painel de Manutenção
---------------------
pip install streamlit pandas
streamlit run app_manutencao.py
"""

import unicodedata

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Painel de Manutenção", layout="wide")

URL_BASE = (
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vRgqjurSWlFiWjsy3V2cpz9vju85"
    "d1-mGNB0wIucZm9Rx_Af0cweCNbXvlEIblD9TlY2bmiYVY5T4N0/pub"
    "?gid=1559301826&single=true&output=csv"
)

INTERVALO_ATUALIZACAO_SEG = 60  # frequência do auto-refresh do fragment

SETORES_PADRAO = [
    "Manutenção", "Expedição", "Estoque", "Montagem",
    "Sala de Reunião", "Atendimento", "Sala de Treinamento",
    "Diretoria", "TI", "Antireflexo",
]

# =============================================================================
# LÓGICA DE URGÊNCIA (AJUSTE AQUI)
# =============================================================================
# SLA por prioridade — vem da coluna "Prioridade" da sua planilha.
# Mude os números livremente conforme a demanda mudar; não precisa mexer
# no resto do código.
PRIORIDADE_SLA_HORAS = {
    "urgente": 2,
    "medio": 6,
    "baixo": 24,
}
SLA_PADRAO_HORAS = 24  # usado quando a prioridade não bate com nenhuma acima

# Fração do SLA a partir da qual o chamado já entra em "quase estourando"
# (amarelo), antes de virar vermelho ao ultrapassar 100% do prazo.
LIMIAR_ATENCAO = 0.7

# Coloque aqui os nomes EXATOS como aparecem na planilha. Setor/máquina
# crítico reduz o prazo efetivo (multiplica o tempo decorrido), então um
# chamado urgente numa linha crítica estoura o SLA mais rápido.
SETORES_CRITICOS = {"Produção", "Montagem", "Expedição", "Antireflexo"}
MAQUINAS_CRITICAS = {"FORNO 1", "LINHA 3", "MÁQUINA X"}


# =============================================================================
# UTILITÁRIOS
# =============================================================================
def normalizar_texto(valor: str) -> str:
    """Remove acentos e deixa em minúsculo, para comparação robusta."""
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
    """Localiza colunas pelo cabeçalho (tolerante a variações e acentos)."""
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
    """
    Regra de negócio confirmada:
    - Data de conclusão preenchida => Concluído (independente do texto do status)
    - Sem conclusão + status contém "atu" => Atuando
    - Caso contrário => Pendente
    """
    tem_conclusao = pd.notnull(df["Data_Conclusao_dt"])
    status_norm = df["Status_Origem"].astype(str).map(normalizar_texto)
    atuando = status_norm.str.contains("atu", na=False)

    status_final = pd.Series("Pendente", index=df.index)
    status_final = status_final.mask((~tem_conclusao) & atuando, "Atuando")
    status_final = status_final.mask(tem_conclusao, "Concluído")
    return status_final


def obter_multiplicador_critico(setor: str, maquina: str) -> int:
    """Dá um 'bump' na urgência se o setor/máquina for crítico (2x); senão 1x."""
    crit_setores = {normalizar_texto(x) for x in SETORES_CRITICOS}
    crit_maquinas = {normalizar_texto(x) for x in MAQUINAS_CRITICAS}
    if normalizar_texto(setor) in crit_setores or normalizar_texto(maquina) in crit_maquinas:
        return 2
    return 1


def obter_sla_horas(prioridade: str) -> float:
    """Prazo (em horas) esperado pra essa prioridade, conforme configurado acima."""
    return PRIORIDADE_SLA_HORAS.get(normalizar_texto(prioridade), SLA_PADRAO_HORAS)


def formatar_horas(h: float) -> str:
    if pd.isna(h):
        return "-"
    return f"{h:.1f}h" if h < 24 else f"{h / 24:.1f}d ({h:.0f}h)"


def classificar_urgencia(row) -> tuple:
    """
    Compara o tempo em aberto contra o SLA da prioridade do chamado
    (Urgente/Médio/Baixo). Setor/máquina crítico reduz o prazo efetivo.
    Retorna (label, fundo, borda, texto, sla_horas) pra colorir a linha
    e ainda mostrar o prazo de referência na tabela.
    """
    status = row["Status_Final"]
    sla = obter_sla_horas(row["Prioridade"])

    if status == "Concluído":
        return ("OK", "#D4EDDA", "#28A745", "#155724", sla)

    mult = obter_multiplicador_critico(row["Setor"], row["Máquina"])
    sla_efetivo = sla / mult  # setor/máquina crítico = prazo mais apertado
    horas = row["Horas_em_aberto"]

    if horas > sla_efetivo:
        return ("ESTOUROU SLA", "#F8D7DA", "#DC3545", "#721C24", sla)
    if horas > sla_efetivo * LIMIAR_ATENCAO:
        return ("QUASE ESTOURANDO", "#FFF3CD", "#FFC107", "#856404", sla)

    cor = ("#FFE8CC", "#FD7E14", "#D9480F") if status == "Pendente" else ("#F8D7DA", "#DC3545", "#721C24")
    return ("DENTRO DO PRAZO", *cor, sla)


# =============================================================================
# CARREGAMENTO
# =============================================================================
# Cache com ttl igual ao intervalo de refresh: evita buscar a planilha duas
# vezes na mesma janela de 60s (uma vez fora do fragment, outra dentro dele),
# e ainda assim garante dado fresco a cada novo ciclo do fragment.
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


# =============================================================================
# UI
# =============================================================================
def montar_estilizador(df_com_cores: pd.DataFrame):
    """
    Retorna uma função de estilo que consulta df_com_cores pelo índice da
    linha (row.name) — assim funciona mesmo que a tabela exibida tenha só
    um subconjunto das colunas.
    """
    def _style(row):
        info = df_com_cores.loc[row.name]
        estilo = (
            f"background-color: {info['Urgencia_Fundo']}; "
            f"color: {info['Urgencia_Texto']}; "
            f"font-weight: bold; "
            f"border-left: 6px solid {info['Urgencia_Borda']};"
        )
        return [estilo] * len(row)
    return _style


def filtrar_por_setor(df: pd.DataFrame, setores: list) -> pd.DataFrame:
    if not setores:
        return df
    # comparação exata (evita falso-positivo de substring, ex.: "TI" batendo
    # em qualquer texto que contenha "ti")
    return df[df["Setor"].isin(setores)]


st.title("Painel de Manutenção")

df_inicial = carregar_dados()
avisos = df_inicial.attrs.get("avisos_colunas", [])
if avisos:
    st.warning(
        "Não encontrei coluna correspondente para: " + ", ".join(avisos)
        + ". Confira os cabeçalhos da planilha."
    )

setores_presentes = df_inicial["Setor"].dropna().unique().tolist()
setores_finais = sorted(set(SETORES_PADRAO + setores_presentes))

with st.sidebar:
    st.header("Filtros")
    setor_selecionado = st.multiselect("Setores", options=setores_finais, default=setores_finais)
    status_selecionado = st.multiselect(
        "Status",
        options=["Pendente", "Atuando", "Concluído"],
        default=["Pendente", "Atuando", "Concluído"],
    )
    st.caption(f"🔄 Atualiza a cada {INTERVALO_ATUALIZACAO_SEG}s")


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

    st.markdown("### 📈 Métricas")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Chamados Hoje", hoje)
    c2.metric("Nesta Semana", semana)
    c3.metric("Neste Mês", mes)
    c4.metric("Total no Filtro", len(df))

    st.markdown("---")
    st.markdown("### 🚦 Fila por Status")
    t1, t2, t3 = st.columns(3)

    def card(titulo, emoji, qtd, fundo, borda, texto):
        st.markdown(
            f"""
            <div style="background-color:{fundo}; padding:15px; border-radius:8px; border-left: 6px solid {borda};">
                <h4 style="color:{texto}; margin:0;">{emoji} {titulo}</h4>
                <h2 style="color:{texto}; margin:0;">{qtd}</h2>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with t1:
        card("PENDENTE", "🟠", (df["Status_Final"] == "Pendente").sum(), "#FFE8CC", "#FD7E14", "#D9480F")
    with t2:
        card("ATUANDO", "🔴", (df["Status_Final"] == "Atuando").sum(), "#F8D7DA", "#DC3545", "#721C24")
    with t3:
        card("CONCLUÍDO", "🟢", (df["Status_Final"] == "Concluído").sum(), "#D4EDDA", "#28A745", "#155724")

    st.markdown("---")
    st.markdown("### ⚠️ Alertas (SLA por prioridade: Urgente 2h · Médio 6h · Baixo 24h)")
    a1, a2, a3 = st.columns(3)
    a1.metric("🔴 Estourou o SLA", (df["Urgência"] == "ESTOUROU SLA").sum())
    a2.metric("🟡 Quase estourando", (df["Urgência"] == "QUASE ESTOURANDO").sum())
    a3.metric("🟢 Dentro do prazo", (df["Urgência"] == "DENTRO DO PRAZO").sum())

    st.markdown("---")
    st.markdown("### 📋 Fila Operacional")

    colunas_exibir = [
        "Chamado", "Setor", "Máquina", "Prioridade",
        "Data Abertura", "Tempo Decorrido", "SLA", "Status_Final", "Urgência",
    ]
    colunas_exibir = [c for c in colunas_exibir if c in df.columns]

    # Mais urgente primeiro: estourou SLA > quase estourando > dentro do prazo.
    ordem_urgencia = {"ESTOUROU SLA": 0, "QUASE ESTOURANDO": 1, "DENTRO DO PRAZO": 2, "OK": 2}
    df = df.assign(_ordem=df["Urgência"].map(ordem_urgencia).fillna(3))
    df = df.sort_values(["_ordem", "Horas_em_aberto"], ascending=[True, False])

    df_tabela = df[colunas_exibir].rename(columns={"Status_Final": "Status"})

    st.dataframe(
        df_tabela.style.apply(montar_estilizador(df), axis=1),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(f"Última atualização: {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M:%S')}")


render_painel(setor_selecionado, status_selecionado)

'@ | Set-Content -Path "app_manutencao.py" -Encoding UTF8

git add .
git commit -m "SLA por prioridade (Urgente 2h / Medio 6h / Baixo 24h), ordenacao por urgencia, coluna SLA na tabela"
git push origin master
