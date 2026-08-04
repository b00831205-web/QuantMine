"""Matplotlib chart builders for the PDF report.

Each function returns a base64 ``data:image/png`` URI (or ``None`` when its
input is empty, so the template can omit the figure). Plain grayscale, print
oriented — the report's philosophy is honest data, not decoration. Uses the
headless Agg backend so it runs on a server with no display.
"""
from __future__ import annotations

import base64
import io
from collections.abc import Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_GRAYS = ["#cccccc", "#aaaaaa", "#888888", "#555555", "#111111"]

plt.rcParams.update({
    "font.size": 11,          # 图内文字放大：图会缩小显示，字号要跟上才清晰
    "axes.edgecolor": "#888888",
    "axes.linewidth": 0.7,
    "figure.dpi": 200,        # 更高 dpi → 缩小显示时依然锐利
    "savefig.dpi": 200,
})

_TICK = 9   # 刻度字号
_LEG = 8    # 图例字号


def _to_uri(fig) -> str:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def ic_series_png(dates: Sequence, ic: Sequence[float], rolling: Sequence[float] | None) -> str | None:
    if not len(ic):
        return None
    fig, ax = plt.subplots(figsize=(3.4, 1.35))
    ax.axhline(0, color="#cccccc", linewidth=0.8)
    ax.plot(dates, ic, color="#bbbbbb", linewidth=0.7, label="daily IC")
    if rolling is not None and len(rolling):
        ax.plot(dates, rolling, color="#111111", linewidth=1.4, label="rolling mean")
    ax.margins(x=0)
    ax.tick_params(labelsize=_TICK)
    ax.spines[["top", "right"]].set_visible(False)
    return _to_uri(fig)


def ic_hist_png(ic: Sequence[float]) -> str | None:
    if not len(ic):
        return None
    fig, ax = plt.subplots(figsize=(3.4, 1.35))
    ax.hist(ic, bins=25, color="#444444", edgecolor="white", linewidth=0.3)
    mean = sum(ic) / len(ic)
    ax.axvline(mean, color="#999999", linewidth=0.9, linestyle="--")
    ax.tick_params(labelsize=_TICK)
    ax.spines[["top", "right"]].set_visible(False)
    return _to_uri(fig)


def quantile_curve_png(dates: Sequence, quantiles: dict[str, Sequence[float]], spy: Sequence[float] | None) -> str | None:
    if not quantiles or not len(dates):
        return None
    fig, ax = plt.subplots(figsize=(3.6, 1.6))
    ordered = sorted(quantiles.items(), key=lambda kv: kv[0])
    for i, (name, series) in enumerate(ordered):
        shade = _GRAYS[min(i, len(_GRAYS) - 1)]
        width = 1.8 if i == len(ordered) - 1 else 0.9
        ax.plot(dates, series, color=shade, linewidth=width, label=name)
    if spy is not None and len(spy):
        ax.plot(dates, spy, color="#111111", linewidth=1.0, linestyle="--", label="SPY")
    ax.margins(x=0)
    ax.tick_params(labelsize=_TICK)
    ax.legend(fontsize=_LEG, ncol=3, frameon=False, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    return _to_uri(fig)


def drawdown_png(dates: Sequence, drawdown: Sequence[float]) -> str | None:
    if not len(drawdown):
        return None
    fig, ax = plt.subplots(figsize=(3.4, 1.35))
    ax.fill_between(dates, drawdown, 0, color="#dddddd", edgecolor="#333333", linewidth=0.8)
    ax.margins(x=0)
    ax.tick_params(labelsize=_TICK)
    ax.spines[["top", "right"]].set_visible(False)
    return _to_uri(fig)


def loadings_png(
    terms: Sequence[str],
    coefs: Sequence[float],
    ci_low: Sequence[float],
    ci_high: Sequence[float],
    significant: Sequence[bool],
) -> str | None:
    if not len(terms):
        return None
    fig, ax = plt.subplots(figsize=(3.8, 1.5))
    y = range(len(terms))
    for i in y:
        colour = "#111111" if significant[i] else "#aaaaaa"
        ax.plot([ci_low[i], ci_high[i]], [i, i], color=colour, linewidth=1.0)
        ax.plot(coefs[i], i, "s", color=colour, markersize=5)
    ax.axvline(0, color="#cccccc", linewidth=0.8)
    ax.set_yticks(list(y))
    ax.set_yticklabels(terms, fontsize=_TICK)
    ax.invert_yaxis()
    ax.tick_params(labelsize=_TICK)
    ax.spines[["top", "right"]].set_visible(False)
    return _to_uri(fig)
