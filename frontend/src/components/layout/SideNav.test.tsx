import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import i18n from '@/i18n';

const clientMocks = vi.hoisted(() => ({
  fetchServices: vi.fn(),
  setServiceAutostart: vi.fn(),
}));

vi.mock('@/api/client', () => clientMocks);

import { SideNav } from './SideNav';

const webService = {
  name: 'quantmine-api',
  label: 'Web 服务',
  description: '提供 API 与前端页面。',
  isSelf: true,
  installed: true,
  autostart: true,
  active: true,
  state: 'enabled',
};

const scheduler = {
  ...webService,
  name: 'quantmine-airflow-scheduler',
  label: '调度器',
  isSelf: false,
};

/** 渲染并等待 fetchServices 落地。
 *
 * 必须 flush 一次微任务：断言「开关不存在」的用例本身不会 await 任何东西，
 * 于是 fetch 解析后的 setState 落在测试之外，React 会警告 not wrapped in act(...)。
 */
const renderNav = async () => {
  const view = render(
    <MemoryRouter>
      <SideNav />
    </MemoryRouter>,
  );
  await act(async () => {});
  return view;
};

/** 点击并等待处理函数的异步续体落地。
 *
 * 光用 fireEvent 只覆盖到同步的 setBusy；await 之后的 setServices/setError 会
 * 落在 act 之外，React 报 not wrapped in act(...)。
 */
const clickToggle = async (el: HTMLElement) => {
  await act(async () => {
    fireEvent.click(el);
  });
};

beforeEach(async () => {
  vi.clearAllMocks();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  await i18n.changeLanguage('zh');
});

