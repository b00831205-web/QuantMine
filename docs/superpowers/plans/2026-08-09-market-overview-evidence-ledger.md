# Market Overview Evidence Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Market Overview content area as an Evidence Ledger while preserving every current API call, query shape, state transition, chart behavior, route, and translation key.

**Architecture:** Keep all business state and effects inside `MarketOverviewPage`. Replace only its rendered hierarchy with one page-local evidence panel composed of a header, analysis toolbar, chart region, and metric ledger. Keep responsive and visual behavior isolated in the page CSS module, and add a focused page test that protects interactions and accessible selection semantics.

**Tech Stack:** React 18, TypeScript 5.6, CSS Modules, Vitest, Testing Library, ECharts 5.

## Global Constraints

- Modify only the Market Overview content surface; do not redesign SideNav, TopBar, AppShell, routes, API clients, or backend code.
- Preserve `fetchLatestMarketDate`, `fetchSeries`, `fetchMarketOverview`, and `fetchWorkflows` behavior and signatures exactly.
- Preserve `SeriesChart` normalization, zoom, restore callback, height, and public props.
- Reuse all current `market.*` translation keys; do not replace factual copy or invent market claims.
- Use existing tokens from `frontend/src/styles/tokens.css`; do not add a new global token.
- Use no gradients, glass effects, blur, glow, large decorative shadows, or red/green P&L treatment.
- Preserve the user's uncommitted API and workflow-status additions already present in `MarketOverviewPage.tsx`.

---

## File Map

- Create `frontend/src/pages/MarketOverviewPage.test.tsx`: behavioral and accessibility regression coverage for the redesigned surface.
- Modify `frontend/src/pages/MarketOverviewPage.tsx`: semantic Evidence Ledger hierarchy only; retain all data and event logic.
- Modify `frontend/src/pages/MarketOverviewPage.module.css`: full page-local desktop, tablet, mobile, hover, and focus styling.
- Do not modify `frontend/src/components/chart/SeriesChart.tsx` unless visual inspection proves a concrete readability defect; its contract and behavior remain unchanged.

### Task 1: Protect the Existing Interaction Contract

**Files:**
- Create: `frontend/src/pages/MarketOverviewPage.test.tsx`

**Interfaces:**
- Consumes: `MarketOverviewPage`, mocked `fetchLatestMarketDate`, `fetchSeries`, `fetchMarketOverview`, `fetchWorkflows`, and mocked `SeriesChart`.
- Produces: regression coverage for selected range semantics, ticker mutation, API query preservation, and chart reset behavior.

- [ ] **Step 1: Write the failing page tests**

Create hoisted mocks for the two API modules and replace `SeriesChart` with a test control that invokes `onReset`:

```tsx
const marketMocks = vi.hoisted(() => ({
  fetchLatestMarketDate: vi.fn(),
  fetchSeries: vi.fn(),
  fetchMarketOverview: vi.fn(),
}));

const clientMocks = vi.hoisted(() => ({ fetchWorkflows: vi.fn() }));

vi.mock('@/api/client/market', () => marketMocks);
vi.mock('@/api/client', () => clientMocks);
vi.mock('@/components/chart/SeriesChart', () => ({
  SeriesChart: ({ onReset }: { onReset?: () => void }) => (
    <button type="button" onClick={onReset}>reset chart</button>
  ),
}));
```

Add tests that assert:

```tsx
expect(await screen.findByRole('button', { name: '1Y' })).toHaveAttribute('aria-pressed', 'true');
fireEvent.click(screen.getByRole('button', { name: '1M' }));
expect(screen.getByRole('button', { name: '1M' })).toHaveAttribute('aria-pressed', 'true');

fireEvent.change(screen.getByRole('textbox'), { target: { value: ' nvda ' } });
fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
expect(await screen.findByText('NVDA')).toBeInTheDocument();

fireEvent.click(screen.getByRole('button', { name: 'reset chart' }));
expect(screen.getByText('SPY')).toBeInTheDocument();
expect(screen.getByText('AAPL')).toBeInTheDocument();
expect(screen.getByText('MSFT')).toBeInTheDocument();
```

Also verify the series request still receives normalized symbols and the expected one-month date interval after changing range:

```tsx
await waitFor(() => {
  expect(marketMocks.fetchSeries).toHaveBeenCalledWith(
    expect.objectContaining({
      symbols: ['SPY', 'AAPL', 'MSFT'],
      endDate: '2026-08-08',
      normalize: true,
    }),
    expect.any(AbortSignal),
  );
});
```

