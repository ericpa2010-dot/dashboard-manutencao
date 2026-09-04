"""
Controle de Setores - Módulo Prático & Direto
"""

import re
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

COBERTURA_VERMELHA = 60   # < 60 dias -> Crítico (2 meses de entrega do fornecedor)
COBERTURA_AMARELA  = 120  # 60 a 120 dias -> Atenção / Ponto de Pedido
                          # >= 120 dias -> Verde Seguro

HOJE_STR = datetime.now(FUSO_BR).strftime("%d/%m/%Y")

DADOS_TECNICOS_INSUMOS = {
    "zircônio":        {"consumo_dia": 0.24,    "gramas_lote": 3.0, "unidade": "kg", "obs": "Pastilha 6g a cada 2 lotes (3g/lote)"},
    "zirconio":        {"consumo_dia": 0.24,    "gramas_lote": 3.0, "unidade": "kg", "obs": "Pastilha 6g a cada 2 lotes (3g/lote)"},
    "silício":         {"consumo_dia": 0.20,    "gramas_lote": 5.0, "unidade": "kg", "obs": "5g por lote (dois potes de 2,5g)"},
    "silicio":         {"consumo_dia": 0.20,    "gramas_lote": 5.0, "unidade": "kg", "obs": "5g por lote (dois potes de 2,5g)"},
    "cromo silício":   {"consumo_dia": 0.00071, "gramas_lote": 2.5, "unidade": "kg", "obs": "Troca 2x por semana (2,5g por troca)"},
    "cromo silicio":   {"consumo_dia": 0.00071, "gramas_lote": 2.5, "unidade": "kg", "obs": "Troca 2x por semana (2,5g por troca)"},
    "hidrofóbico":     {"consumo_dia": 40.0,    "gramas_lote": 0.0, "unidade": "und", "obs": "40 und/dia"},
    "hidrofobico":     {"consumo_dia": 40.0,    "gramas_lote": 0.0, "unidade": "und", "obs": "40 und/dia"},
    "crystal de quartz":{"consumo_dia": 2.9,    "gramas_lote": 0.0, "unidade": "und", "obs": "2,9 und/dia"},
    "ito":             {"consumo_dia": 0.02,    "gramas_lote": 2.5, "unidade": "kg", "obs": "2,5g por lote (processo pausado)"},
    "otb uv-xbt":      {"consumo_dia": 0.067,   "gramas_lote": 0.0, "unidade": "und", "obs": "2 und/mês"},
}

