"""Autocrítica: el bot revisa sus decisiones con las cartas enseñadas y corrige sus estimaciones."""

from musst.agents.orchestrator import ProBot
from musst.bots.builtin import SimpleBot
from musst.learning.self_review import ReviewedDecision, SelfReview
from musst.learning.updater import Learner
from musst.runtime.runner import play_game


def history_with_hands(hands, round_no=1):
    return [
        {"kind": "HandsRevealed", "round": round_no, "payload": {"hands": hands}, "actor": None}
    ]


def test_marca_como_error_solo_lo_que_era_peor_con_las_cartas_reales():
    # Asiento 0 lleva reyes (gana grande); el 1, sotas.
    hist = history_with_hands(
        {
            "0": ["12O", "12C", "12E", "12B"],
            "1": ["10O", "10C", "4E", "5B"],
            "2": ["4O", "5O", "6O", "7O"],
            "3": ["4C", "5C", "6C", "7C"],
        }
    )
    review = SelfReview()
    summary = review.review(
        [
            ReviewedDecision(1, "grande", "accept", 0.9, 0, 0),  # acertó
            ReviewedDecision(1, "grande", "reject", 0.4, 0, 0),
        ],  # rechazó ganando: error
        hist,
        lost=True,
    )
    assert review.error_rate("grande", "accept") == (0.0, 1.0)
    assert review.error_rate("grande", "reject") == (1.0, 1.0)
    assert any("rechacé" in line for line in summary)


def test_la_calibracion_corrige_y_se_encoge_con_pocos_datos():
    review = SelfReview()
    assert review.correct("pares", 0.75) == 0.75
    review.calibration["pares|7"] = [5.0, 10.0]  # creía 70-80 %, ganó el 50 %
    corrected = review.correct("pares", 0.75)
    assert 0.5 < corrected < 0.75
    review.calibration["pares|7"] = [50.0, 100.0]
    assert abs(review.correct("pares", 0.75) - 0.5) < abs(corrected - 0.5)


def test_el_profesional_aprende_y_conserva_la_autocritica():
    learner = Learner()
    for seed in range(3):
        pro = ProBot(seed, learner=learner)
        play_game([pro, SimpleBot(1), ProBot(seed + 9, learner=learner), SimpleBot(2)], seed=seed)
        assert pro.self_review_summary and pro.self_review_summary[0].startswith("Autocrítica")
    memory = SelfReview.from_dict(learner.long_model("self:profesional").extra["self_review"])
    assert memory.games >= 3 and memory.calibration


def test_dos_profesionales_en_la_mesa_no_se_pisan_la_memoria():
    learner = Learner()
    a, b = ProBot(1, learner=learner), ProBot(2, learner=learner)
    play_game([a, SimpleBot(1), b, SimpleBot(2)], seed=3)
    memory = SelfReview.from_dict(learner.long_model("self:profesional").extra["self_review"])
    assert memory.games == 2
