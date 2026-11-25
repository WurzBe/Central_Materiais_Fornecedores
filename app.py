                )
                apagar_forns_puxados = st.checkbox(
                    f"Apagar também os fornecedores puxados por este orçamento ({len(forns_excl)} fornecedor(es) que não estão em nenhum outro orçamento ou vínculo)",
                    value=True,
                    key=f"opt_del_forns_{cid_edit}"
                )
                confirmar_del_cot = st.checkbox(
                    "Confirmo a exclusão permanente deste orçamento, seus preços e os arquivos anexados a ele",
                    key=f"del_cot_{cid_edit}"
                )

                if st.button("🗑️ Excluir orçamento selecionado", type="primary", key=f"btn_del_cot_{cid_edit}"):
                    if not confirmar_del_cot:
                        st.error("Marque a caixa de confirmação antes de excluir.")
                    else:
                        remover_anexos_entidade("cotacao", int(cid_edit))
                        write("DELETE FROM cotacao_itens WHERE cotacao_id=?", (int(cid_edit),))
                        write("DELETE FROM cotacoes WHERE id=?", (int(cid_edit),))

                        qtd_mats_rem = 0
                        if apagar_mats_puxados and mats_excl:
                            for mid_rem in mats_excl:
                                remover_anexos_entidade("material", int(mid_rem))
                                write("DELETE FROM materiais WHERE id=?", (int(mid_rem),))
                                qtd_mats_rem += 1

                        qtd_forns_rem = 0
                        if apagar_forns_puxados and forns_excl:
                            for fid_rem in forns_excl:
                                remover_anexos_entidade("fornecedor", int(fid_rem))
                                write("DELETE FROM fornecedores WHERE id=?", (int(fid_rem),))
                                qtd_forns_rem += 1

                        detalhes_rem = ["orçamento, preços e anexos removidos"]
                        if qtd_mats_rem > 0:
                            detalhes_rem.append(f"{qtd_mats_rem} material(is) exclusivo(s) apagado(s)")
                        if qtd_forns_rem > 0:
                            detalhes_rem.append(f"{qtd_forns_rem} fornecedor(es) exclusivo(s) apagado(s)")

                        st.session_state["msg_del_cot"] = "Exclusão concluída: " + ", ".join(detalhes_rem) + "."
                        st.rerun()


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
                if ax["entidade_tipo"] == "material":
                    vinculo_txt = f"Material: {ax.get('mat_nome') or ax['entidade_id']}"
                elif ax["entidade_tipo"] == "cotacao":
                    vinculo_txt = f"Orçamento/Cotação: {ax.get('cot_proc') or ax['entidade_id']}"
                else:
                    vinculo_txt = f"Fornecedor: {ax.get('forn_ent_nome') or ax['entidade_id']}"

                with st.container(border=True):
                    c1, c2, c3 = st.columns([4, 1, 1])
                    c1.write(f"**{ax['tipo_documento']}** — **{ax['nome_original']}** ({ax.get('data_upload') or ''})\n\n📌 _{vinculo_txt}_")
                    dados_ax = storage_download(ax["arquivo_salvo"])
                    if dados_ax is not None:
                        c2.download_button("Baixar", data=dados_ax, file_name=ax["nome_original"], key=f"dl_ax_{ax['id']}")
                    if c3.button("Excluir", key=f"del_ax_{ax['id']}"):
                        storage_delete(ax["arquivo_salvo"])
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
                ent_id = st.selectbox("Selecione o registro *", options=opcoes_ids, format_func=lambda i: mapa_labels.get(i, str(i)))
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
        if USAR_POSTGRES:
            st.info("**Banco na nuvem ativo:** os dados estão salvos no PostgreSQL e os anexos no Storage.")