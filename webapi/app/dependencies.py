from sqlalchemy.engine import Engine
from quantmine.storage.database import get_engine

def get_request_engine() -> Engine:
    return get_engine()