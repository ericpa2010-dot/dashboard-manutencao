"""
Painel de Manutenção
=====================
Lê os chamados de uma planilha Google Sheets publicada como CSV e exibe
um painel operacional com filtros, métricas e fila de chamados.

Requisitos:
    pip install streamlit pandas

Rodar:
    streamlit run app_manutencao.py
"""

import streamlit as st
import pandas as pd
import time
import unicodedata

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

st.set_page_config(page_title="Painel de Manutenção", layout="wide")

URL_BASE = (
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vRgqjurSWlFiWjsy3V2cpz9vju85"
    "d1-mGNB0wIucZm9Rx_Af0cweCNbXvlEIblD9TlY2bmiYVY5T4N0/pub"
    "?gid=1559301826&single=true&output=csv"
)

INTERVALO_ATUALIZACAO_SEG = 15

SETORES_PADRAO = [
    "Manutenção", "Expedição", "Estoque", "Montagem",
    "Sala de Reunião", "Atendimento", "Sala de Treinamento",
    "Diretoria", "TI", "Antireflexo",
]

# Palavras-chave usadas para reconhecer o status de um chamado a partir do
# texto livre da planilha. Se um chamado ficar "preso" incorretamente em
# Pendente/Atuando, o motivo mais comum é o texto do status não bater com
# nenhuma dessas palavras — use o painel de depuração no final da página
# para conferir o texto exato que está vindo da planilha.
PALAVRAS_CONCLUIDO = [
    "conclu", "finaliz", "fechado", "ok", "pronto",
    "resolvid", "reparad", "atendid", "feito", "encerrad",
]
PALAVRAS_ATUANDO = [
    "atuando", "andamento", "em analise", "em analise",
    "fazendo", "reparo", "execu",
]


# =============================================================================
# CARREGAMENTO E TRATAMENTO DOS DADOS
# =============================================================================

def normalizar_texto(valor: str) -> str:
    """Remove acentos e deixa em minúsculo, para comparação de texto robusta."""
    if not isinstance(valor, str):
        return ""
    sem_acento = unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode("ascii")
    return sem_acento.strip().lower()


def identificar_colunas(df: pd.DataFrame) -> dict:
    """Localiza as colunas relevantes pelo nome, com aviso se alguma não for encontrada."""
    mapeamento = {
        "abertura": ["Carimbo", "Abertura"],
        "conclusao": ["conclusão", "conclusao"],
        "status": ["Status", "Situação", "Situacao"],
        "setor": ["Setor", "Nome e Setor"],
        "maquina": ["Máquina", "Equipamento"],
        "prioridade": ["Prioridade"],
        "chamado": ["N°", "Chamado"],
    }

    colunas = {}
    for chave, termos in mapeamento.items():
        encontrada = next(
            (c for c in df.columns if any(normalizar_texto(t) in normalizar_texto(c) for t in termos)),
            None,
        )
        colunas[chave] = encontrada

    if colunas["chamado"] is None:
        colunas["chamado"] = df.columns[0]

    faltando = [k for k, v in colunas.items() if v is None and k != "chamado"]
    if faltando:
        st.warning(
            f"⚠️ Não encontrei as colunas para: {', '.join(faltando)}. "
            "Confira se o cabeçalho da planilha mudou de nome."
        )

    return colunas


def classificar_status(status_texto: str, tem_data_conclusao: bool) -> str:
    """Define o status final do chamado.

    Regra de prioridade:
    1. Se existe data de conclusão preenchida -> Concluído (sempre vence).
    2. Senão, procura palavras-chave no texto do status.
    3. Se nada bater -> Pendente.
    """
    if tem_data_conclusao:
        return "Concluído"

    texto = normalizar_texto(status_texto)

    if any(termo in texto for termo in PALAVRAS_CONCLUIDO):
        return "Concluído"
    if any(termo in texto for termo in PALAVRAS_ATUANDO):
        return "Atuando"
    return "Pendente"