- [ ] **Step 2: Run the focused test and confirm it fails for the new semantics**

Run: `npm test -- src/pages/MarketOverviewPage.test.tsx`

Expected: FAIL because current range buttons do not expose `aria-pressed` and the Evidence Ledger landmarks are not present.

- [ ] **Step 3: Commit the red test**

```bash
git add frontend/src/pages/MarketOverviewPage.test.tsx
git commit -m "test: protect market overview interactions"
```

### Task 2: Build the Evidence Ledger Semantic Structure

**Files:**
- Modify: `frontend/src/pages/MarketOverviewPage.tsx`
- Test: `frontend/src/pages/MarketOverviewPage.test.tsx`

**Interfaces:**
- Consumes: all existing `MarketOverviewPage` state, effects, derived values, handlers, `PageHeader`, `AsyncBoundary`, and `SeriesChart`.
- Produces: semantic elements styled by `page`, `evidencePanel`, `panelHeader`, `toolbar`, `tickerRow`, `rangeGroup`, `chartWrap`, `metricLedger`, `metricPrimary`, and `metricSecondary` CSS classes.

- [ ] **Step 1: Replace only the returned page hierarchy**

Remove the `Card` import and render the confirmed structure:

```tsx
<div className={styles.page}>
  <PageHeader title={t('market.title')} subtitle={t('market.subtitle')} />

  <section className={styles.evidencePanel} aria-labelledby="market-comparison-title">
    <header className={styles.panelHeader}>
      <div>
        <div className={styles.eyebrow}>MARKET EVIDENCE</div>
        <h2 id="market-comparison-title">{t('market.compareCard')}</h2>
      </div>
      <div className={styles.asOf}>
        <span>{t('market.kpi.latestDate')}</span>
        <strong>{latestTradeDate ?? '-'}</strong>
      </div>
    </header>

    <div className={styles.toolbar}>
      <div className={styles.tickerRow}>{/* existing chips and add control */}</div>
      <div className={styles.rangeGroup} aria-label="Time range">
        {ranges.map((rangeKey) => (
          <button
            type="button"
            aria-pressed={range === rangeKey}
            className={range === rangeKey ? styles.rangeActive : styles.range}
            onClick={() => setRange(rangeKey)}
          >
            {rangeKey}
          </button>
        ))}
      </div>
    </div>

    <div className={styles.chartWrap}>{/* unchanged AsyncBoundary and SeriesChart */}</div>
    <section className={styles.metricLedger} aria-label="Market summary">
      {/* existing five values, first metric primary and remaining metrics secondary */}
    </section>
  </section>
</div>
```

Keep the ticker input handler, remove handler, range setter, `AsyncBoundary` props, query hint, and `SeriesChart` reset callback byte-for-byte equivalent in behavior. Set `type="button"` on non-submit buttons. Keep the remove button translation-backed `aria-label`.

- [ ] **Step 2: Replace `Kpi` with a presentation-only `Metric` component**

Use a `prominent` boolean rather than the old muted tone:

```tsx
const Metric = ({ label, value, prominent = false, valueColor }: MetricProps) => (
  <div className={prominent ? styles.metricPrimary : styles.metricSecondary}>
    <div className={styles.metricLabel}>{label}</div>
    <div className={styles.metricValue} style={valueColor ? { color: valueColor } : undefined}>
      {value}
    </div>
  </div>
);
```

Render latest date with `prominent`; render daily return, advancers, breadth, and task status as secondary metrics. Continue passing `taskStatus?.color` only to task status.

- [ ] **Step 3: Run the focused test**

Run: `npm test -- src/pages/MarketOverviewPage.test.tsx`

Expected: PASS.

- [ ] **Step 4: Run TypeScript validation**

Run: `npm run typecheck`

Expected: exit code 0 with no TypeScript errors.

- [ ] **Step 5: Commit the semantic redesign**

```bash
git add frontend/src/pages/MarketOverviewPage.tsx frontend/src/pages/MarketOverviewPage.test.tsx
git commit -m "refactor: structure market overview as evidence ledger"
```

### Task 3: Apply the Responsive Visual System

**Files:**
- Modify: `frontend/src/pages/MarketOverviewPage.module.css`
- Test: `frontend/src/pages/MarketOverviewPage.test.tsx`

**Interfaces:**
- Consumes: class names produced by Task 2 and tokens from `frontend/src/styles/tokens.css`.
- Produces: the completed desktop, tablet, mobile, hover, active, and keyboard-focus presentation.

