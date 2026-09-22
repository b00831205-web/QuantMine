"""Configuration-driven IC variant and test orchestration."""

import inspect
from collections.abc import Iterable

from ..ic_calculator import (
    VARIANT_PROCESSORS,
    prepare_raw_variant,
)
from ..plugins.context import SourceContext
from ..plugins.ic_engines import (
    ICCalculationComponent,
    resolve_ic_calculation_component,
)
from ..plugins.ic_validators import (
    ICValidationComponent,
    ICValidationRequest,
    create_python_ic_validation_engine,
    resolve_ic_validation_component,
    validate_ic_component,
)
from ..research_config import ResearchRunConfig


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
    *,
    ic_component: ICCalculationComponent | None = None,
    context: SourceContext | None = None,
    validation_component : ICValidationComponent | None = None
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
        component = ic_component,
        context = context,
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
        params = dict(processor_spec.get("params", {}))
        processor_parameters = inspect.signature(processor).parameters

        if "component" in processor_parameters:
            params["component"] = ic_component

        if "context" in processor_parameters:
            params["context"] = context

        variants[processor_id] = processor(variants[input_name], **params)

    resolved_validation_component = (
        validation_component if validation_component is not None else create_python_ic_validation_engine()
    )
    validation_result = validate_ic_component(
        resolved_validation_component,
        ICValidationRequest(
            variants = variants,
            tests = tuple(research_config.get("tests" ,[]))
        ),
        context,
    )

    return variants, dict(validation_result.test_results)

def run_persisted_ic_workflow(
        *,
        config: ResearchRunConfig,
        close,
        factors,
        context: SourceContext,
        membership = None,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine",),
        ic_component: ICCalculationComponent | None = None,
        validation_component: ICValidationComponent | None = None
):
    """Run IC using the engine stored in a research-run snapshot."""

    if not isinstance(config, ResearchRunConfig):
        raise TypeError("config must be a ResearchRunConfig")

    if not isinstance(context, SourceContext):
        raise TypeError("context must be a SourceContext")

    if not config.ic_research:
        raise ValueError("persisted research config does not contain ic_research")


    resolved_ic_component = (
        ic_component if ic_component is not None else resolve_ic_calculation_component(config.ic_engine, allowed_module_prefixes= allowed_module_prefixes)
    )

    resolved_validation_component = (
        validation_component if validation_component is not None else resolve_ic_validation_component(
            config.validation_engine,
            allowed_module_prefixes= allowed_module_prefixes
        )
    )

    return run_ic_workflow(
        close= close,
        factors= factors,
        research_config=dict(config.ic_research),
        membership= membership,
        ic_component= resolved_ic_component,
        validation_component= resolved_validation_component,
        context =context
    )
