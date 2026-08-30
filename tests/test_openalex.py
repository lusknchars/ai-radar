import pytest

from radar.openalex import MAX_POR_LOTE, OpenAlexClient, build_url

RESPOSTA = {"results": [
    {"doi": "https://doi.org/10.48550/arxiv.2608.27428", "cited_by_count": 7},
]}


def test_a_url_pede_so_os_dois_campos_que_importam():
    url = build_url(["2608.27428"])
    assert "select=doi%2Ccited_by_count" in url or "select=doi,cited_by_count" in url
    assert "10.48550%2FarXiv.2608.27428" in url or "10.48550/arXiv.2608.27428" in url


def test_a_url_junta_varios_ids_num_filtro_or():
    url = build_url(["2608.27428", "2608.27351"])
    assert "%7C" in url or "|" in url


def test_lote_acima_do_teto_e_recusado():
    with pytest.raises(ValueError, match="50"):
        build_url([f"26{i:02d}.00001" for i in range(MAX_POR_LOTE + 1)])


def test_o_doi_volta_em_caixa_baixa_e_ainda_casa():
    # A API responde `arxiv.` mesmo tendo sido consultada com `arXiv.`.
    # Sem casamento case-insensitive TODA linha se perde em silencio, e o
    # sintoma seria citacoes sempre nulas -- indistinguivel do bug em conserto.
    c = OpenAlexClient(fetch=lambda url: RESPOSTA)
    assert c.citations_for(["2608.27428"]) == {"2608.27428": 7}


def test_doi_em_caixa_MISTA_tambem_casa():
    """O caso que `.lower()` existe para cobrir.

    A fixture do teste acima ja vem em caixa baixa, entao ela NAO distingue
    `doi.lower()` de `doi` -- verificado por mutacao em 2026-08-29: trocar um
    pelo outro deixava aquele teste verde. Este aqui usa a caixa como a
    consulta a escreve, e e o unico que quebra se o casamento virar sensivel.
    """
    resposta = {"results": [
        {"doi": "https://doi.org/10.48550/arXiv.2608.27428", "cited_by_count": 7},
    ]}
    c = OpenAlexClient(fetch=lambda url: resposta)
    assert c.citations_for(["2608.27428"]) == {"2608.27428": 7}


def test_paper_ausente_vira_none_e_nunca_zero():
    # "Attention Is All You Need" (1706.03762) nao resolve: o arXiv so passou
    # a cunhar DOI automatico por volta de 2022. Medido em 2026-08-29: taxa de
    # resolucao ~92%. Gravar 0 para os 8% recria o bug que este modulo conserta.
    c = OpenAlexClient(fetch=lambda url: RESPOSTA)
    r = c.citations_for(["2608.27428", "1706.03762"])
    assert r["1706.03762"] is None
    assert r["1706.03762"] != 0


def test_zero_de_verdade_e_preservado_como_zero():
    resposta = {"results": [
        {"doi": "https://doi.org/10.48550/arxiv.2608.27428", "cited_by_count": 0},
    ]}
    c = OpenAlexClient(fetch=lambda url: resposta)
    assert c.citations_for(["2608.27428"]) == {"2608.27428": 0}


def test_falha_da_api_degrada_para_none_em_todos():
    def explode(url):
        raise RuntimeError("openalex fora do ar")
    c = OpenAlexClient(fetch=explode)
    assert c.citations_for(["2608.27428", "2608.27351"]) == {
        "2608.27428": None, "2608.27351": None}


def test_lista_vazia_nao_faz_requisicao():
    def nao_deveria(url):
        raise AssertionError("nao pode chamar a rede com lista vazia")
    assert OpenAlexClient(fetch=nao_deveria).citations_for([]) == {}


def test_lote_maior_que_o_teto_e_fatiado_em_varias_requisicoes():
    # O cliente aceita mais que 50 e fatia; e `build_url` que recusa, porque
    # o teto e da API. O acervo de 1088 papers precisa disso.
    chamadas = []
    def contar(url):
        chamadas.append(url)
        return {"results": []}
    ids = [f"26{i:03d}.00001" for i in range(120)]
    r = OpenAlexClient(fetch=contar).citations_for(ids)
    assert len(chamadas) == 3          # 50 + 50 + 20
    assert len(r) == 120
    assert all(v is None for v in r.values())
