def make_registry():

    registry = {}
    def register(name: str):
        def decorator(func):
            registry[name] = func
            return func
        return decorator
    
    return registry, register

def validate_in_registry(value: str, registry: dict, field_name: str = 'value'):
    if value not in registry:
        raise ValueError(f"invalid {field_name}: '{value}' ")

