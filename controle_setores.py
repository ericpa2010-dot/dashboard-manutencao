"""
Controle de Setores - Módulo 100% Nativo & Blindado
---------------------------------------------------
Usa st.container(border=True) para visual limpo sem vazamento de tags HTML.
"""

import re
import math
import textwrap
from datetime import datetime, timedelta
import pandas as pd
import pytz
import streamlit as st
import plotly.graph_objects as go
import gspread
from gspread.utils import rowcol_to_a1
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials
import tema

FUSO_BR = pytz.timezone("America/Sao_Paulo")
SETOR_PADRAO = "Anti Reflexo"

COBERTURA_VERMELHA = 60   # < 60 dias -> Crítico (2 meses de importação)
COBERTURA_AMARELA  = 120  # 60 a 120 dias -> Ponto de Compra
                          # >= 120 dias -> Verde Seguro

# Dias úteis por mês usados na projeção de compra (3/6/12 meses). Mude aqui
# se o ritmo real de produção for diferente.
DIAS_UTEIS_POR_MES = 22

# Água D.I.: limite MÁXIMO rígido (não é faixa ideal) - acima disso, a
# máquina tem problema. Confirmado com o operador: 0,05 µS.
AGUA_DI_LIMITE_US = 0.05

HOJE_STR = datetime.now(FUSO_BR).strftime("%d/%m/%Y")

# Mesma paleta de cores do card de SLA (Dashboard & SLA / cartao_prioridade_jornada
# em app_manutencao.py) - reaproveitada aqui pra manter a mesma linguagem visual.
_CORES_SLA = {"red": "#EF4444", "orange": "#F59E0B", "green": "#10B981", "gray": "#64748B"}

DADOS_TECNICOS_INSUMOS = {
    # Consumo/dia medido na prática (áudio + medição direta do operador),
    # substituindo o cálculo teórico do manual do fabricante. Setor Anti
    # Reflexo: 5 dias úteis/semana, 2 limpezas completas (quarta e sexta).
    "zircônio":        {"consumo_dia": 0.06,     "gramas_lote": 6.0, "unidade": "kg", "obs": "Pastilha 6g, virada entre os 2 lados (CC/CX) da mesma lente, 1 pastilha por ciclo"},
    "zirconio":        {"consumo_dia": 0.06,     "gramas_lote": 6.0, "unidade": "kg", "obs": "Pastilha 6g, virada entre os 2 lados (CC/CX) da mesma lente, 1 pastilha por ciclo"},
    "silício":         {"consumo_dia": 0.058,    "gramas_lote": 5.0, "unidade": "kg", "obs": "2 potinhos: completa 1,4g cada a cada lote (2,8g/lote) + troca completa 2x/semana na limpeza (2,5g cada, 5g/troca)"},
    "silicio":         {"consumo_dia": 0.058,    "gramas_lote": 5.0, "unidade": "kg", "obs": "2 potinhos: completa 1,4g cada a cada lote (2,8g/lote) + troca completa 2x/semana na limpeza (2,5g cada, 5g/troca)"},
    "cromo silício":   {"consumo_dia": 0.001,    "gramas_lote": 2.5, "unidade": "kg", "obs": "Trocado só nas 2 limpezas semanais (quarta e sexta), 2,5g cada"},
    "cromo silicio":   {"consumo_dia": 0.001,    "gramas_lote": 2.5, "unidade": "kg", "obs": "Trocado só nas 2 limpezas semanais (quarta e sexta), 2,5g cada"},
    "hidrofóbico":     {"consumo_dia": 20.0,    "gramas_lote": 0.0, "unidade": "und", "obs": "1 und por LOTE (20 lotes/dia) - alternativo ao Super Hidrofóbico"},
    "hidrofobico":     {"consumo_dia": 20.0,    "gramas_lote": 0.0, "unidade": "und", "obs": "1 und por LOTE (20 lotes/dia) - alternativo ao Super Hidrofóbico"},
    "super hidrofóbico": {"consumo_dia": 10.0,  "gramas_lote": 0.0, "unidade": "und", "obs": "1 und por CICLO (10 ciclos/dia = 2 lotes cada) - alternativo ao Hidrofóbico"},
    "super hidrofobico": {"consumo_dia": 10.0,  "gramas_lote": 0.0, "unidade": "und", "obs": "1 und por CICLO (10 ciclos/dia = 2 lotes cada) - alternativo ao Hidrofóbico"},
    "crystal de quartz":{"consumo_dia": 2.9,    "gramas_lote": 0.0, "unidade": "und", "obs": "2,9 und/dia"},
    "ito":             {"consumo_dia": 0.02,    "gramas_lote": 2.5, "unidade": "kg", "obs": "2,5g por lote (processo pausado)"},
    "otb uv-xbt":      {"consumo_dia": 0.067,   "gramas_lote": 0.0, "unidade": "und", "obs": "2 und/mês"},
}

# ---------------------------------------------------------------------------
# Preparo Químico (SL-501) - referência estática do processo, cuba a cuba.
# ---------------------------------------------------------------------------
PREPARO_QUIMICO_SL501 = [
    {"Cuba": 1,  "Produto": "Soda 50%",           "Temperatura": "50°C", "Dosagem": "3,5L", "Frequência": "1x/semana"},
    {"Cuba": 2,  "Produto": "Soda 5%",             "Temperatura": "50°C", "Dosagem": "700ml", "Frequência": "1x/semana"},
    {"Cuba": 3,  "Produto": "Água",                "Temperatura": "—",    "Dosagem": "7L", "Frequência": "—"},
    {"Cuba": 4,  "Produto": "Detergente ácido",    "Temperatura": "50°C", "Dosagem": "700ml", "Frequência": "1x/semana"},
    {"Cuba": 5,  "Produto": "Água",                "Temperatura": "—",    "Dosagem": "7L", "Frequência": "—"},
    {"Cuba": 6,  "Produto": "Água D.I.",           "Temperatura": "50°C", "Dosagem": "7L", "Frequência": "—"},
    {"Cuba": 7,  "Produto": "Água D.I.",           "Temperatura": "50°C", "Dosagem": "7L", "Frequência": "—"},
    {"Cuba": 8,  "Produto": "Forno (secagem)",     "Temperatura": "80°C", "Dosagem": "—", "Frequência": "—"},
    {"Cuba": 9,  "Produto": "Espera (descanso)",   "Temperatura": "—",    "Dosagem": "—", "Frequência": "—"},
    {"Cuba": 10, "Produto": "Prime",               "Temperatura": "15°C", "Dosagem": "4L", "Frequência": "—"},
    {"Cuba": 11, "Produto": "Forno (secagem)",     "Temperatura": "80°C", "Dosagem": "—", "Frequência": "—"},
    {"Cuba": 12, "Produto": "Espera (descanso)",   "Temperatura": "—",    "Dosagem": "—", "Frequência": "—"},
    {"Cuba": 13, "Produto": "Verniz (espera)",     "Temperatura": "—",    "Dosagem": "descanso", "Frequência": "—"},
    {"Cuba": 14, "Produto": "Verniz",              "Temperatura": "15°C", "Dosagem": "4L", "Frequência": "—"},
    {"Cuba": 15, "Produto": "Forno (secagem)",     "Temperatura": "80°C", "Dosagem": "—", "Frequência": "—"},
    {"Cuba": 16, "Produto": "Saída (retirada)",    "Temperatura": "—",    "Dosagem": "—", "Frequência": "—"},
]

FORMULA_DOSAGEM_SODA = {
    "concentracao_atual": 50, "desejada": 20, "litragem_cuba": 30, "qtd_colocar": "12L",
    "nota_1": "Recomendado manter Soda em 25% para destratar",
    "misturas": [("Soda 50%", "2,5L soda"), ("Soda 5%", "500ml soda"), ("Detergente", "250ml detergente")],
    "nota_2": "Colocar água D.I. antes",
}

# ---------------------------------------------------------------------------
# Polimento (setor Surfaçagem) - polidoras, materiais e tipos de má-polimento.
# ---------------------------------------------------------------------------
POLIDORAS = ["Polidora 1", "Polidora 2", "Polidora 3"]
MATERIAIS_POLIMENTO = ["Policarbonato", "Alto Índice", "CR-39", "1.56"]
TIPOS_MA_POLIMENTO = ["Mau Polido", "Riscos", "Casca de Laranja", "Embaçamento", "Ondulação", "Outro"]

# Cor do "ponto" de cada material no card de polimento (estilo do painel de
# referência - ponto colorido + nome + contador por material).
_CORES_MATERIAL = {
    "Policarbonato": "#38BDF8", "Alto Índice": "#E5E7EB", "CR-39": "#22C55E", "1.56": "#FBBF24",
}

