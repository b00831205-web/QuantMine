---
name: QUANTMINE
description: A calm, statistically honest research dashboard for turning factor ideas into evidence.
colors:
  app-bg: "#0e1116"
  surface: "#161a22"
  surface-2: "#1d2230"
  elevated: "#232a3a"
  border-subtle: "#2a3142"
  border-strong: "#3a4258"
  text-primary: "#e6e8ee"
  text-secondary: "#9aa3b8"
  text-muted: "#6b7388"
  accent: "#4f8cff"
  accent-hover: "#6ea0ff"
  positive: "#4ec98a"
  negative: "#ef6464"
  warning: "#f0b35e"
  info: "#56b6ff"
typography:
  headline:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif"
    fontSize: "22px"
    fontWeight: 600
    lineHeight: 1.5
  title:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif"
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: "0.05em"
  section:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.35
  metric:
    fontFamily: "JetBrains Mono, SF Mono, Consolas, monospace"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1.15
    fontFeature: "tabular-nums"
  micro:
    fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif"
    fontSize: "10px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0.08em"
  data:
    fontFamily: "JetBrains Mono, SF Mono, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  sm: "4px"
  md: "6px"
  lg: "10px"
spacing:
  1: "4px"
  2: "8px"
  3: "12px"
  4: "16px"
  5: "24px"
  6: "32px"
  7: "48px"
components:
  button-secondary:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.sm}"
    padding: "4px 12px"
  nav-active:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.sm}"
    height: "32px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.md}"
    padding: "16px 24px"
---

# Design System: QUANTMINE

## Overview

**Creative North Star: "The Evidence Ledger"**

QUANTMINE treats every factor result as an entry that must be inspected, contextualized, and judged. The visual language is a matte, low-saturation research surface: quiet enough for long sessions, exact enough for dense tables and pipeline state, and restrained enough that the evidence—not the interface—carries the argument. The calm instrument-panel clarity is deliberate, but it never borrows the adrenaline of a live trading desk.

Daily operating surfaces use compact rhythm, clear hierarchy, and stable tonal layers. Reports and result views can become analytical and editorial through stronger headings, generous grouping, and visible statistical context. Uncertainty is part of the composition: p-values, significance flags, controls, and error ranges should sit next to the headline result rather than hide below it.

**Key Characteristics:**
- Matte navy-black surfaces with tonal layering instead of gradients or glass.
- Cobalt blue is a precise interaction accent, not a decorative wash.
- Inter handles interface prose; JetBrains Mono marks data, dates, and machine-readable values.
- Compact 4px rhythm with deliberate 8/16/24/32px grouping.
- Evidence and caveats remain visually present wherever performance is discussed.

## Colors

The palette is a deliberately narrow cool-neutral field. Surfaces are separated by tone, borders stay quiet, and semantic colors signal state without becoming a dashboard spectacle.

### Primary
- **Research Cobalt** (`#4f8cff`): Links, active navigation rails, focus borders, and primary interaction emphasis.
- **Cobalt Lift** (`#6ea0ff`): Hover state for links and accent controls.

### Secondary
- **Verified Mint** (`#4ec98a`): Positive workflow or result state when the supporting evidence is visible.
- **Signal Red** (`#ef6464`): Negative or failed state; never use as an alarm-like flourish.
- **Measured Amber** (`#f0b35e`): Warning, marginal significance, or attention state.
- **Research Blue** (`#56b6ff`): Informational state and secondary analytical annotation.

### Neutral
- **Obsidian Field** (`#0e1116`): Application canvas and the quietest reading background.
- **Ledger Surface** (`#161a22`): Navigation, top bar, and standard cards.
- **Raised Register** (`#1d2230`): Inputs, table headers, hover rows, and selected navigation.
- **Elevated Slate** (`#232a3a`): Higher-priority overlays or nested emphasis.
- **Subtle Rule** (`#2a3142`): Dividers and default borders.
- **Strong Rule** (`#3a4258`): Focused or hovered border emphasis.
- **Ink** (`#e6e8ee`): Primary text and values.
- **Secondary Ink** (`#9aa3b8`): Supporting labels and metadata.
- **Muted Ink** (`#6b7388`): Quiet hints, footer metadata, and disabled-adjacent copy.

