import re
import sqlite3
import uuid
from datetime import date
from pathlib import Path
import streamlit as st
import pandas as pd

DB = Path(__file__).with_name("central.db")
ANEXOS_DIR = Path(__file__).with_name("anexos")
ANEXOS_DIR.mkdir(exist_ok=True)


def db():
    c = sqlite3.connect(DB)
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS materiais (
          id INTEGER PRIMARY KEY, codigo TEXT UNIQUE, descricao TEXT NOT NULL,
          categoria TEXT, subcategoria TEXT, fabricante TEXT, modelo TEXT,
          codigo_fabricante TEXT, dn TEXT, pn TEXT, material_fabricacao TEXT,
          tipo_conexao TEXT, acionamento TEXT, aplicacao TEXT, palavras_chave TEXT,
          descricao_tecnica TEXT, status TEXT DEFAULT 'Em revisão'
        );
        CREATE TABLE IF NOT EXISTS fornecedores (
          id INTEGER PRIMARY KEY, razao_social TEXT NOT NULL, nome_fantasia TEXT,
          cnpj TEXT, contato TEXT, email TEXT, telefone TEXT, site TEXT, observacoes TEXT
        );
        CREATE TABLE IF NOT EXISTS fornecimentos (
          id INTEGER PRIMARY KEY, material_id INTEGER NOT NULL, fornecedor_id INTEGER NOT NULL,
          tipo_relacao TEXT NOT NULL, fabricante_ofertado TEXT, modelo_ofertado TEXT,
          data_interacao TEXT, observacoes TEXT,
          FOREIGN KEY(material_id) REFERENCES materiais(id),
          FOREIGN KEY(fornecedor_id) REFERENCES fornecedores(id)
        );
        CREATE TABLE IF NOT EXISTS cotacoes (
          id INTEGER PRIMARY KEY, processo TEXT, data_cotacao TEXT, objeto TEXT,
          status TEXT, observacoes TEXT
        );
        CREATE TABLE IF NOT EXISTS cotacao_itens (
          id INTEGER PRIMARY KEY, cotacao_id INTEGER NOT NULL,
          material_id INTEGER NOT NULL, fornecedor_id INTEGER NOT NULL,
          quantidade REAL DEFAULT 1, unidade TEXT DEFAULT 'un',
          preco_unitario REAL NOT NULL, prazo_entrega TEXT, observacoes TEXT,
          FOREIGN KEY(cotacao_id) REFERENCES cotacoes(id),
          FOREIGN KEY(material_id) REFERENCES materiais(id),
          FOREIGN KEY(fornecedor_id) REFERENCES fornecedores(id)
        );
        CREATE TABLE IF NOT EXISTS anexos (
          id INTEGER PRIMARY KEY, entidade_tipo TEXT NOT NULL, entidade_id INTEGER NOT NULL,
          fornecedor_id INTEGER, tipo_documento TEXT, nome_original TEXT NOT NULL,
          arquivo_salvo TEXT NOT NULL, data_upload TEXT, observacoes TEXT
        );
        """)
        try:
            c.execute("ALTER TABLE anexos ADD COLUMN fornecedor_id INTEGER")
        except sqlite3.OperationalError:
            pass


def read(sql, params=()):
    with db() as c:
        return pd.read_sql_query(sql, c, params=params)


def write(sql, params=()):
    with db() as c:
        return c.execute(sql, params).lastrowid


def norm(texto):
    return " ".join((str(texto) if texto is not None else "").strip().lower().split())


def apenas_digitos(texto):
    return "".join(ch for ch in (texto or "") if ch.isdigit())


def idx_opcao(opcoes, valor):
    return opcoes.index(valor) if valor in opcoes else 0


def fmt_brl(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def parse_numero(val):
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace("R$", "").replace(" ", "").strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def achar_coluna_padrao(colunas, palavras_chave):
    for idx, col in enumerate(colunas):
        c_norm = norm(col)
        if any(p in c_norm for p in palavras_chave):
            return idx
    return 0


def extrair_specs_descricao(descricao):
    desc_s = str(descricao).strip()
    m_dn = re.search(r"DN\s*(\d+(?:\s*x\s*\d+)?)", desc_s, re.IGNORECASE)
    dn_val = m_dn.group(1) if m_dn else ""
    m_pn = re.search(r"PN\s*(\d+)", desc_s, re.IGNORECASE)
    pn_val = f"PN{m_pn.group(1)}" if m_pn else ""

    u = desc_s.upper()
    if u.endswith("- FD") or "FERRO FUNDIDO" in u:
        mat_val = "Ferro fundido dúctil"
    elif "AÇO" in u or "ACO" in u:
        mat_val = "Aço carbono"
    elif "INOX" in u:
        mat_val = "Aço inoxidável"
    elif "PEAD" in u:
        mat_val = "PEAD"
    elif "PVC" in u:
        mat_val = "PVC"
    else:
        mat_val = ""

    if u.startswith("TUBO"):
        cat_val = "Tubos"
    elif u.startswith(("CURVA", "TÊ", "TE ", "LUVA", "JUNTA", "TOCO", "EXTREMIDADE", "REDUÇÃO")):
        cat_val = "Conexões"
    elif u.startswith(("VÁLVULA", "VALVULA", "REGISTRO", "TAMPA")):
        cat_val = "Válvulas"
    else:
        cat_val = ""

    return dn_val, pn_val, mat_val, cat_val


def detectar_tabela_cotacoes_comparativa(df_raw):
    header_row = None
    for r in range(min(12, len(df_raw))):
        vals = [norm(v) for v in df_raw.iloc[r].tolist() if pd.notna(v)]
        if "descrição" in vals or "descricao" in vals:
            header_row = r
            break

    if header_row is None or header_row + 1 >= len(df_raw):
        return None

    row_h = df_raw.iloc[header_row]
    row_sub = df_raw.iloc[header_row + 1]

    forn_blocks = []
    for c in range(len(row_sub) - 1):
        s_cur = norm(row_sub.iloc[c]) if pd.notna(row_sub.iloc[c]) else ""
        s_nxt = norm(row_sub.iloc[c + 1]) if pd.notna(row_sub.iloc[c + 1]) else ""
        if s_cur == "nome" and ("cotação" in s_nxt or "cotacao" in s_nxt or "valor" in s_nxt):
            s_dt = norm(row_sub.iloc[c + 2]) if (c + 2 < len(row_sub) and pd.notna(row_sub.iloc[c + 2])) else ""
            forn_blocks.append((c, c + 1, c + 2 if "data" in s_dt else None))

    if not forn_blocks:
        return None

    col_ref, col_desc, col_unid, col_qtd, col_vunit = None, None, None, None, None
    for c, val in enumerate(row_h):
        v = norm(val)
        if v in ("ref.", "ref", "código", "codigo"):
            col_ref = c
        elif v in ("descrição", "descricao"):
            col_desc = c
        elif v in ("unidade", "unid", "und"):
            col_unid = c
        elif "quantidade" in v or v in ("qtd", "qtde"):
            col_qtd = c
        elif "valor unit" in v or "preço unit" in v or "preco unit" in v:
            col_vunit = c

    if col_desc is None:
        return None

    itens = []
    for r in range(header_row + 2, len(df_raw)):
        row = df_raw.iloc[r]
        desc = row.iloc[col_desc]
        if pd.isna(desc) or not str(desc).strip():
            continue
        desc_s = str(desc).strip()
        if norm(desc_s) in ("total", "subtotal", "total geral"):
            continue

        ref_s = str(row.iloc[col_ref]).strip() if (col_ref is not None and pd.notna(row.iloc[col_ref])) else ""
        unid_s = str(row.iloc[col_unid]).strip() if (col_unid is not None and pd.notna(row.iloc[col_unid])) else "un"
        qtd_v = parse_numero(row.iloc[col_qtd]) if col_qtd is not None else 1.0
        if qtd_v <= 0:
            qtd_v = 1.0
        vunit_v = parse_numero(row.iloc[col_vunit]) if col_vunit is not None else 0.0

        dn_val, pn_val, mat_val, cat_val = extrair_specs_descricao(desc_s)

        cotacoes_forn = []
        for c_nome, c_preco, c_data in forn_blocks:
            fn = row.iloc[c_nome]
            fp = row.iloc[c_preco]
            fd = row.iloc[c_data] if c_data is not None else None
            if pd.notna(fn) and str(fn).strip() and pd.notna(fp):
                p_num = parse_numero(fp)
                if p_num > 0:
                    dt_str = str(fd)[:10] if pd.notna(fd) else ""
                    cotacoes_forn.append({"fornecedor": str(fn).strip(), "preco": p_num, "data": dt_str})

        itens.append({
            "codigo": ref_s, "descricao": desc_s, "categoria": cat_val,
            "dn": dn_val, "pn": pn_val, "material": mat_val,
            "quantidade": qtd_v, "unidade": unid_s or "un",
            "valor_orcamento": vunit_v, "cotacoes": cotacoes_forn
        })

    return itens


def obter_ou_criar_material(descricao, codigo="", dn="", pn="", material_fab="", categoria="", fabricante=""):
    desc_limpa = str(descricao).strip()
    cod_limpo = str(codigo).strip() if pd.notna(codigo) else ""
    dn_limpo = str(dn).strip() if pd.notna(dn) else ""
    pn_limpo = str(pn).strip() if pd.notna(pn) else ""
    mat_limpo = str(material_fab).strip() if pd.notna(material_fab) else ""
    cat_limpa = str(categoria).strip() if pd.notna(categoria) else ""
    fab_limpo = str(fabricante).strip() if pd.notna(fabricante) else ""

    existentes = read("SELECT id, codigo, descricao, dn FROM materiais")
    if not existentes.empty:
        if cod_limpo:
            match_cod = existentes[existentes["codigo"].fillna("").apply(lambda x: norm(x) == norm(cod_limpo))]
            if not match_cod.empty:
                return int(match_cod.iloc[0]["id"]), False
        match_desc = existentes[
            existentes.apply(lambda r: norm(r["descricao"]) == norm(desc_limpa) and norm(r["dn"]) == norm(dn_limpo), axis=1)
        ]
        if not match_desc.empty:
            return int(match_desc.iloc[0]["id"]), False

    try:
        novo_id = write(
            "INSERT INTO materiais(codigo, descricao, categoria, fabricante, dn, pn, material_fabricacao, status) VALUES(?,?,?,?,?,?,?,'Em revisão')",
            (cod_limpo or None, desc_limpa, cat_limpa, fab_limpo, dn_limpo, pn_limpo, mat_limpo)
        )
    except sqlite3.IntegrityError:
        novo_id = write(
            "INSERT INTO materiais(descricao, categoria, fabricante, dn, pn, material_fabricacao, status) VALUES(?,?,?,?,?,?,'Em revisão')",
            (desc_limpa, cat_limpa, fab_limpo, dn_limpo, pn_limpo, mat_limpo)
        )
    return int(novo_id), True


def obter_ou_criar_fornecedor(nome_fornecedor):
    nome_limpo = str(nome_fornecedor).strip() or "Fornecedor Não Especificado"
    existentes = read("SELECT id, razao_social, nome_fantasia FROM fornecedores")
    if not existentes.empty:
        match = existentes[
            existentes.apply(
                lambda r: norm(r["razao_social"]) == norm(nome_limpo)
                or (r["nome_fantasia"] and norm(r["nome_fantasia"]) == norm(nome_limpo)),
                axis=1
            )
        ]
        if not match.empty:
            return int(match.iloc[0]["id"]), False
    return int(write("INSERT INTO fornecedores(razao_social) VALUES(?)", (nome_limpo,))), True


def salvar_arquivo_anexo(arquivo, entidade_tipo, entidade_id, tipo_documento, observacoes="", fornecedor_id=None):
    ext = Path(arquivo.name).suffix.lower()
    nome_unico = f"{entidade_tipo}_{entidade_id}_{uuid.uuid4().hex[:8]}{ext}"
    (ANEXOS_DIR / nome_unico).write_bytes(arquivo.getbuffer())
    write(
        """INSERT INTO anexos(entidade_tipo, entidade_id, fornecedor_id, tipo_documento,
           nome_original, arquivo_salvo, data_upload, observacoes) VALUES(?,?,?,?,?,?,?,?)""",
        (entidade_tipo, int(entidade_id), int(fornecedor_id) if fornecedor_id else None,
         tipo_documento, arquivo.name, nome_unico, str(date.today()), observacoes.strip())
    )


def remover_anexos_entidade(entidade_tipo, entidade_id):
    df_a = read("SELECT id, arquivo_salvo FROM anexos WHERE entidade_tipo=? AND entidade_id=?", (entidade_tipo, int(entidade_id)))
    for _, r in df_a.iterrows():
        arq = ANEXOS_DIR / r["arquivo_salvo"]
        if arq.exists():
            arq.unlink()
    write("DELETE FROM anexos WHERE entidade_tipo=? AND entidade_id=?", (entidade_tipo, int(entidade_id)))


def aplicar_estilo():
    st.markdown("""
    <style>
        .block-container { padding-top: 1.8rem; padding-bottom: 2rem; max-width: 1200px; }
        [data-testid="stSidebar"] { border-right: 1px solid rgba(128,128,128,0.2); }
        [data-testid="stSidebar"] .stRadio > div { gap: 0.35rem; }
        [data-testid="stSidebar"] .stRadio label {
            background-color: rgba(128,128,128,0.08); padding: 0.6rem 0.85rem;
            border-radius: 8px; border: 1px solid transparent; width: 100%;
        }
        [data-testid="stSidebar"] .stRadio label:hover {
            background-color: rgba(128,128,128,0.16); border-color: rgba(128,128,128,0.3);
        }
        [data-testid="stSidebar"] .stRadio label > div:first-child { display: none; }
        [data-testid="stMetric"] {
            background-color: rgba(128,128,128,0.07); padding: 0.8rem 1rem;
            border-radius: 10px; border: 1px solid rgba(128,128,128,0.18);
        }
        .sidebar-brand { padding: 0.4rem 0 0.8rem 0; border-bottom: 1px solid rgba(128,128,128,0.2); margin-bottom: 1rem; }
        .sidebar-brand h2 { margin: 0; font-size: 1.15rem; font-weight: 700; }
        .sidebar-brand p { margin: 0.2rem 0 0 0; font-size: 0.8rem; opacity: 0.75; }
    </style>
    """, unsafe_allow_html=True)


CATEGORIAS = ["", "Tubos", "Conexões", "Válvulas", "Atuadores", "Medidores", "Bombas", "Materiais elétricos", "Instrumentação", "Outros"]
MATERIAIS_FAB = ["", "Ferro fundido dúctil", "Aço carbono", "Aço inoxidável", "PVC", "PEAD", "Bronze", "Outro"]
CONEXOES = ["", "Flangeada", "Ponta e bolsa", "Roscada", "Soldável", "Wafer", "Lug", "Outro"]
ACIONAMENTOS = ["", "Manual", "Elétrico", "Pneumático", "Hidráulico", "Sem acionamento"]
APLICACOES = ["", "Água potável", "Esgoto", "Drenagem", "Industrial", "Outra"]
STATUS_MAT = ["Em revisão", "Validado", "Inativo"]
TIPOS_DOC = ["Proposta comercial / Orçamento", "Ficha técnica", "Catálogo", "Desenho técnico", "Certificado / Norma", "Outro"]
EXTENSOES_ACEITAS = ["pdf", "png", "jpg", "jpeg", "xlsx", "xls", "docx", "doc", "csv", "txt"]

st.set_page_config(page_title="Central de Materiais e Fornecedores", page_icon="🧰", layout="wide")
init()
aplicar_estilo()

tot_mat = read("SELECT COUNT(*) AS n FROM materiais")["n"].iloc[0]
tot_forn = read("SELECT COUNT(*) AS n FROM fornecedores")["n"].iloc[0]
tot_cot = read("SELECT COUNT(*) AS n FROM cotacoes")["n"].iloc[0]
tot_ax = read("SELECT COUNT(*) AS n FROM anexos")["n"].iloc[0]

with st.sidebar:
    st.markdown('<div class="sidebar-brand"><h2>🧰 Central de Suprimentos</h2><p>Materiais, Fornecedores & Cotações</p></div>', unsafe_allow_html=True)
    menu = st.radio(
        "Menu principal",
        ["🔍 Pesquisa & Catálogo", "📦 Materiais & Fornecedores", "💰 Cotações & Preços", "📎 Anexos & Backup"],
        label_visibility="collapsed"
    )
    st.divider()
    st.caption("RESUMO DO BANCO LOCAL")
    c_s1, c_s2 = st.columns(2)
    c_s1.metric("Materiais", int(tot_mat))
    c_s2.metric("Fornecedores", int(tot_forn))
    c_s3, c_s4 = st.columns(2)
    c_s3.metric("Cotações", int(tot_cot))
    c_s4.metric("Anexos", int(tot_ax))
    st.caption("Armazenamento 100% local (central.db)")


# ==============================================================================
# 1. PESQUISA & CATÁLOGO
# ==============================================================================
if menu == "🔍 Pesquisa & Catálogo":
    st.title("Pesquisa & Catálogo Técnico")
    st.caption("Consulte especificações, fornecedores homologados, histórico de preços e documentos.")

    with st.container(border=True):
        a, b, c = st.columns([3, 1.2, 0.8])
        q = a.text_input("Buscar material", placeholder="Digite descrição, código, fabricante, modelo ou palavra-chave...")
        df_cats = read("SELECT DISTINCT categoria FROM materiais WHERE categoria IS NOT NULL AND categoria<>'' ORDER BY categoria")
        cat = b.selectbox("Categoria", ["Todas"] + df_cats["categoria"].tolist())
        dn = c.text_input("DN", placeholder="Ex.: 400")

    sql = "SELECT * FROM materiais WHERE 1=1"
    p = []
    if q.strip():
        sql += " AND (descricao LIKE ? OR codigo LIKE ? OR fabricante LIKE ? OR modelo LIKE ? OR palavras_chave LIKE ? OR descricao_tecnica LIKE ?)"
        p += [f"%{q.strip()}%"] * 6
    if cat != "Todas":
        sql += " AND categoria=?"
        p.append(cat)
    if dn.strip():
        sql += " AND dn=?"
        p.append(dn.strip())

    rows = read(sql + " ORDER BY descricao", p)
    st.caption(f"Exibindo **{len(rows)}** material(is) encontrado(s)")

    if rows.empty:
        st.info("Nenhum material encontrado com esses filtros. Cadastre novos itens ou importe um orçamento pronto.")

    for _, m in rows.iterrows():
        badge = "🟢" if m.status == "Validado" else ("🟡" if m.status == "Em revisão" else "⚪")
        cod_txt = f"[{m.codigo}] " if m.codigo else ""
        titulo = f"{badge} {cod_txt}{m.descricao}  •  {m.categoria or 'Sem categoria'}  |  DN {m.dn or '—'}  |  PN {m.pn or '—'}"
        with st.expander(titulo):
            x, y = st.columns(2)
            x.write(f"**Código interno:** {m.codigo or 'Não informado'}")
            x.write(f"**Fabricante:** {m.fabricante or 'Não informado'}")
            x.write(f"**Modelo:** {m.modelo or 'Não informado'}")
            x.write(f"**Acionamento:** {m.acionamento or 'Não informado'}")
            y.write(f"**Material:** {m.material_fabricacao or 'Não informado'}")
            y.write(f"**Conexão:** {m.tipo_conexao or 'Não informado'}")
            y.write(f"**Aplicação:** {m.aplicacao or 'Não informado'}")
            y.write(f"**Status:** {m.status}")
            if m.descricao_tecnica:
                st.info(m.descricao_tecnica)

            t_forn, t_prec, t_doc = st.tabs(["🏢 Fornecedores vinculados", "💲 Histórico de preços & Orçamentos", "📄 Documentos técnicos"])

            with t_forn:
                rel = read(
                    """SELECT f.razao_social AS Fornecedor, r.tipo_relacao AS Relação,
                              r.fabricante_ofertado AS Fabricante, r.modelo_ofertado AS Modelo, r.data_interacao AS Data
                       FROM fornecimentos r JOIN fornecedores f ON f.id=r.fornecedor_id
                       WHERE r.material_id=? ORDER BY r.data_interacao DESC""",
                    (int(m.id),)
                )
                st.dataframe(rel, use_container_width=True, hide_index=True) if not rel.empty else st.caption("Sem fornecedores relacionados.")

            with t_prec:
                hist_cot = read(
                    """SELECT c.id AS cot_id, c.data_cotacao AS Data, c.processo AS Processo,
                              f.razao_social AS Fornecedor, ci.quantidade AS Qtd,
                              ci.unidade AS Unid, ci.preco_unitario AS Preço_Unit,
                              ci.prazo_entrega AS Prazo, ci.observacoes AS Obs
                       FROM cotacao_itens ci
                       JOIN cotacoes c ON c.id = ci.cotacao_id
                       JOIN fornecedores f ON f.id = ci.fornecedor_id
                       WHERE ci.material_id=?
                       ORDER BY ci.preco_unitario ASC, c.data_cotacao DESC""",
                    (int(m.id),)
                )
                if not hist_cot.empty:
                    df_h = hist_cot.drop(columns=["cot_id"]).copy()
                    df_h["Preço_Unit"] = df_h["Preço_Unit"].apply(fmt_brl)
                    st.dataframe(df_h, use_container_width=True, hide_index=True)

                    cot_ids = tuple(hist_cot["cot_id"].unique().tolist())
                    ph = ",".join(["?"] * len(cot_ids))
                    anexos_orc = read(
                        f"""SELECT a.id, a.entidade_id, a.nome_original, a.arquivo_salvo, a.data_upload,
                                   c.processo, f.razao_social AS fornecedor_nome
                            FROM anexos a
                            LEFT JOIN cotacoes c ON c.id = a.entidade_id
                            LEFT JOIN fornecedores f ON f.id = a.fornecedor_id
                            WHERE a.entidade_tipo='cotacao' AND a.entidade_id IN ({ph})
                            ORDER BY a.id DESC""",
                        cot_ids
                    )
                    if not anexos_orc.empty:
                        st.markdown("**Planilhas e propostas vinculadas**")
                        for _, ax_o in anexos_orc.iterrows():
                            caminho_o = ANEXOS_DIR / ax_o["arquivo_salvo"]
                            c_o1, c_o2 = st.columns([4, 1])
                            forn_txt = f" | Fornecedor: **{ax_o['fornecedor_nome']}**" if ax_o["fornecedor_nome"] else ""
                            c_o1.write(f"📎 **{ax_o['nome_original']}** — {ax_o['processo'] or 'Cotação'}{forn_txt} ({ax_o['data_upload'] or ''})")
                            if caminho_o.exists():
                                c_o2.download_button("Baixar arquivo", data=caminho_o.read_bytes(), file_name=ax_o["nome_original"], key=f"dl_om_{m.id}_{ax_o['id']}")
                else:
                    st.caption("Sem cotações registradas para este material.")

            with t_doc:
                anexos_mat = read("SELECT id, tipo_documento, nome_original, arquivo_salvo, data_upload, observacoes FROM anexos WHERE entidade_tipo='material' AND entidade_id=? ORDER BY id DESC", (int(m.id),))
                if anexos_mat.empty:
                    st.caption("Nenhum arquivo técnico anexado diretamente a este material.")
                else:
                    for _, ax in anexos_mat.iterrows():
                        caminho = ANEXOS_DIR / ax["arquivo_salvo"]
                        col_a, col_b = st.columns([4, 1])
                        col_a.write(f"**{ax['tipo_documento']}:** {ax['nome_original']} ({ax['data_upload'] or ''})")
                        if caminho.exists():
                            col_b.download_button("Baixar", data=caminho.read_bytes(), file_name=ax["nome_original"], key=f"dl_pm_{ax['id']}")


# ==============================================================================
# 2. MATERIAIS & FORNECEDORES
# ==============================================================================
elif menu == "📦 Materiais & Fornecedores":
    st.title("Materiais & Fornecedores")
    st.caption("Cadastre, edite e vincule os itens do seu catálogo técnico e sua base de fornecedores.")

    sec_mat, sec_forn, sec_vinc = st.tabs(["🧱 Materiais", "🏢 Fornecedores", "🔗 Vincular Material x Fornecedor"])

    with sec_mat:
        sub_m_novo, sub_m_edit = st.tabs(["Cadastrar novo material", "Editar ou excluir material"])

        with sub_m_novo:
            with st.form("material"):
                a, b = st.columns(2)
                descricao = a.text_input("Descrição *")
                codigo = b.text_input("Código interno")
                categoria = a.selectbox("Categoria", CATEGORIAS)
                sub = b.text_input("Subcategoria")
                fab = a.text_input("Fabricante")
                modelo = b.text_input("Modelo")
                codfab = a.text_input("Código do fabricante")
                dn = b.text_input("DN")
                pn = a.text_input("PN")
                mat = b.selectbox("Material de fabricação", MATERIAIS_FAB)
                conex = a.selectbox("Tipo de conexão", CONEXOES)
                ac = b.selectbox("Acionamento", ACIONAMENTOS)
                aplic = a.selectbox("Aplicação", APLICACOES)
                palavras = st.text_input("Palavras-chave (separadas por vírgula)")
                desc = st.text_area("Descrição técnica / observações")
                status = st.selectbox("Status", STATUS_MAT)
                forcar_similar = st.checkbox("Confirmar cadastro mesmo existindo material com descrição igual")
                ok = st.form_submit_button("Salvar material", type="primary")

            if ok:
                if not descricao.strip():
                    st.error("Descrição é obrigatória.")
                else:
                    existentes = read("SELECT id, codigo, descricao, fabricante, modelo, dn, pn, status FROM materiais")
                    desc_n, fab_n, mod_n, dn_n = norm(descricao), norm(fab), norm(modelo), norm(dn)
                    duplicados_exatos = existentes[existentes.apply(lambda r: norm(r["descricao"]) == desc_n and norm(r["fabricante"]) == fab_n and norm(r["modelo"]) == mod_n and norm(r["dn"]) == dn_n, axis=1)] if not existentes.empty else pd.DataFrame()
                    mesma_descricao = existentes[existentes.apply(lambda r: norm(r["descricao"]) == desc_n, axis=1)] if not existentes.empty else pd.DataFrame()

                    if not duplicados_exatos.empty:
                        st.error("Este material já está cadastrado com os mesmos dados:")
                        st.dataframe(duplicados_exatos, use_container_width=True, hide_index=True)
                    elif not mesma_descricao.empty and not forcar_similar:
                        st.warning("Já existe material com essa descrição. Marque a confirmação se for variação válida:")
                        st.dataframe(mesma_descricao, use_container_width=True, hide_index=True)
                    else:
                        try:
                            write(
                                """INSERT INTO materiais(codigo,descricao,categoria,subcategoria,fabricante,modelo,
                                   codigo_fabricante,dn,pn,material_fabricacao,tipo_conexao,
                                   acionamento,aplicacao,palavras_chave,descricao_tecnica,status)
                                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (codigo.strip() or None, descricao.strip(), categoria, sub.strip(), fab.strip(), modelo.strip(),
                                 codfab.strip(), dn.strip(), pn.strip(), mat, conex, ac, aplic, palavras.strip(), desc.strip(), status)
                            )
                            st.success("Material cadastrado.")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Código interno já cadastrado.")

        with sub_m_edit:
            mats = read("SELECT * FROM materiais ORDER BY id DESC")
            if mats.empty:
                st.info("Nenhum material cadastrado.")
            else:
                st.dataframe(mats[["id", "codigo", "descricao", "categoria", "fabricante", "dn", "pn", "status"]], use_container_width=True, hide_index=True)
                mid_edit = st.selectbox("Selecione o material pelo ID", mats["id"].tolist(), format_func=lambda i: f"ID {i} — {mats.loc[mats['id']==i, 'descricao'].iloc[0]}")
                item = mats[mats["id"] == mid_edit].iloc[0]

                with st.form("form_editar_material"):
                    a, b = st.columns(2)
                    e_descricao = a.text_input("Descrição *", value=item["descricao"] or "")
                    e_codigo = b.text_input("Código interno", value=item["codigo"] or "")
                    e_categoria = a.selectbox("Categoria", CATEGORIAS, index=idx_opcao(CATEGORIAS, item["categoria"]))
                    e_sub = b.text_input("Subcategoria", value=item["subcategoria"] or "")
                    e_fab = a.text_input("Fabricante", value=item["fabricante"] or "")
                    e_modelo = b.text_input("Modelo", value=item["modelo"] or "")
                    e_codfab = a.text_input("Código do fabricante", value=item["codigo_fabricante"] or "")
                    e_dn = b.text_input("DN", value=item["dn"] or "")
                    e_pn = a.text_input("PN", value=item["pn"] or "")
                    e_mat = b.selectbox("Material de fabricação", MATERIAIS_FAB, index=idx_opcao(MATERIAIS_FAB, item["material_fabricacao"]))
                    e_conex = a.selectbox("Tipo de conexão", CONEXOES, index=idx_opcao(CONEXOES, item["tipo_conexao"]))
                    e_ac = b.selectbox("Acionamento", ACIONAMENTOS, index=idx_opcao(ACIONAMENTOS, item["acionamento"]))
                    e_aplic = a.selectbox("Aplicação", APLICACOES, index=idx_opcao(APLICACOES, item["aplicacao"]))
                    e_palavras = st.text_input("Palavras-chave", value=item["palavras_chave"] or "")
                    e_desc = st.text_area("Descrição técnica", value=item["descricao_tecnica"] or "")
                    e_status = st.selectbox("Status", STATUS_MAT, index=idx_opcao(STATUS_MAT, item["status"]))
                    salvar_edicao = st.form_submit_button("Salvar alterações")

                if salvar_edicao and e_descricao.strip():
                    try:
                        write(
                            """UPDATE materiais SET codigo=?, descricao=?, categoria=?, subcategoria=?, fabricante=?, modelo=?,
                               codigo_fabricante=?, dn=?, pn=?, material_fabricacao=?, tipo_conexao=?,
                               acionamento=?, aplicacao=?, palavras_chave=?, descricao_tecnica=?, status=? WHERE id=?""",
                            (e_codigo.strip() or None, e_descricao.strip(), e_categoria, e_sub.strip(), e_fab.strip(), e_modelo.strip(),
                             e_codfab.strip(), e_dn.strip(), e_pn.strip(), e_mat, e_conex, e_ac, e_aplic, e_palavras.strip(), e_desc.strip(), e_status, int(mid_edit))
                        )
                        st.success("Material atualizado.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Código interno já pertence a outro material.")

                st.divider()
                confirmar_del_mat = st.checkbox("Confirmo que desejo excluir permanentemente este material", key=f"del_mat_{mid_edit}")
                if st.button("Excluir material selecionado", type="primary"):
                    if confirmar_del_mat:
                        remover_anexos_entidade("material", int(mid_edit))
                        write("DELETE FROM cotacao_itens WHERE material_id=?", (int(mid_edit),))
                        write("DELETE FROM fornecimentos WHERE material_id=?", (int(mid_edit),))
                        write("DELETE FROM materiais WHERE id=?", (int(mid_edit),))
                        st.success("Material excluído.")
                        st.rerun()
                    else:
                        st.error("Marque a confirmação antes de excluir.")

    with sec_forn:
        sub_f_novo, sub_f_edit = st.tabs(["Cadastrar novo fornecedor", "Editar ou excluir fornecedor"])

        with sub_f_novo:
            with st.form("fornecedor"):
                a, b = st.columns(2)
                razao = a.text_input("Razão social *")
                fantasia = b.text_input("Nome fantasia")
                cnpj = a.text_input("CNPJ")
                contato = b.text_input("Contato comercial")
                email = a.text_input("E-mail")
                telefone = b.text_input("Telefone")
                site = st.text_input("Site")
                obs = st.text_area("Observações")
                ok = st.form_submit_button("Salvar fornecedor", type="primary")

            if ok:
                if not razao.strip():
                    st.error("Razão social é obrigatória.")
                else:
                    f_exist = read("SELECT id, razao_social, nome_fantasia, cnpj FROM fornecedores")
                    razao_n, cnpj_d = norm(razao), apenas_digitos(cnpj)
                    dup_f = f_exist[
                        f_exist.apply(lambda r: norm(r["razao_social"]) == razao_n or (cnpj_d != "" and apenas_digitos(r["cnpj"]) == cnpj_d), axis=1)
                    ] if not f_exist.empty else pd.DataFrame()
                    if not dup_f.empty:
                        st.error("Já existe fornecedor com esta Razão Social ou CNPJ:")
                        st.dataframe(dup_f, use_container_width=True, hide_index=True)
                    else:
                        write(
                            "INSERT INTO fornecedores(razao_social,nome_fantasia,cnpj,contato,email,telefone,site,observacoes) VALUES(?,?,?,?,?,?,?,?)",
                            (razao.strip(), fantasia.strip(), cnpj.strip(), contato.strip(), email.strip(), telefone.strip(), site.strip(), obs.strip())
                        )
                        st.success("Fornecedor cadastrado.")
                        st.rerun()

            st.dataframe(read("SELECT id,razao_social,nome_fantasia,cnpj,contato,email,telefone FROM fornecedores ORDER BY razao_social"), use_container_width=True, hide_index=True)

        with sub_f_edit:
            forns = read("SELECT * FROM fornecedores ORDER BY id DESC")
            if forns.empty:
                st.info("Nenhum fornecedor cadastrado.")
            else:
                fid_edit = st.selectbox("Selecione o fornecedor pelo ID", forns["id"].tolist(), format_func=lambda i: f"ID {i} — {forns.loc[forns['id']==i, 'razao_social'].iloc[0]}")
                f_item = forns[forns["id"] == fid_edit].iloc[0]
                with st.form("form_editar_fornecedor"):
                    a, b = st.columns(2)
                    e_razao = a.text_input("Razão social *", value=f_item["razao_social"] or "")
                    e_fantasia = b.text_input("Nome fantasia", value=f_item["nome_fantasia"] or "")
                    e_cnpj = a.text_input("CNPJ", value=f_item["cnpj"] or "")
                    e_contato = b.text_input("Contato", value=f_item["contato"] or "")
                    e_email = a.text_input("E-mail", value=f_item["email"] or "")
                    e_telefone = b.text_input("Telefone", value=f_item["telefone"] or "")
                    e_site = st.text_input("Site", value=f_item["site"] or "")
                    e_obs = st.text_area("Observações", value=f_item["observacoes"] or "")
                    salvar_f = st.form_submit_button("Salvar alterações")

                if salvar_f:
                    if not e_razao.strip():
                        st.error("Razão social é obrigatória.")
                    else:
                        outros_f = forns[forns["id"] != fid_edit]
                        razao_n, cnpj_d = norm(e_razao), apenas_digitos(e_cnpj)
                        dup_f = outros_f[
                            outros_f.apply(lambda r: norm(r["razao_social"]) == razao_n or (cnpj_d != "" and apenas_digitos(r["cnpj"]) == cnpj_d), axis=1)
                        ] if not outros_f.empty else pd.DataFrame()
                        if not dup_f.empty:
                            st.error("Já existe outro fornecedor com esta Razão Social ou CNPJ.")
                        else:
                            write(
                                "UPDATE fornecedores SET razao_social=?, nome_fantasia=?, cnpj=?, contato=?, email=?, telefone=?, site=?, observacoes=? WHERE id=?",
                                (e_razao.strip(), e_fantasia.strip(), e_cnpj.strip(), e_contato.strip(), e_email.strip(), e_telefone.strip(), e_site.strip(), e_obs.strip(), int(fid_edit))
                            )
                            st.success("Fornecedor atualizado.")
                            st.rerun()

                st.divider()
                confirmar_del_forn = st.checkbox("Confirmo que desejo excluir permanentemente este fornecedor", key=f"del_forn_{fid_edit}")
                if st.button("Excluir fornecedor selecionado", type="primary"):
                    if confirmar_del_forn:
                        remover_anexos_entidade("fornecedor", int(fid_edit))
                        write("DELETE FROM cotacao_itens WHERE fornecedor_id=?", (int(fid_edit),))
                        write("DELETE FROM fornecimentos WHERE fornecedor_id=?", (int(fid_edit),))
                        write("DELETE FROM fornecedores WHERE id=?", (int(fid_edit),))
                        st.success("Fornecedor excluído.")
                        st.rerun()
                    else:
                        st.error("Marque a confirmação antes de excluir.")

    with sec_vinc:
        ms = read("SELECT id,descricao,dn FROM materiais ORDER BY descricao")
        fs = read("SELECT id,razao_social FROM fornecedores ORDER BY razao_social")
        if ms.empty or fs.empty:
            st.info("Cadastre ao menos um material e um fornecedor primeiro.")
        else:
            with st.form("rel"):
                c1, c2 = st.columns(2)
                mid = c1.selectbox("Material *", ms["id"].tolist(), format_func=lambda i: f"{ms.loc[ms['id']==i, 'descricao'].iloc[0]} (DN {ms.loc[ms['id']==i, 'dn'].iloc[0] or '—'})")
                fid = c2.selectbox("Fornecedor *", fs["id"].tolist(), format_func=lambda i: fs.loc[fs["id"] == i, "razao_social"].iloc[0])
                c3, c4, c5 = st.columns(3)
                tipo = c3.selectbox("Tipo de relação", ["Forneceu", "Cotou", "Forneceu similar"])
                fabricante = c4.text_input("Fabricante ofertado")
                modelo = c5.text_input("Modelo ofertado")
                data = st.date_input("Data da interação")
                obs = st.text_area("Observações")
                ok = st.form_submit_button("Salvar vínculo", type="primary")
            if ok:
                write(
                    "INSERT INTO fornecimentos(material_id,fornecedor_id,tipo_relacao,fabricante_ofertado,modelo_ofertado,data_interacao,observacoes) VALUES(?,?,?,?,?,?,?)",
                    (mid, fid, tipo, fabricante, modelo, str(data), obs)
                )
                st.success("Relação cadastrada.")
                st.rerun()
            st.dataframe(read("SELECT r.id, m.descricao AS Material, f.razao_social AS Fornecedor, r.tipo_relacao AS Tipo, r.data_interacao AS Data FROM fornecimentos r JOIN materiais m ON m.id=r.material_id JOIN fornecedores f ON f.id=r.fornecedor_id ORDER BY r.id DESC"), use_container_width=True, hide_index=True)


