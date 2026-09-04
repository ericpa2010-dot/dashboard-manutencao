"""
Controle de Setores - Módulo Especialista
-----------------------------------------
Organiza dados por setor (Anti Reflexo, etc.)
1. Estoque de Insumos (kg <-> gramas, contagem de lotes, barra de 60 dias - lead time de compra, metas 3/6/12 meses)
2. Controle de Processo (Verniz & Prime com calculadora de balança analítica, temperaturas individuais, espessura e relatório diário)
3. Limpeza, Filtros e Consumíveis Críticos
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

COBERTURA_VERMELHA = 60   # < 60 dias -> Crítico (lead time de importação: 2 meses)
COBERTURA_AMARELA  = 120  # 60 a 120 dias -> Ponto de Pedido / Atenção
                          # >= 120 dias -> Verde Seguro

HOJE_STR = datetime.now(FUSO_BR).strftime("%d/%m/%Y")

ENTIDADES = {
    "INSUMOS": {
        "headers": [
            "setor", "nome", "estoque_atual", "unidade", "consumo_dia_calculado",
            "gramas_por_lote", "status", "observacao"
        ],
        "seed": [
            ["Anti Reflexo", "Zircônio", 0, "kg", 0.24, 3.0, "ativo", "Pastilha dupla face: 6g a cada 2 lotes (3g/lote)"],
            ["Anti Reflexo", "Silício", 0, "kg", 0.20, 5.0, "ativo", "5g por lote (dois recipientes de 2,5g)"],
            ["Anti Reflexo", "Cromo Silício", 0, "kg", 0.00071, 2.5, "ativo", "Troca 2x por semana (2,5g por troca)"],
            ["Anti Reflexo", "Hidrofóbico", 0, "und", 40, "", "ativo", "40 und/dia"],
            ["Anti Reflexo", "Crystal de quartz", 50, "und", 2.9, "", "ativo", "2,9 und/dia"],
            ["Anti Reflexo", "ITO", 1.5, "kg", 0.02, 2.5, "pausado", "2,5g por lote (processo pausado)"],
            ["Anti Reflexo", "Prime H-580", 2, "und", "", "", "ativo", ""],
            ["Anti Reflexo", "Verniz 150S", 3, "und", "", "", "ativo", ""],
            ["Anti Reflexo", "Verniz 150", 1, "und", "", "", "ativo", ""],
            ["Anti Reflexo", "Soda", 30, "L", "", "", "ativo", ""],
            ["Anti Reflexo", "Detergente ácido", 20, "L", "", "", "ativo", ""],
            ["Anti Reflexo", "Álcool isopropílico", 10, "L", "", "", "ativo", ""],
            ["Anti Reflexo", "OTB UV-XBT", 41, "und", 0.067, "", "ativo", "Consumo est.: 2/mês"],
        ],
    },
    "PARAMETROS_PROCESSO": {
        "headers": [
            "setor", "produto", "teor_min", "teor_max", "temp_min", "temp_max",
            "esp_min", "esp_max", "acao_acima", "acao_abaixo"
        ],
        "seed": [
            ["Anti Reflexo", "Verniz", 33.0, 38.0, 10.0, 15.0, 2.5, 3.5, "diluir com álcool isopropílico", "completar com verniz concentrado"],
            ["Anti Reflexo", "Prime", 5.5, 7.5, 20.0, 25.0, 0.5, 1.0, "diluir com água D.I.", "completar com Prime concentrado"],
        ],
    },
    "MEDICOES_PROCESSO": {
        "headers": [
            "data_hora", "setor", "produto", "massa_cadinho_g", "massa_amostra_g",
            "massa_seco_g", "teor_solidos_pct", "temperatura_c", "espessura_um",
            "status_conformidade", "acao_completado"
        ],
        "seed": [],
    },
    "ROTINA_LIMPEZA": {
        "headers": [
            "setor", "maquina", "tipo", "frequencia", "dias_semana",
            "data_ultima_execucao", "proxima_data"
        ],
        "seed": [
            ["Anti Reflexo", "SL-501", "Soda/Detergente", "semanal", "sexta", HOJE_STR, ""],
            ["Anti Reflexo", "MC-380 X-2", "Chapas + Ion Gun", "semanal", "quarta,sexta", HOJE_STR, ""],
            ["Anti Reflexo", "MC-380 X-2", "EBG", "semanal", "", HOJE_STR, ""],
        ],
    },
    "FILTROS": {
        "headers": [
            "setor", "nome", "maquina", "especificacao",
            "frequencia_troca", "data_ultima_troca", "proxima_troca"
        ],
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

@st.cache_data(ttl=15, show_spinner=False)
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
        if seed:
            return pd.DataFrame(seed, columns=cols)
        return pd.DataFrame(columns=cols)

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

def _num(v, default=0.0):
    try:
        s = str(v).replace(",", ".").strip()
        return float(s) if s.lower() not in ("", "-", "nan", "none") else default
    except (ValueError, TypeError):
        return default

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

def _tela_insumos(setor):
    st.markdown("""
        <div style="background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%); border: 1px solid #334155; border-radius: 12px; padding: 14px 18px; margin-bottom: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h4 style="margin: 0; color: #F8FAFC; font-size: 1.05rem;">📦 Gestão de Insumos, Cobertura & Lotes</h4>
                    <p style="margin: 4px 0 0 0; color: #94A3B8; font-size: 0.8rem;">
                        Conversão automática <b>kg ↔ gramas</b>, cálculo de <b>lotes</b> e ponto de pedido para <b>2 meses</b> (tempo de entrega do fornecedor).
                    </p>
                </div>
                <div style="text-align: right;">
                    <span style="background: rgba(239, 68, 68, 0.2); color: #FCA5A5; font-size: 0.72rem; font-weight: 800; padding: 3px 10px; border-radius: 6px; border: 1px solid rgba(239, 68, 68, 0.4);">
                        🔴 Crítico: &lt; 60 dias (2 meses)
                    </span>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    df = _load("INSUMOS")
    df = df[df["setor"].astype(str).str.strip() == setor].copy()
    if df.empty:
        st.info(f"Nenhum insumo cadastrado para o setor {setor}.")
        return

    for _, r in df.iterrows():
        nome = str(r["nome"]).strip()
        unidade = str(r["unidade"]).strip().lower()
        status = str(r["status"]).strip().lower()
        pausado = (status == "pausado")
        
        estoque_val = _num(r["estoque_atual"])
        consumo_dia = _num(r["consumo_dia_calculado"])
        gramas_lote = _num(r["gramas_por_lote"])
        obs = str(r.get("observacao", "")).strip()

        if unidade == "kg":
            estoque_kg = estoque_val
            estoque_g = estoque_val * 1000.0
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
            estoque_kg = None
            dias_cobertura = (estoque_val / consumo_dia) if (consumo_dia > 0 and not pausado) else None
            lotes_totais = None
            meta_3m_kg = consumo_dia * 90.0 if consumo_dia > 0 else None
            meta_6m_kg = consumo_dia * 180.0 if consumo_dia > 0 else None
            meta_12m_kg = consumo_dia * 365.0 if consumo_dia > 0 else None
            meta_3m_lotes = meta_6m_lotes = meta_12m_lotes = None
            txt_estoque_principal = f"{estoque_val:g} {unidade.upper()}"
            txt_estoque_secundario = ""

        if pausado:
            cor, txt_status_barra, pct_barra, cor_fundo_barra = "#64748B", "⏸️ Processo Pausado", 100.0, "#334155"
        elif dias_cobertura is None:
            cor, txt_status_barra, pct_barra, cor_fundo_barra = "#64748B", "Consumo diário a definir", 100.0, "#334155"
        elif dias_cobertura < COBERTURA_VERMELHA:
            cor, txt_status_barra = "#EF4444", f"🔴 {dias_cobertura:.0f} dias — CRÍTICO (< 2 meses para chegar!)"
            pct_barra = max(5.0, min(100.0, (dias_cobertura / COBERTURA_VERMELHA) * 50.0))
            cor_fundo_barra = "#EF4444"
        elif dias_cobertura < COBERTURA_AMARELA:
            cor, txt_status_barra = "#F59E0B", f"🟡 {dias_cobertura:.0f} dias — ATENÇÃO (Ponto de Compra)"
            pct_barra = 50.0 + ((dias_cobertura - 60) / 60.0) * 35.0
            cor_fundo_barra = "#F59E0B"
        else:
            cor, txt_status_barra = "#22C55E", f"🟢 {dias_cobertura:.0f} dias — SEGURO (> 4 meses garantidos)"
            pct_barra, cor_fundo_barra = 100.0, "#22C55E"

        txt_lotes_str = f" &bull; 🎯 <b>{lotes_totais:,.0f} lotes</b>".replace(",", ".") if lotes_totais else ""
        txt_dias_str = f"⏳ <b>{dias_cobertura:.0f} dias</b>" if dias_cobertura else ""
        
        st.markdown(f"""
            <div style="background-color: #1E293B; border: 1px solid #334155; border-left: 5px solid {cor}; border-radius: 12px; padding: 14px 16px; margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 1.1rem; font-weight: 800; color: #F8FAFC;">{nome}</span>
                            <span style="background: rgba(148, 163, 184, 0.15); color: #CBD5E1; font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 6px;">
                                {unidade.upper()}
                            </span>
                            {f'<span style="background: rgba(100, 116, 139, 0.3); color: #94A3B8; font-size: 0.7rem; padding: 2px 6px; border-radius: 4px;">Pausado</span>' if pausado else ''}
                        </div>
                        <div style="color: #94A3B8; font-size: 0.75rem; margin-top: 4px;">
                            {obs if obs else (f'Consumo: {consumo_dia:g} {unidade}/dia' if consumo_dia > 0 else '')}
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <div style="color: {cor}; font-size: 1.25rem; font-weight: 800;">
                            {txt_estoque_principal} <span style="color: #94A3B8; font-size: 0.8rem;">{txt_estoque_secundario}</span>
                        </div>
                        <div style="color: #CBD5E1; font-size: 0.8rem;">
                            {txt_dias_str} {txt_lotes_str}
                        </div>
                    </div>
                </div>
                <div style="margin: 10px 0 6px 0;">
                    <div style="display: flex; justify-content: space-between; font-size: 0.72rem; color: #94A3B8; margin-bottom: 3px;">
                        <span>Cobertura de Produção</span>
                        <span style="color: {cor}; font-weight: 700;">{txt_status_barra}</span>
                    </div>
                    <div style="background-color: #0F172A; border-radius: 6px; height: 10px; width: 100%; overflow: hidden; border: 1px solid #334155;">
                        <div style="background-color: {cor_fundo_barra}; width: {pct_barra:.1f}%; height: 100%; border-radius: 6px; transition: width 0.3s ease;"></div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        with st.expander(f"⚙️ Movimentar / Ver Metas — {nome}"):
            if meta_3m_kg:
                col_m1, col_m2, col_m3 = st.columns(3)
                col_m1.markdown(f"<div style='background:#0F172A; padding:8px 12px; border-radius:8px; border:1px solid #334155;'><span style='color:#94A3B8; font-size:0.75rem;'>🎯 Meta 3 Meses (90d):</span><br><b style='color:#38BDF8;'>{meta_3m_kg:,.2f} {unidade}</b> {f'<span style=\"color:#64748B; font-size:0.75rem;\">({meta_3m_lotes:,.0f} lotes)</span>' if meta_3m_lotes else ''}</div>".replace(",", "X").replace(".", ",").replace("X", "."), unsafe_allow_html=True)
                col_m2.markdown(f"<div style='background:#0F172A; padding:8px 12px; border-radius:8px; border:1px solid #334155;'><span style='color:#94A3B8; font-size:0.75rem;'>🎯 Meta 6 Meses (180d):</span><br><b style='color:#38BDF8;'>{meta_6m_kg:,.2f} {unidade}</b> {f'<span style=\"color:#64748B; font-size:0.75rem;\">({meta_6m_lotes:,.0f} lotes)</span>' if meta_6m_lotes else ''}</div>".replace(",", "X").replace(".", ",").replace("X", "."), unsafe_allow_html=True)
                col_m3.markdown(f"<div style='background:#0F172A; padding:8px 12px; border-radius:8px; border:1px solid #334155;'><span style='color:#94A3B8; font-size:0.75rem;'>🎯 Meta 12 Meses (365d):</span><br><b style='color:#38BDF8;'>{meta_12m_kg:,.2f} {unidade}</b> {f'<span style=\"color:#64748B; font-size:0.75rem;\">({meta_12m_lotes:,.0f} lotes)</span>' if meta_12m_lotes else ''}</div>".replace(",", "X").replace(".", ",").replace("X", "."), unsafe_allow_html=True)

            col_act1, col_act2 = st.columns(2)
            with col_act1:
                st.markdown("##### 📤 Baixa de Consumo")
                sugestao_baixa = gramas_lote if (unidade == "kg" and gramas_lote > 0) else 1.0
                un_baixa = "gramas (g)" if unidade == "kg" else unidade
                qtd_baixa = st.number_input(f"Quantidade a retirar ({un_baixa})", min_value=0.0, value=float(sugestao_baixa), step=1.0, key=f"bx_{nome}")
                if st.button(f"Confirmar Baixa ({nome})", key=f"btn_bx_{nome}"):
                    if qtd_baixa > 0:
                        qtd_reduzir_oficial = (qtd_baixa / 1000.0) if unidade == "kg" else qtd_baixa
                        novo_saldo = max(0.0, estoque_val - qtd_reduzir_oficial)
                        _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo_saldo})
                        _append("HISTORICO_REPOSICAO", [setor, nome, "BAIXA_CONSUMO", datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"), -qtd_baixa, un_baixa, novo_saldo])
                        st.success(f"✅ Baixa de {qtd_baixa} {un_baixa} realizada! Novo saldo: {novo_saldo:.3f} {unidade}.")
                        st.cache_data.clear()
                        st.rerun()

            with col_act2:
                st.markdown("##### 📥 Entrada de Material")
                tipo_un_entrada = st.radio("Unidade da Entrada:", ["kg", "gramas (g)"] if unidade == "kg" else [unidade], horizontal=True, key=f"rad_{nome}")
                qtd_entrada = st.number_input(f"Quantidade recebida ({tipo_un_entrada})", min_value=0.0, value=0.0, step=1.0, key=f"ent_{nome}")
                if st.button(f"Registrar Entrada ({nome})", key=f"btn_ent_{nome}"):
                    if qtd_entrada > 0:
                        qtd_adicionar_oficial = (qtd_entrada / 1000.0) if tipo_un_entrada == "gramas (g)" else qtd_entrada
                        novo_saldo = estoque_val + qtd_adicionar_oficial
                        _atualizar("INSUMOS", {"setor": setor, "nome": nome}, {"estoque_atual": novo_saldo})
                        _append("HISTORICO_REPOSICAO", [setor, nome, "ENTRADA_COMPRA", datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"), qtd_entrada, tipo_un_entrada, novo_saldo])
                        st.success(f"✅ Entrada de {qtd_entrada} {tipo_un_entrada} registrada! Novo saldo: {novo_saldo:.3f} {unidade}.")
                        st.cache_data.clear()
                        st.rerun()

def _tela_processo(setor):
    st.markdown("""
        <div style="background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%); border: 1px solid #334155; border-radius: 12px; padding: 14px 18px; margin-bottom: 16px;">
            <h4 style="margin: 0; color: #F8FAFC; font-size: 1.05rem;">🧪 Controle de Processo — Verniz & Prime</h4>
            <p style="margin: 4px 0 0 0; color: #94A3B8; font-size: 0.8rem;">
                Cálculo do <b>Teor de Sólidos Secos (%)</b> por pesagem analítica (Cadinho G, Amostra H e Seco I), Temperatura e Espessura.
            </p>
        </div>
    """, unsafe_allow_html=True)

    col_verniz, col_prime = st.columns(2)

    with col_verniz:
        st.markdown("""
            <div style="background: #1E293B; border: 1px solid #334155; border-top: 4px solid #38BDF8; border-radius: 12px; padding: 14px; margin-bottom: 10px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <b style="color: #38BDF8; font-size: 1.05rem;">🧪 VERNIZ</b>
                    <span style="color: #94A3B8; font-size: 0.72rem;">Faixas: 33-38% | 10-15°C | 2.5-3.5 μm</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

        with st.form("form_verniz"):
            st.markdown("<span style='color:#38BDF8; font-weight:700; font-size:0.8rem;'>⚖️ Pesagem Balança Analítica</span>", unsafe_allow_html=True)
            vg_col, vh_col, vi_col = st.columns(3)
            with vg_col:
                v_g = st.number_input("Cadinho (G) [g]", value=1.11, step=0.01, format="%.2f", key="v_g")
            with vh_col:
                v_h = st.number_input("+ Amostra (H) [g]", value=3.11, step=0.01, format="%.2f", key="v_h")
            with vi_col:
                v_i = st.number_input("Seco Estufa (I) [g]", value=1.87, step=0.01, format="%.2f", key="v_i")

            if (v_h - v_g) > 0:
                v_teor = ((v_i - v_g) / (v_h - v_g)) * 100.0
            else:
                v_teor = 0.0

            if 33.0 <= v_teor <= 38.0:
                v_status_teor, v_cor_teor, v_acao_sugerida = "🟢 Conforme", "#4ADE80", "Nenhum ajuste necessário."
            elif v_teor > 38.0:
                v_status_teor, v_cor_teor, v_acao_sugerida = "🔴 Alto", "#F87171", "Diluir com álcool isopropílico."
            else:
                v_status_teor, v_cor_teor, v_acao_sugerida = "🟡 Baixo", "#FBBF24", "Completar com verniz concentrado."

            st.markdown(f"""
                <div style="background: #0F172A; border: 1px solid #334155; border-radius: 8px; padding: 8px 12px; margin: 8px 0; display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 0.8rem; color: #CBD5E1;">Teor de Sólidos Secos:</span>
                    <b style="color: {v_cor_teor}; font-size: 1.15rem;">{v_teor:.2f}% ({v_status_teor})</b>
                </div>
            """, unsafe_allow_html=True)

            v_col_t, v_col_e = st.columns(2)
            with v_col_t:
                v_temp = st.number_input("Temperatura (°C)", value=12.5, step=0.1, key="v_temp", help="Meta: 10 a 15 °C")
            with v_col_e:
                v_esp = st.number_input("Espessura (μm)", value=3.0, step=0.1, key="v_esp", help="Meta: 2.5 a 3.5 μm")

            v_acao = st.text_input("Ação realizada / Como foi completado:", value=v_acao_sugerida, key="v_acao")

            submit_verniz = st.form_submit_button("💾 Salvar Medição do Verniz", use_container_width=True)
            if submit_verniz:
                status_geral = "🟢 Conforme" if (33.0 <= v_teor <= 38.0 and 10.0 <= v_temp <= 15.0 and 2.5 <= v_esp <= 3.5) else "🔴 Fora da Faixa"
                _append("MEDICOES_PROCESSO", [
                    datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"),
                    setor, "Verniz", v_g, v_h, v_i, f"{v_teor:.2f}", v_temp, v_esp, status_geral, v_acao
                ])
                st.success(f"✅ Medição do Verniz registrada! ({v_teor:.2f}%)")
                st.cache_data.clear()
                st.rerun()

    with col_prime:
        st.markdown("""
            <div style="background: #1E293B; border: 1px solid #334155; border-top: 4px solid #C084FC; border-radius: 12px; padding: 14px; margin-bottom: 10px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <b style="color: #C084FC; font-size: 1.05rem;">🧪 PRIME</b>
                    <span style="color: #94A3B8; font-size: 0.72rem;">Faixas: 5,5-7,5% | 20-25°C | 0.5-1.0 μm</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

        with st.form("form_prime"):
            st.markdown("<span style='color:#C084FC; font-weight:700; font-size:0.8rem;'>⚖️ Pesagem Balança Analítica</span>", unsafe_allow_html=True)
            pg_col, ph_col, pi_col = st.columns(3)
            with pg_col:
                p_g = st.number_input("Cadinho (G) [g]", value=1.13, step=0.01, format="%.2f", key="p_g")
            with ph_col:
                p_h = st.number_input("+ Amostra (H) [g]", value=3.13, step=0.01, format="%.2f", key="p_h")
            with pi_col:
                p_i = st.number_input("Seco Estufa (I) [g]", value=1.26, step=0.01, format="%.2f", key="p_i")

            if (p_h - p_g) > 0:
                p_teor = ((p_i - p_g) / (p_h - p_g)) * 100.0
            else:
                p_teor = 0.0

            if 5.5 <= p_teor <= 7.5:
                p_status_teor, p_cor_teor, p_acao_sugerida = "🟢 Conforme", "#4ADE80", "Nenhum ajuste necessário."
            elif p_teor > 7.5:
                p_status_teor, p_cor_teor, p_acao_sugerida = "🔴 Alto", "#F87171", "Diluir com água D.I."
            else:
                p_status_teor, p_cor_teor, p_acao_sugerida = "🟡 Baixo", "#FBBF24", "Completar com Prime concentrado."

            st.markdown(f"""
                <div style="background: #0F172A; border: 1px solid #334155; border-radius: 8px; padding: 8px 12px; margin: 8px 0; display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 0.8rem; color: #CBD5E1;">Teor de Sólidos Secos:</span>
                    <b style="color: {p_cor_teor}; font-size: 1.15rem;">{p_teor:.2f}% ({p_status_teor})</b>
                </div>
            """, unsafe_allow_html=True)

            p_col_t, p_col_e = st.columns(2)
            with p_col_t:
                p_temp = st.number_input("Temperatura (°C)", value=22.5, step=0.1, key="p_temp", help="Meta: 20 a 25 °C")
            with p_col_e:
                p_esp = st.number_input("Espessura (μm)", value=0.8, step=0.1, key="p_esp", help="Meta: 0.5 a 1.0 μm")

            p_acao = st.text_input("Ação realizada / Como foi completado:", value=p_acao_sugerida, key="p_acao")

            submit_prime = st.form_submit_button("💾 Salvar Medição do Prime", use_container_width=True)
            if submit_prime:
                status_geral = "🟢 Conforme" if (5.5 <= p_teor <= 7.5 and 20.0 <= p_temp <= 25.0 and 0.5 <= p_esp <= 1.0) else "🔴 Fora da Faixa"
                _append("MEDICOES_PROCESSO", [
                    datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S"),
                    setor, "Prime", p_g, p_h, p_i, f"{p_teor:.2f}", p_temp, p_esp, status_geral, p_acao
                ])
                st.success(f"✅ Medição do Prime registrada! ({p_teor:.2f}%)")
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
    else:
        st.caption("Nenhuma medição registrada ainda.")

def _tela_limpeza(setor):
    col_l1, col_l2 = st.columns(2)

    with col_l1:
        st.markdown("##### 🧹 Rotinas de Limpeza & Troca de Filtros")
        df_rot = _load("ROTINA_LIMPEZA")
        df_rot = df_rot[df_rot["setor"].astype(str).str.strip() == setor]
        if not df_rot.empty:
            for _, r in df_rot.iterrows():
                maq = str(r["maquina"]).strip()
                tipo = str(r["tipo"]).strip()
                freq = str(r["frequencia"]).strip()
                dias_sem = str(r["dias_semana"]).strip()
                dt_ult = str(r.get("data_ultima_execucao", "")).strip()
                prox = _proxima_data(dt_ult, freq, dias_sem)
                prox_str = prox.strftime("%d/%m/%Y")

                st.markdown(f"""
                    <div style="background: #1E293B; border: 1px solid #334155; border-left: 4px solid #22C55E; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <b style="color: #F8FAFC; font-size: 0.85rem;">{maq}: {tipo}</b>
                            <div style="color: #94A3B8; font-size: 0.72rem;">Frequência: {freq} {f'({dias_sem})' if dias_sem else ''} &bull; Próxima: {prox_str}</div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                if st.button(f"✅ Feito hoje ({maq} - {tipo})", key=f"rot_{maq}_{tipo}"):
                    _atualizar("ROTINA_LIMPEZA", {"setor": setor, "maquina": maq, "tipo": tipo}, {
                        "data_ultima_execucao": HOJE_STR, "proxima_data": prox_str
                    })
                    st.success(f"Rotina de {tipo} na {maq} realizada!")
                    st.cache_data.clear()
                    st.rerun()

        st.markdown("##### 💧 Filtros")
        df_fil = _load("FILTROS")
        df_fil = df_fil[df_fil["setor"].astype(str).str.strip() == setor]
        if not df_fil.empty:
            for _, r in df_fil.iterrows():
                nome_f = str(r["nome"]).strip()
                maq_f = str(r["maquina"]).strip()
                esp_f = str(r["especificacao"]).strip()
                freq_f = str(r["frequencia_troca"]).strip()
                dt_ult_f = str(r.get("data_ultima_troca", "")).strip()
                prox_f = _proxima_data(dt_ult_f, freq_f, "")
                prox_f_str = prox_f.strftime("%d/%m/%Y")

                st.markdown(f"""
                    <div style="background: #1E293B; border: 1px solid #334155; border-left: 4px solid #F59E0B; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <b style="color: #F8FAFC; font-size: 0.85rem;">{maq_f}: {nome_f} ({esp_f})</b>
                            <div style="color: #FBBF24; font-size: 0.72rem;">Frequência: {freq_f} &bull; Próxima: {prox_f_str}</div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                if st.button(f"🔄 Trocar filtro ({nome_f})", key=f"fil_{maq_f}_{nome_f}"):
                    _atualizar("FILTROS", {"setor": setor, "nome": nome_f, "maquina": maq_f}, {
                        "data_ultima_troca": HOJE_STR, "proxima_troca": prox_f_str
                    })
                    st.success(f"Filtro {nome_f} da {maq_f} trocado!")
                    st.cache_data.clear()
                    st.rerun()

    with col_l2:
        st.markdown("##### ⚡ Consumíveis Críticos")
        df_con = _load("CONSUMIVEIS")
        df_con = df_con[df_con["setor"].astype(str).str.strip() == setor]
        if not df_con.empty:
            for _, r in df_con.iterrows():
                nome_c = str(r["nome"]).strip()
                est_c = _num(r["estoque"])
                obs_c = str(r.get("observacao", "")).strip()

                cor_c = "#EF4444" if est_c <= 1 else "#38BDF8"
                st.markdown(f"""
                    <div style="background: #1E293B; border: 1px solid #334155; border-radius: 8px; padding: 12px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <b style="color: #F8FAFC; font-size: 0.85rem;">{nome_c}</b>
                            <div style="color: {cor_c}; font-size: 0.75rem; font-weight: 700;">Estoque atual: {est_c:g} unidade(s)</div>
                            {f'<div style=\"color:#94A3B8; font-size:0.72rem;\">{obs_c}</div>' if obs_c else ''}
                        </div>
                    </div>
                """, unsafe_allow_html=True)

                col_num, col_btn = st.columns([2, 1])
                with col_num:
                    novo_est_c = st.number_input(f"Novo saldo ({nome_c})", min_value=0.0, value=float(est_c), step=1.0, key=f"num_con_{nome_c}", label_visibility="collapsed")
                with col_btn:
                    if st.button("Salvar", key=f"btn_con_{nome_c}"):
                        _atualizar("CONSUMIVEIS", {"setor": setor, "nome": nome_c}, {"estoque": novo_est_c})
                        st.success(f"Estoque de {nome_c} atualizado!")
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
        st.caption("Acompanhamento de Insumos, Parâmetros Analíticos de Processo e Manutenção Periódica.")
    with col_t2:
        setor_selecionado = st.selectbox("Setor Operacional:", ["Anti Reflexo", "Surfaçagem", "Montagem", "Coloração"], index=0, key="cs_setor_topo")

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs([
        "📦 Estoque de Insumos & Lotes",
        "🧪 Controle de Processo (Verniz & Prime)",
        "🧹 Limpeza, Filtros & Consumíveis"
    ])

    with tab1:
        _tela_insumos(setor_selecionado)
    with tab2:
        _tela_processo(setor_selecionado)
    with tab3:
        _tela_limpeza(setor_selecionado)
