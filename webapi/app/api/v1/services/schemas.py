"""Response/request models for the service-autostart endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ServiceState(BaseModel):
    """One managed systemd user unit."""

    name: str = Field(description="unit 名，用于回传给 PUT 接口")
    label: str = Field(description="给人看的名字")
    description: str = Field(description="关掉它的后果，用于开关旁的说明")
    isSelf: bool = Field(
        description="是否就是当前提供本接口的服务；前端应对它额外确认一次"
    )
    installed: bool = Field(
        description="unit 是否已安装。未安装时开关应禁用，而不是渲染成关闭状态"
    )
    autostart: bool | None = Field(
        default=None, description="开机自启是否开启；未安装时为 null"
    )
    active: bool = Field(description="当前是否在运行（只读，本接口不提供起停）")
    state: str = Field(description="systemctl is-enabled 的原始输出，便于排查")


class AutostartRequest(BaseModel):
    enabled: bool = Field(description="true=开机自启，false=关闭")
