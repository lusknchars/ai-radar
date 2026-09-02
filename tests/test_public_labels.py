from radar.models import FAMILIAS, GANHO_EIXOS, PRATICAS
from radar.public_labels import (
    FAMILY_LABELS, GAIN_AXIS_LABELS, PRACTICE_LABELS, public_label,
)


def test_public_labels_cover_every_stored_taxonomy_value():
    assert set(FAMILY_LABELS) == FAMILIAS
    assert set(PRACTICE_LABELS) == PRATICAS
    assert set(GAIN_AXIS_LABELS) == GANHO_EIXOS


def test_unknown_storage_key_is_made_readable_without_leaking_underscores():
    assert public_label({}, "future_internal_key") == "future internal key"
