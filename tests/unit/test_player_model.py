"""PlayerModel: estimaciones con incertidumbre, back-off, aprendizaje y cambio de estrategia."""

from musst import play_game
from musst.bots.builtin import SimpleBot
from musst.learning.player_model import PRIORS, PlayerModel, score_context
from musst.learning.synthetic import SyntheticPlayer
from musst.learning.updater import Learner


def test_sin_datos_devuelve_el_prior_con_confianza_cero():
    est = PlayerModel("x").estimate("bluff_frequency", "grande", "behind")
    assert est.value == PRIORS["bluff_frequency"]
    assert est.confidence == 0.0 and est.label == "Baja"


def test_back_off_contexto_con_poca_muestra_se_acerca_al_padre():
    m = PlayerModel("x")
    for _ in range(50):
        m.record("aggression", False, "chica", "even")
    m.record("aggression", True, "grande", "behind")
    specific = m.estimate("aggression", "grande", "behind")
    assert specific.value < 0.5  # una sola observación no domina
    assert specific.confidence < 0.3


def test_confianza_crece_con_la_muestra():
    m = PlayerModel("x")
    confs = []
    for _ in range(3):
        for _ in range(10):
            m.record("acceptance_rate", True)
        confs.append(m.estimate("acceptance_rate").confidence)
    assert confs == sorted(confs) and confs[-1] > 0.7


def test_contexto_del_marcador():
    assert score_context(10, 33, 40) == "close"
    assert score_context(5, 20, 40) == "behind"
    assert score_context(20, 5, 40) == "ahead"
    assert score_context(10, 12, 40) == "even"


def test_serializacion():
    m = PlayerModel("x")
    m.record("ordago_rate", True, "pares", "close")
    assert PlayerModel.from_dict(m.to_dict()).estimate(
        "ordago_rate", "pares", "close"
    ) == m.estimate("ordago_rate", "pares", "close")


def _observe(player_factory, games=12, seed=0):
    learner = Learner()
    for i in range(games):
        bots = [SimpleBot(i), player_factory(i), SimpleBot(i + 100), player_factory(i + 100)]
        match = play_game(bots, seed=seed + i)
        history = [e.to_dict() for e in match.events if e.visible_to(None)]
        learner.learn_game(history, {1: "rival", 3: "rival"})
    return learner


def test_detecta_progresivamente_a_un_jugador_farolero():
    farolero = _observe(lambda s: SyntheticPlayer(bluff=0.8, seed=s))
    honesto = _observe(lambda s: SyntheticPlayer(bluff=0.0, seed=s))
    f = farolero.long_model("rival").estimate("bluff_frequency")
    h = honesto.long_model("rival").estimate("bluff_frequency")
    assert f.value > h.value + 0.2
    assert f.confidence > 0.5


def test_perfil_conservador_en_riesgo():
    arriesgado = _observe(lambda s: SyntheticPlayer(risk_tolerance=0.9, seed=s))
    prudente = _observe(lambda s: SyntheticPlayer(risk_tolerance=0.1, seed=s))
    a = arriesgado.long_model("rival").estimate("risk_tolerance").value
    p = prudente.long_model("rival").estimate("risk_tolerance").value
    assert a > p


def test_detecta_cambio_de_estrategia():
    learner = Learner()
    shifted = False
    for i in range(14):
        bluff = 0.0 if i < 8 else 0.95
        bots = [
            SimpleBot(i),
            SyntheticPlayer(bluff=bluff, seed=i),
            SimpleBot(i + 9),
            SyntheticPlayer(bluff=bluff, seed=i + 9),
        ]
        match = play_game(bots, seed=500 + i)
        history = [e.to_dict() for e in match.events if e.visible_to(None)]
        updates = learner.learn_game(history, {1: "rival", 3: "rival"})
        if i >= 8 and any(u.drift for u in updates):
            shifted = True
    assert shifted


def test_estilo_y_piedras_segun_la_mano():
    farolero = _observe(lambda s: SyntheticPlayer(bluff=0.8, seed=s)).long_model("rival")
    tapado = _observe(
        lambda s: SyntheticPlayer(bluff=0.0, value_threshold=0.95, seed=s)
    ).long_model("rival")
    assert farolero.style()["label"] == "farolero"
    assert tapado.style()["label"] in ("de tapado", "cauto", "conservador")
    assert farolero.estimate("bet_with_weak").value > tapado.estimate("bet_with_weak").value + 0.2
    stake, n = farolero.mean_stake("floja")
    assert stake is not None and n > 0
    again = PlayerModel.from_dict(farolero.to_dict())
    assert again.style() == farolero.style() and again.stakes == farolero.stakes


def test_sin_datos_no_hay_etiqueta():
    assert PlayerModel("nuevo").style()["label"] == "sin datos aún"
