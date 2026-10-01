from app.stages import CATALOGUE, SCORED_STAGES, Stage, stage_info
from app.textnorm import contains_term, normalize


def test_normalize_lowercases_strips_accents_and_punctuation() -> None:
    assert normalize("  Pulmonary-Embolism. ") == "pulmonary embolism"
    assert normalize("Sjögren’s  syndrome") == "sjogren s syndrome"
    assert normalize("P.E.") == "p e"
    assert normalize("") == ""


def test_contains_term_matches_whole_words_only() -> None:
    assert contains_term("Suspected PE on CT", "PE")
    assert not contains_term("She presents with dyspnea", "PE")
    assert contains_term("history of pulmonary embolism.", "Pulmonary embolism")
    assert not contains_term("anything", "")


def test_catalogue_is_the_nine_eximion_stages_in_order() -> None:
    assert [s.number for s in CATALOGUE] == list(range(1, 10))
    assert [s.key for s in CATALOGUE] == list(Stage)
    assert SCORED_STAGES == {Stage.DIAGNOSIS, Stage.TREATMENT}
    assert stage_info(Stage.WORKUP).hint == "tests you ordered"
    assert stage_info(Stage.HISTORY).kind == "given"
