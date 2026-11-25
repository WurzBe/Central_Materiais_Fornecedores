import sqlite3
from pathlib import Path
import streamlit as st
import pandas as pd

DB = Path(__file__).with_name("central.db")

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

CATEGORIAS = ["", "Tubos", "Conexões", "Válvulas", "Atuadores", "Medidores", "Bombas", "Materiais elétricos", "Instrumentação", "Outros"]
MATERIAIS_FAB = ["", "Ferro fundido dúctil", "Aço carbono", "Aço inoxidável", "PVC", "PEAD", "Bronze", "Outro"]
CONEXOES = ["", "Flangeada", "Ponta e bolsa", "Roscada", "Soldável", "Wafer", "Lug", "Outro"]
ACIONAMENTOS = ["", "Manual", "Elétrico", "Pneumático", "Hidráulico", "Sem acionamento"]
APLICACOES = ["", "Água potável", "Esgoto", "Drenagem", "Industrial", "Outra"]
STATUS_MAT = ["Em revisão", "Validado", "Inativo"]

st.set_page_config(page_title="Central de Materiais e Fornecedores", page_icon="🧰", layout="wide")
init()
st.title("Central de Materiais e Fornecedores")
st.caption("Protótipo local • banco de dados armazenado em central.db neste computador")

page = st.sidebar.radio("Navegação", ["Pesquisa", "Cadastrar material", "Fornecedores", "Relacionar fornecedor", "Cotações", "Exportar"])
st.sidebar.info("Versão inicial para testes locais. Não é multiusuário.")

if page == "Pesquisa":
    st.header("Pesquisar materiais")
    a,b,c = st.columns([3,1,1])
    q = a.text_input("Descrição, código, fabricante ou palavra-chave", "")
    cats = ["Todas"] + read("SELECT DISTINCT categoria FROM materiais WHERE categoria IS NOT NULL AND categoria<>'' ORDER BY categoria")["categoria"].tolist()
    cat = b.selectbox("Categoria", cats)
    dn = c.text_input("DN")
    sql = "SELECT * FROM materiais WHERE 1=1"
    p = []
    if q.strip():
        sql += " AND (descricao LIKE ? OR codigo LIKE ? OR fabricante LIKE ? OR modelo LIKE ? OR palavras_chave LIKE ? OR descricao_tecnica LIKE ?)"
        p += [f"%{q.strip()}%"]*6
    if cat != "Todas":
        sql += " AND categoria=?"; p.append(cat)
    if dn.strip():
        sql += " AND dn=?"; p.append(dn.strip())
    rows = read(sql + " ORDER BY descricao", p)
    st.caption(f"{len(rows)} resultado(s)")
    if rows.empty:
        st.info("Nenhum material encontrado. Cadastre materiais para começar a formar o catálogo.")
    for _,m in rows.iterrows():
        with st.expander(f"{m.descricao} | {m.categoria or 'Sem categoria'} | DN {m.dn or '—'} | PN {m.pn or '—'}"):
            x,y = st.columns(2)
            x.write(f"**Código interno:** {m.codigo or 'Não informado'}")
            x.write(f"**Fabricante:** {m.fabricante or 'Não informado'}")
            x.write(f"**Modelo:** {m.modelo or 'Não informado'}")
            x.write(f"**Acionamento:** {m.acionamento or 'Não informado'}")
            y.write(f"**Material:** {m.material_fabricacao or 'Não informado'}")
            y.write(f"**Conexão:** {m.tipo_conexao or 'Não informado'}")
            y.write(f"**Aplicação:** {m.aplicacao or 'Não informado'}")
            y.write(f"**Status:** {m.status}")
            st.write(m.descricao_tecnica or "")

            rel = read("""SELECT f.razao_social AS Fornecedor, r.tipo_relacao AS Relação,
                                 r.fabricante_ofertado AS Fabricante, r.modelo_ofertado AS Modelo,
                                 r.data_interacao AS Data
                          FROM fornecimentos r JOIN fornecedores f ON f.id=r.fornecedor_id
                          WHERE r.material_id=? ORDER BY r.data_interacao DESC""", (int(m.id),))
            st.markdown("**Fornecedores relacionados**")
            st.dataframe(rel, use_container_width=True, hide_index=True) if not rel.empty else st.caption("Sem fornecedores relacionados.")

            hist_cot = read("""SELECT c.data_cotacao AS Data, c.processo AS Processo,
                                      f.razao_social AS Fornecedor, ci.quantidade AS Qtd,
                                      ci.unidade AS Unid, ci.preco_unitario AS Preço_Unit,
                                      ci.prazo_entrega AS Prazo, ci.observacoes AS Obs
                               FROM cotacao_itens ci
                               JOIN cotacoes c ON c.id = ci.cotacao_id
                               JOIN fornecedores f ON f.id = ci.fornecedor_id
                               WHERE ci.material_id=?
                               ORDER BY c.data_cotacao DESC, ci.preco_unitario ASC""", (int(m.id),))
            st.markdown("**Histórico de cotações e preços**")
            if not hist_cot.empty:
                hist_cot["Preço_Unit"] = hist_cot["Preço_Unit"].apply(fmt_brl)
                st.dataframe(hist_cot, use_container_width=True, hide_index=True)
            else:
                st.caption("Sem cotações registradas para este material.")

