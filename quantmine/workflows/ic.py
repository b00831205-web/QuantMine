"""Configuration-driven IC variant and test orchestration."""

from ..ic_calculator import (
    TEST_METHOD,
    VARIANT_PROCESSORS,
    prepare_raw_variant,
    run_test,
)


def _require_registered(name: str, registry: dict, kind: str):
    try:
        return registry[name]
    except KeyError as error:
        raise ValueError(f"Unknown {kind} '{name}'") from error


def run_ic_workflow(
    close,
    factors,
    research_config: dict,
    membership=None,
):
    """Build configured variants and run configured tests.

    Args:
        membership: Point-in-time spell table, used to keep a name out of the
            cross-section on days it was not in the index. None disables the
            filter and lets every ticker in ``close`` count on every date.
    """
    periods = research_config["periods"]
    raw_variant = prepare_raw_variant(
        close=close,
        factors=factors,
        train_end=research_config["train_end"],
        test_start=research_config["test_start"],
        periods=periods,
        membership=membership,
    )

    variants = {"raw": raw_variant}
    for processor_spec in research_config.get("processors", []):
        processor_id = processor_spec["id"]
        if processor_id in variants:
            raise ValueError(f"Duplicate variant id '{processor_id}'")

        input_name = processor_spec["input"]
        if input_name not in variants:
            raise ValueError(
                f"Variant '{processor_id}' depends on unavailable "
                f"input '{input_name}'"
            )

        processor = _require_registered(
            processor_spec["name"],
            VARIANT_PROCESSORS,
            "variant processor",
        )
        params = processor_spec.get("params", {})
        variants[processor_id] = processor(variants[input_name], **params)

    test_results: dict[str, dict] = {}
    for test_spec in research_config.get("tests", []):
        test_id = test_spec["id"]
        if test_id in test_results:
            raise ValueError(f"Duplicate test id '{test_id}'")

        variant_name = test_spec["input"]
        if variant_name not in variants:
            raise ValueError(
                f"Test '{test_id}' uses unavailable variant '{variant_name}'"
            )
        test_method = test_spec["name"]
        _require_registered(test_method, TEST_METHOD, "test method")

        test_output, corrected_output = run_test(
            variant=variants[variant_name],
            test_method=test_method,
            TEST_METHOD=TEST_METHOD,
            test_params=test_spec.get("params", {}),
        )
        summary_payload, _ = test_output
        summary_df, _ = summary_payload
        multiple_testing_df, _ = corrected_output
        test_results[test_id] = {
            "variant_name": variant_name,
            "test_method": test_method,
            "sample_scope": "train",
            "summary": summary_df,
            "multiple_testing": multiple_testing_df,
        }

    return variants, test_results
