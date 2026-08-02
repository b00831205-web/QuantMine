"""Round-trip contracts for IC artifact storage and loading."""

import json

import pandas as pd
import pandas.testing as pdt

from quantmine.storage import ic as ic_storage


class _FakeColumn:
    def __eq__(self, other):
        return self


class _FakeColumns:
    def __getattr__(self, name):
        return _FakeColumn()


class _FakeTable:
    c = _FakeColumns()


class _FakeStatement:
    def where(self, *args):
        return self

    def order_by(self, *args):
        return self


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeConnection:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, *args, **kwargs):
        return _FakeResult(self._rows)


class _FakeEngine:
    def __init__(self, rows):
        self._rows = rows

    def connect(self):
        return _FakeConnection(self._rows)


def _patch_artifact_query(monkeypatch, rows):
    monkeypatch.setattr(ic_storage, "Table", lambda *args, **kwargs: _FakeTable())
    monkeypatch.setattr(ic_storage, "select", lambda *args: _FakeStatement())
    return _FakeEngine(rows)


def test_save_scope_value_keeps_integer_mapping_keys(tmp_path):
    frame = pd.DataFrame({"A": [0.01, 0.02]})

    entry = ic_storage._save_scope_value(
        {5: frame},
        tmp_path,
        "forward_returns",
    )

    assert entry == {
        "kind": "dataframe_dict",
        "items": [
            {
                "key": 5,
                "path": "forward_returns/5.parquet",
            }
        ],
    }
    pdt.assert_frame_equal(
        pd.read_parquet(tmp_path / "forward_returns" / "5.parquet"),
        frame,
    )


def test_load_ic_variants_restores_full_train_and_test_scope(monkeypatch, tmp_path):
    dates = pd.date_range("2026-01-01", periods=2, freq="B")
    factor = pd.DataFrame({"A": [1.0, 2.0]}, index=dates)
    returns = pd.DataFrame({"A": [0.01, 0.02]}, index=dates)
    cs_ic = pd.DataFrame({("momentum", 5): [0.1, 0.2]}, index=dates)

    artifact_rows = []
    for scope in ("train", "test"):
        scope_dir = tmp_path / "raw" / scope
        (scope_dir / "factors").mkdir(parents=True)
        (scope_dir / "forward_returns").mkdir()
        factor.to_parquet(scope_dir / "factors" / "momentum.parquet")
        returns.to_parquet(scope_dir / "forward_returns" / "5.parquet")
        cs_ic.to_parquet(scope_dir / "cs_ic.parquet")

        manifest_path = scope_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "transforms": [{"name": "raw"}],
                    "entries": {
                        "factors": {
                            "kind": "dataframe_dict",
                            "items": [
                                {
                                    "key": "momentum",
                                    "path": "factors/momentum.parquet",
                                }
                            ],
                        },
                        "forward_returns": {
                            "kind": "dataframe_dict",
                            "items": [
                                {"key": 5, "path": "forward_returns/5.parquet"}
                            ],
                        },
                        "cs_ic": {
                            "kind": "dataframe",
                            "path": "cs_ic.parquet",
                        },
                        "orthogonalized": {"kind": "value", "value": False},
                    },
                }
            ),
            encoding="utf-8",
        )
        artifact_rows.append(
            {
                "variant_name": "raw",
                "sample_scope": scope,
                "transforms": [{"name": "raw"}],
                "path": str(manifest_path),
            }
        )

    engine = _patch_artifact_query(monkeypatch, artifact_rows)

    variants = ic_storage.load_ic_variants(engine, run_id=7)

    assert set(variants) == {"raw"}
    assert variants["raw"].test["orthogonalized"] is False
    assert set(variants["raw"].test["forward_returns"]) == {5}
    pdt.assert_frame_equal(
        variants["raw"].train["factors"]["momentum"],
        factor,
        check_freq=False,
    )
    pdt.assert_frame_equal(
        variants["raw"].test["forward_returns"][5],
        returns,
        check_freq=False,
    )
    pdt.assert_frame_equal(
        variants["raw"].test["cs_ic"],
        cs_ic,
        check_freq=False,
    )


def test_load_test_results_preserves_custom_summary_columns(monkeypatch, tmp_path):
    index = pd.MultiIndex.from_tuples(
        [("momentum", 5)],
        names=["factor", "period"],
    )
    summary = pd.DataFrame(
        {
            "IC_mean": [0.03],
            "bootstrap_ci_low": [0.01],
        },
        index=index,
    )
    multiple_testing = pd.DataFrame(
        {"BH_significant": [True]},
        index=index,
    )
    summary_path = tmp_path / "summary.parquet"
    multiple_path = tmp_path / "multiple_testing.parquet"
    summary.to_parquet(summary_path)
    multiple_testing.to_parquet(multiple_path)

    engine = _patch_artifact_query(
        monkeypatch,
        [
            {
                "test_id": "newey_raw",
                "variant_name": "raw",
                "sample_scope": "train",
                "artifact_type": "summary",
                "path": str(summary_path),
                "metadata": {"test_method": "newey_test"},
            },
            {
                "test_id": "newey_raw",
                "variant_name": "raw",
                "sample_scope": "train",
                "artifact_type": "multiple_testing",
                "path": str(multiple_path),
                "metadata": {"test_method": "newey_test"},
            },
        ],
    )

    test_results = ic_storage.load_test_results(engine, run_id=7)

    assert test_results["newey_raw"]["variant_name"] == "raw"
    assert test_results["newey_raw"]["test_method"] == "newey_test"
    assert "bootstrap_ci_low" in test_results["newey_raw"]["summary"]
    pdt.assert_frame_equal(test_results["newey_raw"]["summary"], summary)
    pdt.assert_frame_equal(
        test_results["newey_raw"]["multiple_testing"],
        multiple_testing,
    )
