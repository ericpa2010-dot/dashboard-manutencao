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
import gspread
from gspread.utils import rowcol_to_a1
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials

FUSO_BR = pytz.timezone("America/Sao_Paulo")
SETOR_PADRAO = "Anti Reflexo"

COBERTURA_VERMELHA = 60   # < 60 dias -> Crítico (2 meses de importação)
COBERTURA_AMARELA  = 120  # 60 a 120 dias -> Ponto de Compra
                          # >= 120 dias -> Verde Seguro

# Dias úteis por mês usados na projeção de compra (3/6/12 meses). Mude aqui
# se o ritmo real de produção for diferente.
DIAS_UTEIS_POR_MES = 22

HOJE_STR = datetime.now(FUSO_BR).strftime("%d/%m/%Y")

# Mesma paleta de cores do card de SLA (Dashboard & SLA / cartao_prioridade_jornada
# em app_manutencao.py) - reaproveitada aqui pra manter a mesma linguagem visual.
_CORES_SLA = {"red": "#EF4444", "orange": "#F59E0B", "green": "#22C55E", "gray": "#64748B"}

DADOS_TECNICOS_INSUMOS = {
    # Consumo/dia medido na prática (áudio + medição direta do operador),
    # substituindo o cálculo teórico do manual do fabricante. Setor Anti
    # Reflexo: 5 dias úteis/semana, 2 limpezas completas (quarta e sexta).
    "zircônio":        {"consumo_dia": 0.12,     "gramas_lote": 3.0, "unidade": "kg", "obs": "Pastilha 6g, virada e usada nos 2 lados (3g cada lado) por ciclo"},
    "zirconio":        {"consumo_dia": 0.12,     "gramas_lote": 3.0, "unidade": "kg", "obs": "Pastilha 6g, virada e usada nos 2 lados (3g cada lado) por ciclo"},
    "silício":         {"consumo_dia": 0.00368,  "gramas_lote": 5.0, "unidade": "kg", "obs": "2 potes: limpeza completa 2x/semana (5g cada) + reposição parcial 3x/semana (2,8g cada, só remove parte queimada)"},
    "silicio":         {"consumo_dia": 0.00368,  "gramas_lote": 5.0, "unidade": "kg", "obs": "2 potes: limpeza completa 2x/semana (5g cada) + reposição parcial 3x/semana (2,8g cada, só remove parte queimada)"},
    "cromo silício":   {"consumo_dia": 0.001,    "gramas_lote": 2.5, "unidade": "kg", "obs": "Trocado só nas 2 limpezas semanais (quarta e sexta), 2,5g cada"},
    "cromo silicio":   {"consumo_dia": 0.001,    "gramas_lote": 2.5, "unidade": "kg", "obs": "Trocado só nas 2 limpezas semanais (quarta e sexta), 2,5g cada"},
    "hidrofóbico":     {"consumo_dia": 40.0,    "gramas_lote": 0.0, "unidade": "und", "obs": "40 und/dia"},
    "hidrofobico":     {"consumo_dia": 40.0,    "gramas_lote": 0.0, "unidade": "und", "obs": "40 und/dia"},
    "crystal de quartz":{"consumo_dia": 2.9,    "gramas_lote": 0.0, "unidade": "und", "obs": "2,9 und/dia"},
    "ito":             {"consumo_dia": 0.02,    "gramas_lote": 2.5, "unidade": "kg", "obs": "2,5g por lote (processo pausado)"},
    "otb uv-xbt":      {"consumo_dia": 0.067,   "gramas_lote": 0.0, "unidade": "und", "obs": "2 und/mês"},
}

