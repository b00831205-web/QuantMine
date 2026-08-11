import { afterEach, describe, expect, it } from 'vitest';
import i18n from '@/i18n';
import type { Catalog, CatalogField } from '@/types/data';
import { getCatalogFieldDescription, getCatalogResourceLabel } from './dataCatalogI18n';

const catalog: Catalog = {
  resource: 'market_latest',
  label: '行情最新快照',
  description: 'S&P 500 成分股最新交易快照',
  fields: [],
};

const field: CatalogField = {
  name: 'ticker',
  type: 'string',
  description: '股票代码',
  filterable: true,
};

afterEach(async () => {
  await i18n.changeLanguage('zh');
});

describe('Data Catalog i18n', () => {
  it('uses stable backend identifiers to render English resource and field copy', async () => {
    await i18n.changeLanguage('en');

    expect(getCatalogResourceLabel(i18n.t, catalog)).toBe('Latest market snapshot');
    expect(getCatalogFieldDescription(i18n.t, catalog.resource, field)).toBe('Ticker symbol');
  });

  it('supports resource-specific field wording', async () => {
    await i18n.changeLanguage('en');

    expect(
      getCatalogFieldDescription(i18n.t, 'backtest_results', {
        ...field,
        name: 'trade_date',
        type: 'date',
        description: '调仓日',
      }),
    ).toBe('Rebalance date');
  });

  it('falls back to backend metadata for an unknown future field', async () => {
    await i18n.changeLanguage('en');
    const futureField = { ...field, name: 'future_metric', description: 'Future metric' };

    expect(getCatalogFieldDescription(i18n.t, catalog.resource, futureField)).toBe('Future metric');
  });
});
