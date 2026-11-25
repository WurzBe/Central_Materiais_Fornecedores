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
          id INTEGER PRIMARY KEY,
          entidade_tipo TEXT NOT NULL,
          entidade_id INTEGER NOT NULL,
          fornecedor_id INTEGER,
          tipo_documento TEXT,
          nome_original TEXT NOT NULL,
          arquivo_salvo TEXT NOT NULL,
          data_upload TEXT,
          observacoes TEXT
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
        cur = c.execute(sql, params)
        return cur.lastrowid


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
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def achar_coluna_padrao(colunas, palavras_chave):
    for idx, col in enumerate(colunas):
        c_norm = norm(col)
        for p in palavras_chave:
            if p in c_norm:
                return idx
    return 0


def obter_ou_criar_material(descricao, dn="", fabricante=""):
    desc_limpa = str(descricao).strip()
    dn_limpo = str(dn).strip() if pd.notna(dn) else ""
    fab_limpo = str(fabricante).strip() if pd.notna(fabricante) else ""

    existentes = read("SELECT id, descricao, dn, fabricante FROM materiais")
    if not existentes.empty:
        match = existentes[
            existentes.apply(
                lambda r: norm(r["descricao"]) == norm(desc_limpa)
                and norm(r["dn"]) == norm(dn_limpo),
                axis=1
            )
        ]
        if not match.empty:
            return int(match.iloc[0]["id"]), False

    novo_id = write(
        """INSERT INTO materiais(descricao, dn, fabricante, status)
           VALUES(?, ?, ?, 'Em revisão')""",
        (desc_limpa, dn_limpo, fab_limpo)
    )
    return int(novo_id), True


def obter_ou_criar_fornecedor(nome_fornecedor):
    nome_limpo = str(nome_fornecedor).strip()
    if not nome_limpo:
        nome_limpo = "Fornecedor Não Especificado"
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

    novo_id = write(
        "INSERT INTO fornecedores(razao_social) VALUES(?)",
        (nome_limpo,)
    )
    return int(novo_id), True


def salvar_arquivo_anexo(arquivo, entidade_tipo, entidade_id, tipo_documento, observacoes="", fornecedor_id=None):
    ext = Path(arquivo.name).suffix.lower()
    nome_unico = f"{entidade_tipo}_{entidade_id}_{uuid.uuid4().hex[:8]}{ext}"
    destino = ANEXOS_DIR / nome_unico
    destino.write_bytes(arquivo.getbuffer())
    write(
        """INSERT INTO anexos(
           entidade_tipo, entidade_id, fornecedor_id, tipo_documento,
           nome_original, arquivo_salvo, data_upload, observacoes)
           VALUES(?,?,?,?,?,?,?,?)""",
        (
            entidade_tipo,
            int(entidade_id),
            int(fornecedor_id) if fornecedor_id else None,
            tipo_documento,
            arquivo.name,
            nome_unico,
            str(date.today()),
            observacoes.strip()
        )
    )


def remover_anexos_entidade(entidade_tipo, entidade_id):
    df_a = read(
        "SELECT id, arquivo_salvo FROM anexos WHERE entidade_tipo=? AND entidade_id=?",
        (entidade_tipo, int(entidade_id))
    )
    for _, r in df_a.iterrows():
        arq = ANEXOS_DIR / r["arquivo_salvo"]
        if arq.exists():
            arq.unlink()
    write(
        "DELETE FROM anexos WHERE entidade_tipo=? AND entidade_id=?",
        (entidade_tipo, int(entidade_id))
    )


def aplicar_estilo():
    st.markdown("""
    <style>
        .block-container {
            padding-top: 1.8rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }
        [data-testid="stSidebar"] {
            border-right: 1px solid rgba(128, 128, 128, 0.2);
        }
        [data-testid="stSidebar"] .stRadio > div {
            gap: 0.35rem;
        }
        [data-testid="stSidebar"] .stRadio label {
            background-color: rgba(128, 128, 128, 0.08);
            padding: 0.6rem 0.85rem;
            border-radius: 8px;
            border: 1px solid transparent;
            transition: all 0.15s ease;
            cursor: pointer;
            width: 100%;
        }
        [data-testid="stSidebar"] .stRadio label:hover {
            background-color: rgba(128, 128, 128, 0.16);
            border-color: rgba(128, 128, 128, 0.3);
        }
        [data-testid="stSidebar"] .stRadio label > div:first-child {
            display: none;
        }
        [data-testid="stMetric"] {
            background-color: rgba(128, 128, 128, 0.07);
            padding: 0.8rem 1rem;
            border-radius: 10px;
            border: 1px solid rgba(128, 128, 128, 0.18);
        }
        .sidebar-brand {
            padding: 0.4rem 0 0.8rem 0;
            border-bottom: 1px solid rgba(128, 128, 128, 0.2);
            margin-bottom: 1rem;
        }
        .sidebar-brand h2 {
            margin: 0;
            font-size: 1.15rem;
            font-weight: 700;
        }
        .sidebar-brand p {
            margin: 0.2rem 0 0 0;
            font-size: 0.8rem;
            opacity: 0.75;
        }
    </style>
    """, unsafe_allow_html=True)


CATEGORIAS = [
    "", "Tubos", "Conexões", "Válvulas", "Atuadores",
    "Medidores", "Bombas", "Materiais elétricos", "Instrumentação", "Outros"
]
MATERIAIS_FAB = [
    "", "Ferro fundido dúctil", "Aço carbono", "Aço inoxidável",
    "PVC", "PEAD", "Bronze", "Outro"
]
CONEXOES = ["", "Flangeada", "Ponta e bolsa", "Roscada", "Soldável", "Wafer", "Lug", "Outro"]
ACIONAMENTOS = ["", "Manual", "Elétrico", "Pneumático", "Hidráulico", "Sem acionamento"]
APLICACOES = ["", "Água potável", "Esgoto", "Drenagem", "Industrial", "Outra"]
STATUS_MAT = ["Em revisão", "Validado", "Inativo"]
TIPOS_DOC = [
    "Proposta comercial / Orçamento", "Ficha técnica", "Catálogo",
    "Desenho técnico", "Certificado / Norma", "Outro"
]
EXTENSOES_ACEITAS = ["pdf", "png", "jpg", "jpeg", "xlsx", "xls", "docx", "doc", "csv", "txt"]

st.set_page_config(page_title="Central de Materiais e Fornecedores", page_icon="🧰", layout="wide")
init()
aplicar_estilo()

tot_mat = read("SELECT COUNT(*) AS n FROM materiais")["n"].iloc[0]
tot_forn = read("SELECT COUNT(*) AS n FROM fornecedores")["n"].iloc[0]
tot_cot = read("SELECT COUNT(*) AS n FROM cotacoes")["n"].iloc[0]
tot_ax = read("SELECT COUNT(*) AS n FROM anexos")["n"].iloc[0]

