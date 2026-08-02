"""Tests for the YAML config layer (migrated from a standalone verification script).

Coverage:
1. fields present in the YAML correctly override defaults
2. keys/fields absent from the YAML fall back to the dataclass defaults
3. __post_init__ validation rejects illegal values
4. an int passed as periods is normalized to a list (annotation accepts int|list)
5. unknown top-level key behavior (current semantics: silently ignored --
   a known limitation, misspelled keys do not raise)
"""
from pathlib import Path

import pytest

from quantmine.config import CONFIG_REGISTRY, ForwardReturnConfig, OrthogonalizeConfig
from quantmine.load_config import load_configs


@pytest.fixture
def yaml_file(tmp_path):
    def _write(content: str):
        p = tmp_path / "config.yaml"
        p.write_text(content, encoding="utf-8")
        return str(p)
    return _write


def test_yaml_values_override_defaults(yaml_file):
    path = yaml_file("""
orthogonalize:
  threshold: 0.05
backtest:
  part: 10
""")
    configs = load_configs(path)
    assert configs["orthogonalize"].threshold == 0.05
    assert configs["backtest"].part == 10


def test_missing_fields_fall_back_to_defaults(yaml_file):
    path = yaml_file("orthogonalize:\n  threshold: 0.05\n")
    configs = load_configs(path)
    assert configs["orthogonalize"].min_period == 60   # field-level default
    assert configs["momentum"].day == 5                # whole key absent -> all defaults


def test_empty_yaml_returns_all_defaults(yaml_file):
    configs = load_configs(yaml_file(""))
    assert set(configs.keys()) == set(CONFIG_REGISTRY.keys())
    assert configs["newey_west"].lag_multiplier == 2


def test_validation_rejects_illegal_values():
    with pytest.raises(ValueError):
        OrthogonalizeConfig(threshold=1.5)      # outside (0, 1)
    with pytest.raises(ValueError):
        ForwardReturnConfig(periods=[0])        # periods must be >= 1


def test_validation_triggered_through_yaml(yaml_file):
    path = yaml_file("transaction_cost:\n  cost_per_trade: 2.0\n")
    with pytest.raises(ValueError):
        load_configs(path)


def test_int_periods_normalized_to_list():
    cfg = ForwardReturnConfig(periods=20)
    assert cfg.periods == [20]


def test_unknown_top_level_key_silently_ignored(yaml_file):
    """Current semantics: a misspelled top-level key (e.g. an extra underscore)
    does not raise; the corresponding config silently uses defaults. Known
    limitation -- update this test if it is ever changed to raise."""
    path = yaml_file("newey_west_typo:\n  lag_multiplier: 99\n")
    configs = load_configs(path)
    assert configs["newey_west"].lag_multiplier == 2


def test_unknown_field_raises_type_error(yaml_file):
    """An unknown field under a known key raises (dataclasses reject extra
    kwargs), so misspelled field names are caught."""
    path = yaml_file("orthogonalize:\n  threshhold: 0.05\n")
    with pytest.raises(TypeError):
        load_configs(path)


def test_example_config_is_accepted():
    example_path = Path(__file__).parents[1] / "config.example.yaml"

    configs = load_configs(example_path)

    assert len(configs["backtest"].jobs) == 2