**The Cobalt Rarity Rule.** Keep the accent concentrated on interaction and evidence markers. Do not flood an entire card, chart, or page with blue.

## Typography

**Display Font:** Inter (with system and Chinese UI fallbacks)
**Body Font:** Inter (with system and Chinese UI fallbacks)
**Label/Mono Font:** JetBrains Mono (with SF Mono and Consolas fallbacks)

**Character:** Inter is compact, neutral, and bilingual-friendly for long research sessions. JetBrains Mono gives dates, symbols, metrics, and machine states a visibly accountable register without turning the whole interface into code.

### Hierarchy
- **Headline** (600, 22px, 1.5): Page titles and the lead of an analytical result view.
- **Section** (600, 18px, 1.35): Editorial-style section titles and report subsections; borrow this level for Reports, not every dashboard card.
- **Title** (600, 15px, 1.5): Card titles and section anchors.
- **Body** (400, 13px, 1.5): Default interface copy and table content.
- **Data** (400, 12px, 1.5, mono): Dates, metrics, identifiers, and technical output.
- **Label** (500, 11px, 0.05em): Compact metadata, table headers, and state labels.
- **Metric** (700, 28px, 1.15, mono, `tabular-nums`): The primary number in a panel; enlarge and weight it so the eye knows what to judge first.
- **Micro label** (600, 10px, 1.4, 0.08em): Small uppercase field names and provenance tags.

**The Evidence-Adjacent Type Rule.** The more consequential the claim, the closer its supporting statistic should sit in the same typographic group; do not enlarge a return figure while shrinking its p-value into a footnote.

**The Intentional Scale Rule.** Every numeric value uses `font-variant-numeric: tabular-nums`; primary metrics are visibly larger and heavier, while field names stay small, uppercase, and quiet. Data UI earns its authority through hierarchy before decoration.

## Layout

The default workspace uses a fixed left navigation rail and a fluid content column. The rail uses the real product routes—Market, Rebalance, Workflows, Research, Data, Reports, and AI—rather than icon-only abstraction. It is 220px wide and collapses to 56px below 960px. A 48px top bar carries global data date, latest workflow status, model context, and user controls. Content scrolls inside the main column with 24px page padding. Cards and page sections use a 4px base rhythm, with 8px and 16px gaps for related controls and 24px/32px gaps for distinct evidence groups.

The default workbench follows the Evidence Ledger direction: one primary evidence area carries visual weight; secondary panels are quieter, with fewer borders and more whitespace. Separation should come from spacing and tonal change before additional containers. The Analytical Brief direction is reserved for Reports, where editorial section hierarchy and reading cadence can take over. The Research Cockpit direction is an optional pattern for workflow and methodology-heavy screens, not the default shell.

Tables are allowed to be dense, but not visually frantic: headers remain sticky, field labels use micro-label styling, all numeric columns are right-aligned with tabular figures, and a subtle baseline rhythm should keep rows aligned. IC and significance columns are the decision columns and receive the strongest typographic emphasis. Significance uses one restrained signal—a single neutral/cobalt status dot plus text—and never red/green P&L coloring.

## Elevation & Depth

Depth is conveyed through flat tonal layers and hairline borders. Shadows are reserved for small, functional separation and never simulate glossy floating glass. The application canvas is the deepest tone; cards, navigation, inputs, and overlays step upward through the existing surface scale.

### Shadow Vocabulary
- **Micro separation** (`0 1px 2px rgba(0, 0, 0, 0.3)`): Small controls and quiet containment.
- **Raised separation** (`0 4px 12px rgba(0, 0, 0, 0.4)`): A functional elevated panel or overlay.

**The Matte Surface Rule.** No gradients, glassmorphism, blur, or luminous shadows. Tonal change and a crisp border should explain hierarchy.

## Shapes

Forms are compact and gently squared: 4px for controls and badges, 6px for cards, and 10px only for larger grouped surfaces. Borders are 1px and low contrast by default. The one recurring exception is the fully rounded 999px workflow toggle, which reads as a control state rather than a container style.

## Components

