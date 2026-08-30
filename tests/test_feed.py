import xml.etree.ElementTree as ET

import pytest

from radar.feed import ItemFeed, render_rss


def item(**kw):
    base = dict(arxiv_id="2608.11111", titulo="Kernel INT4 fundido",
                resumo="Troca o kernel FP16; custa qualidade em batch alto.",
                familia="quantizacao", pratica="adotar",
                independent_impls=3, stars_total=4, entregue_em="2026-08-30")
    return ItemFeed(**{**base, **kw})


def test_o_rss_e_xml_valido():
    raiz = ET.fromstring(render_rss([item()], dia="2026-08-30"))
    assert raiz.tag == "rss"
    assert raiz.get("version") == "2.0"


def test_um_item_por_paper():
    xml = render_rss([item(arxiv_id="a"), item(arxiv_id="b")], dia="2026-08-30")
    assert len(ET.fromstring(xml).findall(".//item")) == 2


def test_o_guid_e_o_arxiv_id_e_e_permanente():
    """O leitor de RSS deduplica por guid. Um guid que muda faria o mesmo
    paper reaparecer como novo a cada execução."""
    it = ET.fromstring(render_rss([item()], dia="2026-08-30")).find(".//item")
    assert it.find("guid").text == "arxiv:2608.11111"
    assert it.find("guid").get("isPermaLink") == "false"


def test_o_link_aponta_para_o_arxiv():
    it = ET.fromstring(render_rss([item()], dia="2026-08-30")).find(".//item")
    assert it.find("link").text == "https://arxiv.org/abs/2608.11111"


def test_a_data_e_rfc_822():
    """RSS exige RFC 822. ISO passa despercebido em alguns leitores e some
    em outros -- e some sem erro, que é o pior modo de falhar."""
    it = ET.fromstring(render_rss([item()], dia="2026-08-30")).find(".//item")
    assert it.find("pubDate").text == "Sun, 30 Aug 2026 00:00:00 +0000"


def test_a_descricao_traz_os_numeros_que_justificam_a_entrada():
    it = ET.fromstring(render_rss([item()], dia="2026-08-30")).find(".//item")
    d = it.find("description").text
    assert "3" in d and "quantizacao" in d and "adotar" in d


def test_texto_com_caractere_de_marcacao_nao_quebra_o_xml():
    xml = render_rss([item(titulo="A & B <hack>")], dia="2026-08-30")
    it = ET.fromstring(xml).find(".//item")       # não levanta ParseError
    assert "A & B <hack>" in it.find("title").text


def test_feed_vazio_ainda_e_xml_valido():
    """Um feed sem itens é estado legítimo: dia sem nada acima do piso."""
    raiz = ET.fromstring(render_rss([], dia="2026-08-30"))
    assert raiz.findall(".//item") == []
    assert raiz.find("channel/title") is not None


def test_o_canal_declara_o_que_o_radar_e():
    ch = ET.fromstring(render_rss([], dia="2026-08-30")).find("channel")
    assert "implementações independentes" in ch.find("description").text
