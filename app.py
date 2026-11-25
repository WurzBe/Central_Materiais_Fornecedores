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
            x.write(f"**Fabricante:** {m.fabricante or 'Não informado'}")
            x.write(f"**Modelo:** {m.modelo or 'Não informado'}")
            x.write(f"**Acionamento:** {m.acionamento or 'Não informado'}")
            y.write(f"**Material:** {m.material_fabricacao or 'Não informado'}")
            y.write(f"**Conexão:** {m.tipo_conexao or 'Não informado'}")
            y.write(f"**Status:** {m.status}")
            st.write(m.descricao_tecnica or "")
            rel = read("""SELECT f.razao_social, r.tipo_relacao, r.fabricante_ofertado, r.modelo_ofertado, r.data_interacao
                         FROM fornecimentos r JOIN fornecedores f ON f.id=r.fornecedor_id
                         WHERE r.material_id=? ORDER BY r.data_interacao DESC""", (int(m.id),))
            st.markdown("**Fornecedores relacionados**")
            st.dataframe(rel, use_container_width=True, hide_index=True) if not rel.empty else st.caption("Sem fornecedores relacionados.")

elif page == "Cadastrar material":
    st.header("Cadastrar material")
    with st.form("material"):
        a,b = st.columns(2)
        descricao = a.text_input("Descrição *")
        codigo = b.text_input("Código interno")
        categoria = a.selectbox("Categoria", ["", "Tubos", "Conexões", "Válvulas", "Atuadores", "Medidores", "Bombas", "Materiais elétricos", "Instrumentação", "Outros"])
        sub = b.text_input("Subcategoria")
        fab = a.text_input("Fabricante")
        modelo = b.text_input("Modelo")
        codfab = a.text_input("Código do fabricante")
        dn = b.text_input("DN")
        pn = a.text_input("PN")
        mat = b.selectbox("Material de fabricação", ["", "Ferro fundido dúctil", "Aço carbono", "Aço inoxidável", "PVC", "PEAD", "Bronze", "Outro"])
        conex = b.selectbox("Tipo de conexão", ["", "Flangeada", "Ponta e bolsa", "Roscada", "Soldável", "Wafer", "Lug", "Outro"])
        ac = b.selectbox("Acionamento", ["", "Manual", "Elétrico", "Pneumático", "Hidráulico", "Sem acionamento"])
        aplic = a.selectbox("Aplicação", ["", "Água potável", "Esgoto", "Drenagem", "Industrial", "Outra"])
        palavras = st.text_input("Palavras-chave (separadas por vírgula)")
        desc = st.text_area("Descrição técnica / observações")
        status = st.selectbox("Status", ["Em revisão", "Validado", "Inativo"])
        forcar_similar = st.checkbox("Confirmar cadastro mesmo existindo material com descrição igual")
        ok = st.form_submit_button("Salvar material")
    if ok:
        if not descricao.strip():
            st.error("Descrição é obrigatória.")
        else:
            existentes = read("SELECT id, codigo, descricao, fabricante, modelo, dn, pn, status FROM materiais")
            desc_n = norm(descricao)
            fab_n = norm(fab)
            mod_n = norm(modelo)
            dn_n = norm(dn)

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
                except sqlite3.IntegrityError:
                    st.error("Código interno já cadastrado. Use outro código ou deixe em branco.")

elif page == "Fornecedores":
    st.header("Cadastro de fornecedores")
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
    st.subheader("Fornecedores registrados")
    st.dataframe(read("SELECT id,razao_social,nome_fantasia,cnpj,contato,email,telefone FROM fornecedores ORDER BY razao_social"), use_container_width=True, hide_index=True)

elif page == "Relacionar fornecedor":
    st.header("Relacionar fornecedor e material")
    ms = read("SELECT id,descricao,dn FROM materiais ORDER BY descricao")
    fs = read("SELECT id,razao_social FROM fornecedores ORDER BY razao_social")
    if ms.empty or fs.empty:
        st.info("Cadastre ao menos um material e um fornecedor primeiro.")
    else:
        with st.form("rel"):
            mid = st.selectbox("Material", ms.id.tolist(), format_func=lambda i: ms.loc[ms.id==i,"descricao"].iloc[0])
            fid = st.selectbox("Fornecedor", fs.id.tolist(), format_func=lambda i: fs.loc[fs.id==i,"razao_social"].iloc[0])
            tipo = st.selectbox("Tipo de relação", ["Forneceu", "Cotou", "Forneceu similar"])
            fabricante = st.text_input("Fabricante ofertado")
            modelo = st.text_input("Modelo ofertado")
            data = st.date_input("Data da interação")
            obs = st.text_area("Observações")
            ok = st.form_submit_button("Salvar relação")
        if ok:
            write("INSERT INTO fornecimentos(material_id,fornecedor_id,tipo_relacao,fabricante_ofertado,modelo_ofertado,data_interacao,observacoes) VALUES(?,?,?,?,?,?,?)",(mid,fid,tipo,fabricante,modelo,str(data),obs))
            st.success("Relação cadastrada.")

elif page == "Cotações":
    st.header("Cadastro de cotações")
    with st.form("cot"):
        processo = st.text_input("Número do processo")
        data = st.date_input("Data")
        objeto = st.text_input("Objeto")
        status = st.selectbox("Status", ["Em andamento", "Concluída", "Cancelada"])
        obs = st.text_area("Observações")
        ok = st.form_submit_button("Criar cotação")
    if ok:
        write("INSERT INTO cotacoes(processo,data_cotacao,objeto,status,observacoes) VALUES(?,?,?,?,?)",(processo,str(data),objeto,status,obs))
        st.success("Cotação criada.")
    st.dataframe(read("SELECT * FROM cotacoes ORDER BY data_cotacao DESC"), use_container_width=True, hide_index=True)

else:
    st.header("Exportar dados")
    st.write("Exporte cópias CSV das tabelas. Para backup integral, copie o arquivo central.db com o aplicativo fechado.")
    for table in ["materiais","fornecedores","fornecimentos","cotacoes"]:
        data = read(f"SELECT * FROM {table}")
        st.download_button(f"Baixar {table}.csv", data.to_csv(index=False).encode("utf-8-sig"), f"{table}.csv", "text/csv")