def carregar_dados() -> pd.DataFrame:
    """Busca a planilha sempre atualizada (sem cache) e trata os dados."""
    url_dinamica = f"{URL_BASE}&_nocache={int(time.time())}"
    df = pd.read_csv(url_dinamica)
    df.columns = df.columns.astype(str).str.strip()

    col = identificar_colunas(df)

    # Datas
    df["Data_Abertura_dt"] = (
        pd.to_datetime(df[col["abertura"]], dayfirst=True, errors="coerce")
        if col["abertura"] else pd.NaT
    )
    df["Data_Conclusao_dt"] = (
        pd.to_datetime(df[col["conclusao"]], dayfirst=True, errors="coerce")
        if col["conclusao"] else pd.NaT
    )

    # Remove linhas sem data de abertura válida (linhas vazias/lixo da planilha)
    if col["abertura"]:
        df = df.dropna(subset=["Data_Abertura_dt"])

    # Status
    texto_status_col = df[col["status"]] if col["status"] else pd.Series([""] * len(df), index=df.index)
    df["Status_Padrao"] = [
        classificar_status(texto, pd.notnull(conclusao))
        for texto, conclusao in zip(texto_status_col, df["Data_Conclusao_dt"])
    ]

    # Tempo decorrido
    def calcular_tempo(row):
        dt_ab = row["Data_Abertura_dt"]
        dt_cx = row["Data_Conclusao_dt"]

        if row["Status_Padrao"] == "Concluído":
            if pd.notnull(dt_ab) and pd.notnull(dt_cx):
                diff_horas = (dt_cx - dt_ab).total_seconds() / 3600
                if diff_horas >= 0:
                    return f"{diff_horas:.1f}h" if diff_horas < 24 else f"{diff_horas/24:.1f}d ({diff_horas:.0f}h)"
            return "Concluído"

        if pd.notnull(dt_ab):
            horas_aberto = (pd.Timestamp.now() - dt_ab).total_seconds() / 3600
            return f"{horas_aberto:.1f}h em aberto"
        return "Em aberto"

    df["Tempo Decorrido"] = df.apply(calcular_tempo, axis=1)
    df["Data Abertura"] = df["Data_Abertura_dt"].dt.strftime("%d/%m/%Y %H:%M").fillna("-")
    df["Data Conclusão"] = df["Data_Conclusao_dt"].dt.strftime("%d/%m/%Y").fillna("-")

    df.attrs["colunas"] = col
    return df


# =============================================================================
# COMPONENTES DE INTERFACE
# =============================================================================

