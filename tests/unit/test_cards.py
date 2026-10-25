"""Baraja y naipes (FEM II.3)."""

import random

import pytest

from musst.engine.cards import RANKS, Card, Suit, full_deck, normalized_rank, point_value, shuffled_deck


def test_baraja_espanola_de_40_naipes_unicos():
    deck = full_deck()
    assert len(deck) == 40
    assert len(set(deck)) == 40
    assert {c.rank for c in deck} == set(RANKS)
    assert 8 not in RANKS and 9 not in RANKS


def test_ocho_reyes_y_ocho_ases():
    deck = full_deck()
    assert sum(1 for c in deck if normalized_rank(c) == 12) == 8
    assert sum(1 for c in deck if normalized_rank(c) == 1) == 8


def test_modalidad_cuatro_reyes_configurable():
    assert normalized_rank(Card(3, Suit.OROS), eight_kings=False) == 3


@pytest.mark.parametrize(
    ("rank", "value"), [(1, 1), (2, 1), (3, 10), (4, 4), (7, 7), (10, 10), (11, 10), (12, 10)]
)
def test_valor_para_juego(rank, value):
    assert point_value(Card(rank, Suit.COPAS)) == value


def test_codigo_y_parseo():
    card = Card(12, Suit.OROS)
    assert card.code == "12O"
    assert Card.parse("12o") == card
    with pytest.raises(ValueError):
        Card.parse("8O")
    with pytest.raises(ValueError):
        Card.parse("X")


def test_barajado_reproducible():
    assert shuffled_deck(random.Random(5)) == shuffled_deck(random.Random(5))
    assert shuffled_deck(random.Random(5)) != shuffled_deck(random.Random(6))