### Buttons
- **Shape:** Compact, gently squared controls (4px radius) with 4–12px internal padding.
- **Secondary / pager:** Raised-register background, primary text, and a subtle border; disabled states lower opacity rather than changing geometry.
- **Ghost / logout:** Transparent background with a subtle border; hover strengthens the border and text.
- **Focus:** Use the existing cobalt border treatment and preserve a visible keyboard focus state.

### Cards / Containers
- **Hierarchy:** One primary panel or evidence region per viewport; supporting panels are quieter and should not all read as equal cards.
- **Corner Style:** 6px radius.
- **Background:** Ledger Surface, with a 1px Subtle Rule border reserved for the primary panel; secondary panels may use tonal change and whitespace alone.
- **Shadow Strategy:** Flat by default; use only the micro or raised separation shadows for functional overlays.
- **Internal Padding:** 16px vertical and 24px horizontal for the primary card; secondary panels may use more whitespace and fewer visible edges.
- **Header:** Title and optional extra metadata sit in one row with a 12px bottom gap.

### Inputs / Fields
- **Style:** Raised Register background, Subtle Rule border, 4px radius, and 4px/8px padding.
- **Focus:** Border shifts to Research Cobalt; keep the control otherwise matte.
- **Error / Disabled:** Use semantic state colors sparingly and preserve readable text contrast.

### Navigation
- **Style:** Ledger Surface rail with a right divider. QUANTMINE uses a 15px/700 wordmark with slight tracking.
- **Default:** Real text routes—Market, Rebalance, Workflows, Research, Data, Reports, AI—in Secondary Ink with compact 8px/16px padding.
- **Active:** Ink on Raised Register with a 2px cobalt left rail.
- **Responsive:** Collapse the rail to 56px below 960px while preserving the active rail and keyboard route access.

### Data Tables
- **Style:** 12px body, 10–11px uppercase micro labels with 0.05–0.08em tracking, sticky Raised Register headers, and 8px/12px cell padding.
- **Alignment:** Numeric columns are right-aligned and use mono `tabular-nums`; IC, p-value, significance, and confidence interval columns stay adjacent.
- **Decision columns:** IC and significance receive the strongest type emphasis; all other columns recede through neutral color and weight.
- **State:** Hover uses a tonal shift; selection uses a 2px inset cobalt rail. Significance is a single restrained dot plus neutral/cobalt text, never red/green P&L coloring.

### Methodology Drawer
- **Style:** A collapsible right rail that can remain discoverable without consuming the main workspace; use tonal separation and one strong divider rather than a stack of cards.
- **Content:** Newey–West settings, multiple-testing control, point-in-time universe, turnover costs, and attribution assumptions.
- **Interaction:** Keep methodology available on demand and expose per-value tooltips for unfamiliar statistics; expanded content must not obscure the primary evidence panel.

### Workflow Toggle
- **Shape:** 38px × 20px pill with a fully rounded track and a 16px circular thumb.
- **State:** Verified Mint for the running state, Raised Register for paused, with a short 150ms background/thumb transition.

## Do's and Don'ts

### Do:
- **Do** preserve the dark, low-saturation surface hierarchy and use the existing tokens as the source of truth.
- **Do** use cobalt to clarify active state, focus, and interaction—not as decoration.
- **Do** keep p-values, significance flags, multiple-testing controls, and error bars near consequential results.
- **Do** use mono type for dates, metrics, and identifiers where alignment improves trust.
- **Do** make every numeric value tabular, right-align decision data, and give primary metrics a clear size/weight step above supporting values.
- **Do** let whitespace and tonal grouping establish card hierarchy before adding borders.
- **Do** keep Methodology one interaction away in a collapsible right rail or per-value tooltip.
- **Do** keep Chinese and English layouts equally legible, including exported report headings and labels.

### Don't:
- **Don't** introduce blinking tickers, pulsing live P&L, or red/green trading-desk adrenaline.
- **Don't** use glossy gradients, glassmorphism, or decorative glow to create hierarchy.
- **Don't** use gamified language, streaks, confetti, leaderboards, or triumphant performance framing.
- **Don't** show a large return number without its uncertainty, significance context, and methodological caveats.
- **Don't** make every panel equally loud or box every secondary module.
- **Don't** use red/green P&L-style coloring to communicate significance.
- **Don't** imply live trading, personalized advice, or certainty that the evidence does not support.
