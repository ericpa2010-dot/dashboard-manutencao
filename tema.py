"""
Tema compartilhado (claro/escuro) do painel inteiro - fonte única de cores
usada por app_manutencao.py e controle_setores.py, pra manter a aparência
consistente entre as abas em vez de cada arquivo ter sua própria paleta.

Visual "profissional/limpo" (paleta neutra + 1 azul de destaque), não mais
o preto-com-ciano-neon de antes. As cores de status (verde/laranja/
vermelho/roxo) continuam fixas nos dois temas - são semânticas, não
decorativas.
"""
import streamlit as st

PALETA = {
    "escuro": {
        "fundo": "#0B1220",
        "superficie": "#161F32",
        "superficie_alt": "#1C2740",
        "borda": "#2A3752",
        "texto": "#F1F5F9",
        "texto_muted": "#94A3B8",
        "primaria": "#3B82F6",
        "primaria_hover": "#60A5FA",
        "primaria_fraca": "rgba(59, 130, 246, 0.16)",
    },
    "claro": {
        "fundo": "#F8FAFC",
        "superficie": "#FFFFFF",
        "superficie_alt": "#F1F5F9",
        "borda": "#E2E8F0",
        "texto": "#0F172A",
        "texto_muted": "#64748B",
        "primaria": "#2563EB",
        "primaria_hover": "#3B82F6",
        "primaria_fraca": "rgba(37, 99, 235, 0.08)",
    },
}

# Cores semânticas de status - praticamente as mesmas nos dois temas (só o
# tom de fundo das linhas de tabela muda pra manter contraste de texto).
SUCESSO, ATENCAO, PERIGO, INFO = "#10B981", "#F59E0B", "#EF4444", "#8B5CF6"

# Fundo/texto das linhas de tabela coloridas por status (histórico de
# chamados, ativos etc.) - um par por tema, pra manter contraste legível.
LINHA_STATUS = {
    "escuro": {
        "critico":   ("#7F1D1D", "#FECDD3"),
        "atencao":   ("#78350F", "#FDE68A"),
        "ok":        ("#064E3B", "#A7F3D0"),
        "neutro":    ("#1E3A8A", "#F0F9FF"),
    },
    "claro": {
        "critico":   ("#FEE2E2", "#991B1B"),
        "atencao":   ("#FEF3C7", "#92400E"),
        "ok":        ("#D1FAE5", "#065F46"),
        "neutro":    ("#DBEAFE", "#1E3A8A"),
    },
}


def tema_atual():
    """'escuro' ou 'claro' - lido do session_state (default: escuro, mesma
    aparência inicial de antes)."""
    return st.session_state.get("tema_app", "escuro")


def cores():
    """Dict de cores do tema ativo agora."""
    return PALETA[tema_atual()]


def linha_status():
    """Dict {critico/atencao/ok/neutro: (fundo, texto)} do tema ativo -
    para colorir linhas de tabela por status."""
    return LINHA_STATUS[tema_atual()]


def plotly_template():
    return "plotly_dark" if tema_atual() == "escuro" else "plotly_white"


def alternar_tema():
    st.session_state["tema_app"] = "claro" if tema_atual() == "escuro" else "escuro"


def botao_alternar_tema():
    """Botão compacto de alternar tema - chamar 1x, perto do topo da página."""
    label = "🌙 Escuro" if tema_atual() == "claro" else "☀️ Claro"
    if st.button(label, key="btn_alternar_tema_app", help="Alternar entre tema claro e escuro"):
        alternar_tema()
        st.rerun()


# Seletores de botão redundantes (classe antiga .stButton + data-testid
# novo stBaseButton) - Streamlit muda esses nomes internos entre versões,
# então cobrimos os dois em vez de apostar em só um.
_SEL_BOTAO = (
    'div.stButton > button, div.stFormSubmitButton > button, '
    'div[data-testid="stButton"] button, div[data-testid="stFormSubmitButton"] button, '
    'button[data-testid^="stBaseButton-primary"], button[data-testid^="stBaseButton-secondaryFormSubmit"]'
)
_SEL_BOTAO_SECUNDARIO = (
    'div.stButton > button[kind="secondary"], '
    'button[data-testid^="stBaseButton-secondary"]:not([data-testid^="stBaseButton-secondaryFormSubmit"])'
)


