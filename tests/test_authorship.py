from radar.authorship import classify_repos, normalize
from radar.models import Repo


def repo(full_name, stars, created_at):
    return Repo(full_name=full_name, owner=full_name.split("/")[0],
                stars=stars, created_at=created_at)


def test_normalize_strips_accents_case_and_punctuation():
    assert normalize("Frantar") == "frantar"
    assert normalize("Elías-Gonçalves") == "eliasgoncalves"


def test_owner_matching_author_surname_is_flagged():
    repos = [repo("efrantar/gptq-fast", 30, "2024-01-01T00:00:00Z"),
             repo("someone/other", 20, "2024-02-01T00:00:00Z")]
    out = {c.repo.full_name: c for c in classify_repos(repos, ["Elias Frantar"], "")}
    assert out["efrantar/gptq-fast"].is_author is True
    assert out["efrantar/gptq-fast"].reason == "sobrenome"
    assert out["someone/other"].is_author is False


def test_short_surname_does_not_match_by_substring():
    """'Lin' casaria com linux-foundation, linkedin, linear-ai...

    O segundo repo existe para ISOLAR a regra sob teste: com um repo so,
    'mais antigo E mais estrelado' dispara sozinha e o teste passaria (ou
    falharia) sem nunca exercitar o casamento por sobrenome.
    """
    repos = [repo("linux-foundation/serving", 40, "2024-01-01T00:00:00Z"),
             repo("outro/mais-estrelado", 500, "2024-02-01T00:00:00Z")]
    out = {c.repo.full_name: c for c in classify_repos(repos, ["Ji Lin"], "")}
    assert out["linux-foundation/serving"].is_author is False


def test_short_surname_still_matches_exactly():
    repos = [repo("lin/impl", 40, "2024-01-01T00:00:00Z"),
             repo("outro/mais-estrelado", 500, "2024-02-01T00:00:00Z")]
    out = {c.repo.full_name: c for c in classify_repos(repos, ["Ji Lin"], "")}
    assert out["lin/impl"].is_author is True
    # Conferir a RAZAO, nao so o booleano: sem isso o teste passa pelo
    # motivo errado quando outra regra dispara.
    assert out["lin/impl"].reason == "sobrenome"


def test_repo_named_in_the_abstract_is_flagged():
    repos = [repo("acme/official-impl", 5, "2024-03-01T00:00:00Z")]
    abstract = "Code is available at https://github.com/acme/official-impl"
    out = classify_repos(repos, ["Someone Else"], abstract)
    assert out[0].is_author is True
    assert out[0].reason == "citado_no_abstract"


def test_oldest_and_most_starred_is_presumed_official():
    """Cobre o laboratorio que publica sob nome de organizacao, como
    IST-DASLab/gptq, que nenhum sobrenome alcanca."""
    repos = [repo("IST-DASLab/gptq", 2360, "2022-10-19T00:00:00Z"),
             repo("fpgaminer/GPTQ-triton", 322, "2023-03-28T00:00:00Z"),
             repo("davisyoshida/jax-gptq", 10, "2023-05-05T00:00:00Z")]
    out = {c.repo.full_name: c for c in classify_repos(repos, ["Elias Frantar"], "")}
    assert out["IST-DASLab/gptq"].is_author is True
    assert out["IST-DASLab/gptq"].reason == "mais_antigo_e_mais_estrelado"
    assert out["fpgaminer/GPTQ-triton"].is_author is False
    assert out["davisyoshida/jax-gptq"].is_author is False


def test_oldest_but_not_most_starred_is_not_presumed_official():
    repos = [repo("a/first", 5, "2022-01-01T00:00:00Z"),
             repo("b/popular", 900, "2023-01-01T00:00:00Z")]
    out = {c.repo.full_name: c for c in classify_repos(repos, [], "")}
    assert out["a/first"].is_author is False
    assert out["b/popular"].is_author is False


def test_single_repo_is_presumed_official():
    """Com um repo so, ele e simultaneamente o mais antigo e o mais estrelado.
    Conferir a RAZAO importa: e a regra 3, a que mais erra, e sem ela o teste
    nao distingue este caso de um acidente da regra 1 (sobrenome)."""
    out = classify_repos([repo("solo/only", 5, "2024-01-01T00:00:00Z")], [], "")
    assert out[0].is_author is True
    assert out[0].reason == "mais_antigo_e_mais_estrelado"


def test_every_classification_carries_an_auditable_reason():
    repos = [repo("efrantar/x", 10, "2024-01-01T00:00:00Z"),
             repo("outro/y", 5, "2024-02-01T00:00:00Z")]
    for c in classify_repos(repos, ["Elias Frantar"], ""):
        if c.is_author:
            assert c.reason, "toda flag de autoria precisa registrar qual regra disparou"
        else:
            assert c.reason is None


def test_empty_repo_list_returns_empty():
    assert classify_repos([], ["A B"], "") == []