- [ ] **Step 1: Implement the desktop hierarchy**

Define a compact page rhythm, one bordered evidence panel, a balanced panel header, a two-zone toolbar, a dominant chart area, and an integrated metric ledger. Use these material rules:

```css
.evidencePanel {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--sp-4);
  padding: var(--sp-3) var(--sp-5);
  background: var(--bg-surface-2);
  border-block: 1px solid var(--border-subtle);
}

.metricLedger {
  display: grid;
  grid-template-columns: minmax(210px, 1.35fr) repeat(4, minmax(120px, 1fr));
  border-top: 1px solid var(--border-subtle);
}
```

Use `var(--font-mono)` and `font-variant-numeric: tabular-nums` for date and metric values. Give the primary metric a clear 28px scale and secondary metrics an 18px scale. Use low-contrast dividers between metrics rather than separate cards.

- [ ] **Step 2: Implement interaction states**

Add visible hover and `:focus-visible` states for range, ticker removal, add button, and input. The active range must combine cobalt color with a non-color indicator such as an inset bottom line. Do not turn the entire control group cobalt.

- [ ] **Step 3: Implement tablet and mobile layouts**

At `max-width: 900px`, wrap the toolbar and change the ledger to a 2-column grid with the primary metric spanning both columns. At `max-width: 640px`, reduce panel padding, allow the ticker input group to fill available width, keep the range group visible without horizontal overflow, and use a single-column ledger where necessary.

- [ ] **Step 4: Run the complete automated checks**

Run from `frontend`:

```bash
npm test
npm run typecheck
npm run lint
npm run build
```

Expected: every command exits 0. If a pre-existing unrelated lint failure appears, record its exact file and message; do not change unrelated code.

- [ ] **Step 5: Run the Impeccable detector once**

Run from the repository root:

```bash
node .agents/skills/impeccable/scripts/detect.mjs --json frontend/src/pages/MarketOverviewPage.tsx frontend/src/pages/MarketOverviewPage.module.css
```

Expected: no mechanical violations on the changed targets. Fix only findings inside the two target files.

- [ ] **Step 6: Commit the responsive styling**

```bash
git add frontend/src/pages/MarketOverviewPage.module.css
git commit -m "style: finish market overview evidence ledger"
```

### Task 4: Visual QA and Final Verification

**Files:**
- Modify only if defects are found: `frontend/src/pages/MarketOverviewPage.tsx`
- Modify only if defects are found: `frontend/src/pages/MarketOverviewPage.module.css`

**Interfaces:**
- Consumes: built Market Overview route and design spec `docs/superpowers/specs/2026-08-09-market-overview-redesign-design.md`.
- Produces: verified desktop and mobile renders with no overflow, clipping, hierarchy, or focus defects.

- [ ] **Step 1: Start the frontend and capture one bounded screenshot batch**

Capture the Market Overview route at a representative desktop viewport near 1440×900 and a mobile viewport near 390×844. Inspect both together for first-viewport hierarchy, ticker wrapping, chart size, ledger order, text clipping, horizontal overflow, and keyboard focus visibility.

- [ ] **Step 2: Apply one consolidated defect-fix batch**

Change only the page TSX or CSS module. Do not modify API logic, chart props, shell components, tokens, or other pages.

- [ ] **Step 3: Capture at most one confirmation batch**

Confirm the same two viewports. Stop visual polishing after this confirmation pass.

- [ ] **Step 4: Re-run completion checks with fresh output**

Run from `frontend`:

```bash
npm test -- src/pages/MarketOverviewPage.test.tsx
npm run typecheck
npm run build
```

Expected: all commands exit 0 after the final visual fixes.

- [ ] **Step 5: Review the final diff for interface preservation**

Run:

```bash
git diff -- frontend/src/pages/MarketOverviewPage.tsx frontend/src/pages/MarketOverviewPage.module.css frontend/src/pages/MarketOverviewPage.test.tsx
```

Confirm that the diff changes rendered markup, accessibility attributes, page-local styles, and tests only. Verify the existing four request effects, query memo, ticker handlers, daily-return calculation, and chart reset values remain behaviorally identical.

- [ ] **Step 6: Commit final QA fixes if any**

```bash
git add frontend/src/pages/MarketOverviewPage.tsx frontend/src/pages/MarketOverviewPage.module.css frontend/src/pages/MarketOverviewPage.test.tsx
git commit -m "fix: resolve market overview visual qa findings"
```
