"""Service routes: read and toggle boot autostart.

Read and write both go through ``systemctl --user``; see ``systemd.py`` for why
user units rather than system units, and why only autostart is exposed.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Path

from .schemas import AutostartRequest, ServiceState
from .systemd import SystemdUnavailable, find_unit, list_states, set_autostart

router = APIRouter()


def _unavailable(exc: SystemdUnavailable) -> HTTPException:
    # 503, not 500: the request is fine, the environment is not. Callers can
    # tell "your button did nothing because services are not installed here"
    # apart from "the backend is broken".
    return HTTPException(status_code=503, detail=str(exc))


@router.get(
    "/services",
    response_model=list[ServiceState],
    summary="服务列表与开机自启状态",
)
def get_services() -> list[ServiceState]:
    """Return every managed unit with its autostart and running state."""
    try:
        return [ServiceState(**state) for state in list_states()]
    except SystemdUnavailable as exc:
        raise _unavailable(exc) from exc


@router.put(
    "/services/{name}/autostart",
    response_model=ServiceState,
    summary="开关开机自启",
)
def put_autostart(
    name: str = Path(description="unit 名，必须来自 GET /services 的返回"),
    payload: AutostartRequest = Body(...),
) -> ServiceState:
    """Turn one unit's boot autostart on or off.

    Raises:
        HTTPException: 404 when the name is not one this API manages, 503 when
            systemd cannot be reached or the unit is not installed.

    Notes:
        The name is resolved against a fixed allowlist and the *stored* name is
        what reaches systemctl. Forwarding the caller's string would hand over
        control of every unit the account owns.

        Nothing starts or stops here -- only the next boot changes -- so this is
        safe to call even for the unit serving the request.
    """
    unit = find_unit(name)
    if unit is None:
        raise HTTPException(status_code=404, detail=f"未知服务：{name}")
    try:
        return ServiceState(**set_autostart(unit, payload.enabled))
    except SystemdUnavailable as exc:
        raise _unavailable(exc) from exc