ENTIDADES = {
    "INSUMOS": {
        "headers": ["setor", "nome", "estoque_atual", "unidade", "consumo_dia_calculado", "gramas_por_lote", "status", "observacao"],
        # estoque_atual dos insumos em "kg" já semeado em GRAMAS inteiras
        # (0 = 0g, 6000 = 6kg, 1500 = 1,5kg) - mesma convenção da blindagem
        # de gravação em _tela_insumos.
        "seed": [
            ["Anti Reflexo", "Zircônio", 0, "kg", 0.06, 6.0, "ativo", "Pastilha 6g, virada entre os 2 lados (CC/CX) da mesma lente, 1 pastilha por ciclo"],
            ["Anti Reflexo", "Silício", 6000, "kg", 0.058, 5.0, "ativo", "2 potinhos: completa 1,4g cada a cada lote (2,8g/lote) + troca completa 2x/semana na limpeza (2,5g cada, 5g/troca)"],
            ["Anti Reflexo", "Cromo Silício", 0, "kg", 0.001, 2.5, "ativo", "Trocado só nas 2 limpezas semanais (quarta e sexta), 2,5g cada"],
            ["Anti Reflexo", "Hidrofóbico", 0.0, "und", 20, "", "ativo", "1 und por lote"],
            ["Anti Reflexo", "Super Hidrofóbico", 0.0, "und", 10, "", "pausado", "1 und por ciclo (alternativo ao Hidrofóbico)"],
            ["Anti Reflexo", "Crystal de quartz", 50.0, "und", 2.9, "", "ativo", "2,9 und/dia"],
            ["Anti Reflexo", "ITO", 1500, "kg", 0.02, 2.5, "pausado", "2,5g por lote (processo pausado)"],
            ["Anti Reflexo", "Prime H-580", 2.0, "und", "", "", "ativo", ""],
            ["Anti Reflexo", "Verniz 150S", 3.0, "und", "", "", "ativo", ""],
            ["Anti Reflexo", "Verniz 150", 1.0, "und", "", "", "ativo", ""],
            ["Anti Reflexo", "Soda", 30.0, "L", "", "", "ativo", ""],
            ["Anti Reflexo", "Detergente ácido", 20.0, "L", "", "", "ativo", ""],
            ["Anti Reflexo", "Álcool isopropílico", 10.0, "L", "", "", "ativo", ""],
            ["Anti Reflexo", "OTB UV-XBT", 41.0, "und", 0.067, "", "ativo", "Consumo est.: 2/mês"],
        ],
    },
    "PARAMETROS_PROCESSO": {
        "headers": ["setor", "produto", "teor_min", "teor_max", "temp_min", "temp_max", "esp_min", "esp_max", "acao_acima", "acao_abaixo"],
        "seed": [
            ["Anti Reflexo", "Verniz", 33.0, 38.0, 10.0, 15.0, 2.5, 3.5, "diluir com álcool isopropílico", "completar com verniz concentrado"],
            ["Anti Reflexo", "Prime", 5.5, 7.5, 20.0, 25.0, 0.5, 1.0, "diluir com água D.I.", "completar com Prime concentrado"],
        ],
    },
    "MEDICOES_PROCESSO": {
        "headers": ["data_hora", "setor", "produto", "massa_cadinho_g", "massa_amostra_g", "massa_seco_g",
                    "teor_solidos_pct", "temperatura_c", "espessura_um", "agua_di_us",
                    "status_conformidade", "acao_completado"],
        "seed": [],
    },
    "ROTINA_LIMPEZA": {
        "headers": ["setor", "maquina", "tipo", "frequencia", "dias_semana", "data_ultima_execucao", "proxima_data"],
        "seed": [
            ["Anti Reflexo", "SL-501", "Soda/Detergente", "semanal", "sexta", HOJE_STR, ""],
            ["Anti Reflexo", "MC-380 X-2", "Chapas + Ion Gun", "semanal", "quarta,sexta", HOJE_STR, ""],
            ["Anti Reflexo", "MC-380 X-2", "EBG", "semanal", "", HOJE_STR, ""],
        ],
    },
    "FILTROS": {
        "headers": ["setor", "nome", "maquina", "especificacao", "frequencia_troca", "data_ultima_troca", "proxima_troca"],
        "seed": [
            ["Anti Reflexo", "Filtro químico", "SL-501", '1µ, 5"', "quinzenal", HOJE_STR, ""],
            ["Anti Reflexo", "Filtro da máquina", "SL-501", '1µ, 10"', "mensal", HOJE_STR, ""],
            ["Anti Reflexo", "Pré-filtro água de poço", "SL-501", '5µ e 10µ, 20"', "mensal", HOJE_STR, ""],
        ],
    },
    "CONSUMIVEIS": {
        "headers": ["setor", "nome", "estoque", "data_ultima_troca", "motivo", "observacao"],
        "seed": [
            ["Anti Reflexo", "Filamento Ion Gun", 1, HOJE_STR, "", "Estoque crítico"],
            ["Anti Reflexo", "Filamento EBG", 3, HOJE_STR, "", ""],
            ["Anti Reflexo", "Distribuidor de gás", 1, HOJE_STR, "", "1 estoque + 1 em uso na máquina"],
        ],
    },
    "HISTORICO_REPOSICAO": {
        "headers": ["setor", "insumo", "tipo_movimento", "data_hora", "quantidade", "unidade", "saldo_pos"],
        "seed": [],
    },
    "PREPARO_QUIMICO": {
        "headers": ["setor", "nome", "estoque", "unidade", "observacao"],
        "seed": [
            ["Anti Reflexo", "Galão de soda 50%", 32.89, "L", ""],
            ["Anti Reflexo", "Galão ácido", 20.0, "L", ""],
        ],
    },
    "POLIMENTO_OCORRENCIAS": {
        "headers": ["setor", "data_hora", "polidora", "material", "quantidade", "tipo_ma_polimento", "conferente"],
        "seed": [],
    },
    "POLIMENTO_DISCOS": {
        "headers": ["setor", "polidora", "data_ultima_troca", "proxima_troca"],
        "seed": [
            ["Surfaçagem", "Polidora 1", HOJE_STR, ""],
            ["Surfaçagem", "Polidora 2", HOJE_STR, ""],
            ["Surfaçagem", "Polidora 3", HOJE_STR, ""],
        ],
    },
    "PRODUCAO_DIARIA": {
        "headers": ["setor", "data", "lotes", "limpeza", "zirconio_g", "silicio_g",
                    "cromo_silicio_g", "ito_g", "hidrofobico_und", "super_hidrofobico_und",
                    "crystal_und"],
        "seed": [],
    },
}

_DIAS_SEMANA = {
    "segunda": 0, "seg": 0, "terca": 1, "terça": 1, "ter": 1,
    "quarta": 2, "qua": 2, "quinta": 3, "qui": 3, "sexta": 4, "sex": 4,
    "sabado": 5, "sábado": 5, "domingo": 6
}
_FREQ_DIAS = {"diario": 1, "semanal": 7, "quinzenal": 15, "mensal": 30}

@st.cache_resource(ttl=300)
def _spreadsheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace(r"\n", "\n")
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_url(st.secrets["spreadsheet"]["url"])

def _ws(nome):
    cfg = ENTIDADES[nome]
    ss = _spreadsheet()
    try:
        return ss.worksheet(nome)
    except WorksheetNotFound:
        ws = ss.add_worksheet(title=nome, rows=250, cols=max(12, len(cfg["headers"])))
        linhas = [cfg["headers"]] + cfg.get("seed", [])
        ws.append_rows(linhas, value_input_option="RAW")
        return ws

@st.cache_resource(show_spinner=False)
def _garantir_abas():
    for nome in ENTIDADES:
        _ws(nome)
    return True

@st.cache_data(ttl=10, show_spinner=False)
def _load(nome):
    cols = ENTIDADES[nome]["headers"]
    try:
        ws = _ws(nome)
        df = pd.DataFrame(ws.get_all_records())
        if df.empty:
            df = pd.DataFrame(columns=cols)
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df[cols].copy()
    except Exception:
        seed = ENTIDADES[nome].get("seed", [])
        return pd.DataFrame(seed, columns=cols) if seed else pd.DataFrame(columns=cols)

def _append(nome, linha):
    _ws(nome).append_row(linha, value_input_option="RAW")