# ==============================================================================
# 3. COTAÇÕES & PREÇOS
# ==============================================================================
elif menu == "💰 Cotações & Preços":
    st.title("Cotações & Histórico de Preços")
    st.caption("Importe planilhas de orçamento prontas ou gerencie processos de cotação manualmente.")

    if "msg_import" in st.session_state:
        st.success(st.session_state.pop("msg_import"))

    aba_import, aba_cot_lista, aba_cot_itens, aba_cot_editar = st.tabs([
        "📥 Importar Planilha Pronta",
        "📋 Cadastrar cotação manual",
        "💲 Itens e preços",
        "✏️ Editar ou excluir"
    ])

    with aba_import:
        st.subheader("Importar orçamento pronto (Excel ou CSV)")
        st.write("Envie sua planilha de orçamento ou **Tabela de Cotações**. O sistema **arquiva o arquivo original** e **cadastra automaticamente todos os materiais, fornecedores e preços**.")

        arq_planilha = st.file_uploader("Selecione a planilha de orçamento (.xlsx, .xls ou .csv)", type=["xlsx", "xls", "csv"], key="up_planilha_pronta")

        if arq_planilha is not None:
            try:
                if arq_planilha.name.lower().endswith(".csv"):
                    try:
                        df_bruto = pd.read_csv(arq_planilha, header=None, sep=None, engine="python")
                    except Exception:
                        arq_planilha.seek(0)
                        df_bruto = pd.read_csv(arq_planilha, header=None, sep=";", encoding="latin1")
                else:
                    excel_file = pd.ExcelFile(arq_planilha)
                    aba_escolhida = excel_file.sheet_names[0]
                    if len(excel_file.sheet_names) > 1:
                        aba_escolhida = st.selectbox("Selecione a aba da planilha", excel_file.sheet_names)
                    df_bruto = pd.read_excel(excel_file, sheet_name=aba_escolhida, header=None)

                itens_comparativos = detectar_tabela_cotacoes_comparativa(df_bruto)

                if itens_comparativos is not None and len(itens_comparativos) > 0:
                    total_cots_forn = sum(len(x["cotacoes"]) for x in itens_comparativos)
                    forns_unicos = sorted({c["fornecedor"] for x in itens_comparativos for c in x["cotacoes"]})

                    st.info(
                        f"Modelo **Tabela de Cotações Comparativa** detectado: "
                        f"**{len(itens_comparativos)} materiais** e **{total_cots_forn} propostas** "
                        f"({', '.join(forns_unicos)})."
                    )

                    previa_rows = []
                    for it in itens_comparativos[:10]:
                        forns_str = " | ".join(f"{c['fornecedor']}: {fmt_brl(c['preco'])}" for c in it["cotacoes"])
                        previa_rows.append({
                            "Código": it["codigo"], "Descrição": it["descricao"], "DN": it["dn"],
                            "Qtd": it["quantidade"], "Valor Orçamento": fmt_brl(it["valor_orcamento"]),
                            "Propostas": forns_str
                        })
                    st.dataframe(pd.DataFrame(previa_rows), use_container_width=True, hide_index=True)

                    with st.form("form_confirmar_import_comp"):
                        g1, g2 = st.columns([2, 1])
                        nome_orc = g1.text_input("Identificação do orçamento *", value=Path(arq_planilha.name).stem)
                        data_orc = g2.date_input("Data de referência", value=date.today())
                        modo_imp = st.radio(
                            "Quais preços deseja importar para o histórico?",
                            [
                                "Todas as propostas de todos os fornecedores da tabela (Recomendado)",
                                "Apenas o menor preço / valor adotado no orçamento"
                            ]
                        )
                        confirmar_imp = st.form_submit_button("🚀 Arquivar planilha e importar tudo para o catálogo", type="primary")

                    if confirmar_imp:
                        if not nome_orc.strip():
                            st.error("Informe uma identificação para o orçamento.")
                        else:
                            cid_novo = write(
                                "INSERT INTO cotacoes(processo, data_cotacao, objeto, status, observacoes) VALUES(?, ?, ?, 'Concluída', ?)",
                                (nome_orc.strip(), str(data_orc), f"Importado de {arq_planilha.name}", "Importação automática de Tabela de Cotações")
                            )
                            arq_planilha.seek(0)
                            salvar_arquivo_anexo(arq_planilha, "cotacao", int(cid_novo), "Proposta comercial / Orçamento", "Planilha original importada")

                            qtd_mat_novos = 0
                            qtd_precos_salvos = 0

                            for it in itens_comparativos:
                                mid_linha, eh_novo = obter_ou_criar_material(
                                    descricao=it["descricao"], codigo=it["codigo"], dn=it["dn"],
                                    pn=it["pn"], material_fab=it["material"], categoria=it["categoria"]
                                )
                                if eh_novo:
                                    qtd_mat_novos += 1

                                if modo_imp.startswith("Todas") and it["cotacoes"]:
                                    for c_forn in it["cotacoes"]:
                                        fid_linha, _ = obter_ou_criar_fornecedor(c_forn["fornecedor"])
                                        obs_c = f"Data cotação: {c_forn['data']}" if c_forn["data"] else f"Importado de {arq_planilha.name}"
                                        write(
                                            "INSERT INTO cotacao_itens(cotacao_id, material_id, fornecedor_id, quantidade, unidade, preco_unitario, observacoes) VALUES (?,?,?,?,?,?,?)",
                                            (int(cid_novo), int(mid_linha), int(fid_linha), float(it["quantidade"]), it["unidade"], float(c_forn["preco"]), obs_c)
                                        )
                                        qtd_precos_salvos += 1
                                else:
                                    v_adotado = it["valor_orcamento"]
                                    forn_vencedor = "Fornecedor do Orçamento"
                                    if it["cotacoes"]:
                                        menor = min(it["cotacoes"], key=lambda x: x["preco"])
                                        if v_adotado <= 0:
                                            v_adotado = menor["preco"]
                                        forn_vencedor = menor["fornecedor"]
                                    if v_adotado > 0:
                                        fid_linha, _ = obter_ou_criar_fornecedor(forn_vencedor)
                                        write(
                                            "INSERT INTO cotacao_itens(cotacao_id, material_id, fornecedor_id, quantidade, unidade, preco_unitario, observacoes) VALUES (?,?,?,?,?,?,?)",
                                            (int(cid_novo), int(mid_linha), int(fid_linha), float(it["quantidade"]), it["unidade"], float(v_adotado), f"Valor adotado em {arq_planilha.name}")
                                        )
                                        qtd_precos_salvos += 1

                            st.session_state["msg_import"] = (
                                f"Importação concluída! {qtd_precos_salvos} registros de preço importados "
                                f"({qtd_mat_novos} materiais novos cadastrados) e a planilha original foi arquivada."
                            )
                            st.rerun()

                else:
                    linha_cab = st.number_input("Número da linha do cabeçalho (1 = primeira linha)", min_value=1, max_value=min(30, max(1, len(df_bruto))), value=1)
                    idx_h = int(linha_cab) - 1
                    df_raw = df_bruto.iloc[idx_h + 1:].copy().reset_index(drop=True)
                    df_raw.columns = [str(c).strip() if pd.notna(c) and str(c).strip() else f"Coluna_{i+1}" for i, c in enumerate(df_bruto.iloc[idx_h].tolist())]
                    df_raw = df_raw.dropna(how="all").reset_index(drop=True)

                    if not df_raw.empty:
                        st.dataframe(df_raw.head(8), use_container_width=True, hide_index=True)
                        cols_plan = list(df_raw.columns)
                        cols_opc = ["(Não tem na planilha)"] + cols_plan

                        with st.form("form_confirmar_import_simples"):
                            g1, g2, g3 = st.columns([1.5, 1, 1.5])
                            nome_orc = g1.text_input("Identificação do orçamento *", value=Path(arq_planilha.name).stem)
                            data_orc = g2.date_input("Data", value=date.today())
                            forn_padrao = g3.text_input("Fornecedor padrão (se não houver coluna)")

                            m1, m2, m3 = st.columns(3)
                            col_desc = m1.selectbox("Coluna Descrição *", cols_plan, index=achar_coluna_padrao(cols_plan, ["descr", "material", "item"]))
                            col_preco = m2.selectbox("Coluna Preço Unitário *", cols_plan, index=achar_coluna_padrao(cols_plan, ["unit", "preco", "preço", "valor"]))
                            col_qtd = m3.selectbox("Coluna Quantidade", cols_opc, index=achar_coluna_padrao(cols_opc, ["qtd", "quant"]))

                            m4, m5, m6 = st.columns(3)
                            col_unid = m4.selectbox("Coluna Unidade", cols_opc, index=achar_coluna_padrao(cols_opc, ["unid", "und"]))
                            col_forn = m5.selectbox("Coluna Fornecedor", cols_opc, index=achar_coluna_padrao(cols_opc, ["forn", "empresa"]))
                            col_cod = m6.selectbox("Coluna Código / Ref.", cols_opc, index=achar_coluna_padrao(cols_opc, ["ref", "cod"]))

                            confirmar_s = st.form_submit_button("🚀 Arquivar planilha e importar itens", type="primary")

                        if confirmar_s and nome_orc.strip():
                            cid_novo = write("INSERT INTO cotacoes(processo, data_cotacao, objeto, status, observacoes) VALUES(?, ?, ?, 'Concluída', ?)", (nome_orc.strip(), str(data_orc), f"Importado de {arq_planilha.name}", "Importação de planilha"))
                            fid_default = obter_ou_criar_fornecedor(forn_padrao.strip())[0] if forn_padrao.strip() else None
                            arq_planilha.seek(0)
                            salvar_arquivo_anexo(arq_planilha, "cotacao", int(cid_novo), "Proposta comercial / Orçamento", "Planilha original importada", fid_default)

                            qtd_imp, qtd_nov = 0, 0
                            for _, linha in df_raw.iterrows():
                                desc_val = linha.get(col_desc)
                                if pd.isna(desc_val) or not str(desc_val).strip() or norm(desc_val) in ("total", "subtotal", "total geral"):
                                    continue
                                preco_val = parse_numero(linha.get(col_preco))
                                if preco_val <= 0:
                                    continue
                                qtd_val = parse_numero(linha.get(col_qtd)) if col_qtd != "(Não tem na planilha)" else 1.0
                                if qtd_val <= 0:
                                    qtd_val = 1.0
                                unid_val = str(linha.get(col_unid)).strip() if (col_unid != "(Não tem na planilha)" and pd.notna(linha.get(col_unid))) else "un"
                                cod_val = str(linha.get(col_cod)).strip() if (col_cod != "(Não tem na planilha)" and pd.notna(linha.get(col_cod))) else ""

                                if col_forn != "(Não tem na planilha)" and pd.notna(linha.get(col_forn)) and str(linha.get(col_forn)).strip():
                                    fid_linha, _ = obter_ou_criar_fornecedor(str(linha.get(col_forn)).strip())
                                elif fid_default:
                                    fid_linha = fid_default
                                else:
                                    fid_linha, _ = obter_ou_criar_fornecedor("Fornecedor Não Especificado")

                                dn_v, pn_v, mat_v, cat_v = extrair_specs_descricao(str(desc_val).strip())
                                mid_linha, eh_novo = obter_ou_criar_material(str(desc_val).strip(), cod_val, dn_v, pn_v, mat_v, cat_v)
                                if eh_novo:
                                    qtd_nov += 1
                                write(
                                    "INSERT INTO cotacao_itens(cotacao_id, material_id, fornecedor_id, quantidade, unidade, preco_unitario, observacoes) VALUES (?,?,?,?,?,?,?)",
                                    (int(cid_novo), int(mid_linha), int(fid_linha), float(qtd_val), unid_val or "un", float(preco_val), f"Importado de {arq_planilha.name}")
                                )
                                qtd_imp += 1

                            st.session_state["msg_import"] = f"Concluído! {qtd_imp} itens importados ({qtd_nov} materiais novos) e planilha arquivada."
                            st.rerun()
            except Exception as erro:
                st.error(f"Erro ao processar planilha: {erro}")

    with aba_cot_lista:
        with st.form("cot"):
            a, b = st.columns(2)
            processo = a.text_input("Número do processo")
            data = b.date_input("Data")
            objeto = a.text_input("Objeto")
            status = b.selectbox("Status", ["Em andamento", "Concluída", "Cancelada"])
            obs = st.text_area("Observações")
            ok = st.form_submit_button("Criar cotação", type="primary")
        if ok:
            write("INSERT INTO cotacoes(processo,data_cotacao,objeto,status,observacoes) VALUES(?,?,?,?,?)", (processo.strip(), str(data), objeto.strip(), status, obs.strip()))
            st.success("Cotação criada.")
            st.rerun()
        st.dataframe(read("SELECT * FROM cotacoes ORDER BY data_cotacao DESC, id DESC"), use_container_width=True, hide_index=True)

    with aba_cot_itens:
        cots = read("SELECT id, processo, data_cotacao, objeto FROM cotacoes ORDER BY data_cotacao DESC, id DESC")
        ms = read("SELECT id, descricao, dn FROM materiais ORDER BY descricao")
        fs = read("SELECT id, razao_social FROM fornecedores ORDER BY razao_social")

        if cots.empty or ms.empty or fs.empty:
            st.info("Cadastre ou importe uma cotação, material e fornecedor para gerenciar itens.")
        else:
            cid = st.selectbox("Selecione a cotação / orçamento", cots["id"].tolist(), format_func=lambda i: f"ID {i} | {cots.loc[cots['id']==i, 'processo'].iloc[0] or 'Sem nº'} — {cots.loc[cots['id']==i, 'objeto'].iloc[0] or ''}")
            with st.form("form_item_cotacao"):
                col1, col2 = st.columns(2)
                mid_c = col1.selectbox("Material *", ms["id"].tolist(), format_func=lambda i: f"{ms.loc[ms['id']==i, 'descricao'].iloc[0]} (DN {ms.loc[ms['id']==i, 'dn'].iloc[0] or '—'})")
                fid_c = col2.selectbox("Fornecedor *", fs["id"].tolist(), format_func=lambda i: fs.loc[fs["id"] == i, "razao_social"].iloc[0])
                c1, c2, c3, c4 = st.columns([1, 1, 1.2, 1.3])
                qtd = c1.number_input("Quantidade *", min_value=0.01, value=1.0, step=1.0)
                unid = c2.text_input("Unidade", value="un")
                preco = c3.number_input("Preço unitário (R$) *", min_value=0.0, value=0.0, step=10.0, format="%.2f")
                prazo = c4.text_input("Prazo de entrega")
                obs_item = st.text_input("Observações do item")
                arq_orc_item = st.file_uploader("Anexar proposta deste fornecedor (opcional)", type=EXTENSOES_ACEITAS)
                add_item = st.form_submit_button("Adicionar preço", type="primary")

            if add_item:
                if preco <= 0:
                    st.error("Informe um preço unitário maior que zero.")
                else:
                    write("INSERT INTO cotacao_itens(cotacao_id, material_id, fornecedor_id, quantidade, unidade, preco_unitario, prazo_entrega, observacoes) VALUES (?,?,?,?,?,?,?,?)", (int(cid), int(mid_c), int(fid_c), float(qtd), unid.strip() or "un", float(preco), prazo.strip(), obs_item.strip()))
                    if arq_orc_item is not None:
                        salvar_arquivo_anexo(arq_orc_item, "cotacao", int(cid), "Proposta comercial / Orçamento", obs_item.strip(), int(fid_c))
                    st.success("Item adicionado.")
                    st.rerun()

            st.subheader("Itens lançados nesta cotação")
            itens_cot = read(
                """SELECT ci.id, m.descricao AS Material, m.dn AS DN, f.razao_social AS Fornecedor,
                          ci.quantidade AS Qtd, ci.unidade AS Unid, ci.preco_unitario AS Preço_Unit,
                          (ci.quantidade * ci.preco_unitario) AS Total, ci.prazo_entrega AS Prazo, ci.observacoes AS Obs
                   FROM cotacao_itens ci JOIN materiais m ON m.id=ci.material_id JOIN fornecedores f ON f.id=ci.fornecedor_id
                   WHERE ci.cotacao_id=? ORDER BY m.descricao, ci.preco_unitario ASC""",
                (int(cid),)
            )
            if itens_cot.empty:
                st.caption("Nenhum item lançado nesta cotação.")
            else:
                df_ex = itens_cot.copy()
                df_ex["Preço_Unit"] = df_ex["Preço_Unit"].apply(fmt_brl)
                df_ex["Total"] = df_ex["Total"].apply(fmt_brl)
                st.dataframe(df_ex, use_container_width=True, hide_index=True)

                item_del = st.selectbox(
                    "Remover item lançado (se necessário)",
                    itens_cot["id"].tolist(),
                    format_func=lambda i: f"Item ID {i} — {itens_cot.loc[itens_cot['id']==i, 'Material'].iloc[0]} | {itens_cot.loc[itens_cot['id']==i, 'Fornecedor'].iloc[0]}"
                )
                if st.button("Remover item selecionado"):
                    write("DELETE FROM cotacao_itens WHERE id=?", (int(item_del),))
                    st.success("Item removido.")
                    st.rerun()

            st.divider()
            st.subheader("📎 Arquivos e propostas vinculados")
            anexos_desta_cot = read(
                """SELECT a.id, a.tipo_documento, a.nome_original, a.arquivo_salvo, a.data_upload, a.observacoes, f.razao_social AS fornecedor_nome
                   FROM anexos a LEFT JOIN fornecedores f ON f.id = a.fornecedor_id
                   WHERE a.entidade_tipo='cotacao' AND a.entidade_id=? ORDER BY a.id DESC""",
                (int(cid),)
            )
            if anexos_desta_cot.empty:
                st.caption("Nenhum arquivo anexado a este orçamento.")
            else:
                for _, ax_c in anexos_desta_cot.iterrows():
                    caminho_c = ANEXOS_DIR / ax_c["arquivo_salvo"]
                    with st.container(border=True):
                        c_a1, c_a2, c_a3 = st.columns([4, 1, 1])
                        forn_label = f" • Fornecedor: **{ax_c['fornecedor_nome']}**" if ax_c["fornecedor_nome"] else ""
                        c_a1.write(f"**{ax_c['tipo_documento']}:** {ax_c['nome_original']}{forn_label} ({ax_c['data_upload'] or ''})")
                        if ax_c["observacoes"]:
                            c_a1.caption(ax_c["observacoes"])
                        if caminho_c.exists():
                            c_a2.download_button("Baixar", data=caminho_c.read_bytes(), file_name=ax_c["nome_original"], key=f"dl_ci_{ax_c['id']}")
                        if c_a3.button("Excluir", key=f"del_ci_{ax_c['id']}"):
                            if caminho_c.exists():
                                caminho_c.unlink()
                            write("DELETE FROM anexos WHERE id=?", (int(ax_c["id"]),))
                            st.rerun()

    with aba_cot_editar:
        cots_ed = read("SELECT * FROM cotacoes ORDER BY id DESC")
        if cots_ed.empty:
            st.info("Nenhuma cotação cadastrada.")
        else:
            st.dataframe(cots_ed, use_container_width=True, hide_index=True)
            cid_edit = st.selectbox("Selecione a cotação pelo ID", cots_ed["id"].tolist(), format_func=lambda i: f"ID {i} | {cots_ed.loc[cots_ed['id']==i, 'processo'].iloc[0] or 'Sem nº'} — {cots_ed.loc[cots_ed['id']==i, 'objeto'].iloc[0] or ''}")
            c_item = cots_ed[cots_ed["id"] == cid_edit].iloc[0]

            try:
                data_atual = date.fromisoformat(str(c_item["data_cotacao"]))
            except ValueError:
                data_atual = date.today()

            status_cots = ["Em andamento", "Concluída", "Cancelada"]
            with st.form("form_editar_cotacao"):
                a, b = st.columns(2)
                e_proc = a.text_input("Número do processo", value=c_item["processo"] or "")
                e_data = b.date_input("Data", value=data_atual)
                e_obj = a.text_input("Objeto", value=c_item["objeto"] or "")
                e_status = b.selectbox("Status", status_cots, index=idx_opcao(status_cots, c_item["status"]))
                e_obs = st.text_area("Observações", value=c_item["observacoes"] or "")
                salvar_cot = st.form_submit_button("Salvar alterações")

            if salvar_cot:
                write(
                    "UPDATE cotacoes SET processo=?, data_cotacao=?, objeto=?, status=?, observacoes=? WHERE id=?",
                    (e_proc.strip(), str(e_data), e_obj.strip(), e_status, e_obs.strip(), int(cid_edit))
                )
                st.success("Cotação atualizada com sucesso.")
                st.rerun()

            st.divider()
            st.subheader("Excluir cotação / orçamento")
            confirmar_del_cot = st.checkbox("Confirmo que desejo excluir permanentemente este registro (e seus itens/anexos)", key=f"del_cot_{cid_edit}")
            if st.button("Excluir registro selecionado", type="primary"):
                if confirmar_del_cot:
                    remover_anexos_entidade("cotacao", int(cid_edit))
                    write("DELETE FROM cotacao_itens WHERE cotacao_id=?", (int(cid_edit),))
                    write("DELETE FROM cotacoes WHERE id=?", (int(cid_edit),))
                    st.success("Registro excluído.")
                    st.rerun()
                else:
                    st.error("Marque a confirmação antes de excluir.")


