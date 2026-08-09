# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary users are individual quantitative researchers and practitioners who self-host the product and are usually also its deployers. Students learning quantitative methods are a secondary audience. It is not intended for portfolio managers making live allocations.

## Product Purpose

QUANTMINE helps researchers turn raw factor ideas into statistically defensible evidence. Its dashboard supports the research workflow from market-data exploration and factor-mining pipeline execution through factor, IC-test, rebalance, and backtest review, then report export and AI-assisted research-data querying.

## Positioning

Statistical honesty is the product's defining mechanism: conclusions retain uncertainty and explicitly account for the sources of inflated backtest results rather than presenting false certainty.

## Operating Context

Users work in a self-hosted research environment. They explore market data; run and monitor Airflow-style workflows; inspect factor outputs and Information Coefficient tests; review rebalancing returns and backtest details; export PDF/XLSX research reports; and use an AI assistant with RAG over prior conversations to query their research data.

## Capabilities and Constraints

- Research and education only; no live trading or personalized investment advice.
- Preserve the visible research rigor of Newey-West IC tests, multiple-testing control, point-in-time universes, turnover-based costs, and Carhart attribution.
- Preserve full Chinese/English support across the app and exported reports.
- Multi-user login uses an HttpOnly session cookie and bcrypt-hashed passwords.
- AI features send messages, chat history, and uploaded attachments to a user-configured external LLM/embedding provider; this must remain transparent wherever AI is used.
- Preserve this persistent but unobtrusive disclaimer: “For research and educational purposes only. Not investment advice. Past performance does not guarantee future results.”

## Brand Commitments

The product name is QUANTMINE. Its established identity is a dark, low-saturation research-terminal aesthetic, with `--bg-app: #0e1116` and accent `#4f8cff`. No external logo rules apply.

## Evidence on Hand

The repository contains the quantmine research library, daily Airflow pipeline, React/Vite dashboard, bilingual i18n files, test suite, example configuration, and a documented S&P 500 case study. Market data is not redistributed. Future work must not invent investment performance, customers, or other evidence.

## Product Principles

1. Make research claims traceable to the assumptions and tests that support them.
2. Show uncertainty, limitations, and statistical controls alongside headline results.
3. Support the whole research loop without suggesting execution or investment advice.
4. Keep self-hosted researchers in control of their data and external AI-provider choices.

## Accessibility & Inclusion

Best-effort accessibility for a self-hosted product: forms should be keyboard navigable, focus states visible, and contrast adequate in the dark theme. Preserve bilingual Chinese/English support.
