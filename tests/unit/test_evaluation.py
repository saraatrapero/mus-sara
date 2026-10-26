"""Evaluación de manos por lance."""

from musst.engine import evaluation as ev
from musst.engine.cards import parse_hand


def test_grande_el_tres_cuenta_como_rey():
    assert ev.grande_key(parse_hand("3O 12C 1E 4B")) == (12, 12, 4, 1)
    assert ev.grande_key(parse_hand("12O 12C 7E 4B")) > ev.grande_key(parse_hand("12E 11C 11E 11B"))


def test_chica_el_dos_cuenta_como_as():
    assert ev.chica_key(parse_hand("2O 1C 4E 5B")) > ev.chica_key(parse_hand("1O 4C 4E 5B"))


def test_pares_tipos():
    assert ev.pairs(parse_hand("12O 3C 1E 4B")).kind is ev.PairsKind.PAR
    assert ev.pairs(parse_hand("12O 3C 12E 4B")).kind is ev.PairsKind.MEDIAS
    assert ev.pairs(parse_hand("12O 3C 1E 2B")).kind is ev.PairsKind.DUPLES
    assert ev.pairs(parse_hand("5O 5C 5E 5B")).kind is ev.PairsKind.DUPLES
    assert not ev.pairs(parse_hand("12O 11C 10E 7B")).has_pairs


def test_pares_orden():
    duples = ev.pairs(parse_hand("12O 12C 1E 1B")).key
    medias = ev.pairs(parse_hand("12O 12C 12E 1B")).key
    par = ev.pairs(parse_hand("12O 12C 7E 1B")).key
    assert duples > medias > par
    assert ev.pairs(parse_hand("12O 12C 1E 1B")).key > ev.pairs(parse_hand("11O 11C 10E 10B")).key
    assert ev.pairs(parse_hand("7O 7C 1E 4B")).key > ev.pairs(parse_hand("6O 6C 12E 4B")).key


def test_juego_orden_31_32_40_y_resto():
    hands = {
        31: parse_hand("12O 11C 10E 1B"),
        32: parse_hand("12O 11C 5E 7B"),
        40: parse_hand("12O 11C 10E 12B"),
        37: parse_hand("12O 11C 10E 7B"),
        33: parse_hand("12O 11C 6E 7C"),
    }
    for total, hand in hands.items():
        assert ev.total_points(hand) == total
    j = {total: ev.juego_key(hand) for total, hand in hands.items()}
    assert j[31] > j[32] > j[40] > j[37] > j[33]


def test_sin_juego_y_punto():
    hand = parse_hand("7O 7C 6E 5B")
    assert not ev.has_juego(hand)
    assert ev.juego_key(hand) == (-1,)
    assert ev.punto_key(hand) == (25,)


def test_empate_gana_el_mas_cercano_al_mano():
    keys = {0: (5,), 1: (5,), 2: (5,), 3: (5,)}
    assert ev.best_seat(keys, [2, 3, 0, 1]) == 2
    assert ev.best_seat({1: (5,), 3: (6,)}, [0, 1, 2, 3]) == 3
