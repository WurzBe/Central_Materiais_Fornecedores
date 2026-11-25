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
          tipo_documento TEXT,
          nome_original TEXT NOT NULL,
          arquivo_salvo TEXT NOT NULL,
          data_upload TEXT,
          observacoes TEXT
        );
        """)


def read(sql, params=()):
    with db() as c:
        return pd.read_sql_query(sql, c, params=params)


def write(sql, params=()):
    with db() as c:
        c.execute(sql, params)


def norm(texto):
    return " ".join((texto or "").strip().lower().split())


def apenas_digitos(texto):
    return "".join(ch for ch in (texto or "") if ch.isdigit())


def idx_opcao(opcoes, valor):
    return opcoes.index(valor) if valor in opcoes else 0


def fmt_brl(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


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
    "Ficha técnica", "Catálogo", "Proposta comercial",
    "Desenho técnico", "Certificado / Norma", "Outro"
]

st.set_page_config(page_title="Central de Materiais e Fornecedores", page_icon="🧰", layout="wide")
init()
st.title("Central de Materiais e Fornecedores")
st.caption("Protótipo local • banco central.db e arquivos na pasta anexos/")

paginas = [
    "Pesquisa", "Cadastrar material", "Fornecedores",
    "Relacionar fornecedor", "Cotações", "Anexos", "Exportar"
]
page = st.sidebar.radio("Navegação", paginas)
st.sidebar.info("Versão local (custo zero). Para backup completo, copie central.db e a pasta anexos/.")

if page == "Pesquisa":
    st.header("Pesquisar materiais")
    a, b, c = st.columns([3, 1, 1])
    q = a.text_input("Descrição, código, fabricante ou palavra-chave", "")
    df_cats = read(
        "SELECT DISTINCT categoria FROM materiais "
        "WHERE categoria IS NOT NULL AND categoria<>'' ORDER BY categoria"
    )
    cats = ["Todas"] + df_cats["categoria"].tolist()
    cat = b.selectbox("Categoria", cats)
    dn = c.text_input("DN")

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
    st.caption(f"{len(rows)} resultado(s)")
    if rows.empty:
        st.info("Nenhum material encontrado. Cadastre materiais para começar a formar o catálogo.")

    for _, m in rows.iterrows():
        titulo = f"{m.descricao} | {m.categoria or 'Sem categoria'} | DN {m.dn or '—'} | PN {m.pn or '—'}"
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
            st.write(m.descricao_tecnica or "")

            rel = read(
                """SELECT f.razao_social AS Fornecedor, r.tipo_relacao AS Relação,
                          r.fabricante_ofertado AS Fabricante, r.modelo_ofertado AS Modelo,
                          r.data_interacao AS Data
                   FROM fornecimentos r JOIN fornecedores f ON f.id=r.fornecedor_id
                   WHERE r.material_id=? ORDER BY r.data_interacao DESC""",
                (int(m.id),)
            )
            st.markdown("**Fornecedores relacionados**")
            if not rel.empty:
                st.dataframe(rel, use_container_width=True, hide_index=True)
            else:
                st.caption("Sem fornecedores relacionados.")

            hist_cot = read(
                """SELECT c.data_cotacao AS Data, c.processo AS Processo,
                          f.razao_social AS Fornecedor, ci.quantidade AS Qtd,
                          ci.unidade AS Unid, ci.preco_unitario AS Preço_Unit,
                          ci.prazo_entrega AS Prazo, ci.observacoes AS Obs
                   FROM cotacao_itens ci
                   JOIN cotacoes c ON c.id = ci.cotacao_id
                   JOIN fornecedores f ON f.id = ci.fornecedor_id
                   WHERE ci.material_id=?
                   ORDER BY c.data_cotacao DESC, ci.preco_unitario ASC""",
                (int(m.id),)
            )
            st.markdown("**Histórico de cotações e preços**")
            if not hist_cot.empty:
                hist_cot["Preço_Unit"] = hist_cot["Preço_Unit"].apply(fmt_brl)
                st.dataframe(hist_cot, use_container_width=True, hide_index=True)
            else:
                st.caption("Sem cotações registradas para este material.")

            anexos_mat = read(
                "SELECT id, tipo_documento, nome_original, arquivo_salvo, data_upload, observacoes "
                "FROM anexos WHERE entidade_tipo='material' AND entidade_id=? ORDER BY id DESC",
                (int(m.id),)
            )
            st.markdown("**Documentos e fichas técnicas anexadas**")
            if anexos_mat.empty:
                st.caption("Nenhum arquivo anexado a este material.")
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

elif page == "Cadastrar material":
    st.header("Materiais")
    aba_novo, aba_editar = st.tabs(["Cadastrar novo", "Editar ou excluir"])

    with aba_novo:
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
            ok = st.form_submit_button("Salvar material")

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

    with aba_editar:
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

elif page == "Fornecedores":
    st.header("Fornecedores")
    aba_f_novo, aba_f_editar = st.tabs(["Cadastrar novo", "Editar ou excluir"])

    with aba_f_novo:
        with st.form("fornecedor"):
            razao = st.text_input("Razão social *")
            fantasia = st.text_input("Nome fantasia")
            cnpj = st.text_input("CNPJ")
            contato = st.text_input("Contato comercial")
            email = st.text_input("E-mail")
            telefone = st.text_input("Telefone")
            site = st.text_input("Site")
            obs = st.text_area("Observações")
            ok = st.form_submit_button("Salvar fornecedor")

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

    with aba_f_editar:
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
                e_razao = st.text_input("Razão social *", value=f_item["razao_social"] or "")
                e_fantasia = st.text_input("Nome fantasia", value=f_item["nome_fantasia"] or "")
                e_cnpj = st.text_input("CNPJ", value=f_item["cnpj"] or "")
                e_contato = st.text_input("Contato comercial", value=f_item["contato"] or "")
                e_email = st.text_input("E-mail", value=f_item["email"] or "")
                e_telefone = st.text_input("Telefone", value=f_item["telefone"] or "")
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

elif page == "Relacionar fornecedor":
    st.header("Relacionar fornecedor e material")
    ms = read("SELECT id,descricao,dn FROM materiais ORDER BY descricao")
    fs = read("SELECT id,razao_social FROM fornecedores ORDER BY razao_social")
    if ms.empty or fs.empty:
        st.info("Cadastre ao menos um material e um fornecedor primeiro.")
    else:
        def label_mat_rel(i):
            r = ms.loc[ms["id"] == i].iloc[0]
            return f"{r['descricao']} (DN {r['dn'] or '—'})"

        with st.form("rel"):
            mid = st.selectbox("Material", ms["id"].tolist(), format_func=label_mat_rel)
            fid = st.selectbox(
                "Fornecedor",
                fs["id"].tolist(),
                format_func=lambda i: fs.loc[fs["id"] == i, "razao_social"].iloc[0]
            )
            tipo = st.selectbox("Tipo de relação", ["Forneceu", "Cotou", "Forneceu similar"])
            fabricante = st.text_input("Fabricante ofertado")
            modelo = st.text_input("Modelo ofertado")
            data = st.date_input("Data da interação")
            obs = st.text_area("Observações")
            ok = st.form_submit_button("Salvar relação")
        if ok:
            write(
                """INSERT INTO fornecimentos(
                   material_id,fornecedor_id,tipo_relacao,fabricante_ofertado,
                   modelo_ofertado,data_interacao,observacoes)
                   VALUES(?,?,?,?,?,?,?)""",
                (mid, fid, tipo, fabricante, modelo, str(data), obs)
            )
            st.success("Relação cadastrada.")

elif page == "Cotações":
    st.header("Cotações")
    aba_cot_lista, aba_cot_itens = st.tabs(["Cadastrar cotação", "Itens e preços da cotação"])

    with aba_cot_lista:
        with st.form("cot"):
            a, b = st.columns(2)
            processo = a.text_input("Número do processo")
            data = b.date_input("Data")
            objeto = a.text_input("Objeto")
            status = b.selectbox("Status", ["Em andamento", "Concluída", "Cancelada"])
            obs = st.text_area("Observações")
            ok = st.form_submit_button("Criar cotação")
        if ok:
            write(
                "INSERT INTO cotacoes(processo,data_cotacao,objeto,status,observacoes) VALUES(?,?,?,?,?)",
                (processo.strip(), str(data), objeto.strip(), status, obs.strip())
            )
            st.success("Cotação criada.")
            st.rerun()
        st.subheader("Cotações registradas")
        st.dataframe(read("SELECT * FROM cotacoes ORDER BY data_cotacao DESC, id DESC"), use_container_width=True, hide_index=True)

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
            st.info("Crie uma cotação na aba 'Cadastrar cotação' antes de lançar itens e preços.")
        elif ms.empty or fs.empty:
            st.info("Cadastre ao menos um material e um fornecedor para lançar preços.")
        else:
            cid = st.selectbox("Selecione a cotação", cots["id"].tolist(), format_func=label_cotacao)

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
                add_item = st.form_submit_button("Adicionar preço à cotação")

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
                    st.success("Item e preço adicionados à cotação.")
                    st.rerun()

            st.subheader("Itens lançados nesta cotação")
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

elif page == "Anexos":
    st.header("Anexos: Propostas, Catálogos e Fichas Técnicas")
    st.caption(f"Arquivos armazenados localmente em: {ANEXOS_DIR}")

    aba_up, aba_lista = st.tabs(["Enviar novo arquivo", "Consultar e baixar anexos"])

    with aba_up:
        tipo_entidade = st.selectbox(
            "Vincular arquivo a:",
            ["material", "cotacao", "fornecedor"],
            format_func=lambda t: {
                "material": "Material (ficha técnica / catálogo)",
                "cotacao": "Cotação (proposta comercial)",
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

        if not opcoes_ids:
            st.info("Cadastre primeiro um registro desse tipo antes de anexar arquivos.")
        else:
            with st.form("form_upload_anexo"):
                ent_id = st.selectbox("Selecione o registro *", opcoes_ids, format_func=lambda i: mapa_labels[i])
                tipo_doc = st.selectbox("Tipo de documento", TIPOS_DOC)
                arquivo = st.file_uploader(
                    "Escolha o arquivo (PDF, imagem, Excel, Word, etc.)",
                    type=["pdf", "png", "jpg", "jpeg", "xlsx", "xls", "docx", "doc", "csv", "txt"]
                )
                obs_ax = st.text_input("Observações sobre o arquivo")
                enviar_ax = st.form_submit_button("Salvar anexo")

            if enviar_ax:
                if arquivo is None:
                    st.error("Selecione um arquivo antes de salvar.")
                else:
                    ext = Path(arquivo.name).suffix.lower()
                    nome_unico = f"{tipo_entidade}_{ent_id}_{uuid.uuid4().hex[:8]}{ext}"
                    destino = ANEXOS_DIR / nome_unico
                    destino.write_bytes(arquivo.getbuffer())
                    write(
                        """INSERT INTO anexos(
                           entidade_tipo, entidade_id, tipo_documento,
                           nome_original, arquivo_salvo, data_upload, observacoes)
                           VALUES(?,?,?,?,?,?,?)""",
                        (
                            tipo_entidade, int(ent_id), tipo_doc,
                            arquivo.name, nome_unico, str(date.today()), obs_ax.strip()
                        )
                    )
                    st.success(f"Arquivo '{arquivo.name}' salvo com sucesso.")
                    st.rerun()

    with aba_lista:
        filtro_t = st.selectbox(
            "Filtrar por vínculo",
            ["Todos", "material", "cotacao", "fornecedor"],
            format_func=lambda t: {
                "Todos": "Todos os anexos",
                "material": "Materiais",
                "cotacao": "Cotações",
                "fornecedor": "Fornecedores"
            }[t]
        )
        if filtro_t == "Todos":
            df_ax = read("SELECT * FROM anexos ORDER BY id DESC")
        else:
            df_ax = read("SELECT * FROM anexos WHERE entidade_tipo=? ORDER BY id DESC", (filtro_t,))

        if df_ax.empty:
            st.info("Nenhum arquivo anexado encontrado.")
        else:
            for _, ax in df_ax.iterrows():
                caminho = ANEXOS_DIR / ax["arquivo_salvo"]
                with st.container(border=True):
                    c1, c2, c3 = st.columns([4, 1, 1])
                    c1.write(
                        f"**[{ax['entidade_tipo'].upper()} ID {ax['entidade_id']}]** "
                        f"{ax['tipo_documento']} — **{ax['nome_original']}** ({ax['data_upload'] or ''})"
                    )
                    if ax["observacoes"]:
                        c1.caption(ax["observacoes"])
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

else:
    st.header("Exportar dados")
    st.write("Exporte cópias CSV das tabelas. Para backup integral, copie o arquivo central.db e a pasta anexos/ com o aplicativo fechado.")
    for table in ["materiais", "fornecedores", "fornecimentos", "cotacoes", "cotacao_itens", "anexos"]:
        data = read(f"SELECT * FROM {table}")
        st.download_button(
            f"Baixar {table}.csv",
            data.to_csv(index=False).encode("utf-8-sig"),
            f"{table}.csv",
            "text/csv"
        )