with st.sidebar:
    st.markdown("""
    <div class="sidebar-brand">
        <h2>🧰 Central de Suprimentos</h2>
        <p>Materiais, Fornecedores & Cotações</p>
    </div>
    """, unsafe_allow_html=True)

    menu = st.radio(
        "Menu principal",
        [
            "🔍 Pesquisa & Catálogo",
            "📦 Materiais & Fornecedores",
            "💰 Cotações & Preços",
            "📎 Anexos & Backup",
        ],
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
        q = a.text_input(
            "Buscar material",
            placeholder="Digite descrição, código, fabricante, modelo ou palavra-chave..."
        )
        df_cats = read(
            "SELECT DISTINCT categoria FROM materiais "
            "WHERE categoria IS NOT NULL AND categoria<>'' ORDER BY categoria"
        )
        cats = ["Todas"] + df_cats["categoria"].tolist()
        cat = b.selectbox("Categoria", cats)
        dn = c.text_input("DN", placeholder="Ex.: 400")

    sql = "SELECT * FROM materiais WHERE 1=1"
    p = []
    if q.strip():
        sql += (
            " AND (descricao LIKE ? OR codigo LIKE ? OR fabricante LIKE ? "
            "OR modelo LIKE ? OR palavras_chave LIKE ? OR descricao_tecnica LIKE ?)"
        )
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
        badge_status = "🟢" if m.status == "Validado" else ("🟡" if m.status == "Em revisão" else "⚪")
        titulo = (
            f"{badge_status} {m.descricao}  •  "
            f"{m.categoria or 'Sem categoria'}  |  DN {m.dn or '—'}  |  PN {m.pn or '—'}"
        )
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

            t_forn, t_prec, t_doc = st.tabs([
                "🏢 Fornecedores vinculados",
                "💲 Histórico de preços & Orçamentos",
                "📄 Documentos técnicos"
            ])

            with t_forn:
                rel = read(
                    """SELECT f.razao_social AS Fornecedor, r.tipo_relacao AS Relação,
                              r.fabricante_ofertado AS Fabricante, r.modelo_ofertado AS Modelo,
                              r.data_interacao AS Data
                       FROM fornecimentos r JOIN fornecedores f ON f.id=r.fornecedor_id
                       WHERE r.material_id=? ORDER BY r.data_interacao DESC""",
                    (int(m.id),)
                )
                if not rel.empty:
                    st.dataframe(rel, use_container_width=True, hide_index=True)
                else:
                    st.caption("Sem fornecedores relacionados a este material.")

            with t_prec:
                hist_cot = read(
                    """SELECT c.id AS cot_id, c.data_cotacao AS Data, c.processo AS Processo,
                              f.id AS forn_id, f.razao_social AS Fornecedor, ci.quantidade AS Qtd,
                              ci.unidade AS Unid, ci.preco_unitario AS Preço_Unit,
                              ci.prazo_entrega AS Prazo, ci.observacoes AS Obs
                       FROM cotacao_itens ci
                       JOIN cotacoes c ON c.id = ci.cotacao_id
                       JOIN fornecedores f ON f.id = ci.fornecedor_id
                       WHERE ci.material_id=?
                       ORDER BY c.data_cotacao DESC, ci.preco_unitario ASC""",
                    (int(m.id),)
                )
                if not hist_cot.empty:
                    df_h = hist_cot.drop(columns=["cot_id", "forn_id"]).copy()
                    df_h["Preço_Unit"] = df_h["Preço_Unit"].apply(fmt_brl)
                    st.dataframe(df_h, use_container_width=True, hide_index=True)

                    cot_ids = tuple(hist_cot["cot_id"].unique().tolist())
                    placeholders = ",".join(["?"] * len(cot_ids))
                    anexos_orc = read(
                        f"""SELECT a.id, a.entidade_id, a.tipo_documento, a.nome_original,
                                   a.arquivo_salvo, a.data_upload, a.observacoes,
                                   c.processo, f.razao_social AS fornecedor_nome
                            FROM anexos a
                            LEFT JOIN cotacoes c ON c.id = a.entidade_id
                            LEFT JOIN fornecedores f ON f.id = a.fornecedor_id
                            WHERE a.entidade_tipo='cotacao' AND a.entidade_id IN ({placeholders})
                            ORDER BY a.id DESC""",
                        cot_ids
                    )
                    if not anexos_orc.empty:
                        st.markdown("**Planilhas e propostas das cotações acima**")
                        for _, ax_o in anexos_orc.iterrows():
                            caminho_o = ANEXOS_DIR / ax_o["arquivo_salvo"]
                            c_o1, c_o2 = st.columns([4, 1])
                            forn_txt = f" | Fornecedor: **{ax_o['fornecedor_nome']}**" if ax_o["fornecedor_nome"] else ""
                            proc_txt = ax_o["processo"] or f"Cotação #{ax_o['entidade_id']}"
                            c_o1.write(
                                f"📎 **{ax_o['nome_original']}** — {proc_txt}{forn_txt} ({ax_o['data_upload'] or ''})"
                            )
                            if caminho_o.exists():
                                c_o2.download_button(
                                    "Baixar arquivo",
                                    data=caminho_o.read_bytes(),
                                    file_name=ax_o["nome_original"],
                                    key=f"dl_orc_mat_{m.id}_{ax_o['id']}"
                                )
                else:
                    st.caption("Sem cotações registradas para este material.")

            with t_doc:
                anexos_mat = read(
                    "SELECT id, tipo_documento, nome_original, arquivo_salvo, data_upload, observacoes "
                    "FROM anexos WHERE entidade_tipo='material' AND entidade_id=? ORDER BY id DESC",
                    (int(m.id),)
                )
                if anexos_mat.empty:
                    st.caption("Nenhum arquivo técnico anexado diretamente a este material.")
                else:
                    for _, ax in anexos_mat.iterrows():
                        caminho = ANEXOS_DIR / ax["arquivo_salvo"]
                        col_a, col_b = st.columns([4, 1])
                        info_ax = f"**{ax['tipo_documento']}:** {ax['nome_original']} ({ax['data_upload'] or ''})"
                        if ax["observacoes"]:
                            info_ax += f" — _{ax['observacoes']}_"
                        col_a.write(info_ax)
                        if caminho.exists():
                            col_b.download_button(
                                "Baixar",
                                data=caminho.read_bytes(),
                                file_name=ax["nome_original"],
                                key=f"dl_pesq_mat_{ax['id']}"
                            )
                        else:
                            col_b.caption("Arquivo ausente")


# ==============================================================================
# 2. MATERIAIS & FORNECEDORES
# ==============================================================================
elif menu == "📦 Materiais & Fornecedores":
    st.title("Materiais & Fornecedores")
    st.caption("Cadastre, edite e vincule os itens do seu catálogo técnico e sua base de fornecedores.")

    sec_mat, sec_forn, sec_vinc = st.tabs([
        "🧱 Materiais",
        "🏢 Fornecedores",
        "🔗 Vincular Material x Fornecedor"
    ])

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

                    if not existentes.empty:
                        duplicados_exatos = existentes[
                            existentes.apply(
                                lambda r: norm(r["descricao"]) == desc_n
                                and norm(r["fabricante"]) == fab_n
                                and norm(r["modelo"]) == mod_n
                                and norm(r["dn"]) == dn_n,
                                axis=1,
                            )
                        ]
                        mesma_descricao = existentes[
                            existentes.apply(lambda r: norm(r["descricao"]) == desc_n, axis=1)
                        ]
                    else:
                        duplicados_exatos = pd.DataFrame()
                        mesma_descricao = pd.DataFrame()

                    if not duplicados_exatos.empty:
                        st.error("Este material já está cadastrado com os mesmos dados:")
                        st.dataframe(duplicados_exatos, use_container_width=True, hide_index=True)
                    elif not mesma_descricao.empty and not forcar_similar:
                        st.warning("Já existe material com essa descrição. Marque a caixa de confirmação se for variação válida:")
                        st.dataframe(mesma_descricao, use_container_width=True, hide_index=True)
                    else:
                        try:
                            write(
                                """INSERT INTO materiais(
                                   codigo,descricao,categoria,subcategoria,fabricante,modelo,
                                   codigo_fabricante,dn,pn,material_fabricacao,tipo_conexao,
                                   acionamento,aplicacao,palavras_chave,descricao_tecnica,status)
                                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (
                                    codigo.strip() or None, descricao.strip(), categoria, sub.strip(),
                                    fab.strip(), modelo.strip(), codfab.strip(), dn.strip(), pn.strip(),
                                    mat, conex, ac, aplic, palavras.strip(), desc.strip(), status
                                )
                            )
                            st.success("Material cadastrado.")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Código interno já cadastrado. Use outro código ou deixe em branco.")

        with sub_m_edit:
            mats = read("SELECT * FROM materiais ORDER BY id DESC")
            if mats.empty:
                st.info("Nenhum material cadastrado para editar ou excluir.")
            else:
                cols_resumo = ["id", "codigo", "descricao", "categoria", "fabricante", "modelo", "dn", "pn", "status"]
                st.dataframe(mats[cols_resumo], use_container_width=True, hide_index=True)

                def label_mat_edit(i):
                    r = mats.loc[mats["id"] == i].iloc[0]
                    return f"ID {i} — {r['descricao']} (DN {r['dn'] or '—'} | Fab: {r['fabricante'] or '—'})"

                mid_edit = st.selectbox("Selecione o material pelo ID", mats["id"].tolist(), format_func=label_mat_edit)
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
                    e_palavras = st.text_input("Palavras-chave (separadas por vírgula)", value=item["palavras_chave"] or "")
                    e_desc = st.text_area("Descrição técnica / observações", value=item["descricao_tecnica"] or "")
                    e_status = st.selectbox("Status", STATUS_MAT, index=idx_opcao(STATUS_MAT, item["status"]))
                    salvar_edicao = st.form_submit_button("Salvar alterações")

                if salvar_edicao:
                    if not e_descricao.strip():
                        st.error("Descrição é obrigatória.")
                    else:
                        outros = mats[mats["id"] != mid_edit]
                        if not outros.empty:
                            dup_exato = outros[
                                outros.apply(
                                    lambda r: norm(r["descricao"]) == norm(e_descricao)
                                    and norm(r["fabricante"]) == norm(e_fab)
                                    and norm(r["modelo"]) == norm(e_modelo)
                                    and norm(r["dn"]) == norm(e_dn),
                                    axis=1,
                                )
                            ]
                        else:
                            dup_exato = pd.DataFrame()

                        if not dup_exato.empty:
                            st.error("Já existe outro material cadastrado com exatamente estes mesmos dados.")
                        else:
                            try:
                                write(
                                    """UPDATE materiais SET
                                       codigo=?, descricao=?, categoria=?, subcategoria=?, fabricante=?, modelo=?,
                                       codigo_fabricante=?, dn=?, pn=?, material_fabricacao=?, tipo_conexao=?,
                                       acionamento=?, aplicacao=?, palavras_chave=?, descricao_tecnica=?, status=?
                                       WHERE id=?""",
                                    (
                                        e_codigo.strip() or None, e_descricao.strip(), e_categoria, e_sub.strip(),
                                        e_fab.strip(), e_modelo.strip(), e_codfab.strip(), e_dn.strip(), e_pn.strip(),
                                        e_mat, e_conex, e_ac, e_aplic, e_palavras.strip(), e_desc.strip(), e_status,
                                        int(mid_edit)
                                    )
                                )
                                st.success("Material atualizado com sucesso.")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Código interno já pertence a outro material.")

                st.divider()
                st.subheader("Excluir material")
                qtd_rel = read("SELECT COUNT(*) AS total FROM fornecimentos WHERE material_id=?", (int(mid_edit),))["total"].iloc[0]
                qtd_cot = read("SELECT COUNT(*) AS total FROM cotacao_itens WHERE material_id=?", (int(mid_edit),))["total"].iloc[0]
                if qtd_rel > 0 or qtd_cot > 0:
                    st.warning(f"Este material possui {qtd_rel} vínculo(s) com fornecedores e {qtd_cot} item(ns) em cotações.")
                confirmar_del_mat = st.checkbox(
                    "Confirmo que desejo excluir permanentemente este material",
                    key=f"del_mat_{mid_edit}"
                )
                if st.button("Excluir material selecionado", type="primary"):
                    if not confirmar_del_mat:
                        st.error("Marque a caixa de confirmação antes de excluir.")
                    else:
                        remover_anexos_entidade("material", int(mid_edit))
                        write("DELETE FROM cotacao_itens WHERE material_id=?", (int(mid_edit),))
                        write("DELETE FROM fornecimentos WHERE material_id=?", (int(mid_edit),))
                        write("DELETE FROM materiais WHERE id=?", (int(mid_edit),))
                        st.success("Material excluído.")
                        st.rerun()

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
                    f_existentes = read("SELECT id, razao_social, nome_fantasia, cnpj, contato FROM fornecedores")
                    razao_n = norm(razao)
                    cnpj_d = apenas_digitos(cnpj)

                    if not f_existentes.empty:
                        dup_forn = f_existentes[
                            f_existentes.apply(
                                lambda r: norm(r["razao_social"]) == razao_n
                                or (cnpj_d != "" and apenas_digitos(r["cnpj"]) == cnpj_d),
                                axis=1,
                            )
                        ]
                    else:
                        dup_forn = pd.DataFrame()

                    if not dup_forn.empty:
                        st.error("Já existe um fornecedor cadastrado com esta Razão Social ou CNPJ:")
                        st.dataframe(dup_forn, use_container_width=True, hide_index=True)
                    else:
                        write(
                            """INSERT INTO fornecedores(
                               razao_social,nome_fantasia,cnpj,contato,email,telefone,site,observacoes)
                               VALUES(?,?,?,?,?,?,?,?)""",
                            (
                                razao.strip(), fantasia.strip(), cnpj.strip(), contato.strip(),
                                email.strip(), telefone.strip(), site.strip(), obs.strip()
                            )
                        )
                        st.success("Fornecedor cadastrado.")
                        st.rerun()

            st.subheader("Fornecedores registrados")
            df_forn_lista = read(
                "SELECT id,razao_social,nome_fantasia,cnpj,contato,email,telefone "
                "FROM fornecedores ORDER BY razao_social"
            )
            st.dataframe(df_forn_lista, use_container_width=True, hide_index=True)

        with sub_f_edit:
            forns = read("SELECT * FROM fornecedores ORDER BY id DESC")
            if forns.empty:
                st.info("Nenhum fornecedor cadastrado para editar ou excluir.")
            else:
                cols_f = ["id", "razao_social", "nome_fantasia", "cnpj", "contato", "email", "telefone"]
                st.dataframe(forns[cols_f], use_container_width=True, hide_index=True)

                def label_forn_edit(i):
                    r = forns.loc[forns["id"] == i].iloc[0]
                    return f"ID {i} — {r['razao_social']} ({r['cnpj'] or 'Sem CNPJ'})"

                fid_edit = st.selectbox("Selecione o fornecedor pelo ID", forns["id"].tolist(), format_func=label_forn_edit)
                f_item = forns[forns["id"] == fid_edit].iloc[0]

                with st.form("form_editar_fornecedor"):
                    a, b = st.columns(2)
                    e_razao = a.text_input("Razão social *", value=f_item["razao_social"] or "")
                    e_fantasia = b.text_input("Nome fantasia", value=f_item["nome_fantasia"] or "")
                    e_cnpj = a.text_input("CNPJ", value=f_item["cnpj"] or "")
                    e_contato = b.text_input("Contato comercial", value=f_item["contato"] or "")
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
                        razao_n = norm(e_razao)
                        cnpj_d = apenas_digitos(e_cnpj)
                        if not outros_f.empty:
                            dup_f = outros_f[
                                outros_f.apply(
                                    lambda r: norm(r["razao_social"]) == razao_n
                                    or (cnpj_d != "" and apenas_digitos(r["cnpj"]) == cnpj_d),
                                    axis=1,
                                )
                            ]
                        else:
                            dup_f = pd.DataFrame()

                        if not dup_f.empty:
                            st.error("Já existe outro fornecedor com esta Razão Social ou CNPJ.")
                        else:
                            write(
                                """UPDATE fornecedores SET
                                   razao_social=?, nome_fantasia=?, cnpj=?, contato=?,
                                   email=?, telefone=?, site=?, observacoes=?
                                   WHERE id=?""",
                                (
                                    e_razao.strip(), e_fantasia.strip(), e_cnpj.strip(), e_contato.strip(),
                                    e_email.strip(), e_telefone.strip(), e_site.strip(), e_obs.strip(), int(fid_edit)
                                )
                            )
                            st.success("Fornecedor atualizado com sucesso.")
                            st.rerun()

                st.divider()
                st.subheader("Excluir fornecedor")
                qtd_rel_f = read("SELECT COUNT(*) AS total FROM fornecimentos WHERE fornecedor_id=?", (int(fid_edit),))["total"].iloc[0]
                qtd_cot_f = read("SELECT COUNT(*) AS total FROM cotacao_itens WHERE fornecedor_id=?", (int(fid_edit),))["total"].iloc[0]
                if qtd_rel_f > 0 or qtd_cot_f > 0:
                    st.warning(f"Este fornecedor possui {qtd_rel_f} vínculo(s) com materiais e {qtd_cot_f} item(ns) em cotações.")
                confirmar_del_forn = st.checkbox(
                    "Confirmo que desejo excluir permanentemente este fornecedor",
                    key=f"del_forn_{fid_edit}"
                )
                if st.button("Excluir fornecedor selecionado", type="primary"):
                    if not confirmar_del_forn:
                        st.error("Marque a caixa de confirmação antes de excluir.")
                    else:
                        remover_anexos_entidade("fornecedor", int(fid_edit))
                        write("DELETE FROM cotacao_itens WHERE fornecedor_id=?", (int(fid_edit),))
                        write("DELETE FROM fornecimentos WHERE fornecedor_id=?", (int(fid_edit),))
                        write("DELETE FROM fornecedores WHERE id=?", (int(fid_edit),))
                        st.success("Fornecedor excluído.")
                        st.rerun()

    with sec_vinc:
        ms = read("SELECT id,descricao,dn FROM materiais ORDER BY descricao")
        fs = read("SELECT id,razao_social FROM fornecedores ORDER BY razao_social")
        if ms.empty or fs.empty:
            st.info("Cadastre ao menos um material e um fornecedor nas abas ao lado primeiro.")
        else:
            def label_mat_rel(i):
                r = ms.loc[ms["id"] == i].iloc[0]
                return f"{r['descricao']} (DN {r['dn'] or '—'})"

            with st.form("rel"):
                c1, c2 = st.columns(2)
                mid = c1.selectbox("Material *", ms["id"].tolist(), format_func=label_mat_rel)
                fid = c2.selectbox(
                    "Fornecedor *",
                    fs["id"].tolist(),
                    format_func=lambda i: fs.loc[fs["id"] == i, "razao_social"].iloc[0]
                )
                c3, c4, c5 = st.columns(3)
                tipo = c3.selectbox("Tipo de relação", ["Forneceu", "Cotou", "Forneceu similar"])
                fabricante = c4.text_input("Fabricante ofertado")
                modelo = c5.text_input("Modelo ofertado")
                data = st.date_input("Data da interação")
                obs = st.text_area("Observações")
                ok = st.form_submit_button("Salvar vínculo", type="primary")
            if ok:
                write(
                    """INSERT INTO fornecimentos(
                       material_id,fornecedor_id,tipo_relacao,fabricante_ofertado,
                       modelo_ofertado,data_interacao,observacoes)
                       VALUES(?,?,?,?,?,?,?)""",
                    (mid, fid, tipo, fabricante, modelo, str(data), obs)
                )
                st.success("Relação cadastrada.")
                st.rerun()

            st.subheader("Vínculos registrados")
            df_vinc = read(
                """SELECT r.id, m.descricao AS Material, m.dn AS DN, f.razao_social AS Fornecedor,
                          r.tipo_relacao AS Tipo, r.fabricante_ofertado AS Fabricante,
                          r.modelo_ofertado AS Modelo, r.data_interacao AS Data
                   FROM fornecimentos r
                   JOIN materiais m ON m.id = r.material_id
                   JOIN fornecedores f ON f.id = r.fornecedor_id
                   ORDER BY r.id DESC"""
            )
            st.dataframe(df_vinc, use_container_width=True, hide_index=True)


# ==============================================================================
# 3. COTAÇÕES & PREÇOS
# ==============================================================================
elif menu == "💰 Cotações & Preços":
    st.title("Cotações & Histórico de Preços")
    st.caption("Importe planilhas de orçamento prontas ou gerencie processos de cotação manualmente.")

    aba_import, aba_cot_lista, aba_cot_itens, aba_cot_editar = st.tabs([
        "📥 Importar Planilha Pronta",
        "📋 Cadastrar cotação manual",
        "💲 Itens e preços",
        "✏️ Editar ou excluir"
    ])

    # --- NOVA ABA: IMPORTAÇÃO AUTOMÁTICA + ARQUIVO ---
    with aba_import:
        st.subheader("Importar orçamento pronto (Excel ou CSV)")
        st.write(
            "Envie uma planilha de orçamento pronta. O sistema **arquiva o documento original** "
            "e **cadastra automaticamente os materiais e preços** para consulta na Pesquisa."
        )

        arq_planilha = st.file_uploader(
            "Selecione a planilha de orçamento (.xlsx, .xls ou .csv)",
            type=["xlsx", "xls", "csv"],
            key="up_planilha_pronta"
        )

        if arq_planilha is not None:
            try:
                if arq_planilha.name.lower().endswith(".csv"):
                    try:
                        df_raw = pd.read_csv(arq_planilha, sep=None, engine="python")
                    except Exception:
                        arq_planilha.seek(0)
                        df_raw = pd.read_csv(arq_planilha, sep=";", encoding="latin1")
                else:
                    excel_file = pd.ExcelFile(arq_planilha)
                    aba_escolhida = excel_file.sheet_names[0]
                    if len(excel_file.sheet_names) > 1:
                        aba_escolhida = st.selectbox("Selecione a aba da planilha", excel_file.sheet_names)
                    df_raw = pd.read_excel(excel_file, sheet_name=aba_escolhida)

                df_raw = df_raw.dropna(how="all").reset_index(drop=True)
                df_raw.columns = [str(c).strip() for c in df_raw.columns]

                if df_raw.empty or len(df_raw.columns) == 0:
                    st.error("A planilha selecionada está vazia.")
                else:
                    st.markdown("**Prévia dos dados encontrados na planilha:**")
                    st.dataframe(df_raw.head(8), use_container_width=True, hide_index=True)

                    cols_plan = list(df_raw.columns)
                    cols_opc = ["(Não tem na planilha)"] + cols_plan

                    st.markdown("**1. Dados gerais do orçamento**")
                    g1, g2, g3 = st.columns([1.5, 1, 1.5])
                    nome_orc = g1.text_input("Identificação do orçamento *", value=Path(arq_planilha.name).stem)
                    data_orc = g2.date_input("Data do orçamento", value=date.today())
                    forn_padrao = g3.text_input(
                        "Fornecedor padrão (usado se não houver coluna de fornecedor)",
                        placeholder="Ex.: Tubos & Conexões Ltda"
                    )

                    st.markdown("**2. Mapeamento das colunas da planilha**")
                    m1, m2, m3 = st.columns(3)
                    col_desc = m1.selectbox(
                        "Coluna da Descrição / Material *",
                        cols_plan,
                        index=achar_coluna_padrao(cols_plan, ["descr", "material", "item", "produto", "espec"])
                    )
                    col_preco = m2.selectbox(
                        "Coluna do Preço Unitário *",
                        cols_plan,
                        index=achar_coluna_padrao(cols_plan, ["unit", "preco", "preço", "valor", "vlr"])
                    )
                    col_qtd = m3.selectbox(
                        "Coluna da Quantidade",
                        cols_opc,
                        index=achar_coluna_padrao(cols_opc, ["qtd", "quant", "qtde"])
                    )

                    m4, m5, m6 = st.columns(3)
                    col_unid = m4.selectbox(
                        "Coluna da Unidade",
                        cols_opc,
                        index=achar_coluna_padrao(cols_opc, ["unid", "und", "un"])
                    )
                    col_forn = m5.selectbox(
                        "Coluna do Fornecedor (se houver)",
                        cols_opc,
                        index=achar_coluna_padrao(cols_opc, ["forn", "empresa", "fornecedor"])
                    )
                    col_dn = m6.selectbox(
                        "Coluna de DN / Bitola (opcional)",
                        cols_opc,
                        index=achar_coluna_padrao(cols_opc, ["dn", "diam", "bitola"])
                    )

                    if st.button("🚀 Arquivar planilha e importar itens para o catálogo", type="primary"):
                        if not nome_orc.strip():
                            st.error("Informe uma identificação para o orçamento.")
                        else:
                            cid_novo = write(
                                """INSERT INTO cotacoes(processo, data_cotacao, objeto, status, observacoes)
                                   VALUES(?, ?, ?, 'Concluída', ?)""",
                                (
                                    nome_orc.strip(),
                                    str(data_orc),
                                    f"Importado de {arq_planilha.name}",
                                    "Importação automática de planilha pronta"
                                )
                            )

                            fid_default = None
                            if forn_padrao.strip():
                                fid_default, _ = obter_ou_criar_fornecedor(forn_padrao.strip())

                            arq_planilha.seek(0)
                            salvar_arquivo_anexo(
                                arq_planilha,
                                entidade_tipo="cotacao",
                                entidade_id=int(cid_novo),
                                tipo_documento="Proposta comercial / Orçamento",
                                observacoes="Planilha original importada",
                                fornecedor_id=fid_default
                            )

                            qtd_importados = 0
                            qtd_mat_novos = 0

                            for _, linha in df_raw.iterrows():
                                desc_val = linha.get(col_desc)
                                if pd.isna(desc_val) or not str(desc_val).strip():
                                    continue
                                if norm(desc_val) in ["total", "subtotal", "total geral", "valor total"]:
                                    continue

                                preco_val = parse_numero(linha.get(col_preco))
                                if preco_val <= 0:
                                    continue

                                qtd_val = parse_numero(linha.get(col_qtd)) if col_qtd != "(Não tem na planilha)" else 1.0
                                if qtd_val <= 0:
                                    qtd_val = 1.0

                                unid_val = str(linha.get(col_unid)).strip() if (col_unid != "(Não tem na planilha)" and pd.notna(linha.get(col_unid))) else "un"
                                dn_val = str(linha.get(col_dn)).strip() if (col_dn != "(Não tem na planilha)" and pd.notna(linha.get(col_dn))) else ""

                                if col_forn != "(Não tem na planilha)" and pd.notna(linha.get(col_forn)) and str(linha.get(col_forn)).strip():
                                    fid_linha, _ = obter_ou_criar_fornecedor(str(linha.get(col_forn)).strip())
                                elif fid_default is not None:
                                    fid_linha = fid_default
                                else:
                                    fid_linha, _ = obter_ou_criar_fornecedor("Fornecedor Não Especificado")

                                mid_linha, eh_novo = obter_ou_criar_material(str(desc_val).strip(), dn=dn_val)
                                if eh_novo:
                                    qtd_mat_novos += 1

                                write(
                                    """INSERT INTO cotacao_itens
                                       (cotacao_id, material_id, fornecedor_id, quantidade, unidade, preco_unitario, observacoes)
                                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                    (
                                        int(cid_novo),
                                        int(mid_linha),
                                        int(fid_linha),
                                        float(qtd_val),
                                        unid_val or "un",
                                        float(preco_val),
                                        f"Importado de {arq_planilha.name}"
                                    )
                                )
                                qtd_importados += 1

                            if qtd_importados == 0:
                                st.warning(
                                    "A planilha foi arquivada, mas nenhuma linha com descrição e preço maior que zero "
                                    "foi importada. Verifique se selecionou as colunas corretas."
                                )
                            else:
                                st.success(
                                    f"Concluído! {qtd_importados} item(ns) de preço importados "
                                    f"({qtd_mat_novos} material(is) novo(s) cadastrado(s)) e planilha arquivada."
                                )
            except Exception as erro:
                st.error(f"Não foi possível ler a planilha: {erro}")

    # --- ABA: CADASTRAR COTAÇÃO MANUAL ---
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
            write(
                "INSERT INTO cotacoes(processo,data_cotacao,objeto,status,observacoes) VALUES(?,?,?,?,?)",
                (processo.strip(), str(data), objeto.strip(), status, obs.strip())
            )
            st.success("Cotação criada.")
            st.rerun()
        st.subheader("Cotações registradas")
        df_cots_reg = read("SELECT * FROM cotacoes ORDER BY data_cotacao DESC, id DESC")
        st.dataframe(df_cots_reg, use_container_width=True, hide_index=True)

    # --- ABA: ITENS E PREÇOS ---
    with aba_cot_itens:
        cots = read("SELECT id, processo, data_cotacao, objeto, status FROM cotacoes ORDER BY data_cotacao DESC, id DESC")
        ms = read("SELECT id, descricao, dn, fabricante FROM materiais ORDER BY descricao")
        fs = read("SELECT id, razao_social FROM fornecedores ORDER BY razao_social")

        def label_cotacao(i):
            row = cots.loc[cots["id"] == i].iloc[0]
            proc = row["processo"] or "Sem nº"
            obj = row["objeto"] or "Sem objeto"
            dt = row["data_cotacao"] or ""
            return f"ID {i} | {proc} — {obj} ({dt})"

        def label_mat_cot(i):
            row = ms.loc[ms["id"] == i].iloc[0]
            dn_txt = row["dn"] or "—"
            fab_txt = row["fabricante"] or "Sem fab."
            return f"{row['descricao']} (DN {dn_txt} | {fab_txt})"

        if cots.empty:
            st.info("Importe uma planilha na primeira aba ou crie uma cotação manual antes de lançar itens.")
        elif ms.empty or fs.empty:
            st.info("Cadastre ao menos um material e um fornecedor para lançar preços manualmente.")
        else:
            cid = st.selectbox("Selecione a cotação / orçamento", cots["id"].tolist(), format_func=label_cotacao)

            with st.form("form_item_cotacao"):
                col1, col2 = st.columns(2)
                mid_c = col1.selectbox("Material *", ms["id"].tolist(), format_func=label_mat_cot)
                fid_c = col2.selectbox(
                    "Fornecedor *",
                    fs["id"].tolist(),
                    format_func=lambda i: fs.loc[fs["id"] == i, "razao_social"].iloc[0]
                )
                c1, c2, c3, c4 = st.columns([1, 1, 1.2, 1.3])
                qtd = c1.number_input("Quantidade *", min_value=0.01, value=1.0, step=1.0)
                unid = c2.text_input("Unidade", value="un")
                preco = c3.number_input("Preço unitário (R$) *", min_value=0.0, value=0.0, step=10.0, format="%.2f")
                prazo = c4.text_input("Prazo de entrega", placeholder="Ex.: 15 dias úteis")
                obs_item = st.text_input("Observações do item (frete, impostos, marca ofertada)")
                arq_orc_item = st.file_uploader(
                    "Anexar proposta / orçamento deste fornecedor (opcional)",
                    type=EXTENSOES_ACEITAS,
                    key="up_orc_junto_item"
                )
                add_item = st.form_submit_button("Adicionar preço à cotação", type="primary")

            if add_item:
                if preco <= 0:
                    st.error("Informe um preço unitário maior que zero.")
                else:
                    write(
                        """INSERT INTO cotacao_itens
                           (cotacao_id, material_id, fornecedor_id, quantidade, unidade,
                            preco_unitario, prazo_entrega, observacoes)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            int(cid), int(mid_c), int(fid_c), float(qtd),
                            unid.strip() or "un", float(preco), prazo.strip(), obs_item.strip()
                        )
                    )
                    if arq_orc_item is not None:
                        salvar_arquivo_anexo(
                            arq_orc_item,
                            entidade_tipo="cotacao",
                            entidade_id=int(cid),
                            tipo_documento="Proposta comercial / Orçamento",
                            observacoes=obs_item.strip(),
                            fornecedor_id=int(fid_c)
                        )
                    st.success("Item e preço adicionados.")
                    st.rerun()

            st.subheader("Itens lançados neste orçamento")
            itens_cot = read(
                """SELECT ci.id, m.descricao AS Material, m.dn AS DN, f.razao_social AS Fornecedor,
                          ci.quantidade AS Qtd, ci.unidade AS Unid,
                          ci.preco_unitario AS Preço_Unit,
                          (ci.quantidade * ci.preco_unitario) AS Total,
                          ci.prazo_entrega AS Prazo, ci.observacoes AS Obs
                   FROM cotacao_itens ci
                   JOIN materiais m ON m.id = ci.material_id
                   JOIN fornecedores f ON f.id = ci.fornecedor_id
                   WHERE ci.cotacao_id=?
                   ORDER BY m.descricao, ci.preco_unitario ASC""",
                (int(cid),)
            )

            if itens_cot.empty:
                st.caption("Nenhum item lançado nesta cotação ainda.")
            else:
                df_exibir = itens_cot.copy()
                df_exibir["Preço_Unit"] = df_exibir["Preço_Unit"].apply(fmt_brl)
                df_exibir["Total"] = df_exibir["Total"].apply(fmt_brl)
                st.dataframe(df_exibir, use_container_width=True, hide_index=True)

                def label_item_del(i):
                    row = itens_cot.loc[itens_cot["id"] == i].iloc[0]
                    return f"Item ID {i} — {row['Material']} | {row['Fornecedor']}"

                item_del = st.selectbox(
                    "Remover item lançado (se necessário)",
                    itens_cot["id"].tolist(),
                    format_func=label_item_del
                )
                if st.button("Remover item selecionado"):
                    write("DELETE FROM cotacao_itens WHERE id=?", (int(item_del),))
                    st.success("Item removido.")
                    st.rerun()

            st.divider()
            st.subheader("📎 Arquivos e planilhas vinculados")
            anexos_desta_cot = read(
                """SELECT a.id, a.tipo_documento, a.nome_original, a.arquivo_salvo,
                          a.data_upload, a.observacoes, f.razao_social AS fornecedor_nome
                   FROM anexos a
                   LEFT JOIN fornecedores f ON f.id = a.fornecedor_id
                   WHERE a.entidade_tipo='cotacao' AND a.entidade_id=?
                   ORDER BY a.id DESC""",
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
                        c_a1.write(
                            f"**{ax_c['tipo_documento']}:** {ax_c['nome_original']}{forn_label} ({ax_c['data_upload'] or ''})"
                        )
                        if ax_c["observacoes"]:
                            c_a1.caption(ax_c["observacoes"])
                        if caminho_c.exists():
                            c_a2.download_button(
                                "Baixar",
                                data=caminho_c.read_bytes(),
                                file_name=ax_c["nome_original"],
                                key=f"dl_cot_inline_{ax_c['id']}"
                            )
                        if c_a3.button("Excluir", key=f"del_cot_inline_{ax_c['id']}"):
                            if caminho_c.exists():
                                caminho_c.unlink()
                            write("DELETE FROM anexos WHERE id=?", (int(ax_c["id"]),))
                            st.rerun()

    # --- ABA: EDITAR OU EXCLUIR ---
    with aba_cot_editar:
        cots_ed = read("SELECT * FROM cotacoes ORDER BY id DESC")
        if cots_ed.empty:
            st.info("Nenhuma cotação cadastrada para editar ou excluir.")
        else:
            st.dataframe(cots_ed, use_container_width=True, hide_index=True)

            def label_cot_ed(i):
                r = cots_ed.loc[cots_ed["id"] == i].iloc[0]
                return f"ID {i} | {r['processo'] or 'Sem nº'} — {r['objeto'] or 'Sem objeto'} ({r['data_cotacao'] or ''})"

            cid_edit = st.selectbox("Selecione a cotação pelo ID", cots_ed["id"].tolist(), format_func=label_cot_ed)
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
                    """UPDATE cotacoes SET
                       processo=?, data_cotacao=?, objeto=?, status=?, observacoes=?
                       WHERE id=?""",
                    (e_proc.strip(), str(e_data), e_obj.strip(), e_status, e_obs.strip(), int(cid_edit))
                )
                st.success("Cotação atualizada com sucesso.")
                st.rerun()

            st.divider()
            st.subheader("Excluir cotação / orçamento")
            qtd_itens_c = read(
                "SELECT COUNT(*) AS total FROM cotacao_itens WHERE cotacao_id=?",
                (int(cid_edit),)
            )["total"].iloc[0]
            qtd_ax_c = read(
                "SELECT COUNT(*) AS total FROM anexos WHERE entidade_tipo='cotacao' AND entidade_id=?",
                (int(cid_edit),)
            )["total"].iloc[0]
            if qtd_itens_c > 0 or qtd_ax_c > 0:
                st.warning(f"Este registro possui {qtd_itens_c} item(ns) de preço e {qtd_ax_c} anexo(s) vinculado(s).")

            confirmar_del_cot = st.checkbox(
                "Confirmo que desejo excluir permanentemente este registro (e seus itens/anexos)",
                key=f"del_cot_{cid_edit}"
            )
            if st.button("Excluir registro selecionado", type="primary"):
                if not confirmar_del_cot:
                    st.error("Marque a caixa de confirmação antes de excluir.")
                else:
                    remover_anexos_entidade("cotacao", int(cid_edit))
                    write("DELETE FROM cotacao_itens WHERE cotacao_id=?", (int(cid_edit),))
                    write("DELETE FROM cotacoes WHERE id=?", (int(cid_edit),))
                    st.success("Registro excluído.")
                    st.rerun()


# ==============================================================================
# 4. ANEXOS & BACKUP
# ==============================================================================
else:
    st.title("Anexos & Exportação de Dados")
    st.caption("Gerencie todos os documentos técnicos, propostas comerciais e cópias de segurança.")

    aba_lista, aba_up, aba_exp = st.tabs([
        "📂 Todos os documentos anexados",
        "📤 Enviar anexo avulso",
        "💾 Exportar CSV & Backup"
    ])

    with aba_lista:
        filtro_t = st.selectbox(
            "Filtrar por vínculo",
            ["Todos", "cotacao", "material", "fornecedor"],
            format_func=lambda t: {
                "Todos": "Todos os anexos",
                "cotacao": "Cotações / Orçamentos",
                "material": "Materiais (Fichas e Catálogos)",
                "fornecedor": "Fornecedores"
            }[t]
        )
        if filtro_t == "Todos":
            df_ax = read("""
                SELECT a.*,
                       m.descricao AS mat_nome,
                       c.processo AS cot_proc, c.objeto AS cot_obj,
                       f_ent.razao_social AS forn_ent_nome,
                       f_orc.razao_social AS forn_orc_nome
                FROM anexos a
                LEFT JOIN materiais m ON a.entidade_tipo='material' AND m.id = a.entidade_id
                LEFT JOIN cotacoes c ON a.entidade_tipo='cotacao' AND c.id = a.entidade_id
                LEFT JOIN fornecedores f_ent ON a.entidade_tipo='fornecedor' AND f_ent.id = a.entidade_id
                LEFT JOIN fornecedores f_orc ON f_orc.id = a.fornecedor_id
                ORDER BY a.id DESC
            """)
        else:
            df_ax = read("""
                SELECT a.*,
                       m.descricao AS mat_nome,
                       c.processo AS cot_proc, c.objeto AS cot_obj,
                       f_ent.razao_social AS forn_ent_nome,
                       f_orc.razao_social AS forn_orc_nome
                FROM anexos a
                LEFT JOIN materiais m ON a.entidade_tipo='material' AND m.id = a.entidade_id
                LEFT JOIN cotacoes c ON a.entidade_tipo='cotacao' AND c.id = a.entidade_id
                LEFT JOIN fornecedores f_ent ON a.entidade_tipo='fornecedor' AND f_ent.id = a.entidade_id
                LEFT JOIN fornecedores f_orc ON f_orc.id = a.fornecedor_id
                WHERE a.entidade_tipo=?
                ORDER BY a.id DESC
            """, (filtro_t,))

        if df_ax.empty:
            st.info("Nenhum arquivo anexado encontrado.")
        else:
            for _, ax in df_ax.iterrows():
                caminho = ANEXOS_DIR / ax["arquivo_salvo"]
                if ax["entidade_tipo"] == "material":
                    vinculo_txt = f"Material: {ax['mat_nome'] or 'ID ' + str(ax['entidade_id'])}"
                elif ax["entidade_tipo"] == "cotacao":
                    proc_s = ax["cot_proc"] or f"ID {ax['entidade_id']}"
                    obj_s = f" ({ax['cot_obj']})" if ax["cot_obj"] else ""
                    forn_s = f" • Fornecedor: {ax['forn_orc_nome']}" if ax["forn_orc_nome"] else ""
                    vinculo_txt = f"Orçamento/Cotação: {proc_s}{obj_s}{forn_s}"
                else:
                    vinculo_txt = f"Fornecedor: {ax['forn_ent_nome'] or 'ID ' + str(ax['entidade_id'])}"

                with st.container(border=True):
                    c1, c2, c3 = st.columns([4, 1, 1])
                    c1.write(
                        f"**{ax['tipo_documento']}** — **{ax['nome_original']}** ({ax['data_upload'] or ''})\n\n"
                        f"📌 _{vinculo_txt}_"
                    )
                    if ax["observacoes"]:
                        c1.caption(f"Obs.: {ax['observacoes']}")
                    if caminho.exists():
                        c2.download_button(
                            "Baixar",
                            data=caminho.read_bytes(),
                            file_name=ax["nome_original"],
                            key=f"dl_tab_ax_{ax['id']}"
                        )
                    else:
                        c2.caption("Ausente")
                    if c3.button("Excluir", key=f"del_tab_ax_{ax['id']}"):
                        if caminho.exists():
                            caminho.unlink()
                        write("DELETE FROM anexos WHERE id=?", (int(ax["id"]),))
                        st.rerun()

    with aba_up:
        tipo_entidade = st.selectbox(
            "Vincular arquivo a:",
            ["cotacao", "material", "fornecedor"],
            format_func=lambda t: {
                "cotacao": "Cotação / Orçamento (proposta comercial)",
                "material": "Material (ficha técnica / catálogo)",
                "fornecedor": "Fornecedor (portfólio / certificado)"
            }[t]
        )

        opcoes_ids = []
        mapa_labels = {}

        if tipo_entidade == "material":
            df_e = read("SELECT id, descricao, dn, fabricante FROM materiais ORDER BY descricao")
            for _, r in df_e.iterrows():
                opcoes_ids.append(int(r["id"]))
                mapa_labels[int(r["id"])] = f"ID {r['id']} — {r['descricao']} (DN {r['dn'] or '—'})"
        elif tipo_entidade == "cotacao":
            df_e = read("SELECT id, processo, objeto, data_cotacao FROM cotacoes ORDER BY data_cotacao DESC, id DESC")
            for _, r in df_e.iterrows():
                opcoes_ids.append(int(r["id"]))
                mapa_labels[int(r["id"])] = f"ID {r['id']} | {r['processo'] or 'Sem nº'} — {r['objeto'] or 'Sem objeto'}"
        else:
            df_e = read("SELECT id, razao_social, cnpj FROM fornecedores ORDER BY razao_social")
            for _, r in df_e.iterrows():
                opcoes_ids.append(int(r["id"]))
                mapa_labels[int(r["id"])] = f"ID {r['id']} — {r['razao_social']}"

        fs_up = read("SELECT id, razao_social FROM fornecedores ORDER BY razao_social")

        if not opcoes_ids:
            st.info("Cadastre primeiro um registro desse tipo antes de anexar arquivos.")
        else:
            with st.form("form_upload_anexo"):
                ent_id = st.selectbox("Selecione o registro *", opcoes_ids, format_func=lambda i: mapa_labels[i])
                fid_up_sel = None
                if tipo_entidade == "cotacao" and not fs_up.empty:
                    op_f_up = [0] + fs_up["id"].tolist()
                    fid_up_sel = st.selectbox(
                        "Fornecedor deste orçamento (opcional)",
                        op_f_up,
                        format_func=lambda i: "Não especificar" if i == 0 else fs_up.loc[fs_up["id"] == i, "razao_social"].iloc[0]
                    )
                tipo_doc = st.selectbox("Tipo de documento", TIPOS_DOC)
                arquivo = st.file_uploader("Escolha o arquivo", type=EXTENSOES_ACEITAS)
                obs_ax = st.text_input("Observações sobre o arquivo")
                enviar_ax = st.form_submit_button("Salvar anexo", type="primary")

            if enviar_ax:
                if arquivo is None:
                    st.error("Selecione um arquivo antes de salvar.")
                else:
                    salvar_arquivo_anexo(
                        arquivo,
                        entidade_tipo=tipo_entidade,
                        entidade_id=int(ent_id),
                        tipo_documento=tipo_doc,
                        observacoes=obs_ax,
                        fornecedor_id=int(fid_up_sel) if fid_up_sel and fid_up_sel != 0 else None
                    )
                    st.success(f"Arquivo '{arquivo.name}' salvo com sucesso.")
                    st.rerun()

    with aba_exp:
        st.subheader("Exportar tabelas em CSV")
        st.write("Baixe planilhas individuais de cada módulo para abrir no Excel:")
        col_e1, col_e2, col_e3 = st.columns(3)
        tabelas = [
            ("materiais", "Materiais", col_e1),
            ("fornecedores", "Fornecedores", col_e2),
            ("fornecimentos", "Vínculos", col_e3),
            ("cotacoes", "Cotações", col_e1),
            ("cotacao_itens", "Itens Cotados", col_e2),
            ("anexos", "Lista de Anexos", col_e3),
        ]
        for tab_nome, rotulo, coluna in tabelas:
            data = read(f"SELECT * FROM {tab_nome}")
            coluna.download_button(
                f"⬇️ Baixar {rotulo} (.csv)",
                data.to_csv(index=False).encode("utf-8-sig"),
                f"{tab_nome}.csv",
                "text/csv",
                use_container_width=True
            )

        st.divider()
        st.info(
            "**Backup completo do sistema:** para salvar tudo em um pendrive ou pasta de segurança, "
            "basta copiar o arquivo `central.db` e a pasta `anexos/` localizados na pasta do projeto."
        )