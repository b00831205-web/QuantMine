import { http } from '@/api/http';

/** 系统服务状态（systemd user unit） */
export interface ServiceState {
  /** unit 名，用于回传给 PUT 接口 */
  name: string;
  /** 给人看的名字 */
  label: string;
  /** 关掉它的后果，用于开关旁的说明 */
  description: string;
  /** 是否就是当前提供本接口的服务；前端应对它额外确认一次 */
  isSelf: boolean;
  /** unit 是否已安装。未安装时开关应禁用，而不是渲染成关闭状态 */
  installed: boolean;
  /** 开机自启是否开启；未安装时为 null */
  autostart: boolean | null;
  /** 当前是否在运行（只读） */
  active: boolean;
  /** systemctl is-enabled 的原始输出，便于排查 */
  state: string;
}

/** GET /api/v1/services —— 服务列表与开机自启状态 */
export function fetchServices(signal?: AbortSignal): Promise<ServiceState[]> {
  return http<ServiceState[]>('/api/v1/services', { signal });
}

/** PUT /api/v1/services/{name}/autostart —— 开关开机自启 */
export function setServiceAutostart(
  name: string,
  enabled: boolean,
  signal?: AbortSignal,
): Promise<ServiceState> {
  return http<ServiceState>(`/api/v1/services/${name}/autostart`, {
    method: 'PUT',
    body: { enabled },
    signal,
  });
}