def _atualizar(nome, filtros, updates):
    ws = _ws(nome)
    valores = ws.get_all_values()
    if not valores: return False
    header = valores[0]
    idx = {h: i for i, h in enumerate(header)}

    def celula(row, col):
        i = idx.get(col)
        return row[i].strip() if (i is not None and i < len(row)) else ""

    lote = []
    for num_linha, row in enumerate(valores[1:], start=2):
        if all(celula(row, k) == str(v).strip() for k, v in filtros.items()):
            for col, novo in updates.items():
                if col in idx:
                    lote.append({"range": rowcol_to_a1(num_linha, idx[col] + 1), "values": [[novo]]})
            break
    if lote:
        ws.batch_update(lote, value_input_option="RAW")
        return True
    return False

def _parse_num(v, padrao=0.0):
    if v is None or pd.isna(v): return padrao
    s = str(v).strip().replace(" ", "").replace(",", ".")
    if s.lower() in ("", "-", "nan", "none", "null"): return padrao
    try: return float(s)
    except (ValueError, TypeError): return padrao

def _proxima_data(data_ultima, frequencia, dias_semana):
    dias_sem = str(dias_semana or "").strip().lower()
    freq = str(frequencia or "").strip().lower()
    hoje = datetime.now(FUSO_BR).date()
    if dias_sem:
        alvos = set()
        for tok in re.split(r"[,;/]| e ", dias_sem):
            tok = tok.strip()
            if tok in _DIAS_SEMANA: alvos.add(_DIAS_SEMANA[tok])
        if alvos:
            d = hoje + timedelta(days=1)
            for _ in range(21):
                if d.weekday() in alvos: return d
                d += timedelta(days=1)
    try:
        d_base = pd.to_datetime(str(data_ultima), dayfirst=True).date() if data_ultima else hoje
        n = _FREQ_DIAS.get(freq, 30)
        return d_base + timedelta(days=n)
    except Exception:
        return hoje + timedelta(days=7)

def _e_dia_limpeza(data):
    """Quarta ou sexta - mesmo critério das 2 limpezas semanais completas."""
    return data.weekday() in (2, 4)  # 2=quarta, 4=sexta

def _crystal_deduzir(setor, lotes_hoje):
    """Unidades de Crystal de quartz a descontar HOJE (1 a cada 7 lotes),
    acumulando a fração entre os dias em vez de arredondar toda vez: soma
    todo o histórico de lotes já registrado, e desconta só a diferença
    entre o total-devido-até-hoje e o que já foi deduzido até ontem."""
    df_prod = _load("PRODUCAO_DIARIA")
    df_prod = df_prod[df_prod["setor"].astype(str).str.strip() == setor]
    lotes_antes = df_prod["lotes"].apply(lambda v: _parse_num(v, 0.0)).sum() if not df_prod.empty else 0.0
    total_antes = math.floor(lotes_antes / 7)
    total_com_hoje = math.floor((lotes_antes + lotes_hoje) / 7)
    return float(total_com_hoje - total_antes)

def _calcular_deducoes_producao(setor, lotes, data_produzida):
    """Fórmulas de desconto automático por 'lotes produzidos hoje'. Retorna
    (deducoes, limpeza) - deducoes é {nome_insumo: quantidade}, em gramas
    pros insumos em kg e em unidades pros demais."""
    ciclos = lotes / 2.0
    limpeza = _e_dia_limpeza(data_produzida)
    deducoes = {
        "Zircônio": 6.0 * ciclos,
        "Silício": 2.8 * lotes + (5.0 if limpeza else 0.0),
        "Cromo Silício": 5.0 if limpeza else 0.0,
        "Hidrofóbico": 1.0 * lotes,
        "Super Hidrofóbico": 1.0 * ciclos,
        "Crystal de quartz": _crystal_deduzir(setor, lotes),
    }
    return deducoes, limpeza

_MAPA_COLUNA_PRODUCAO = {
    "Zircônio": "zirconio_g", "Silício": "silicio_g", "Cromo Silício": "cromo_silicio_g",
    "Hidrofóbico": "hidrofobico_und", "Super Hidrofóbico": "super_hidrofobico_und",
    "Crystal de quartz": "crystal_und",
}

def _registrar_producao_dia(setor, df_insumos, lotes, data_produzida):
    """Aplica o desconto automático (respeitando insumos pausados - ex: só
    um dos dois Hidrofóbicos ativo por vez) e grava a linha do dia em
    PRODUCAO_DIARIA. Retorna a lista de resumo (texto) do que foi descontado."""
    deducoes, limpeza = _calcular_deducoes_producao(setor, lotes, data_produzida)
    resumo = []
    valores_linha = {c: 0 for c in _MAPA_COLUNA_PRODUCAO.values()}
    valores_linha["ito_g"] = 0

    for nome, qtd in deducoes.items():
        if qtd is None or qtd <= 0:
            continue
        linha = df_insumos[df_insumos["nome"].astype(str).str.strip() == nome]
        if linha.empty:
            continue
        r = linha.iloc[0]
        if str(r["status"]).strip().lower() == "pausado":
            continue  # respeita pausado (ex: alternância Hidrofóbico x Super Hidrofóbico)
        unidade = str(r["unidade"]).strip().lower()
        estoque_raw = _parse_num(r["estoque_atual"])
        if unidade == "kg":
            novo = max(0, round(estoque_raw - qtd))
            resumo.append(f"{nome}: -{qtd:g}g")
        else:
            novo = max(0.0, estoque_raw - qtd)
            resumo.append(f"{nome}: -{qtd:g} {unidade}")
        _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo})
        if nome in _MAPA_COLUNA_PRODUCAO:
            valores_linha[_MAPA_COLUNA_PRODUCAO[nome]] = qtd

    _append("PRODUCAO_DIARIA", [
        setor, data_produzida.strftime("%d/%m/%Y"), lotes, "Sim" if limpeza else "Não",
        valores_linha["zirconio_g"], valores_linha["silicio_g"], valores_linha["cromo_silicio_g"],
        valores_linha["ito_g"], valores_linha["hidrofobico_und"], valores_linha["super_hidrofobico_und"],
        valores_linha["crystal_und"],
    ])
    return resumo, limpeza

def _bump_inp_versao(nome):
    """Força o text_input de estoque a virar um widget NOVO no próximo rerun
    (troca a key, incrementando um contador à parte) em vez de escrever
    direto em st.session_state[key do widget] - isso é proibido pelo
    Streamlit depois que o widget já foi instanciado no mesmo ciclo do
    script (StreamlitWidgetAlreadyInstantiatedError)."""
    chave_versao = f"inp_{nome}_v"
    st.session_state[chave_versao] = st.session_state.get(chave_versao, 0) + 1

def _badge_sla(cor_status, titulo, valor_grande, pct_barra, rodape=""):
    """Badge + barra coloridos, mesmo padrao (textwrap.dedent().strip()) usado
    no card de prioridade do Dashboard & SLA - já comprovado sem vazar HTML.
    Fundo/borda puxam do tema compartilhado (claro/escuro); a cor de status
    (verde/laranja/vermelho/cinza) é semântica e fixa nos dois temas."""
    c = tema.cores()
    cor_hex = _CORES_SLA.get(cor_status, _CORES_SLA["gray"])
    pct_barra = max(0.0, min(100.0, pct_barra))
    rodape_html = f'<div style="font-size:0.8rem; color:{c["texto_muted"]}; margin-top:4px;">{rodape}</div>' if rodape else ""
    return textwrap.dedent(f"""
        <div style="background-color:{c['superficie']}; border:2px solid {cor_hex}; padding:12px 15px; border-radius:12px; margin-top:6px;">
            <div style="font-weight:800; color:{cor_hex}; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.03em;">{titulo}</div>
            <div style="font-size:1.25rem; font-weight:800; color:{cor_hex}; margin:4px 0;">{valor_grande}</div>
            <div style="background-color:{c['borda']}; border-radius:6px; height:12px; width:100%; margin:8px 0; overflow:hidden;">
                <div style="background-color:{cor_hex}; width:{pct_barra:.1f}%; height:100%; border-radius:6px; transition: width 0.5s ease;"></div>
            </div>
            {rodape_html}
        </div>
    """).strip()

def _linha_estoque_simples(entidade, campo_estoque, nome, valor_atual, unidade, chave, filtros):
    """Linha 'nome (atual: X un) + campo + salvar' - o mesmo padrão simples já
    usado em Consumíveis, reaproveitado aqui em vez de criar um componente novo."""
    c_a, c_b, c_c = st.columns([2, 1, 1])
    c_a.write(f"**{nome}** (Atual: `{valor_atual:g} {unidade}`)")
    novo = c_b.number_input("Saldo", min_value=0.0, value=float(valor_atual), step=1.0,
                             key=f"est_{chave}", label_visibility="collapsed")
    if c_c.button("Salvar", key=f"btn_est_{chave}"):
        _atualizar(entidade, filtros, {campo_estoque: novo})
        st.success(f"{nome} salvo!")
        st.cache_data.clear()
        st.rerun()