ENTIDADES = {
    "INSUMOS": {
        "headers": ["setor", "nome", "estoque_atual", "unidade", "consumo_dia_calculado", "gramas_por_lote", "status", "observacao"],
        "seed": [
            ["Anti Reflexo", "Zircônio", 0.0, "kg", 0.24, 3.0, "ativo", "Pastilha 6g a cada 2 lotes (3g/lote)"],
            ["Anti Reflexo", "Silício", 0.0, "kg", 0.20, 5.0, "ativo", "5g por lote (dois recipientes de 2,5g)"],
            ["Anti Reflexo", "Cromo Silício", 0.0, "kg", 0.00071, 2.5, "ativo", "Troca 2x por semana (2,5g por troca)"],
            ["Anti Reflexo", "Hidrofóbico", 0.0, "und", 40, "", "ativo", "40 und/dia"],
            ["Anti Reflexo", "Crystal de quartz", 50.0, "und", 2.9, "", "ativo", "2,9 und/dia"],
            ["Anti Reflexo", "ITO", 1.5, "kg", 0.02, 2.5, "pausado", "2,5g por lote (processo pausado)"],
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

def _parse_numero(v, padrao=0.0):
    if v is None or pd.isna(v): return padrao
    s = str(v).strip().replace(" ", "")
    if s.lower() in ("", "-", "nan", "none", "null"): return padrao
    s = s.replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return padrao

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

# ---------------------------------------------------------------------------
# TELA 1: ESTOQUE DE INSUMOS PRÁTICO (DEFINIÇÃO DIRETA + BOTÃO ZERAR)
# ---------------------------------------------------------------------------
def _tela_insumos(setor):
    # Cabeçalho com botão para Zerar Todos os Insumos
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.markdown("""
            <div style="background: #1E293B; border: 1px solid #334155; border-radius: 10px; padding: 10px 14px; margin-bottom: 12px;">
                <b style="color: #38BDF8; font-size: 0.95rem;">📦 Gestão Prática de Insumos & Lotes</b>
                <div style="color: #94A3B8; font-size: 0.78rem; margin-top: 2px;">
                    Defina o estoque real de cada item abaixo (em kg ou gramas) e use os botões rápidos de 1 clique para baixar consumo.
                </div>
            </div>
        """, unsafe_allow_html=True)
    with col_h2:
        if st.button("🗑️ Zerar Todos os Insumos", use_container_width=True, help="Zera o estoque de todos os insumos para recomeçar o inventário limpo"):
            try:
                ws = _ws("INSUMOS")
                valores = ws.get_all_values()
                header = valores[0]
                idx_est = header.index("estoque_atual") if "estoque_atual" in header else 2
                updates = []
                for i in range(2, len(valores) + 1):
                    updates.append({"range": rowcol_to_a1(i, idx_est + 1), "values": [[0.0]]})
                if updates:
                    ws.batch_update(updates, value_input_option="RAW")
                st.success("✅ Todos os insumos foram zerados com sucesso!")
                st.cache_data.clear()
                st.rerun()
            except Exception as ex:
                st.error(f"Erro ao zerar: {ex}")

    df = _load("INSUMOS")
    df = df[df["setor"].astype(str).str.strip() == setor].copy()
    if df.empty:
        st.info(f"Nenhum insumo cadastrado para o setor {setor}.")
        return

    for _, r in df.iterrows():
        nome = str(r["nome"]).strip()
        nome_key = nome.lower().strip()
        unidade = str(r["unidade"]).strip().lower()
        status = str(r["status"]).strip().lower()
        pausado = (status == "pausado")
        
        estoque_raw = _parse_numero(r["estoque_atual"])
        obs_raw = str(r.get("observacao", "")).strip()

        # Dados técnicos garantidos
        if nome_key in DADOS_TECNICOS_INSUMOS:
            tec = DADOS_TECNICOS_INSUMOS[nome_key]
            unidade = tec["unidade"]
            consumo_dia = tec["consumo_dia"]
            gramas_lote = tec["gramas_lote"]
            obs = tec["obs"] if not obs_raw or obs_raw == "a preencher" else obs_raw
        else:
            consumo_dia = _parse_numero(r.get("consumo_dia_calculado", 0.0))
            gramas_lote = _parse_numero(r.get("gramas_por_lote", 0.0))
            obs = obs_raw

        # Se alguém digitou um valor absurdo de milhares, sanitiza para o valor real
        if unidade == "kg" and estoque_raw > 1000.0:
            estoque_kg = 0.0
            estoque_g = 0.0
        elif unidade == "kg":
            estoque_kg = estoque_raw
            estoque_g = estoque_raw * 1000.0
        else:
            estoque_kg = estoque_raw
            estoque_g = 0.0

        if unidade == "kg":
            dias_cobertura = (estoque_kg / consumo_dia) if (consumo_dia > 0 and not pausado) else None
            lotes_totais = (estoque_g / gramas_lote) if (gramas_lote > 0 and not pausado) else None
            meta_3m_kg = consumo_dia * 90.0 if consumo_dia > 0 else None
            meta_6m_kg = consumo_dia * 180.0 if consumo_dia > 0 else None
            meta_12m_kg = consumo_dia * 365.0 if consumo_dia > 0 else None
            meta_3m_lotes = (meta_3m_kg * 1000.0 / gramas_lote) if (meta_3m_kg and gramas_lote > 0) else None
            meta_6m_lotes = (meta_6m_kg * 1000.0 / gramas_lote) if (meta_6m_kg and gramas_lote > 0) else None
            meta_12m_lotes = (meta_12m_kg * 1000.0 / gramas_lote) if (meta_12m_kg and gramas_lote > 0) else None
            txt_estoque_principal = f"{estoque_kg:,.2f} kg".replace(",", "X").replace(".", ",").replace("X", ".")
            txt_estoque_secundario = f"({estoque_g:,.0f} g)".replace(",", ".")
        else:
            dias_cobertura = (estoque_raw / consumo_dia) if (consumo_dia > 0 and not pausado) else None
            lotes_totais = None
            meta_3m_kg = consumo_dia * 90.0 if consumo_dia > 0 else None
            meta_6m_kg = consumo_dia * 180.0 if consumo_dia > 0 else None
            meta_12m_kg = consumo_dia * 365.0 if consumo_dia > 0 else None
            meta_3m_lotes = meta_6m_lotes = meta_12m_lotes = None
            txt_estoque_principal = f"{estoque_raw:g} {unidade.upper()}"
            txt_estoque_secundario = ""

        # Status da barra
        if pausado:
            cor, txt_status_barra, pct_barra = "#64748B", "⏸️ Processo Pausado", 100.0
        elif dias_cobertura is None:
            cor, txt_status_barra, pct_barra = "#64748B", "Consumo diário a definir", 100.0
        elif dias_cobertura < COBERTURA_VERMELHA:
            cor, txt_status_barra = "#EF4444", f"🔴 {dias_cobertura:.0f} dias — CRÍTICO (< 2 meses de importação!)"
            pct_barra = max(5.0, min(100.0, (dias_cobertura / COBERTURA_VERMELHA) * 50.0))
        elif dias_cobertura < COBERTURA_AMARELA:
            cor, txt_status_barra = "#F59E0B", f"🟡 {dias_cobertura:.0f} dias — ATENÇÃO (Ponto de Compra)"
            pct_barra = 50.0 + ((dias_cobertura - 60) / 60.0) * 35.0
        else:
            cor, txt_status_barra = "#22C55E", f"🟢 {dias_cobertura:.0f} dias — SEGURO (> 4 meses garantidos)"
            pct_barra = 100.0

        txt_lotes_str = f" &bull; 🎯 <b>{lotes_totais:,.0f} lotes</b>".replace(",", ".") if lotes_totais else ""
        txt_dias_str = f"⏳ <b>{dias_cobertura:.0f} dias</b>" if dias_cobertura else ""

        # Card Visual Compacto
        st.markdown(f"""
            <div style="background-color: #1E293B; border: 1px solid #334155; border-left: 5px solid {cor}; border-radius: 10px; padding: 12px 16px; margin-top: 10px;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 1.1rem; font-weight: 800; color: #F8FAFC;">{nome}</span>
                            <span style="background: rgba(56, 189, 248, 0.15); color: #38BDF8; font-size: 0.72rem; font-weight: 800; padding: 2px 6px; border-radius: 4px;">{unidade.upper()}</span>
                            {f'<span style=\"background: #334155; color: #94A3B8; font-size: 0.7rem; padding: 2px 6px; border-radius: 4px;\">Pausado</span>' if pausado else ''}
                        </div>
                        <div style="color: #94A3B8; font-size: 0.75rem; margin-top: 2px;">{obs}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="color: {cor}; font-size: 1.3rem; font-weight: 800;">
                            {txt_estoque_principal} <span style="color: #94A3B8; font-size: 0.8rem;">{txt_estoque_secundario}</span>
                        </div>
                        <div style="color: #CBD5E1; font-size: 0.8rem;">
                            {txt_dias_str} {txt_lotes_str}
                        </div>
                    </div>
                </div>
                <div style="margin: 8px 0 4px 0;">
                    <div style="display: flex; justify-content: space-between; font-size: 0.72rem; color: #94A3B8; margin-bottom: 2px;">
                        <span>Cobertura de Produção</span>
                        <span style="color: {cor}; font-weight: 700;">{txt_status_barra}</span>
                    </div>
                    <div style="background-color: #0F172A; border-radius: 6px; height: 8px; width: 100%; overflow: hidden; border: 1px solid #334155;">
                        <div style="background-color: {cor}; width: {pct_barra:.1f}%; height: 100%; border-radius: 6px;"></div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        # Barra de Ações Práticas do Insumo (Sem expander, tudo direto!)
        col_act_esq, col_act_dir = st.columns([1, 1])

        # Ação Esquerda: Baixa Rápida de 1 Clique
        with col_act_esq:
            if nome_key in ["zircônio", "zirconio"]:
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("📤 - 1 Pastilha (6g / 2 lotes)", key=f"bx1_{nome}", use_container_width=True):
                        novo_s = max(0.0, estoque_kg - 0.006)
                        _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo_s})
                        _append("HISTORICO_REPOSICAO", [setor, nome, "BAIXA_PASTILHA", datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"), -6.0, "g", novo_s])
                        st.success(f"Baixa de 6g de {nome} registrada! Novo saldo: {novo_s:.3f} kg")
                        st.cache_data.clear()
                        st.rerun()
                with b2:
                    if st.button("📤 - 2 Pastilhas (12g)", key=f"bx2_{nome}", use_container_width=True):
                        novo_s = max(0.0, estoque_kg - 0.012)
                        _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo_s})
                        _append("HISTORICO_REPOSICAO", [setor, nome, "BAIXA_2PASTILHAS", datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"), -12.0, "g", novo_s])
                        st.success(f"Baixa de 12g de {nome} registrada! Novo saldo: {novo_s:.3f} kg")
                        st.cache_data.clear()
                        st.rerun()
            elif nome_key in ["silício", "silicio"]:
                if st.button("📤 - 1 Lote (5g)", key=f"bx1_{nome}", use_container_width=True):
                    novo_s = max(0.0, estoque_kg - 0.005)
                    _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo_s})
                    _append("HISTORICO_REPOSICAO", [setor, nome, "BAIXA_LOTE", datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"), -5.0, "g", novo_s])
                    st.success(f"Baixa de 5g de {nome} registrada! Novo saldo: {novo_s:.3f} kg")
                    st.cache_data.clear()
                    st.rerun()
            elif nome_key in ["cromo silício", "cromo silicio"]:
                if st.button("📤 - 1 Troca (2,5g)", key=f"bx1_{nome}", use_container_width=True):
                    novo_s = max(0.0, estoque_kg - 0.0025)
                    _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo_s})
                    _append("HISTORICO_REPOSICAO", [setor, nome, "BAIXA_TROCA", datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"), -2.5, "g", novo_s])
                    st.success(f"Baixa de 2,5g de {nome} registrada! Novo saldo: {novo_s:.3f} kg")
                    st.cache_data.clear()
                    st.rerun()
            else:
                st.caption(f"Consumo diário: {consumo_dia:g} {unidade}/dia")

        # Ação Direita: Definir Estoque Real Direto
        with col_act_dir:
            f_col1, f_col2, f_col3 = st.columns([2, 1, 2])
            with f_col1:
                val_sug = float(estoque_kg) if unidade == "kg" else float(estoque_raw)
                val_direto = st.number_input(f"Estoque Real", min_value=0.0, value=val_sug, step=0.1, key=f"num_real_{nome}", label_visibility="collapsed")
            with f_col2:
                un_escolhida = st.selectbox("Unidade", ["kg", "g"] if unidade == "kg" else [unidade], key=f"sel_un_{nome}", label_visibility="collapsed")
            with f_col3:
                if st.button("💾 Gravar", key=f"btn_set_{nome}", use_container_width=True):
                    valor_final_oficial = (val_direto / 1000.0) if un_escolhida == "g" else val_direto
                    _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": valor_final_oficial})
                    st.success(f"Estoque de {nome} atualizado para {valor_final_oficial:g} {unidade}!")
                    st.cache_data.clear()
                    st.rerun()

        st.markdown("<hr style='margin: 6px 0; border-color: #334155;'>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# TELA 2: CONTROLE DE PROCESSO (VERNIZ & PRIME)
# ---------------------------------------------------------------------------
def _tela_processo(setor):
    st.markdown("""
        <div style="background: #1E293B; border: 1px solid #334155; border-radius: 10px; padding: 10px 16px; margin-bottom: 12px;">
            <b style="color: #38BDF8; font-size: 0.95rem;">🧪 Controle de Processo Analítico</b>
            <div style="color: #94A3B8; font-size: 0.78rem; margin-top: 2px;">
                Cálculo instantâneo pela fórmula da balança: <b>Teor (%) = [(I - G) / (H - G)] × 100</b>
            </div>
        </div>
    """, unsafe_allow_html=True)

    col_verniz, col_prime = st.columns(2)

    with col_verniz:
        st.markdown("""
            <div style="background: #1E293B; border: 1px solid #334155; border-top: 4px solid #38BDF8; border-radius: 10px; padding: 12px; margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <b style="color: #38BDF8; font-size: 1.05rem;">🧪 VERNIZ</b>
                    <span style="color: #94A3B8; font-size: 0.72rem;">33-38% | 10-15°C | 2.5-3.5 μm</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

        with st.form("form_verniz"):
            vg_col, vh_col, vi_col = st.columns(3)
            with vg_col: v_g = st.number_input("Cadinho (G) [g]", value=1.11, step=0.01, format="%.2f", key="v_g")
            with vh_col: v_h = st.number_input("+ Amostra (H) [g]", value=3.11, step=0.01, format="%.2f", key="v_h")
            with vi_col: v_i = st.number_input("Seco Estufa (I) [g]", value=1.87, step=0.01, format="%.2f", key="v_i")

            v_teor = (((v_i - v_g) / (v_h - v_g)) * 100.0) if (v_h - v_g) > 0 else 0.0
            if 33.0 <= v_teor <= 38.0:
                v_cor, v_status, v_sug = "#4ADE80", "🟢 Conforme", "Parâmetros normais."
            elif v_teor > 38.0:
                v_cor, v_status, v_sug = "#F87171", "🔴 Alto", "Diluir com álcool isopropílico."
            else:
                v_cor, v_status, v_sug = "#FBBF24", "🟡 Baixo", "Completar com verniz concentrado."

            st.markdown(f"""
                <div style="background: #0F172A; border: 1px solid #334155; border-radius: 6px; padding: 6px 12px; margin: 6px 0; display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 0.8rem; color: #CBD5E1;">Teor Calculado:</span>
                    <b style="color: {v_cor}; font-size: 1.15rem;">{v_teor:.2f}% ({v_status})</b>
                </div>
            """, unsafe_allow_html=True)

            vt_col, ve_col = st.columns(2)
            with vt_col: v_temp = st.number_input("Temperatura (°C)", value=12.5, step=0.1, key="v_temp")
            with ve_col: v_esp = st.number_input("Espessura (μm)", value=3.0, step=0.1, key="v_esp")

            v_acao = st.text_input("Como foi completado / Ação:", value=v_sug, key="v_acao")
            if st.form_submit_button("💾 Salvar Medição Verniz", use_container_width=True):
                st_ok = "🟢 Conforme" if (33.0 <= v_teor <= 38.0 and 10.0 <= v_temp <= 15.0 and 2.5 <= v_esp <= 3.5) else "🔴 Fora da Faixa"
                _append("MEDICOES_PROCESSO", [
                    datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"),
                    setor, "Verniz", v_g, v_h, v_i, f"{v_teor:.2f}", v_temp, v_esp, st_ok, v_acao
                ])
                st.success(f"✅ Medição do Verniz gravada ({v_teor:.2f}%)!")
                st.cache_data.clear()
                st.rerun()

    with col_prime:
        st.markdown("""
            <div style="background: #1E293B; border: 1px solid #334155; border-top: 4px solid #C084FC; border-radius: 10px; padding: 12px; margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <b style="color: #C084FC; font-size: 1.05rem;">🧪 PRIME</b>
                    <span style="color: #94A3B8; font-size: 0.72rem;">5,5-7,5% | 20-25°C | 0.5-1.0 μm</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

        with st.form("form_prime"):
            pg_col, ph_col, pi_col = st.columns(3)
            with pg_col: p_g = st.number_input("Cadinho (G) [g]", value=1.13, step=0.01, format="%.2f", key="p_g")
            with ph_col: p_h = st.number_input("+ Amostra (H) [g]", value=3.13, step=0.01, format="%.2f", key="p_h")
            with pi_col: p_i = st.number_input("Seco Estufa (I) [g]", value=1.26, step=0.01, format="%.2f", key="p_i")

            p_teor = (((p_i - p_g) / (p_h - p_g)) * 100.0) if (p_h - p_g) > 0 else 0.0
            if 5.5 <= p_teor <= 7.5:
                p_cor, p_status, p_sug = "#4ADE80", "🟢 Conforme", "Parâmetros normais."
            elif p_teor > 7.5:
                p_cor, p_status, p_sug = "#F87171", "🔴 Alto", "Diluir com água D.I."
            else:
                p_cor, p_status, p_sug = "#FBBF24", "🟡 Baixo", "Completar com Prime concentrado."

            st.markdown(f"""
                <div style="background: #0F172A; border: 1px solid #334155; border-radius: 6px; padding: 6px 12px; margin: 6px 0; display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 0.8rem; color: #CBD5E1;">Teor Calculado:</span>
                    <b style="color: {p_cor}; font-size: 1.15rem;">{p_teor:.2f}% ({p_status})</b>
                </div>
            """, unsafe_allow_html=True)

            pt_col, pe_col = st.columns(2)
            with pt_col: p_temp = st.number_input("Temperatura (°C)", value=22.5, step=0.1, key="p_temp")
            with pe_col: p_esp = st.number_input("Espessura (μm)", value=0.8, step=0.1, key="p_esp")

            p_acao = st.text_input("Como foi completado / Ação:", value=p_sug, key="p_acao")
            if st.form_submit_button("💾 Salvar Medição Prime", use_container_width=True):
                st_ok = "🟢 Conforme" if (5.5 <= p_teor <= 7.5 and 20.0 <= p_temp <= 25.0 and 0.5 <= p_esp <= 1.0) else "🔴 Fora da Faixa"
                _append("MEDICOES_PROCESSO", [
                    datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"),
                    setor, "Prime", p_g, p_h, p_i, f"{p_teor:.2f}", p_temp, p_esp, st_ok, p_acao
                ])
                st.success(f"✅ Medição do Prime gravada ({p_teor:.2f}%)!")
                st.cache_data.clear()
                st.rerun()

    st.markdown("---")
    st.markdown("##### 📋 Relatório Histórico Diário de Processo")
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
        st.markdown("##### 🧹 Rotinas de Limpeza & Troca de Filtros")
        df_rot = _load("ROTINA_LIMPEZA")
        df_rot = df_rot[df_rot["setor"].astype(str).str.strip() == setor]
        if not df_rot.empty:
            for _, r in df_rot.iterrows():
                maq, tipo, freq = str(r["maquina"]).strip(), str(r["tipo"]).strip(), str(r["frequencia"]).strip()
                dias_sem, dt_ult = str(r["dias_semana"]).strip(), str(r.get("data_ultima_execucao", "")).strip()
                prox_str = _proxima_data(dt_ult, freq, dias_sem).strftime("%d/%m/%Y")
                col_r1, col_r2 = st.columns([3, 1])
                col_r1.markdown(f"**{maq}: {tipo}** ({freq}) &bull; Próxima: `{prox_str}`")
                if col_r2.button("✅ Feito", key=f"r_{maq}_{tipo}"):
                    _atualizar("ROTINA_LIMPEZA", {"setor": setor, "maquina": maq, "tipo": tipo}, {"data_ultima_execucao": HOJE_STR, "proxima_data": prox_str})
                    st.success("Registrado!")
                    st.cache_data.clear()
                    st.rerun()

        st.markdown("##### 💧 Filtros")
        df_fil = _load("FILTROS")
        df_fil = df_fil[df_fil["setor"].astype(str).str.strip() == setor]
        if not df_fil.empty:
            for _, r in df_fil.iterrows():
                nome_f, maq_f, esp_f = str(r["nome"]).strip(), str(r["maquina"]).strip(), str(r["especificacao"]).strip()
                freq_f, dt_ult_f = str(r["frequencia_troca"]).strip(), str(r.get("data_ultima_troca", "")).strip()
                prox_f_str = _proxima_data(dt_ult_f, freq_f, "").strftime("%d/%m/%Y")
                col_f1, col_f2 = st.columns([3, 1])
                col_f1.markdown(f"**{maq_f}: {nome_f}** ({esp_f}) &bull; Próxima: `{prox_f_str}`")
                if col_f2.button("🔄 Trocar", key=f"f_{maq_f}_{nome_f}"):
                    _atualizar("FILTROS", {"setor": setor, "nome": nome_f, "maquina": maq_f}, {"data_ultima_troca": HOJE_STR, "proxima_troca": prox_f_str})
                    st.success("Filtro trocado!")
                    st.cache_data.clear()
                    st.rerun()

    with c_cons:
        st.markdown("##### ⚡ Consumíveis Críticos")
        df_con = _load("CONSUMIVEIS")
        df_con = df_con[df_con["setor"].astype(str).str.strip() == setor]
        if not df_con.empty:
            for _, r in df_con.iterrows():
                nome_c = str(r["nome"]).strip()
                est_c = _parse_numero(r["estoque"])
                c_a, c_b, c_c = st.columns([2, 1, 1])
                c_a.markdown(f"**{nome_c}** (Atual: `{est_c:g}`)")
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