# ==============================================================================
# 4. ANEXOS & BACKUP
# ==============================================================================
else:
    st.title("Anexos & Exportação de Dados")
    st.caption("Gerencie todos os documentos técnicos, propostas comerciais e cópias de segurança.")

    aba_lista, aba_up, aba_exp = st.tabs(["📂 Todos os documentos anexados", "📤 Enviar anexo avulso", "💾 Exportar CSV & Backup"])

    with aba_lista:
        df_ax = read("""
            SELECT a.*, m.descricao AS mat_nome, c.processo AS cot_proc, c.objeto AS cot_obj,
                   f_ent.razao_social AS forn_ent_nome, f_orc.razao_social AS forn_orc_nome
            FROM anexos a
            LEFT JOIN materiais m ON a.entidade_tipo='material' AND m.id = a.entidade_id
            LEFT JOIN cotacoes c ON a.entidade_tipo='cotacao' AND c.id = a.entidade_id
            LEFT JOIN fornecedores f_ent ON a.entidade_tipo='fornecedor' AND f_ent.id = a.entidade_id
            LEFT JOIN fornecedores f_orc ON f_orc.id = a.fornecedor_id
            ORDER BY a.id DESC
        """)
        if df_ax.empty:
            st.info("Nenhum arquivo anexado encontrado.")
        else:
            for _, ax in df_ax.iterrows():
                caminho = ANEXOS_DIR / ax["arquivo_salvo"]
                if ax["entidade_tipo"] == "material":
                    vinculo_txt = f"Material: {ax['mat_nome'] or ax['entidade_id']}"
                elif ax["entidade_tipo"] == "cotacao":
                    vinculo_txt = f"Orçamento/Cotação: {ax['cot_proc'] or ax['entidade_id']}"
                else:
                    vinculo_txt = f"Fornecedor: {ax['forn_ent_nome'] or ax['entidade_id']}"

                with st.container(border=True):
                    c1, c2, c3 = st.columns([4, 1, 1])
                    c1.write(f"**{ax['tipo_documento']}** — **{ax['nome_original']}** ({ax['data_upload'] or ''})\n\n📌 _{vinculo_txt}_")
                    if caminho.exists():
                        c2.download_button("Baixar", data=caminho.read_bytes(), file_name=ax["nome_original"], key=f"dl_ax_{ax['id']}")
                    if c3.button("Excluir", key=f"del_ax_{ax['id']}"):
                        if caminho.exists():
                            caminho.unlink()
                        write("DELETE FROM anexos WHERE id=?", (int(ax["id"]),))
                        st.rerun()

    with aba_up:
        tipo_entidade = st.selectbox("Vincular arquivo a:", ["cotacao", "material", "fornecedor"], format_func=lambda t: {"cotacao": "Cotação / Orçamento", "material": "Material", "fornecedor": "Fornecedor"}[t])
        opcoes_ids, mapa_labels = [], {}
        if tipo_entidade == "material":
            for _, r in read("SELECT id, descricao, dn FROM materiais ORDER BY descricao").iterrows():
                opcoes_ids.append(int(r["id"]))
                mapa_labels[int(r["id"])] = f"ID {r['id']} — {r['descricao']} (DN {r['dn'] or '—'})"
        elif tipo_entidade == "cotacao":
            for _, r in read("SELECT id, processo, objeto FROM cotacoes ORDER BY id DESC").iterrows():
                opcoes_ids.append(int(r["id"]))
                mapa_labels[int(r["id"])] = f"ID {r['id']} | {r['processo'] or 'Sem nº'} — {r['objeto'] or ''}"
        else:
            for _, r in read("SELECT id, razao_social FROM fornecedores ORDER BY razao_social").iterrows():
                opcoes_ids.append(int(r["id"]))
                mapa_labels[int(r["id"])] = f"ID {r['id']} — {r['razao_social']}"

        if opcoes_ids:
            with st.form("form_upload_anexo"):
                ent_id = st.selectbox("Selecione o registro *", opcoes_ids, format_func=lambda i: mapa_labels[i])
                tipo_doc = st.selectbox("Tipo de documento", TIPOS_DOC)
                arquivo = st.file_uploader("Escolha o arquivo", type=EXTENSOES_ACEITAS)
                obs_ax = st.text_input("Observações")
                enviar_ax = st.form_submit_button("Salvar anexo", type="primary")
            if enviar_ax and arquivo is not None:
                salvar_arquivo_anexo(arquivo, tipo_entidade, int(ent_id), tipo_doc, obs_ax)
                st.success("Arquivo salvo.")
                st.rerun()

    with aba_exp:
        st.subheader("Exportar tabelas em CSV")
        col_e1, col_e2, col_e3 = st.columns(3)
        for tab_nome, rotulo, coluna in [
            ("materiais", "Materiais", col_e1), ("fornecedores", "Fornecedores", col_e2),
            ("fornecimentos", "Vínculos", col_e3), ("cotacoes", "Cotações", col_e1),
            ("cotacao_itens", "Itens Cotados", col_e2), ("anexos", "Lista de Anexos", col_e3),
        ]:
            coluna.download_button(
                f"⬇️ Baixar {rotulo} (.csv)",
                read(f"SELECT * FROM {tab_nome}").to_csv(index=False).encode("utf-8-sig"),
                f"{tab_nome}.csv", "text/csv", use_container_width=True
            )
        st.info("**Backup completo:** copie o arquivo `central.db` e a pasta `anexos/` da pasta do projeto.")