def _fmt_projecao(consumo_dia, dias, unidade):
    """Consumo projetado (consumo_dia x dias) convertido pra unidade de compra:
    pacotes de 1kg (arredondado pra cima) se unidade == kg, senão unidades."""
    total = consumo_dia * dias
    qtd = math.ceil(total) if total > 0 else 0
    if unidade == "kg":
        return f"{qtd} pacote(s) de 1kg"
    return f"{qtd} {unidade}"

def _grafico_barra(serie, titulo, cores_barras=None):
    """Barra simples com o valor escrito em cima de cada barra, no mesmo
    tema (cor/fundo) do resto do site - troca o st.bar_chart nativo (sem
    rótulo de valor) por algo mais claro pro pessoal ler de longe."""
    c = tema.cores()
    if serie.empty:
        return None
    if cores_barras is None:
        cor_barra = c["primaria"]
    else:
        cor_barra = [cores_barras.get(x, c["primaria"]) for x in serie.index]
    fig = go.Figure(go.Bar(
        x=serie.index, y=serie.values, marker_color=cor_barra,
        text=serie.values, texttemplate="%{text:.0f}", textposition="outside",
        textfont=dict(color=c["texto"], size=13),
    ))
    fig.update_layout(
        template=tema.plotly_template(),
        title=dict(text=f"<b>{titulo}</b>", font=dict(size=14, color=c["texto"])),
        xaxis=dict(tickfont=dict(color=c["texto_muted"], size=11), showgrid=False),
        yaxis=dict(tickfont=dict(color=c["texto_muted"]), gridcolor=c["borda"], showgrid=True),
        paper_bgcolor=c["superficie"], plot_bgcolor=c["superficie"],
        margin=dict(l=10, r=10, t=40, b=10), height=300, showlegend=False,
    )
    return fig