ENTIDADES = {
    "INSUMOS": {
        "headers": ["setor", "nome", "estoque_atual", "unidade", "consumo_dia_calculado", "gramas_por_lote", "status", "observacao"],
        # estoque_atual dos insumos em "kg" já semeado em GRAMAS inteiras
        # (0 = 0g, 6000 = 6kg, 1500 = 1,5kg) - mesma convenção da blindagem
        # de gravação em _tela_insumos.
        "seed": [
            ["Anti Reflexo", "Zircônio", 0, "kg", 0.12, 3.0, "ativo", "Pastilha 6g, virada e usada nos 2 lados (3g cada lado) por ciclo"],
            ["Anti Reflexo", "Silício", 6000, "kg", 0.00368, 5.0, "ativo", "2 potes: limpeza completa 2x/semana (5g cada) + reposição parcial 3x/semana (2,8g cada, só remove parte queimada)"],
            ["Anti Reflexo", "Cromo Silício", 0, "kg", 0.001, 2.5, "ativo", "Trocado só nas 2 limpezas semanais (quarta e sexta), 2,5g cada"],
            ["Anti Reflexo", "Hidrofóbico", 0.0, "und", 40, "", "ativo", "40 und/dia"],
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
        "headers": ["data_hora", "setor", "produto", "massa_cadinho_g", "massa_amostra_g", "massa_seco_g", "teor_solidos_pct", "temperatura_c", "espessura_um", "status_conformidade", "acao_completado"],
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
    no card de prioridade do Dashboard & SLA - já comprovado sem vazar HTML."""
    cor_hex = _CORES_SLA.get(cor_status, _CORES_SLA["gray"])
    pct_barra = max(0.0, min(100.0, pct_barra))
    rodape_html = f'<div style="font-size:0.8rem; color:#CBD5E1; margin-top:4px;">{rodape}</div>' if rodape else ""
    return textwrap.dedent(f"""
        <div style="background-color:#1E293B; border:2px solid {cor_hex}; padding:12px 15px; border-radius:12px; margin-top:6px;">
            <div style="font-weight:800; color:{cor_hex}; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.03em;">{titulo}</div>
            <div style="font-size:1.25rem; font-weight:800; color:{cor_hex}; margin:4px 0;">{valor_grande}</div>
            <div style="background-color:#334155; border-radius:6px; height:12px; width:100%; margin:8px 0; overflow:hidden;">
                <div style="background-color:{cor_hex}; width:{pct_barra:.1f}%; height:100%; border-radius:6px; transition: width 0.5s ease;"></div>
            </div>
            {rodape_html}
        </div>
    """).strip()

def _fmt_projecao(consumo_dia, dias, unidade):
    """Consumo projetado (consumo_dia x dias) convertido pra unidade de compra:
    pacotes de 1kg (arredondado pra cima) se unidade == kg, senão unidades."""
    total = consumo_dia * dias
    qtd = math.ceil(total) if total > 0 else 0
    if unidade == "kg":
        return f"{qtd} pacote(s) de 1kg"
    return f"{qtd} {unidade}"

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

            # Linha 3: ajuste direto - 1 campo + 1 botão. Insumos em kg
            # digitam SEMPRE em gramas (sem seletor de unidade) - fecha de
            # vez a ambiguidade kg/g que causava o bug de conversão.
            if unidade == "kg":
                label_campo, placeholder = "Novo estoque (g)", "Ex: 390"
                val_base_txt = str(int(round(estoque_g)))
            else:
                label_campo, placeholder = f"Novo estoque ({unidade})", "Ex: 2"
                val_base_txt = f"{estoque_raw:g}".replace(".", ",")

            # Key versionada: cada salvamento incrementa o contador (via
            # _bump_inp_versao), então o widget seguinte nasce "novo" e usa
            # o value= recém-calculado, sem violar a regra do Streamlit de
            # não reescrever session_state de um widget já instanciado.
            versao_inp = st.session_state.get(f"inp_{nome}_v", 0)
            col_inp, col_save = st.columns([3, 1])
            with col_inp:
                # text_input (não number_input) porque number_input só aceita
                # ponto como decimal - aqui aceitamos vírgula, e ignoramos
                # texto solto tipo "kg"/"g" digitado junto por engano.
                txt_val = st.text_input(
                    label_campo, value=val_base_txt, key=f"inp_{nome}_{versao_inp}",
                    label_visibility="collapsed", placeholder=placeholder,
                )
            with col_save:
                if st.button("💾 Salvar", key=f"btn_save_{nome}", use_container_width=True):
                    limpo = re.sub(r"[^0-9,.\-]", "", txt_val).strip()
                    novo_val = _parse_num(limpo, padrao=None)
                    if novo_val is None or novo_val < 0:
                        st.error("Valor inválido — use apenas números (ex: 390 ou 2).")
                    else:
                        if unidade == "kg":
                            val_gravar = int(round(novo_val))  # já digitado em gramas
                            val_exibicao = f"{val_gravar/1000:.3f} kg ({val_gravar} g)"
                        else:
                            val_gravar = novo_val
                            val_exibicao = f"{val_gravar:g} {unidade}"
                        _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": val_gravar})
                        # Evita a caixa ficar "presa" mostrando o texto digitado
                        # antes, mesmo depois de já ter salvo (sem reescrever a
                        # key do widget já instanciado - ver _bump_inp_versao).
                        _bump_inp_versao(nome)
                        st.success(f"Estoque de {nome} salvo como {val_exibicao}!")
                        st.cache_data.clear()
                        st.rerun()

            # Ações rápidas - discretas, escondidas por padrão
            if tem_acao_rapida:
                with st.expander("▸ Ações rápidas (baixa de lote)"):
                    if nome_k in ["zircônio", "zirconio"]:
                        b1, b2 = st.columns(2)
                        with b1:
                            if st.button("📤 -1 Pastilha (6g)", key=f"bx1_{nome}"):
                                novo_g = max(0, round(estoque_g - 6))
                                _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo_g})
                                _bump_inp_versao(nome)
                                st.success(f"Baixa de 6g salva! Novo saldo: {novo_g} g ({novo_g/1000:.3f} kg)")
                                st.cache_data.clear()
                                st.rerun()
                        with b2:
                            if st.button("📤 -2 Pastilhas (12g)", key=f"bx2_{nome}"):
                                novo_g = max(0, round(estoque_g - 12))
                                _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo_g})
                                _bump_inp_versao(nome)
                                st.success(f"Baixa de 12g salva! Novo saldo: {novo_g} g ({novo_g/1000:.3f} kg)")
                                st.cache_data.clear()
                                st.rerun()
                    elif nome_k in ["silício", "silicio"]:
                        if st.button("📤 -1 Lote (5g)", key=f"bx1_{nome}"):
                            novo_g = max(0, round(estoque_g - 5))
                            _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo_g})
                            _bump_inp_versao(nome)
                            st.success(f"Baixa de 5g salva! Novo saldo: {novo_g} g ({novo_g/1000:.3f} kg)")
                            st.cache_data.clear()
                            st.rerun()
                    elif nome_k in ["cromo silício", "cromo silicio"]:
                        if st.button("📤 -1 Troca (2,5g)", key=f"bx1_{nome}"):
                            novo_g = max(0, round(estoque_g - 2.5))
                            _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo_g})
                            _bump_inp_versao(nome)
                            st.success(f"Baixa de 2,5g salva! Novo saldo: {novo_g} g ({novo_g/1000:.3f} kg)")
                            st.cache_data.clear()
                            st.rerun()
            elif consumo_dia and consumo_dia > 0:
                st.caption(f"Consumo diário previsto: **{consumo_dia:g} {unidade}/dia**")

    if linhas_projecao:
        with st.expander("📈 Projeção de Compra (3 / 6 / 12 meses)"):
            st.caption(
                f"consumo/dia × dias úteis, usando {DIAS_UTEIS_POR_MES} dias úteis/mês "
                "(constante DIAS_UTEIS_POR_MES no topo do arquivo). Insumos sem "
                "consumo/dia definido não entram aqui."
            )
            st.dataframe(pd.DataFrame(linhas_projecao), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# TELA 2: CONTROLE DE PROCESSO (VERNIZ & PRIME)
# ---------------------------------------------------------------------------
def _tela_processo(setor):
    st.info("🧪 **Controle de Processo Analítico** — Cálculo do Teor de Sólidos Secos (%) pela fórmula da balança: `Teor = [(I - G) / (H - G)] × 100`")

    col_verniz, col_prime = st.columns(2)

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
                        setor, "Verniz", v_g, v_h, v_i, f"{v_teor:.2f}", v_temp, v_esp, st_ok, v_acao
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
                        setor, "Prime", p_g, p_h, p_i, f"{p_teor:.2f}", p_temp, p_esp, st_ok, p_acao
                    ])
                    st.success(f"✅ Medição do Prime salva ({p_teor:.2f}%)!")
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
                    c_a, c_b, c_c = st.columns([2, 1, 1])
                    c_a.write(f"**{nome_c}** (Atual: `{est_c:g}`)")
                    novo_est = c_b.number_input("Saldo", min_value=0.0, value=float(est_c), step=1.0, key=f"con_{nome_c}", label_visibility="collapsed")
                    if c_c.button("Salvar", key=f"bcon_{nome_c}"):
                        _atualizar("CONSUMIVEIS", {"setor": setor, "nome": nome_c}, {"estoque": novo_est})
                        st.success(f"{nome_c} salvo!")
                        st.cache_data.clear()
                        st.rerun()

def render():
    try:
        _garantir_abas()
    except Exception as e:
        st.error(f"Erro ao conectar com as abas de Controle de Setores: {e}")

    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.title("🏭 Controle de Setores")
    with col_t2:
        setor_selecionado = st.selectbox("Setor Operacional:", ["Anti Reflexo", "Surfaçagem", "Montagem", "Coloração"], index=0, key="cs_setor_topo")

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs([
        "📦 Estoque de Insumos & Lotes",
        "🧪 Controle de Processo (Verniz & Prime)",
        "🧹 Limpeza, Filtros & Consumíveis"
    ])

    with tab1: _tela_insumos(setor_selecionado)
    with tab2: _tela_processo(setor_selecionado)
    with tab3: _tela_limpeza(setor_selecionado)