describe('SideNav 开机自启开关', () => {
  it('读取服务状态后渲染出开关', async () => {
    clientMocks.fetchServices.mockResolvedValue([webService]);
    await renderNav();

    const toggle = await screen.findByRole('switch');
    expect(toggle).toHaveAttribute('aria-checked', 'true');
  });

  it('点击后调用接口并采用返回的状态，而不是本地取反', async () => {
    // 后端才是权威：systemctl 可能拒绝，UI 必须显示实际结果
    clientMocks.fetchServices.mockResolvedValue([webService]);
    clientMocks.setServiceAutostart.mockResolvedValue({ ...webService, autostart: false });
    await renderNav();

    await clickToggle(await screen.findByRole('switch'));

    expect(clientMocks.setServiceAutostart).toHaveBeenCalledWith('quantmine-api', false);
    await waitFor(() =>
      expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false'),
    );
  });

  it('关掉“当前服务自身”前要二次确认', async () => {
    clientMocks.fetchServices.mockResolvedValue([webService]);
    clientMocks.setServiceAutostart.mockResolvedValue({ ...webService, autostart: false });
    await renderNav();

    await clickToggle(await screen.findByRole('switch'));

    expect(window.confirm).toHaveBeenCalled();
  });

  it('确认框点取消则不发请求', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    clientMocks.fetchServices.mockResolvedValue([webService]);
    await renderNav();

    await clickToggle(await screen.findByRole('switch'));

    expect(clientMocks.setServiceAutostart).not.toHaveBeenCalled();
  });

  it('开启方向不需要确认', async () => {
    clientMocks.fetchServices.mockResolvedValue([{ ...webService, autostart: false }]);
    clientMocks.setServiceAutostart.mockResolvedValue(webService);
    await renderNav();

    await clickToggle(await screen.findByRole('switch'));

    expect(window.confirm).not.toHaveBeenCalled();
    expect(clientMocks.setServiceAutostart).toHaveBeenCalledWith('quantmine-api', true);
  });

  it('未安装时不渲染开关，避免点了没反应', async () => {
    clientMocks.fetchServices.mockResolvedValue([
      { ...webService, installed: false, autostart: null },
    ]);
    await renderNav();

    await waitFor(() => expect(screen.queryByRole('switch')).not.toBeInTheDocument());
  });

  it('接口不可用时整块隐藏，不显示一个假的关闭态', async () => {
    // 503（systemd 不可达 / 非 Linux 环境）不应看起来像“自启已关闭”
    clientMocks.fetchServices.mockRejectedValue(new Error('503'));
    await renderNav();

    await waitFor(() => expect(screen.queryByRole('switch')).not.toBeInTheDocument());
  });

  it('切换失败时开关必须弹回原状态', async () => {
    clientMocks.fetchServices.mockResolvedValue([webService]);
    clientMocks.setServiceAutostart.mockRejectedValue(new Error('503 systemd 不可达'));
    await renderNav();

    await clickToggle(await screen.findByRole('switch'));

    // 请求失败了，真实状态没变，开关不能停在“已关闭”上误导人
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'));
  });

  it('切换失败时必须给出可见提示，而不是悄无声息', async () => {
    // 静默失败下用户只看到“点了没反应”，分不清是点歪了还是后端拒绝了
    clientMocks.fetchServices.mockResolvedValue([webService]);
    clientMocks.setServiceAutostart.mockRejectedValue({
      code: 'SERVICE_UNAVAILABLE',
      title: '服务不可用',
      detail: 'quantmine-api 尚未安装；先运行 deploy/install-services.sh',
      status: 503,
    });
    await renderNav();

    await clickToggle(await screen.findByRole('switch'));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });

  it('四个服务都要渲染出各自的开关', async () => {
    // 只露 Web 服务的话，唯一能点的正好是最危险的那个；调度器才是
    // “每日数据管道要不要自动跑”这个真正有用的开关
    clientMocks.fetchServices.mockResolvedValue([webService, scheduler]);
    await renderNav();

    await waitFor(() => expect(screen.getAllByRole('switch')).toHaveLength(2));
  });

  it('英文模式下翻译服务名称与说明，不显示后端的中文硬编码', async () => {
    await i18n.changeLanguage('en');
    clientMocks.fetchServices.mockResolvedValue([webService]);
    clientMocks.setServiceAutostart.mockResolvedValue({ ...webService, autostart: false });
    await renderNav();

    const label = await screen.findByText('Web service');
    expect(label).toHaveAttribute(
      'title',
      'Serves the API and frontend. If autostart is disabled, you must start it manually after the next boot to open this page.',
    );
    expect(screen.queryByText('Web 服务')).not.toBeInTheDocument();
    const toggle = await screen.findByRole('switch');
    expect(toggle).toHaveAccessibleName('Autostart — Web service');

    await clickToggle(toggle);
    expect(window.confirm).toHaveBeenCalledWith(
      'Disabling boot autostart for "Web service" means you must start it manually after the next boot. Disable anyway?',
    );
  });

  it('isSelf 排在最后，不做列表里最顺手点到的那个', async () => {
    clientMocks.fetchServices.mockResolvedValue([webService, scheduler]);
    await renderNav();

    const labels = (await screen.findAllByRole('switch')).map((el) =>
      el.getAttribute('aria-label'),
    );
    expect(labels[labels.length - 1]).toContain(webService.label);
  });

  it('切换只更新被点的那一个，其余保持原状', async () => {
    clientMocks.fetchServices.mockResolvedValue([webService, scheduler]);
    clientMocks.setServiceAutostart.mockResolvedValue({ ...scheduler, autostart: false });
    await renderNav();

    // 排序后调度器在前
    const [schedulerSwitch] = await screen.findAllByRole('switch');
    expect(schedulerSwitch).toBeDefined();
    await clickToggle(schedulerSwitch as HTMLElement);

    await waitFor(() => {
      const switches = screen.getAllByRole('switch');
      expect(switches[0]).toHaveAttribute('aria-checked', 'false');
      expect(switches[1]).toHaveAttribute('aria-checked', 'true');
    });
  });
});