# ---------------------------------------------------------------------------
# TELA 1: ESTOQUE DE INSUMOS (100% NATIVO, DIRETO E SEM QUEBRAS)
# ---------------------------------------------------------------------------
def _tela_insumos(setor):
    st.info("📦 **Gestão Prática de Insumos & Lotes** — Defina abaixo o estoque real exato de cada item. Use os botões de 1 clique para registrar baixas de pastilha/lote.")

    # Botão de Zerar Tudo - só habilita depois de marcar a confirmação
    col_z1, col_z2 = st.columns([3, 1])
    with col_z2:
        confirmar_zerar = st.checkbox("Confirmar zerar TODOS os insumos", key="cs_confirma_zerar")
        if st.button(
            "🗑️ Zerar Todos os Insumos", use_container_width=True,
            disabled=not confirmar_zerar,
            help="Marque a confirmação acima para habilitar. Zera o estoque de TODOS os insumos, de TODOS os setores — ação irreversível.",
        ):
            try:
                ws = _ws("INSUMOS")
                valores = ws.get_all_values()
                header = valores[0]
                idx_est = header.index("estoque_atual") if "estoque_atual" in header else 2
                updates = []
                for i in range(2, len(valores) + 1):
                    updates.append({"range": rowcol_to_a1(i, idx_est + 1), "values": [[0]]})
                if updates:
                    ws.batch_update(updates, value_input_option="RAW")
                st.success("✅ Todos os insumos foram zerados!")
                st.session_state["cs_confirma_zerar"] = False  # desarma a confirmação
                st.cache_data.clear()
                st.rerun()
            except Exception as ex:
                st.error(f"Erro ao zerar: {ex}")

    df = _load("INSUMOS")
    df = df[df["setor"].astype(str).str.strip() == setor].copy()
    if df.empty:
        st.warning("Nenhum insumo encontrado para este setor.")
        return

    with st.expander("📋 Registrar Produção do Dia (desconto automático por lote)"):
        col_d, col_l, col_r = st.columns([2, 2, 1])
        with col_d:
            data_prod = st.date_input("Data", value=datetime.now(FUSO_BR).date(), key="prod_data")
        with col_l:
            lotes_txt = st.text_input("Lotes produzidos", key="prod_lotes", placeholder="Ex: 20")
        with col_r:
            st.write("")
            if st.button("✅ Registrar e Descontar", key="prod_registrar", use_container_width=True):
                lotes = _parse_num(lotes_txt, padrao=None)
                if lotes is None or lotes <= 0:
                    st.error("Informe uma quantidade de lotes válida.")
                else:
                    resumo, limpeza = _registrar_producao_dia(setor, df, lotes, data_prod)
                    txt_limpeza = " (dia de limpeza — quarta/sexta)" if limpeza else ""
                    txt_resumo = " · ".join(resumo) if resumo else "nenhum insumo com fórmula automática foi afetado"
                    st.success(f"Produção de {lotes:g} lotes registrada{txt_limpeza}! {txt_resumo}")
                    st.cache_data.clear()
                    st.rerun()

    linhas_projecao = []
    for _, r in df.iterrows():
        nome = str(r["nome"]).strip()
        nome_k = nome.lower().strip()
        unidade = str(r["unidade"]).strip().lower()
        status = str(r["status"]).strip().lower()
        pausado = (status == "pausado")
        
        estoque_raw = _parse_num(r["estoque_atual"])
        obs_raw = str(r.get("observacao", "")).strip()

        # Dados técnicos garantidos
        if nome_k in DADOS_TECNICOS_INSUMOS:
            tec = DADOS_TECNICOS_INSUMOS[nome_k]
            unidade = tec["unidade"]
            consumo_dia = tec["consumo_dia"]
            gramas_lote = tec["gramas_lote"]
            obs = tec["obs"] if not obs_raw or obs_raw == "a preencher" else obs_raw
        else:
            consumo_dia = _parse_num(r.get("consumo_dia_calculado", 0.0))
            gramas_lote = _parse_num(r.get("gramas_por_lote", 0.0))
            obs = obs_raw

        # Projeção de compra (só entram insumos com consumo/dia conhecido)
        if consumo_dia and consumo_dia > 0:
            linhas_projecao.append({
                "Insumo": nome,
                "Consumo/dia": f"{consumo_dia:g} {unidade}",
                f"3 meses ({DIAS_UTEIS_POR_MES * 3}d)": _fmt_projecao(consumo_dia, DIAS_UTEIS_POR_MES * 3, unidade),
                f"6 meses ({DIAS_UTEIS_POR_MES * 6}d)": _fmt_projecao(consumo_dia, DIAS_UTEIS_POR_MES * 6, unidade),
                f"12 meses ({DIAS_UTEIS_POR_MES * 12}d)": _fmt_projecao(consumo_dia, DIAS_UTEIS_POR_MES * 12, unidade),
            })

        # Estoque: para insumos cadastrados em "kg", estoque_atual é SEMPRE
        # gravado na planilha como inteiro de GRAMAS (nunca decimal) -
        # blindagem contra o Sheets reinterpretar "." como separador de
        # milhar em locale pt-BR. Aqui só convertemos pra kg pra exibir.
        if unidade == "kg":
            estoque_g = estoque_raw
            estoque_kg = estoque_raw / 1000.0
        else:
            estoque_kg = estoque_raw
            estoque_g = 0.0

        if unidade == "kg":
            dias_cobertura = (estoque_kg / consumo_dia) if (consumo_dia > 0 and not pausado) else None
            lotes_totais = (estoque_g / gramas_lote) if (gramas_lote > 0 and not pausado) else None
            txt_est_principal = f"{estoque_kg:,.2f} kg ({estoque_g:,.0f} g)".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            dias_cobertura = (estoque_raw / consumo_dia) if (consumo_dia > 0 and not pausado) else None
            lotes_totais = None
            txt_est_principal = f"{estoque_raw:g} {unidade.upper()}"

        # Status do SLA de cobertura (Meta: 60 dias de compra)
        if pausado:
            cor_status = "gray"
            msg_sla = "⏸️ Processo Pausado"
            progresso_pct = 1.0
        elif dias_cobertura is None:
            cor_status = "gray"
            msg_sla = "Consumo diário a definir"
            progresso_pct = 1.0
        elif dias_cobertura < COBERTURA_VERMELHA:
            cor_status = "red"
            msg_sla = f"🔴 {dias_cobertura:.0f} dias — CRÍTICO (< 2 meses para chegar!)"
            progresso_pct = max(0.05, min(1.0, dias_cobertura / COBERTURA_VERMELHA))
        elif dias_cobertura < COBERTURA_AMARELA:
            cor_status = "orange"
            msg_sla = f"🟡 {dias_cobertura:.0f} dias — ATENÇÃO (Ponto de Pedido)"
            progresso_pct = 0.5 + ((dias_cobertura - 60) / 60.0) * 0.4
        else:
            cor_status = "green"
            msg_sla = f"🟢 {dias_cobertura:.0f} dias — SEGURO (> 4 meses garantidos)"
            progresso_pct = 1.0

        # CARD NATIVO - mesma densidade dos cards de SLA (Dashboard & SLA):
        # nome+valor em 1 linha, badge+barra, 1 campo + 1 botão de salvar,
        # ações rápidas escondidas num expander.
        tem_acao_rapida = nome_k in ["zircônio", "zirconio", "silício", "silicio", "cromo silício", "cromo silicio"]

        with st.container(border=True):
            # Linha 1: nome + estoque atual em destaque
            col_nome, col_valor = st.columns([3, 2])
            with col_nome:
                st.subheader(nome)
                if obs:
                    st.caption(obs)
            with col_valor:
                st.metric("Estoque Atual", txt_est_principal)

            # Linha 2: Barra de Vida - mesmo estilo (cores/card) do badge de
            # prioridade do Dashboard & SLA
            rodape_lotes = f"{lotes_totais:,.0f} lotes restantes".replace(",", ".") if (dias_cobertura and lotes_totais) else ""
            st.markdown(
                _badge_sla(cor_status, "Saúde do Estoque", msg_sla, progresso_pct * 100, rodape_lotes),
                unsafe_allow_html=True,
            )

            # Toggle discreto de ativo/pausado - existe pra insumos alternativos
            # (ex: só um dos dois Hidrofóbicos em uso por vez).
            if st.button("▶️ Ativar" if pausado else "⏸️ Pausar", key=f"toggle_status_{nome}", use_container_width=True):
                novo_status = "ativo" if pausado else "pausado"
                _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"status": novo_status})
                st.success(f"{nome} agora está **{novo_status}**.")
                st.cache_data.clear()
                st.rerun()

            # 3 ações do card - Atual (corrigir) / Acrescentar (reposição) /
            # Retirar (baixa manual) - cada uma num popover pequeno, sem
            # inflar o card. Insumos em kg sempre em gramas (sem seletor de
            # unidade) - fecha de vez a ambiguidade que causava o bug antigo.
            if unidade == "kg":
                label_campo, placeholder = "Novo estoque (g)", "Ex: 390"
                val_base_txt = str(int(round(estoque_g)))
            else:
                label_campo, placeholder = f"Novo estoque ({unidade})", "Ex: 2"
                val_base_txt = f"{estoque_raw:g}".replace(".", ",")

            col_atual, col_add, col_rem = st.columns(3)

            with col_atual:
                with st.popover("📏 Atual", use_container_width=True):
                    st.caption("Corrige o estoque pro valor medido agora (conferência).")
                    # Key versionada: cada salvamento incrementa o contador (via
                    # _bump_inp_versao) pra não reescrever session_state de um
                    # widget já instanciado no mesmo ciclo do script.
                    versao_inp = st.session_state.get(f"inp_{nome}_v", 0)
                    txt_val = st.text_input(
                        label_campo, value=val_base_txt, key=f"inp_{nome}_{versao_inp}", placeholder=placeholder,
                    )
                    if st.button("Confirmar correção", key=f"btn_atual_{nome}", use_container_width=True):
                        limpo = re.sub(r"[^0-9,.\-]", "", txt_val).strip()
                        novo_val = _parse_num(limpo, padrao=None)
                        if novo_val is None or novo_val < 0:
                            st.error("Valor inválido — use apenas números (ex: 390 ou 2).")
                        else:
                            if unidade == "kg":
                                val_gravar = int(round(novo_val))
                                val_exibicao = f"{val_gravar/1000:.3f} kg ({val_gravar} g)"
                            else:
                                val_gravar = novo_val
                                val_exibicao = f"{val_gravar:g} {unidade}"
                            _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": val_gravar})
                            _append("HISTORICO_REPOSICAO", [setor, nome, "conferencia",
                                    datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"), val_gravar, unidade, val_gravar])
                            _bump_inp_versao(nome)
                            st.success(f"Estoque de {nome} corrigido para {val_exibicao}!")
                            st.cache_data.clear()
                            st.rerun()

            with col_add:
                with st.popover("➕ Acrescentar", use_container_width=True):
                    st.caption("Registra chegada/compra de insumo novo.")
                    txt_add = st.text_input(
                        f"Quantidade recebida ({'g' if unidade == 'kg' else unidade})",
                        key=f"add_{nome}", placeholder="Ex: 1000",
                    )
                    if st.button("Confirmar entrada", key=f"btn_add_{nome}", use_container_width=True):
                        limpo = re.sub(r"[^0-9,.\-]", "", txt_add).strip()
                        qtd = _parse_num(limpo, padrao=None)
                        if qtd is None or qtd <= 0:
                            st.error("Informe uma quantidade válida.")
                        else:
                            novo = int(round(estoque_g + qtd)) if unidade == "kg" else (estoque_raw + qtd)
                            _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo})
                            _append("HISTORICO_REPOSICAO", [setor, nome, "reposicao",
                                    datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"), qtd,
                                    "g" if unidade == "kg" else unidade, novo])
                            st.success(f"+{qtd:g} {'g' if unidade == 'kg' else unidade} adicionados a {nome}!")
                            st.cache_data.clear()
                            st.rerun()

            with col_rem:
                with st.popover("➖ Retirar", use_container_width=True):
                    st.caption("Baixa manual avulsa (fora do fluxo de lotes).")
                    if tem_acao_rapida:
                        st.write("**Atalhos rápidos:**")
                        if nome_k in ["zircônio", "zirconio"]:
                            b1, b2 = st.columns(2)
                            with b1:
                                if st.button("-1 Pastilha (6g)", key=f"bx1_{nome}", use_container_width=True):
                                    novo_g = max(0, round(estoque_g - 6))
                                    _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo_g})
                                    _bump_inp_versao(nome)
                                    st.success(f"Baixa de 6g salva! Novo saldo: {novo_g} g")
                                    st.cache_data.clear()
                                    st.rerun()
                            with b2:
                                if st.button("-2 Pastilhas (12g)", key=f"bx2_{nome}", use_container_width=True):
                                    novo_g = max(0, round(estoque_g - 12))
                                    _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo_g})
                                    _bump_inp_versao(nome)
                                    st.success(f"Baixa de 12g salva! Novo saldo: {novo_g} g")
                                    st.cache_data.clear()
                                    st.rerun()
                        elif nome_k in ["silício", "silicio"]:
                            if st.button("-1 Lote (5g)", key=f"bx1_{nome}", use_container_width=True):
                                novo_g = max(0, round(estoque_g - 5))
                                _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo_g})
                                _bump_inp_versao(nome)
                                st.success(f"Baixa de 5g salva! Novo saldo: {novo_g} g")
                                st.cache_data.clear()
                                st.rerun()
                        elif nome_k in ["cromo silício", "cromo silicio"]:
                            if st.button("-1 Troca (2,5g)", key=f"bx1_{nome}", use_container_width=True):
                                novo_g = max(0, round(estoque_g - 2.5))
                                _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo_g})
                                _bump_inp_versao(nome)
                                st.success(f"Baixa de 2,5g salva! Novo saldo: {novo_g} g")
                                st.cache_data.clear()
                                st.rerun()
                        st.markdown("---")
                    txt_rem = st.text_input(
                        f"Quantidade a retirar ({'g' if unidade == 'kg' else unidade})",
                        key=f"rem_{nome}", placeholder="Ex: 6",
                    )
                    if st.button("Confirmar retirada", key=f"btn_rem_{nome}", use_container_width=True):
                        limpo = re.sub(r"[^0-9,.\-]", "", txt_rem).strip()
                        qtd = _parse_num(limpo, padrao=None)
                        if qtd is None or qtd <= 0:
                            st.error("Informe uma quantidade válida.")
                        else:
                            novo = max(0, round(estoque_g - qtd)) if unidade == "kg" else max(0.0, estoque_raw - qtd)
                            _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo})
                            _append("HISTORICO_REPOSICAO", [setor, nome, "retirada_manual",
                                    datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"), qtd,
                                    "g" if unidade == "kg" else unidade, novo])
                            st.success(f"-{qtd:g} {'g' if unidade == 'kg' else unidade} retirados de {nome}!")
                            st.cache_data.clear()
                            st.rerun()

            if not tem_acao_rapida and consumo_dia and consumo_dia > 0:
                st.caption(f"Consumo diário previsto: **{consumo_dia:g} {unidade}/dia**")

    if linhas_projecao:
        with st.expander("📈 Projeção de Compra (3 / 6 / 12 meses)"):
            st.caption(
                f"consumo/dia × dias úteis, usando {DIAS_UTEIS_POR_MES} dias úteis/mês "
                "(constante DIAS_UTEIS_POR_MES no topo do arquivo). Insumos sem "
                "consumo/dia definido não entram aqui."
            )
            st.dataframe(pd.DataFrame(linhas_projecao), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("📅 Consumo Diário (últimos registros)")
    df_prod = _load("PRODUCAO_DIARIA")
    df_prod = df_prod[df_prod["setor"].astype(str).str.strip() == setor]
    if df_prod.empty:
        st.caption("Nenhuma produção registrada ainda — use \"Registrar Produção do Dia\" acima.")
    else:
        tabela = df_prod.tail(30).iloc[::-1].rename(columns={
            "data": "Data", "lotes": "Lotes feitos", "limpeza": "Limpeza?",
            "zirconio_g": "Zircônio (g)", "silicio_g": "Silício (g)",
            "cromo_silicio_g": "Cromo Silício (g)", "ito_g": "ITO (g)",
            "hidrofobico_und": "Hidrofóbico (und)", "super_hidrofobico_und": "Super Hidrofóbico (und)",
            "crystal_und": "Crystal de quartz (und)",
        }).drop(columns=["setor"])
        st.dataframe(tabela, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# TELA: PREPARO QUÍMICO (SL-501) - checklist do processo + estoque de galões
# ---------------------------------------------------------------------------
def _tela_preparo_quimico(setor):
    st.info("🧪 Sequência de montagem da SL-501 — processo de referência, cuba a cuba.")

    st.dataframe(pd.DataFrame(PREPARO_QUIMICO_SL501), use_container_width=True, hide_index=True)

    st.markdown("---")
    col_formula, col_estoque = st.columns(2)

    with col_formula:
        with st.container(border=True):
            st.subheader("🧮 Fórmula de Dosagem (Soda)")
            f = FORMULA_DOSAGEM_SODA
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Concentração atual", f"{f['concentracao_atual']}")
            c2.metric("Soda desejada", f"{f['desejada']}")
            c3.metric("Litragem da cuba", f"{f['litragem_cuba']}")
            c4.metric("Colocar", f["qtd_colocar"])
            st.caption(f"⚠️ {f['nota_1']}")
            st.write("**Misturas de referência:**")
            for nome_mistura, qtd in f["misturas"]:
                st.write(f"- {nome_mistura} = {qtd}")
            st.caption(f"💡 {f['nota_2']}")

    with col_estoque:
        with st.container(border=True):
            st.subheader("🛢️ Estoque de Galões")
            df_pq = _load("PREPARO_QUIMICO")
            df_pq = df_pq[df_pq["setor"].astype(str).str.strip() == setor]
            if df_pq.empty:
                st.caption("Nenhum item cadastrado para este setor.")
            for _, r in df_pq.iterrows():
                nome_g = str(r["nome"]).strip()
                un_g = str(r["unidade"]).strip() or "L"
                val_g = _parse_num(r["estoque"])
                _linha_estoque_simples(
                    "PREPARO_QUIMICO", "estoque", nome_g, val_g, un_g,
                    chave=f"pq_{nome_g}", filtros={"setor": setor, "nome": nome_g},
                )

# ---------------------------------------------------------------------------
# TELA 2: CONTROLE DE PROCESSO (VERNIZ & PRIME)
# ---------------------------------------------------------------------------
def _pontos_atencao_processo(setor):
    """Olha a medição mais recente de cada produto (Verniz/Prime/Água D.I.)
    e lista quem está fora da faixa AGORA - não depende de estar no momento
    de salvar uma medição pra aparecer."""
    df_med = _load("MEDICOES_PROCESSO")
    if df_med.empty or "setor" not in df_med.columns:
        return []
    df_med = df_med[df_med["setor"].astype(str).str.strip() == setor]

    pontos = []
    for produto in ["Verniz", "Prime", "Água D.I."]:
        sub = df_med[df_med["produto"].astype(str).str.strip() == produto]
        if sub.empty:
            continue
        ultima = sub.iloc[-1]
        status = str(ultima.get("status_conformidade", ""))
        if "Fora" not in status and "🔴" not in status:
            continue
        if produto == "Água D.I.":
            valor = _parse_num(ultima.get("agua_di_us"))
            pontos.append(f"💧 **Água D.I.**: {valor:g} µS (limite máximo {AGUA_DI_LIMITE_US:g} µS)")
        else:
            teor = ultima.get("teor_solidos_pct", "?")
            temp = ultima.get("temperatura_c", "?")
            esp = ultima.get("espessura_um", "?")
            pontos.append(f"🧪 **{produto}**: teor {teor}% · {temp}°C · espessura {esp}µm")
    return pontos

def _tela_processo(setor):
    with st.container(border=True):
        pontos = _pontos_atencao_processo(setor)
        if pontos:
            st.markdown("### 🚨 Pontos de Atenção (última medição de cada parâmetro)")
            for p in pontos:
                st.error(p)
        else:
            st.markdown("### ✅ Pontos de Atenção")
            st.success("Nenhum parâmetro fora da faixa na última medição registrada.")

    st.info("🧪 **Controle de Processo Analítico** — Cálculo do Teor de Sólidos Secos (%) pela fórmula da balança: `Teor = [(I - G) / (H - G)] × 100`")

    col_verniz, col_prime, col_agua = st.columns(3)

    with col_verniz:
        with st.container(border=True):
            st.subheader("🧪 VERNIZ")
            st.caption("Faixas Ideais: **33 a 38%** | **10 a 15 °C** | **2.5 a 3.5 μm**")

            with st.form("form_verniz"):
                st.write("**Balança Analítica (g):**")
                vg_col, vh_col, vi_col = st.columns(3)
                with vg_col: v_g = st.number_input("Cadinho (G)", value=1.11, step=0.01, format="%.2f", key="v_g")
                with vh_col: v_h = st.number_input("+ Amostra (H)", value=3.11, step=0.01, format="%.2f", key="v_h")
                with vi_col: v_i = st.number_input("Seco Estufa (I)", value=1.87, step=0.01, format="%.2f", key="v_i")

                v_teor = (((v_i - v_g) / (v_h - v_g)) * 100.0) if (v_h - v_g) > 0 else 0.0
                if 33.0 <= v_teor <= 38.0:
                    v_status, v_sug = "🟢 Conforme", "Parâmetros normais."
                elif v_teor > 38.0:
                    v_status, v_sug = "🔴 Alto", "Diluir com álcool isopropílico."
                else:
                    v_status, v_sug = "🟡 Baixo", "Completar com verniz concentrado."

                st.metric("Teor de Sólidos Secos", f"{v_teor:.2f}%", v_status)

                vt_col, ve_col = st.columns(2)
                with vt_col: v_temp = st.number_input("Temperatura (°C)", value=12.5, step=0.1, key="v_temp")
                with ve_col: v_esp = st.number_input("Espessura (μm)", value=3.0, step=0.1, key="v_esp")

                v_acao = st.text_input("Ação / Como foi completado:", value=v_sug, key="v_acao")
                if st.form_submit_button("💾 Salvar Medição Verniz", use_container_width=True):
                    st_ok = "🟢 Conforme" if (33.0 <= v_teor <= 38.0 and 10.0 <= v_temp <= 15.0 and 2.5 <= v_esp <= 3.5) else "🔴 Fora da Faixa"
                    _append("MEDICOES_PROCESSO", [
                        datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"),
                        setor, "Verniz", v_g, v_h, v_i, f"{v_teor:.2f}", v_temp, v_esp, "", st_ok, v_acao
                    ])
                    st.success(f"✅ Medição do Verniz salva ({v_teor:.2f}%)!")
                    st.cache_data.clear()
                    st.rerun()

    with col_prime:
        with st.container(border=True):
            st.subheader("🧪 PRIME")
            st.caption("Faixas Ideais: **5,5 a 7,5%** | **20 a 25 °C** | **0.5 a 1.0 μm**")

            with st.form("form_prime"):
                st.write("**Balança Analítica (g):**")
                pg_col, ph_col, pi_col = st.columns(3)
                with pg_col: p_g = st.number_input("Cadinho (G)", value=1.13, step=0.01, format="%.2f", key="p_g")
                with ph_col: p_h = st.number_input("+ Amostra (H)", value=3.13, step=0.01, format="%.2f", key="p_h")
                with pi_col: p_i = st.number_input("Seco Estufa (I)", value=1.26, step=0.01, format="%.2f", key="p_i")

                p_teor = (((p_i - p_g) / (p_h - p_g)) * 100.0) if (p_h - p_g) > 0 else 0.0
                if 5.5 <= p_teor <= 7.5:
                    p_status, p_sug = "🟢 Conforme", "Parâmetros normais."
                elif p_teor > 7.5:
                    p_status, p_sug = "🔴 Alto", "Diluir com água D.I."
                else:
                    p_status, p_sug = "🟡 Baixo", "Completar com Prime concentrado."

                st.metric("Teor de Sólidos Secos", f"{p_teor:.2f}%", p_status)

                pt_col, pe_col = st.columns(2)
                with pt_col: p_temp = st.number_input("Temperatura (°C)", value=22.5, step=0.1, key="p_temp")
                with pe_col: p_esp = st.number_input("Espessura (μm)", value=0.8, step=0.1, key="p_esp")

                p_acao = st.text_input("Ação / Como foi completado:", value=p_sug, key="p_acao")
                if st.form_submit_button("💾 Salvar Medição Prime", use_container_width=True):
                    st_ok = "🟢 Conforme" if (5.5 <= p_teor <= 7.5 and 20.0 <= p_temp <= 25.0 and 0.5 <= p_esp <= 1.0) else "🔴 Fora da Faixa"
                    _append("MEDICOES_PROCESSO", [
                        datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"),
                        setor, "Prime", p_g, p_h, p_i, f"{p_teor:.2f}", p_temp, p_esp, "", st_ok, p_acao
                    ])
                    st.success(f"✅ Medição do Prime salva ({p_teor:.2f}%)!")
                    st.cache_data.clear()
                    st.rerun()

    with col_agua:
        with st.container(border=True):
            st.subheader("💧 ÁGUA D.I.")
            st.caption(f"Limite MÁXIMO: **{AGUA_DI_LIMITE_US:g} µS** — rígido, não é faixa ideal. Acima disso indica problema na máquina.")

            with st.form("form_agua_di"):
                a_valor = st.number_input("Valor medido (µS)", value=0.03, min_value=0.0, step=0.01, format="%.3f", key="a_valor")
                fora = a_valor > AGUA_DI_LIMITE_US
                st.metric("Leitura", f"{a_valor:.3f} µS", "🔴 Acima do limite" if fora else "🟢 Dentro do limite")

                a_acao = st.text_input(
                    "Ação:", value=("Verificar máquina — acima do limite" if fora else "Dentro do limite"), key="a_acao",
                )
                if st.form_submit_button("💾 Salvar Medição Água D.I.", use_container_width=True):
                    status_agua = "🔴 Fora da Faixa" if fora else "🟢 Conforme"
                    _append("MEDICOES_PROCESSO", [
                        datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"),
                        setor, "Água D.I.", "", "", "", "", "", "", f"{a_valor:.3f}", status_agua, a_acao,
                    ])
                    st.success(f"✅ Medição de Água D.I. salva ({a_valor:.3f} µS)!")
                    st.cache_data.clear()
                    st.rerun()

    st.markdown("---")
    st.subheader("📋 Relatório Histórico Diário de Processo")
    df_med = _load("MEDICOES_PROCESSO")
    if not df_med.empty and "setor" in df_med.columns:
        df_med_setor = df_med[df_med["setor"].astype(str).str.strip() == setor].iloc[::-1]
        if not df_med_setor.empty:
            st.dataframe(df_med_setor, use_container_width=True, hide_index=True)
        else:
            st.caption("Nenhuma medição registrada ainda para este setor.")

# ---------------------------------------------------------------------------
# TELA 3: LIMPEZA, FILTROS & CONSUMÍVEIS
# ---------------------------------------------------------------------------
def _tela_limpeza(setor):
    c_limp, c_cons = st.columns(2)
    with c_limp:
        with st.container(border=True):
            st.subheader("🧹 Rotinas de Limpeza & Filtros")
            df_rot = _load("ROTINA_LIMPEZA")
            df_rot = df_rot[df_rot["setor"].astype(str).str.strip() == setor]
            if not df_rot.empty:
                for _, r in df_rot.iterrows():
                    maq, tipo, freq = str(r["maquina"]).strip(), str(r["tipo"]).strip(), str(r["frequencia"]).strip()
                    dias_sem, dt_ult = str(r["dias_semana"]).strip(), str(r.get("data_ultima_execucao", "")).strip()
                    prox_str = _proxima_data(dt_ult, freq, dias_sem).strftime("%d/%m/%Y")
                    col_r1, col_r2 = st.columns([3, 1])
                    col_r1.write(f"**{maq}: {tipo}** ({freq}) | Próx: `{prox_str}`")
                    if col_r2.button("✅ Feito", key=f"r_{maq}_{tipo}"):
                        _atualizar("ROTINA_LIMPEZA", {"setor": setor, "maquina": maq, "tipo": tipo}, {"data_ultima_execucao": HOJE_STR, "proxima_data": prox_str})
                        st.success("Registrado!")
                        st.cache_data.clear()
                        st.rerun()

            st.markdown("---")
            st.write("**💧 Filtros:**")
            df_fil = _load("FILTROS")
            df_fil = df_fil[df_fil["setor"].astype(str).str.strip() == setor]
            if not df_fil.empty:
                for _, r in df_fil.iterrows():
                    nome_f, maq_f, esp_f = str(r["nome"]).strip(), str(r["maquina"]).strip(), str(r["especificacao"]).strip()
                    freq_f, dt_ult_f = str(r["frequencia_troca"]).strip(), str(r.get("data_ultima_troca", "")).strip()
                    prox_f_str = _proxima_data(dt_ult_f, freq_f, "").strftime("%d/%m/%Y")
                    col_f1, col_f2 = st.columns([3, 1])
                    col_f1.write(f"**{maq_f}: {nome_f}** ({esp_f}) | Próx: `{prox_f_str}`")
                    if col_f2.button("🔄 Trocar", key=f"f_{maq_f}_{nome_f}"):
                        _atualizar("FILTROS", {"setor": setor, "nome": nome_f, "maquina": maq_f}, {"data_ultima_troca": HOJE_STR, "proxima_troca": prox_f_str})
                        st.success("Filtro trocado!")
                        st.cache_data.clear()
                        st.rerun()

    with c_cons:
        with st.container(border=True):
            st.subheader("⚡ Consumíveis Críticos")
            df_con = _load("CONSUMIVEIS")
            df_con = df_con[df_con["setor"].astype(str).str.strip() == setor]
            if not df_con.empty:
                for _, r in df_con.iterrows():
                    nome_c = str(r["nome"]).strip()
                    est_c = _parse_num(r["estoque"])
                    _linha_estoque_simples(
                        "CONSUMIVEIS", "estoque", nome_c, est_c, "und",
                        chave=f"con_{nome_c}", filtros={"setor": setor, "nome": nome_c},
                    )

# ---------------------------------------------------------------------------
# TELA: POLIMENTO (setor Surfaçagem) - 3 polidoras, registro por lote/toque
# ---------------------------------------------------------------------------
def _registrar_ocorrencia_polimento(setor, polidora, material, qtd, tipo, conferente):
    """Grava a ocorrência e avisa por toast (flutuante, não empurra o layout)
    - SEM st.rerun()/limpar cache do app inteiro. Um clique de registro não
    pode recarregar o app inteiro (Chamados, Dashboard, todos os setores);
    só invalida o cache de dados do Controle Setores, e o próprio ciclo de
    rerun que o Streamlit já faz depois de qualquer clique/Enter mostra o
    dado fresco no próximo toque - sem tela piscando nem trocar de aba.
    Também NÃO chama _load.clear(): isso limparia o cache de TODAS as
    entidades (Insumos, Preparo Químico, etc.), forçando buscar tudo nas
    planilhas de novo - caro. O cache de 10s expira sozinho; a gravação
    em si (linha abaixo) já é imediata e definitiva."""
    qtd_fmt = int(qtd) if float(qtd).is_integer() else qtd
    _append("POLIMENTO_OCORRENCIAS", [
        setor, datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"), polidora,
        material, qtd_fmt, tipo, (conferente or "").strip() or "—",
    ])
    st.toast(f"✅ {polidora} · {material} · qtd {qtd_fmt}")

def _on_lote_submit(setor, polidora, material, qtd_key, tipo_key, conf_key):
    """Callback do campo 'Qtd lote' - dispara ao apertar Enter (ou sair do
    campo), sem precisar de um botão separado de confirmar."""
    qtd_txt = st.session_state.get(qtd_key, "")
    st.session_state[qtd_key] = ""  # limpa o campo pro próximo registro
    qtd = _parse_num(qtd_txt, padrao=None)
    if qtd is None or qtd <= 0:
        if qtd_txt.strip():
            st.toast(f"⚠️ Quantidade inválida para {material}: '{qtd_txt}'")
        return
    tipo_val = st.session_state.get(tipo_key, TIPOS_MA_POLIMENTO[0])
    conferente_val = st.session_state.get(conf_key, "")
    _registrar_ocorrencia_polimento(setor, polidora, material, qtd, tipo_val, conferente_val)

def _card_polidora(setor, polidora, df_oc, df_discos):
    sub = df_oc[df_oc["polidora"] == polidora]
    total = sub["quantidade_num"].sum() if not sub.empty else 0.0
    pior_material = sub.groupby("material")["quantidade_num"].sum().idxmax() if not sub.empty else "—"

    # Borda/badge colorida pelo volume de rejeito da polidora - mesma
    # linguagem visual do resto do app (verde/laranja/vermelho).
    c = tema.cores()
    if total <= 0:
        cor_card = "#10B981"
    elif total <= 5:
        cor_card = "#F59E0B"
    else:
        cor_card = "#EF4444"

    with st.container(border=True):
        st.markdown(
            f'<div style="border-left:6px solid {cor_card}; padding-left:10px; margin-bottom:8px; '
            f'display:flex; justify-content:space-between; align-items:center;">'
            f'<span style="font-size:1.15rem; font-weight:800; color:{c["texto"]};">{polidora}</span>'
            f'<span style="background:{cor_card}22; color:{cor_card}; padding:3px 12px; '
            f'border-radius:9999px; font-size:0.75rem; font-weight:800;">{total:g} lentes ativas</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        c1, c2 = st.columns(2)
        c1.metric("Lentes c/ polimento ruim", f"{total:g}")
        c2.metric("Material mais problemático", pior_material)

        tipo = st.selectbox("Tipo de má-polimento", TIPOS_MA_POLIMENTO, key=f"pol_tipo_{polidora}")
        conferente = st.text_input("Conferente", key=f"pol_conf_{polidora}", placeholder="Quem conferiu")

        st.markdown("**Apontar material rejeitado:**")
        for material in MATERIAIS_POLIMENTO:
            cor_mat = _CORES_MATERIAL.get(material, c["texto_muted"])
            total_mat = sub[sub["material"] == material]["quantidade_num"].sum() if not sub.empty else 0.0

            c_info, c_mais1, c_qtd = st.columns([2.3, 0.8, 1.9])
            with c_info:
                st.markdown(
                    f'<div style="display:flex; align-items:center; gap:6px; margin-top:6px;">'
                    f'<span style="width:10px; height:10px; border-radius:50%; background:{cor_mat}; flex-shrink:0;"></span>'
                    f'<span style="font-weight:700; color:{c["texto"]}; font-size:0.9rem;">{material}</span>'
                    f'</div>'
                    f'<div style="font-size:0.72rem; color:{c["texto_muted"]}; margin-left:16px;">Total: {total_mat:g} un</div>',
                    unsafe_allow_html=True,
                )
            with c_mais1:
                if st.button("+1", key=f"pol_mat1_{polidora}_{material}", use_container_width=True,
                             help=f"Registro de 1 toque para {material}"):
                    _registrar_ocorrencia_polimento(setor, polidora, material, 1, tipo, conferente)
            with c_qtd:
                qtd_key = f"pol_qtdmat_{polidora}_{material}"
                st.text_input(
                    f"Qtd lote {material}", key=qtd_key,
                    label_visibility="collapsed", placeholder="Qtd + Enter",
                    on_change=_on_lote_submit,
                    args=(setor, polidora, material, qtd_key, f"pol_tipo_{polidora}", f"pol_conf_{polidora}"),
                )

        st.markdown("---")
        linha_disco = df_discos[df_discos["polidora"] == polidora]
        dt_ultima = str(linha_disco.iloc[0]["data_ultima_troca"]).strip() if not linha_disco.empty else ""
        prox = _proxima_data(dt_ultima, "mensal", "")
        st.caption(f"Galão — última troca: `{dt_ultima or '—'}` · próxima: `{prox.strftime('%d/%m/%Y')}`")
        if st.button("Confirmar troca do galão hoje", key=f"pol_disco_{polidora}", use_container_width=True):
            nova_prox = _proxima_data(HOJE_STR, "mensal", "").strftime("%d/%m/%Y")
            _atualizar("POLIMENTO_DISCOS", {"setor": setor, "polidora": polidora},
                       {"data_ultima_troca": HOJE_STR, "proxima_troca": nova_prox})
            _load.clear()
            st.toast(f"✅ Troca do galão da {polidora} registrada hoje!")
            st.rerun()

def _tela_polimento(setor):
    st.info("💎 **Controle de Polimento** — registre por lote (digite a quantidade) ou por toque (+1). Sem status de aberto/resolvido: é um log histórico.")

    df_oc = _load("POLIMENTO_OCORRENCIAS")
    df_oc = df_oc[df_oc["setor"].astype(str).str.strip() == setor].copy()
    if not df_oc.empty:
        df_oc["quantidade_num"] = df_oc["quantidade"].apply(lambda v: _parse_num(v, 1.0))

    df_discos = _load("POLIMENTO_DISCOS")
    df_discos = df_discos[df_discos["setor"].astype(str).str.strip() == setor]

    cols = st.columns(3)
    for col, polidora in zip(cols, POLIDORAS):
        with col:
            _card_polidora(setor, polidora, df_oc, df_discos)

    st.markdown("---")
    st.subheader("📊 Indicadores")
    g1, g2 = st.columns(2)
    with g1:
        if not df_oc.empty:
            fig1 = _grafico_barra(df_oc.groupby("polidora")["quantidade_num"].sum(), "Lentes Reprovadas por Polidora")
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.write("**Lentes Reprovadas por Polidora**")
            st.caption("Sem registros ainda.")
    with g2:
        if not df_oc.empty:
            ranking_mat = df_oc.groupby("material")["quantidade_num"].sum().sort_values(ascending=False)
            fig2 = _grafico_barra(ranking_mat, "Ranking de Perda/Rejeição por Material", _CORES_MATERIAL)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.write("**Ranking de Perda/Rejeição por Material**")
            st.caption("Sem registros ainda.")

    st.markdown("---")
    st.subheader("📋 Log de Ocorrências")
    if not df_oc.empty:
        st.dataframe(df_oc.iloc[::-1].drop(columns=["quantidade_num"]), use_container_width=True, hide_index=True)
    else:
        st.caption("Nenhuma ocorrência registrada ainda.")

# ---------------------------------------------------------------------------
# Registro de sub-abas por setor - cada setor tem seu próprio conjunto, em
# vez de assumir que todo setor usa Insumos/Processo/Limpeza.
# ---------------------------------------------------------------------------
SETORES_ABAS = {
    "Anti Reflexo": [
        ("📦 Estoque de Insumos & Lotes", _tela_insumos),
        ("🧪 Controle de Processo (Verniz & Prime)", _tela_processo),
        ("🧹 Limpeza, Filtros & Consumíveis", _tela_limpeza),
        ("🧫 Preparo Químico", _tela_preparo_quimico),
    ],
    "Surfaçagem": [
        ("💎 Polimento", _tela_polimento),
    ],
}

def render():
    try:
        _garantir_abas()
    except Exception as e:
        st.error(f"Erro ao conectar com as abas de Controle de Setores: {e}")

    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.title("🏭 Controle de Setores")
    with col_t2:
        setor_selecionado = st.selectbox(
            "Setor Operacional:", list(SETORES_ABAS.keys()), index=0, key="cs_setor_topo",
        )

    st.markdown("---")

    abas_do_setor = SETORES_ABAS.get(setor_selecionado, [])
    if not abas_do_setor:
        st.info(f"Nenhuma sub-aba configurada ainda para o setor **{setor_selecionado}**.")
        return

    # st.tabs() tem uma limitação conhecida do Streamlit: perde a aba
    # selecionada a cada re-execução do script (o que acontece a cada
    # clique/Enter) e ainda renderiza o conteúdo de TODAS as sub-abas por
    # baixo dos panos mesmo quando só uma está visível. st.radio guarda a
    # escolha de verdade em session_state (não reseta sozinho) e só chama
    # a função da sub-aba realmente selecionada - mais rápido também.
    if len(abas_do_setor) == 1:
        titulo_unico, funcao_unica = abas_do_setor[0]
        st.subheader(titulo_unico)
        funcao_unica(setor_selecionado)
        return

    titulos = [titulo for titulo, _ in abas_do_setor]
    aba_escolhida = st.radio(
        "Seção", titulos, key=f"cs_subaba_{setor_selecionado}",
        horizontal=True, label_visibility="collapsed",
    )
    st.markdown("---")
    for titulo, funcao_tela in abas_do_setor:
        if titulo == aba_escolhida:
            funcao_tela(setor_selecionado)
            break