def cartao_status(titulo: str, emoji: str, qtd: int, cor_fundo: str, cor_borda: str, cor_texto: str):
    st.markdown(
        f"""
        <div style="background-color:{cor_fundo}; padding:15px; border-radius:8px; border-left: 6px solid {cor_borda};">
            <h4 style="color:{cor_texto}; margin:0;">{emoji} {titulo}</h4>
            <h2 style="color:{cor_texto}; margin:0;">{qtd}</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )


def estilar_linha_inteira(row):
    cores = {
        "Concluído": "background-color: #D4EDDA; color: #155724; font-weight: bold;",
        "Atuando": "background-color: #F8D7DA; color: #721C24; font-weight: bold;",
        "Pendente": "background-color: #FFE8CC; color: #D9480F; font-weight: bold;",
    }
    return [cores.get(row["Status Final"], "")] * len(row)


# =============================================================================
# BLOCO DE DADOS — atualiza sozinho a cada N segundos, sem recarregar a página
# (por isso os filtros escolhidos na sidebar NÃO são perdidos).
# Requer Streamlit >= 1.33 (recurso st.fragment).
# =============================================================================

@st.fragment(run_every=INTERVALO_ATUALIZACAO_SEG)
def painel_de_dados(setor_selecionado, status_selecionado):
    df = carregar_dados()
    col = df.attrs["colunas"]

    df_filtrado = df[df["Status_Padrao"].isin(status_selecionado)]
    if col["setor"] and setor_selecionado:
        df_filtrado = df_filtrado[
            df_filtrado[col["setor"]].astype(str).str.contains("|".join(setor_selecionado), case=False, na=False)
        ]

    # --- Volumetria ---
    agora = pd.Timestamp.now()
    df_validas = df_filtrado.dropna(subset=["Data_Abertura_dt"])

    st.markdown("### 📈 Volumetria de Chamados")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Chamados Hoje", len(df_validas[df_validas["Data_Abertura_dt"].dt.date == agora.date()]))
    m2.metric("Chamados Nesta Semana", len(df_validas[df_validas["Data_Abertura_dt"].dt.isocalendar().week == agora.isocalendar().week]))
    m3.metric("Chamados Neste Mês", len(df_validas[
        (df_validas["Data_Abertura_dt"].dt.month == agora.month) & (df_validas["Data_Abertura_dt"].dt.year == agora.year)
    ]))
    m4.metric("Total no Filtro", len(df_filtrado))

    st.markdown("---")

    # --- Cartões de status ---
    st.markdown("### 🚦 Chamados na Fila")
    c1, c2, c3 = st.columns(3)
    with c1:
        cartao_status("PENDENTE", "🟠", len(df_filtrado[df_filtrado["Status_Padrao"] == "Pendente"]), "#FFE8CC", "#FD7E14", "#D9480F")
    with c2:
        cartao_status("ATUANDO", "🔴", len(df_filtrado[df_filtrado["Status_Padrao"] == "Atuando"]), "#F8D7DA", "#DC3545", "#721C24")
    with c3:
        cartao_status("CONCLUÍDO", "🟢", len(df_filtrado[df_filtrado["Status_Padrao"] == "Concluído"]), "#D4EDDA", "#28A745", "#155724")

    st.markdown("---")

    # --- Tabela ---
    st.markdown("### 📋 Fila Operacional de Chamados")
    colunas_base = [
        col["chamado"], "Data Abertura", "Data Conclusão", "Tempo Decorrido",
        col["setor"], col["maquina"], col["prioridade"], "Status_Padrao",
    ]
    colunas_exibir = [c for c in colunas_base if c in df_filtrado.columns]
    df_tabela = df_filtrado[colunas_exibir].rename(columns={"Status_Padrao": "Status Final"})

    st.dataframe(
        df_tabela.style.apply(estilar_linha_inteira, axis=1),
        use_container_width=True,
        hide_index=True,
    )

    # --- Painel de depuração: ajuda a achar chamado "preso" em Pendente ---
    with st.expander("🔍 Depuração — ver texto bruto do status de cada chamado"):
        colunas_debug = [c for c in [col["chamado"], col["status"], "Status_Padrao", "Data Conclusão"] if c and c in df_filtrado.columns]
        st.dataframe(df_filtrado[colunas_debug], use_container_width=True, hide_index=True)

    st.caption(f"Última atualização: {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M:%S')}")


# =============================================================================
# LAYOUT PRINCIPAL
# =============================================================================

st.title("Painel de Manutenção")

st.sidebar.header("Filtros por Operação")

# Carrega uma vez fora do fragmento só para popular as opções de setor disponíveis
_df_inicial = carregar_dados()
_col_inicial = _df_inicial.attrs["colunas"]
setores_presentes = _df_inicial[_col_inicial["setor"]].dropna().unique().tolist() if _col_inicial["setor"] else []
setores_finais = sorted(set(SETORES_PADRAO + setores_presentes))

setor_selecionado = st.sidebar.multiselect(
    "Setores da Empresa:",
    options=setores_finais,
    default=setores_finais,
)

status_selecionado = st.sidebar.multiselect(
    "Status do Chamado:",
    options=["Pendente", "Atuando", "Concluído"],
    default=["Pendente", "Atuando", "Concluído"],
)

st.sidebar.caption(f"🔄 Atualiza automaticamente a cada {INTERVALO_ATUALIZACAO_SEG}s")

painel_de_dados(setor_selecionado, status_selecionado)
