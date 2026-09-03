"""
Controle de Setores
-------------------
Aba adicional do painel de manutencao, separada do fluxo de chamados.

Organiza dados POR SETOR (o primeiro e "Anti Reflexo", mas a estrutura ja
suporta novos setores - basta semear linhas do novo setor na planilha; o
seletor de setor da aba se monta a partir dos valores distintos da coluna
"setor", sem mexer no codigo).

Armazenamento: Google Sheets, na MESMA planilha usada pelo app principal
(st.secrets["spreadsheet"]["url"]). Cada entidade e uma aba (worksheet)
propria. Se a aba nao existir, este modulo cria com o cabecalho exato e,
quando ha dados iniciais, ja semeia as linhas do "Anti Reflexo".

Cabecalhos EXATOS de cada aba (crie/edite direto na planilha se precisar):

  INSUMOS             : setor | nome | estoque_atual | unidade | consumo_dia_calculado | status | observacao
  PARAMETROS_PROCESSO : setor | produto | parametro | valor_min | valor_max | acao_se_acima | acao_se_abaixo
  ROTINA_LIMPEZA      : setor | maquina | tipo | frequencia | dias_semana | data_ultima_execucao | proxima_data
  FILTROS             : setor | nome | maquina | especificacao | frequencia_troca | data_ultima_troca | proxima_troca
  CONSUMIVEIS         : setor | nome | estoque | data_ultima_troca | motivo | observacao
  HISTORICO_REPOSICAO : setor | insumo | data_hora | quantidade_recebida | quantidade_anterior
  MEDICOES_PROCESSO   : setor | data | produto | parametro | valor | dentro_faixa | acao
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

# Setor usado para semear os dados iniciais e como fallback quando as abas
# ainda nao existem. A lista real do seletor vem dos valores distintos da
# coluna "setor" nas abas abaixo (ver _setores_existentes) - basta adicionar
# linhas de um novo setor na planilha para ele aparecer, sem mexer no codigo.
SETOR_PADRAO = "Anti Reflexo"
ENTIDADES_COM_SETOR = ["INSUMOS", "PARAMETROS_PROCESSO", "ROTINA_LIMPEZA",
                       "FILTROS", "CONSUMIVEIS"]

# Faixas fixas da barra de cobertura de estoque (em dias de producao).
COBERTURA_VERDE = 60   # >= 60 dias  -> verde
COBERTURA_AMARELA = 30  # 30 a 60 dias -> amarelo ; < 30 -> vermelho

HOJE_SEED = "03/09/2026"  # data de partida das rotinas/filtros iniciais

# ---------------------------------------------------------------------------
# Definicao das entidades (cabecalho + dados iniciais do "Anti Reflexo")
# ---------------------------------------------------------------------------
ENTIDADES = {
    "INSUMOS": {
        "headers": ["setor", "nome", "estoque_atual", "unidade",
                    "consumo_dia_calculado", "status", "observacao"],
        "seed": [
            ["Anti Reflexo", "Zirconio", 0, "kg", 0.24, "ativo", "a preencher"],
            ["Anti Reflexo", "Silicio", 0, "kg", 0.2, "ativo", "a preencher"],
            ["Anti Reflexo", "Cromo Silicio", 0, "kg", 0.00036, "ativo", "2,5 g/semana"],
            ["Anti Reflexo", "Hidrofobico", 0, "und", 40, "ativo", "consumo a validar na pratica"],
            ["Anti Reflexo", "Crystal de quartz", 50, "und", 2.9, "ativo", ""],
            ["Anti Reflexo", "ITO", 1.5, "kg", 0.02, "pausado", ""],
            ["Anti Reflexo", "Prime H-580", 2, "und", "", "ativo", "sem consumo/dia definido"],
            ["Anti Reflexo", "Verniz 150S", 3, "und", "", "ativo", "sem consumo/dia definido"],
            ["Anti Reflexo", "Verniz 150", 1, "und", "", "ativo", "sem consumo/dia definido"],
            ["Anti Reflexo", "OTB UV-XBT", 41, "und", 0.067, "ativo", "2/mes"],
        ],
    },
    "PARAMETROS_PROCESSO": {
        "headers": ["setor", "produto", "parametro", "valor_min", "valor_max",
                    "acao_se_acima", "acao_se_abaixo"],
        "seed": [
            ["Anti Reflexo", "Verniz", "teor_solidos", 33, 38,
             "diluir com alcool isopropilico", "completar com verniz concentrado"],
            ["Anti Reflexo", "Prime", "teor_solidos", 5.5, 7.5,
             "diluir com agua D.I.", "completar com Prime concentrado"],
            ["Anti Reflexo", "Verniz", "temperatura", 10, 15,
             "verificar resfriamento", "verificar aquecimento"],
            ["Anti Reflexo", "Prime", "temperatura", 10, 15,
             "verificar resfriamento", "verificar aquecimento"],
        ],
    },
    "ROTINA_LIMPEZA": {
        "headers": ["setor", "maquina", "tipo", "frequencia", "dias_semana",
                    "data_ultima_execucao", "proxima_data"],
        "seed": [
            ["Anti Reflexo", "SL-501", "soda/detergente", "semanal", "sexta", HOJE_SEED, ""],
            ["Anti Reflexo", "MC-380 X-2", "chapas + Ion Gun", "semanal", "quarta,sexta", HOJE_SEED, ""],
            ["Anti Reflexo", "MC-380 X-2", "EBG", "semanal", "", HOJE_SEED, ""],
        ],
    },
    "FILTROS": {
        "headers": ["setor", "nome", "maquina", "especificacao",
                    "frequencia_troca", "data_ultima_troca", "proxima_troca"],
        "seed": [
            ["Anti Reflexo", "Filtro quimico", "SL-501", '1u, 5"', "quinzenal", HOJE_SEED, ""],
            ["Anti Reflexo", "Filtro da maquina", "SL-501", '1u, 10"', "mensal", HOJE_SEED, ""],
            ["Anti Reflexo", "Pre-filtro agua de poco", "SL-501", '5u e 10u, 20"', "mensal", HOJE_SEED, ""],
        ],
    },
    "CONSUMIVEIS": {
        "headers": ["setor", "nome", "estoque", "data_ultima_troca", "motivo", "observacao"],
        "seed": [
            ["Anti Reflexo", "Filamento Ion Gun", 1, HOJE_SEED, "", ""],
            ["Anti Reflexo", "Filamento EBG", 3, HOJE_SEED, "", ""],
            ["Anti Reflexo", "Distribuidor de gas", 1, HOJE_SEED, "", "+1 em uso"],
        ],
    },
    "HISTORICO_REPOSICAO": {
        "headers": ["setor", "insumo", "data_hora", "quantidade_recebida", "quantidade_anterior"],
        "seed": [],
    },
    "MEDICOES_PROCESSO": {
        "headers": ["setor", "data", "produto", "parametro", "valor", "dentro_faixa", "acao"],
        "seed": [],
    },
}

_DIAS_SEMANA = {
    "segunda": 0, "segunda-feira": 0, "seg": 0,
    "terca": 1, "terça": 1, "terca-feira": 1, "terça-feira": 1, "ter": 1,
    "quarta": 2, "quarta-feira": 2, "qua": 2,
    "quinta": 3, "quinta-feira": 3, "qui": 3,
    "sexta": 4, "sexta-feira": 4, "sex": 4,
    "sabado": 5, "sábado": 5, "sab": 5,
    "domingo": 6, "dom": 6,
}
_FREQ_DIAS = {"diario": 1, "diaria": 1, "semanal": 7, "quinzenal": 15,
              "mensal": 30, "bimestral": 60, "trimestral": 90}


# ---------------------------------------------------------------------------
# Infra Google Sheets (cliente proprio - o modulo nao importa o app principal)
# ---------------------------------------------------------------------------
@st.cache_resource(ttl=300)
def _spreadsheet():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace(r"\n", "\n")
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_url(st.secrets["spreadsheet"]["url"])


def _ws(nome):
    """Retorna a worksheet da entidade; cria e semeia se ainda nao existir."""
    cfg = ENTIDADES[nome]
    ss = _spreadsheet()
    try:
        return ss.worksheet(nome)
    except WorksheetNotFound:
        ws = ss.add_worksheet(title=nome, rows=200, cols=max(12, len(cfg["headers"])))
        linhas = [cfg["headers"]] + cfg.get("seed", [])
        ws.append_rows(linhas, value_input_option="USER_ENTERED")
        return ws


@st.cache_resource(show_spinner=False)
def _garantir_abas():
    """Cria e semeia todas as 7 abas de uma vez no primeiro carregamento
    (roda so uma vez por processo)."""
    for nome in ENTIDADES:
        _ws(nome)
    return True


@st.cache_data(ttl=30, show_spinner=False)
def _load(nome):
    cols = ENTIDADES[nome]["headers"]
    ws = _ws(nome)
    df = pd.DataFrame(ws.get_all_records())
    if df.empty:
        df = pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols].copy()


def _append(nome, linha):
    _ws(nome).append_row(linha, value_input_option="USER_ENTERED")


def _atualizar(nome, filtros, updates):
    """Acha a 1a linha que casa com todos os `filtros` e aplica `updates`."""
    ws = _ws(nome)
    valores = ws.get_all_values()
    if not valores:
        return False
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
                    lote.append({"range": rowcol_to_a1(num_linha, idx[col] + 1),
                                 "values": [[novo]]})
            break
    if lote:
        ws.batch_update(lote, value_input_option="USER_ENTERED")
        return True
    return False


def _setores_existentes():
    """Lista de setores para o seletor: valores distintos da coluna `setor`
    nas abas de cadastro. Se nada existir ainda, cai no SETOR_PADRAO."""
    achados = set()
    for nome in ENTIDADES_COM_SETOR:
        try:
            df = _load(nome)
        except Exception:
            continue
        for v in df.get("setor", pd.Series(dtype=str)).astype(str).str.strip():
            if v and v.lower() not in ("nan", "none"):
                achados.add(v)
    return sorted(achados) if achados else [SETOR_PADRAO]


# ---------------------------------------------------------------------------
# Helpers de valor / data / render
# ---------------------------------------------------------------------------
def _num(v, default=0.0):
    try:
        s = str(v).replace(",", ".").strip()
        return float(s) if s.lower() not in ("", "-", "nan", "none") else default
    except (ValueError, TypeError):
        return default


def _fmt_num(v):
    f = float(v)
    return int(f) if f.is_integer() else round(f, 4)


def _hoje():
    return datetime.now(FUSO_BR).date()


def _agora_str():
    return datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S")


def _data(v):
    s = str(v).strip()
    if s.lower() in ("", "-", "nan", "none"):
        return None
    try:
        return pd.to_datetime(s, dayfirst=True).date()
    except Exception:
        return None


def _proxima(data_ultima, frequencia, dias_semana):
    """Proxima data a partir da ultima execucao + frequencia / dias da semana."""
    dias_semana = str(dias_semana or "").strip().lower()
    freq = str(frequencia or "").strip().lower()

    if dias_semana:
        alvos = set()
        for tok in re.split(r"[,;/]| e ", dias_semana):
            tok = tok.strip()
            if tok in _DIAS_SEMANA:
                alvos.add(_DIAS_SEMANA[tok])
        if alvos:
            base = data_ultima or _hoje()
            d = base + timedelta(days=1)
            for _ in range(21):
                if d.weekday() in alvos:
                    return d
                d += timedelta(days=1)

    if data_ultima is None:
        return None
    n = _FREQ_DIAS.get(freq)
    if n is None:
        m = re.search(r"(\d+)", freq)
        n = int(m.group(1)) if m else 30
    return data_ultima + timedelta(days=n)


def _barra(pct, cor):
    pct = max(0.0, min(100.0, pct))
    return (
        f'<div style="background-color:#334155;border-radius:6px;height:12px;'
        f'width:100%;margin:8px 0;overflow:hidden;">'
        f'<div style="background-color:{cor};width:{pct:.1f}%;height:100%;'
        f'border-radius:6px;"></div></div>'
    )


def _alerta_fora(produto, parametro, valor, faixa, acao):
    titulo = "Parametro fora da faixa"
    corpo_erro = f"**{produto} - {parametro.replace('_', ' ')} = {valor:g}** (faixa: {faixa})"
    _dialog = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
    if _dialog:
        @_dialog(f"⚠️ {titulo}")
        def _mostrar():
            st.error(corpo_erro)
            st.markdown(f"### Acao corretiva\n{acao}")
        _mostrar()
    else:
        st.error(f"⚠️ {corpo_erro}")
        st.warning(f"**Acao corretiva:** {acao}")
    try:
        st.toast(f"⚠️ {produto}: {acao}", icon="⚠️")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tela 1 - Estoque de insumos
# ---------------------------------------------------------------------------
def _tela_insumos(setor):
    df = _load("INSUMOS")
    df = df[df["setor"].astype(str).str.strip() == setor].copy()
    if df.empty:
        st.info("Nenhum insumo cadastrado para este setor.")
        return

    df["_consumo"] = df["consumo_dia_calculado"].apply(lambda v: _num(v, 0.0))
    df["_estoque"] = df["estoque_atual"].apply(lambda v: _num(v, 0.0))
    df["_pausado"] = df["status"].astype(str).str.strip().str.lower().eq("pausado")
    df["_dias"] = df.apply(
        lambda r: (r["_estoque"] / r["_consumo"])
        if (r["_consumo"] > 0 and not r["_pausado"]) else None,
        axis=1,
    )

    em_alerta = df[(~df["_pausado"]) & df["_dias"].notna() & (df["_dias"] < COBERTURA_AMARELA)]
    c1, c2, c3 = st.columns(3)
    c1.metric("Insumos ativos", int((~df["_pausado"]).sum()))
    c2.metric(f"Em alerta (< {COBERTURA_AMARELA} dias)", len(em_alerta))
    c3.metric("Pausados", int(df["_pausado"].sum()))
    st.markdown("---")

    for _, r in df.iterrows():
        _card_insumo(setor, r)


def _card_insumo(setor, r):
    nome = str(r["nome"])
    unidade = str(r["unidade"]).strip()
    estoque = r["_estoque"]
    consumo = r["_consumo"]
    dias = r["_dias"]

    if r["_pausado"]:
        cor, label, txt = "#64748B", "⏸️ Pausado", "Sem alerta"
        barra = _barra(100, "#334155")
    elif dias is None:
        cor, label, txt = "#64748B", "sem consumo/dia", "Cobertura nao calculada"
        barra = _barra(100, "#334155")
    else:
        if dias >= COBERTURA_VERDE:
            cor = "#22C55E"
        elif dias >= COBERTURA_AMARELA:
            cor = "#F59E0B"
        else:
            cor = "#EF4444"
        label = f"{consumo:g} {unidade}/dia"
        txt = f"{dias:.0f} dias de cobertura"
        barra = _barra(dias / COBERTURA_VERDE * 100, cor)

    obs = str(r.get("observacao", "")).strip()
    obs_html = f' &middot; <span style="color:#94A3B8;">{obs}</span>' if obs else ""
    st.markdown(
        f"""
        <div style="background-color:#1E293B;border:1px solid #334155;border-left:4px solid {cor};
                    border-radius:12px;padding:14px 16px;margin-bottom:6px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="font-weight:800;color:#F8FAFC;font-size:1rem;">{nome}</span>
            <span style="color:#94A3B8;font-size:0.8rem;font-weight:600;">{label}</span>
          </div>
          <div style="color:{cor};font-size:1.2rem;font-weight:800;margin-top:2px;">{txt}</div>
          {barra}
          <div style="color:#CBD5E1;font-size:0.82rem;">Estoque atual:
             <b>{estoque:g} {unidade}</b>{obs_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander(f"Atualizar / repor - {nome}"):
        ca, cb = st.columns(2)
        with ca:
            with st.form(f"est_{setor}_{nome}"):
                nova = st.number_input("Quantidade atual", min_value=0.0,
                                       value=float(estoque), step=1.0)
                if st.form_submit_button("Salvar quantidade"):
                    _atualizar("INSUMOS", {"setor": setor, "nome": nome},
                               {"estoque_atual": _fmt_num(nova)})
                    st.cache_data.clear()
                    st.rerun()
        with cb:
            with st.form(f"repo_{setor}_{nome}"):
                qtd = st.number_input("Quantidade recebida (reposicao)",
                                      min_value=0.0, value=0.0, step=1.0)
                if st.form_submit_button("Registrar reposicao"):
                    if qtd <= 0:
                        st.warning("Informe uma quantidade maior que zero.")
                    else:
                        novo = estoque + qtd
                        _append("HISTORICO_REPOSICAO",
                                [setor, nome, _agora_str(), _fmt_num(qtd), _fmt_num(estoque)])
                        _atualizar("INSUMOS", {"setor": setor, "nome": nome},
                                   {"estoque_atual": _fmt_num(novo)})
                        st.cache_data.clear()
                        st.rerun()


# ---------------------------------------------------------------------------
# Tela 2 - Controle de processo (teor de solidos / temperatura)
# ---------------------------------------------------------------------------
def _tela_processo(setor):
    alerta = st.session_state.pop("cs_alerta", None)
    if alerta:
        _alerta_fora(**alerta)
    if st.session_state.pop("cs_processo_ok", False):
        st.success("Medicao dentro da faixa e registrada.")

    par = _load("PARAMETROS_PROCESSO")
    par = par[par["setor"].astype(str).str.strip() == setor].copy()
    if par.empty:
        st.info("Nenhum parametro de processo cadastrado para este setor.")
        return

    par["produto"] = par["produto"].astype(str).str.strip()
    par["parametro"] = par["parametro"].astype(str).str.strip()
    produtos = sorted(par["produto"].unique())

    with st.form(f"proc_{setor}"):
        c1, c2, c3 = st.columns(3)
        with c1:
            try:
                data_m = st.date_input("Data", value=_hoje(), format="DD/MM/YYYY")
            except TypeError:
                data_m = st.date_input("Data", value=_hoje())
        with c2:
            produto = st.selectbox("Produto", produtos)
        with c3:
            params_disp = sorted(par[par["produto"] == produto]["parametro"].unique())
            parametro = st.selectbox("Parametro medido", params_disp)
        valor = st.number_input("Valor medido", min_value=0.0, step=0.1, format="%.2f")
        enviar = st.form_submit_button("Salvar medicao")

    if enviar:
        linha = par[(par["produto"] == produto) & (par["parametro"] == parametro)]
        if linha.empty:
            st.error("Parametro nao encontrado para esse produto.")
            return
        lo = _num(linha.iloc[0]["valor_min"])
        hi = _num(linha.iloc[0]["valor_max"])
        if valor > hi:
            dentro, acao = "nao", str(linha.iloc[0]["acao_se_acima"])
        elif valor < lo:
            dentro, acao = "nao", str(linha.iloc[0]["acao_se_abaixo"])
        else:
            dentro, acao = "sim", ""

        _append("MEDICOES_PROCESSO",
                [setor, data_m.strftime("%d/%m/%Y"), produto, parametro,
                 _fmt_num(valor), dentro, acao])

        if dentro == "nao":
            st.session_state["cs_alerta"] = {
                "produto": produto, "parametro": parametro, "valor": float(valor),
                "faixa": f"{lo:g} - {hi:g}", "acao": acao,
            }
        else:
            st.session_state["cs_processo_ok"] = True
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.markdown("##### Ultimas medicoes")
    med = _load("MEDICOES_PROCESSO")
    med = med[med["setor"].astype(str).str.strip() == setor]
    if med.empty:
        st.caption("Nenhuma medicao registrada ainda.")
    else:
        st.dataframe(med.iloc[::-1].head(15), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Tela 3 - Limpeza, filtros e consumiveis
# ---------------------------------------------------------------------------
def _linha_agenda(nome_ent, r, col_titulo, col_sub, proxima, filtros,
                  campo_data, campo_prox, freq, dias_sem):
    hoje = _hoje()
    if proxima is None:
        cor, sit = "#64748B", "Sem data de partida definida"
    elif proxima < hoje:
        cor, sit = "#EF4444", f"\U0001f534 Atrasado (previa: {proxima.strftime('%d/%m/%Y')})"
    elif proxima == hoje:
        cor, sit = "#F59E0B", "\U0001f7e1 Vence hoje"
    else:
        cor, sit = "#22C55E", f"\U0001f7e2 Proxima: {proxima.strftime('%d/%m/%Y')}"

    titulo = str(r[col_titulo])
    sub = str(r[col_sub]).strip()
    freq_txt = str(freq).strip()
    if str(dias_sem).strip():
        freq_txt = f"{freq_txt} ({dias_sem})" if freq_txt else str(dias_sem)

    st.markdown(
        f"""
        <div style="background-color:#1E293B;border:1px solid #334155;border-left:4px solid {cor};
                    border-radius:12px;padding:12px 16px;margin-bottom:6px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="font-weight:800;color:#F8FAFC;">{titulo}
              <span style="color:#94A3B8;font-weight:500;font-size:0.85rem;">
              {(' - ' + sub) if sub else ''}</span></span>
            <span style="color:#94A3B8;font-size:0.8rem;">{freq_txt}</span>
          </div>
          <div style="color:{cor};font-weight:700;margin-top:4px;">{sit}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    chave = re.sub(r"\W+", "_", f"{nome_ent}_{titulo}_{sub}")
    if st.button("Marcar como feito hoje", key=f"done_{chave}"):
        prox_nova = _proxima(hoje, freq, dias_sem)
        ups = {campo_data: hoje.strftime("%d/%m/%Y")}
        if prox_nova:
            ups[campo_prox] = prox_nova.strftime("%d/%m/%Y")
        _atualizar(nome_ent, filtros, ups)
        st.cache_data.clear()
        st.rerun()


def _tela_limpeza(setor):
    st.markdown("##### Rotinas de limpeza")
    rot = _load("ROTINA_LIMPEZA")
    rot = rot[rot["setor"].astype(str).str.strip() == setor]
    if rot.empty:
        st.caption("Nenhuma rotina cadastrada.")
    else:
        for _, r in rot.iterrows():
            _linha_agenda(
                "ROTINA_LIMPEZA", r, "maquina", "tipo",
                _proxima(_data(r["data_ultima_execucao"]), r["frequencia"], r["dias_semana"]),
                {"setor": setor, "maquina": str(r["maquina"]), "tipo": str(r["tipo"])},
                "data_ultima_execucao", "proxima_data", r["frequencia"], r["dias_semana"],
            )

    st.markdown("---")
    st.markdown("##### Filtros")
    fil = _load("FILTROS")
    fil = fil[fil["setor"].astype(str).str.strip() == setor]
    if fil.empty:
        st.caption("Nenhum filtro cadastrado.")
    else:
        for _, r in fil.iterrows():
            _linha_agenda(
                "FILTROS", r, "nome", "especificacao",
                _proxima(_data(r["data_ultima_troca"]), r["frequencia_troca"], ""),
                {"setor": setor, "nome": str(r["nome"])},
                "data_ultima_troca", "proxima_troca", r["frequencia_troca"], "",
            )

    st.markdown("---")
    st.markdown("##### Consumiveis")
    con = _load("CONSUMIVEIS")
    con = con[con["setor"].astype(str).str.strip() == setor]
    if con.empty:
        st.caption("Nenhum consumivel cadastrado.")
    else:
        for _, r in con.iterrows():
            nome = str(r["nome"])
            obs = str(r.get("observacao", "")).strip()
            ca, cb, cc = st.columns([3, 2, 2])
            ca.markdown(
                f"**{nome}**" + (f" &middot; <span style='color:#94A3B8'>{obs}</span>" if obs else ""),
                unsafe_allow_html=True,
            )
            nova = cb.number_input(
                "Estoque", min_value=0.0, value=_num(r["estoque"]), step=1.0,
                key=f"con_{setor}_{nome}", label_visibility="collapsed",
            )
            if cc.button("Salvar", key=f"consave_{setor}_{nome}"):
                _atualizar("CONSUMIVEIS", {"setor": setor, "nome": nome},
                           {"estoque": _fmt_num(nova)})
                st.cache_data.clear()
                st.rerun()


# ---------------------------------------------------------------------------
# Ponto de entrada da aba
# ---------------------------------------------------------------------------
def render():
    st.title("\U0001f3ed Controle de Setores")
    st.caption("Area compartilhada - todo o time pode visualizar e atualizar.")

    try:
        _garantir_abas()
    except Exception as e:
        st.error(f"Nao consegui preparar as abas da planilha: {e}")
        return

    # Nivel 1: escolha do setor (lista montada a partir dos dados da planilha).
    setores = _setores_existentes()
    setor = st.selectbox("Setor", setores, key="cs_setor")
    st.markdown("---")

    # Nivel 2: dentro do setor escolhido, as 3 sub-abas.
    aba_ins, aba_proc, aba_limp = st.tabs(
        ["Estoque de Insumos", "Controle de Processo", "Limpeza & Filtros"]
    )
    with aba_ins:
        try:
            _tela_insumos(setor)
        except Exception as e:
            st.error(f"Erro ao carregar insumos: {e}")
    with aba_proc:
        try:
            _tela_processo(setor)
        except Exception as e:
            st.error(f"Erro no controle de processo: {e}")
    with aba_limp:
        try:
            _tela_limpeza(setor)
        except Exception as e:
            st.error(f"Erro em limpeza & filtros: {e}")
