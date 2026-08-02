from .config import CONFIG_REGISTRY
import yaml

def load_configs(yaml_path: str) -> dict:
    """Load a YAML file into a ``{config_name: config_instance}`` dict.

    Top-level keys missing from the YAML fall back to the config class
    defaults. Unknown fields under a known key raise ``TypeError``; unknown
    top-level keys are silently ignored (known limitation).
    """
    with open(yaml_path, 'r') as f:
        raw = yaml.safe_load(f) or {}  # safe_load returns None for an empty file, so fall back to {}

    result = {}
    for config_name, config_class in CONFIG_REGISTRY.items():
        kwargs = raw.get(config_name, {})  # key absent from YAML -> empty dict -> all defaults
        result[config_name] = config_class(**kwargs)
    return result