def css_global():
    """CSS injetado 1x no topo do app, reagindo ao tema ativo. Cobre os
    componentes nativos do Streamlit (botões, inputs, métricas, abas,
    containers com borda, dataframes) - a base que garante consistência
    entre todas as abas do site."""
    c = cores()
    return f"""
    <style>
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}

    /* Variáveis de tema do PRÓPRIO Streamlit (as mesmas que o config.toml
    [theme] define) - alguns componentes internos são renderizados com
    Shadow DOM, que bloqueia CSS externo comum mas NÃO bloqueia variáveis
    CSS (elas atravessam a fronteira do shadow tree). Setar isso aqui é o
    que realmente alcança esses componentes; as regras !important abaixo
    cobrem o resto (texto solto, legendas, botões). */
    :root, .stApp {{
        --primary-color: {c['primaria']};
        --background-color: {c['fundo']};
        --secondary-background-color: {c['superficie']};
        --text-color: {c['texto']};
    }}

    .stApp {{
        background-color: {c['fundo']};
        color: {c['texto']};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}

    /* st.radio usado como barra de sub-abas (mais confiável que st.tabs,
    que perde a seleção a cada re-execução do script) - visual de pílula. */
    div[data-testid="stRadio"] > div[role="radiogroup"] {{
        gap: 8px;
        flex-wrap: wrap;
    }}
    div[data-testid="stRadio"] label {{
        background-color: {c['superficie']};
        border: 1px solid {c['borda']};
        border-radius: 8px;
        padding: 6px 14px;
        margin: 0 !important;
    }}
    div[data-testid="stRadio"] label[data-checked="true"],
    div[data-testid="stRadio"] label:has(input:checked) {{
        background-color: {c['primaria']};
        border-color: {c['primaria']};
    }}
    div[data-testid="stRadio"] label:has(input:checked) p {{
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }}

    h1, h2, h3, h4, h5, h6, label, p, span, li, .stMarkdown,
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] span,
    [data-testid="stWidgetLabel"] p,
    [data-testid="stWidgetLabel"] label,
    [data-testid="stSelectbox"] div,
    [data-testid="stSelectbox"] span,
    [data-testid="stMetricDelta"] {{
        color: {c['texto']} !important;
    }}
    h1, h2, h3, h4, h5, h6 {{ font-weight: 700 !important; }}

    /* Legendas e textos secundários - testid mudou entre versões do
    Streamlit, cobrindo os dois pra não depender de qual está rodando. */
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p,
    [data-testid="stCaption"],
    .stCaption {{
        color: {c['texto_muted']} !important;
    }}

    div[data-baseweb="tab-list"] {{
        gap: 8px;
        background-color: transparent;
        border-bottom: 1px solid {c['borda']};
    }}
    button[data-baseweb="tab"] {{
        background-color: {c['superficie']} !important;
        color: {c['texto_muted']} !important;
        border-radius: 8px 8px 0 0 !important;
        padding: 12px 18px !important;
        font-weight: 600 !important;
        border: 1px solid {c['borda']} !important;
        border-bottom: none !important;
    }}
    button[aria-selected="true"] {{
        background-color: {c['primaria']} !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        border: 1px solid {c['primaria']} !important;
        border-bottom: none !important;
    }}

    div[data-testid="stMetric"] {{
        background-color: {c['superficie']};
        border: 1px solid {c['borda']};
        border-radius: 12px;
        padding: 14px 18px;
    }}
    div[data-testid="stMetricLabel"] {{
        font-size: 0.78rem !important;
        color: {c['texto_muted']} !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.02em;
    }}
    div[data-testid="stMetricValue"] {{
        font-size: 1.6rem !important;
        color: {c['primaria']} !important;
        font-weight: 700 !important;
    }}

    .stTextInput > div > div > input,
    .stSelectbox > div > div,
    .stTextArea textarea,
    .stNumberInput input,
    .stDateInput input {{
        background-color: {c['superficie']} !important;
        color: {c['texto']} !important;
        border: 1px solid {c['borda']} !important;
        border-radius: 8px !important;
    }}

    /* Botões - seletores redundantes (classe antiga + data-testid novo)
    porque o DOM interno do Streamlit muda de nome entre versões; sem
    isso a regra simplesmente não pega e o botão fica com o tema nativo
    do navegador/SO, que pode ficar ilegível em cima do nosso fundo.
    O "*" dentro do botão força o texto interno (o Streamlit às vezes
    envolve o rótulo num <p>/<div> com cor própria que ganha do pai). */
    {_SEL_BOTAO} {{
        background-color: {c['primaria']} !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        padding: 10px 18px !important;
        border: none !important;
        opacity: 1 !important;
        transition: all 0.15s ease;
    }}
    {_SEL_BOTAO}, {_SEL_BOTAO} * {{
        color: #FFFFFF !important;
    }}
    {_SEL_BOTAO}:hover {{
        background-color: {c['primaria_hover']} !important;
        transform: translateY(-1px);
    }}
    {_SEL_BOTAO_SECUNDARIO} {{
        background-color: {c['superficie_alt']} !important;
        border: 1px solid {c['borda']} !important;
    }}
    {_SEL_BOTAO_SECUNDARIO}, {_SEL_BOTAO_SECUNDARIO} * {{
        color: {c['texto']} !important;
    }}
    {_SEL_BOTAO}:disabled,
    {_SEL_BOTAO_SECUNDARIO}:disabled {{
        background-color: {c['superficie_alt']} !important;
        border: 1px solid {c['borda']} !important;
        opacity: 0.6 !important;
    }}
    {_SEL_BOTAO}:disabled *,
    {_SEL_BOTAO_SECUNDARIO}:disabled * {{
        color: {c['texto_muted']} !important;
    }}

    hr {{
        border-color: {c['borda']} !important;
        margin: 1.25rem 0 !important;
    }}

    div[data-testid="stDataFrame"],
    div[data-testid="stExpander"],
    div[data-testid="stForm"],
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: {c['superficie']};
        border: 1px solid {c['borda']};
        border-radius: 12px;
    }}
    div[data-testid="stExpander"] summary {{
        color: {c['texto']} !important;
        font-weight: 600;
    }}
    [data-testid="stPopoverBody"] {{
        background-color: {c['superficie']} !important;
        border: 1px solid {c['borda']} !important;
        border-radius: 12px !important;
    }}
    [data-testid="stAlert"] {{
        border-radius: 10px;
    }}
    </style>
    """