elif page == "Cadastrar material":
    st.header("Materiais")
    aba_novo, aba_editar = st.tabs(["Cadastrar novo", "Editar ou excluir"])

    with aba_novo:
        with st.form("material"):
            a,b = st.columns(2)
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

                duplicados_exatos = existentes[
                    existentes.apply(
                        lambda r: norm(r["descricao"]) == desc_n
                        and norm(r["fabricante"]) == fab_n
                        and norm(r["modelo"]) == mod_n
                        and norm(r["dn"]) == dn_n,
                        axis=1,
                    )
                ] if not existentes.empty else pd.DataFrame()

                mesma_descricao = existentes[
                    existentes.apply(lambda r: norm(r["descricao"]) == desc_n, axis=1)
                ] if not existentes.empty else pd.DataFrame()

                if not duplicados_exatos.empty:
                    st.error("Este material já está cadastrado com os mesmos dados (Descrição, DN, Fabricante e Modelo):")
                    st.dataframe(duplicados_exatos, use_container_width=True, hide_index=True)
                elif not mesma_descricao.empty and not forcar_similar:
                    st.warning("Já existe(m) material(is) com essa mesma descrição. Verifique abaixo antes de duplicar. Se for uma variação válida, marque a caixa de confirmação e clique em Salvar novamente:")
                    st.dataframe(mesma_descricao, use_container_width=True, hide_index=True)
                else:
                    try:
                        write("""INSERT INTO materiais(codigo,descricao,categoria,subcategoria,fabricante,modelo,codigo_fabricante,dn,pn,material_fabricacao,tipo_conexao,acionamento,aplicacao,palavras_chave,descricao_tecnica,status)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (codigo.strip() or None, descricao.strip(), categoria, sub.strip(), fab.strip(), modelo.strip(), codfab.strip(), dn.strip(), pn.strip(), mat, conex, ac, aplic, palavras.strip(), desc.strip(), status))
                        st.success("Material cadastrado.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Código interno já cadastrado. Use outro código ou deixe em branco.")

    with aba_editar:
        mats = read("SELECT * FROM materiais ORDER BY id DESC")
        if mats.empty:
            st.info("Nenhum material cadastrado para editar ou excluir.")
        else:
            st.dataframe(mats[["id", "codigo", "descricao", "categoria", "fabricante", "modelo", "dn", "pn", "status"]], use_container_width=True, hide_index=True)
            mid_edit = st.selectbox(
                "Selecione o material pelo ID para editar ou excluir",
                mats["id"].tolist(),
                format_func=lambda i: f"ID {i} — {mats.loc[mats.id==i, 'descricao'].iloc[0]} (DN {mats.loc[mats.id==i, 'dn'].iloc[0] or '—'} | Fab: {mats.loc[mats.id==i, 'fabricante'].iloc[0] or '—'})"
            )
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
                    dup_exato = outros[
                        outros.apply(
                            lambda r: norm(r["descricao"]) == norm(e_descricao)
                            and norm(r["fabricante"]) == norm(e_fab)
                            and norm(r["modelo"]) == norm(e_modelo)
                            and norm(r["dn"]) == norm(e_dn),
                            axis=1,
                        )
                    ] if not outros.empty else pd.DataFrame()

                    if not dup_exato.empty:
                        st.error("Já existe outro material cadastrado com exatamente estes mesmos dados.")
                    else:
                        try:
                            write("""UPDATE materiais SET
                                codigo=?, descricao=?, categoria=?, subcategoria=?, fabricante=?, modelo=?,
                                codigo_fabricante=?, dn=?, pn=?, material_fabricacao=?, tipo_conexao=?,
                                acionamento=?, aplicacao=?, palavras_chave=?, descricao_tecnica=?, status=?
                                WHERE id=?""",
                                (e_codigo.strip() or None, e_descricao.strip(), e_categoria, e_sub.strip(), e_fab.strip(),
                                 e_modelo.strip(), e_codfab.strip(), e_dn.strip(), e_pn.strip(), e_mat, e_conex,
                                 e_ac, e_aplic, e_palavras.strip(), e_desc.strip(), e_status, int(mid_edit)))
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
            confirmar_del_mat = st.checkbox("Confirmo que desejo excluir permanentemente este material (e seus vínculos/itens de cotação, se houver)", key=f"del_mat_{mid_edit}")
            if st.button("Excluir material selecionado", type="primary"):
                if not confirmar_del_mat:
                    st.error("Marque a caixa de confirmação antes de excluir.")
                else:
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

                dup_forn = f_existentes[
                    f_existentes.apply(
                        lambda r: norm(r["razao_social"]) == razao_n
                        or (cnpj_d != "" and apenas_digitos(r["cnpj"]) == cnpj_d),
                        axis=1,
                    )
                ] if not f_existentes.empty else pd.DataFrame()

                if not dup_forn.empty:
                    st.error("Já existe um fornecedor cadastrado com esta Razão Social ou CNPJ:")
                    st.dataframe(dup_forn, use_container_width=True, hide_index=True)
                else:
                    write("INSERT INTO fornecedores(razao_social,nome_fantasia,cnpj,contato,email,telefone,site,observacoes) VALUES(?,?,?,?,?,?,?,?)",
                          (razao.strip(), fantasia.strip(), cnpj.strip(), contato.strip(), email.strip(), telefone.strip(), site.strip(), obs.strip()))
                    st.success("Fornecedor cadastrado.")
                    st.rerun()
        st.subheader("Fornecedores registrados")
        st.dataframe(read("SELECT id,razao_social,nome_fantasia,cnpj,contato,email,telefone FROM fornecedores ORDER BY razao_social"), use_container_width=True, hide_index=True)

    with aba_f_editar:
        forns = read("SELECT * FROM fornecedores ORDER BY id DESC")
        if forns.empty:
            st.info("Nenhum fornecedor cadastrado para editar ou excluir.")
        else:
            st.dataframe(forns[["id", "razao_social", "nome_fantasia", "cnpj", "contato", "email", "telefone"]], use_container_width=True, hide_index=True)
            fid_edit = st.selectbox(
                "Selecione o fornecedor pelo ID para editar ou excluir",
                forns["id"].tolist(),
                format_func=lambda i: f"ID {i} — {forns.loc[forns.id==i, 'razao_social'].iloc[0]} ({forns.loc[forns.id