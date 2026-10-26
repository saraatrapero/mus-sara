from pathlib import Path

from musst.engine import RulesConfig

ROOT = Path(__file__).resolve().parents[2]


def test_el_fichero_de_reglas_coincide_con_los_valores_por_defecto():
    assert RulesConfig.from_toml(ROOT / "config" / "rules.default.toml") == RulesConfig()
