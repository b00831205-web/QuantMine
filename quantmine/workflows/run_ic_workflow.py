"""Config-driven IC research orchestration.

Builds the raw factor/forward-return variant, applies the configured variant
processors (e.g. orthogonalization) to derive further variants, then runs the
configured statistical tests over them.
"""
from quantmine.ic_calculator import VARIANT_PROCESSORS, TEST_METHOD, prepare_raw_variant, run_test

def run_ic_workflow(close, factors, research_config: dict, artifact_dir: str):
    """Run the IC workflow for one research config.

    Args:
        close: Wide date-by-ticker close prices.
        factors: Factor frames by name.
        research_config: The research section: ``train_end``, ``test_start``,
            ``periods``, plus ``processors`` and ``tests`` definitions. Each
            processor names the variant it consumes, so variants can chain.
        artifact_dir: Directory for intermediate parquet artifacts.

    Returns:
        A tuple of ``(variants, test_results)``, both keyed by their config id.

    Notes:
        The train/test split happens here, which is what lets factor selection
        read train-scope results while backtests trade test-scope data.
    """
    raw_variant = prepare_raw_variant(
        close = close,
        factors= factors,
        train_end = research_config['train_end'],
        test_start = research_config['test_start'],
        periods = research_config['periods'],
        output_path=f'{artifact_dir}/raw_cs_ic.parquet'
    )

    variants = {'raw': raw_variant}
    for processor_spec in research_config['processors']:
        input_variant = variants[processor_spec['input']]
        processor = VARIANT_PROCESSORS[processor_spec['name']]

        variants[processor_spec['id']] = processor(
            input_variant,
            output_path=(
                f'{artifact_dir}/'
                f'{processor_spec['id']}_cs_ic_parquet'
            ),
            **processor_spec.get('params',{}),
        )
    test_results = {}

    for test_spec in research_config['tests']:
        variant = variants[test_spec['input']]

        test_results[test_spec['id']] = run_test(
            variant = variant,
            test_method = test_spec['name'],
            TEST_METHOD=TEST_METHOD,
            test_params=test_spec.get('param',{})
        )
    return variants, test_results