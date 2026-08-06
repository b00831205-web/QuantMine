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
import pandas as pd

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
    fig, ax = plt.subplots(figsize=(3.0, 1.15))
    ax.hist(ic, bins=25, color="#444444", edgecolor="white", linewidth=0.3)
    mean = sum(ic) / len(ic)
    ax.axvline(mean, color="#999999", linewidth=0.9, linestyle="--")
    ax.tick_params(labelsize=_TICK)
    ax.spines[["top", "right"]].set_visible(False)
    return _to_uri(fig)


def ic_heatmap_png(matrix: pd.DataFrame) -> str | None:
    """分年（或分月）均值 IC 热力图：行=时间，列=组合，颜色=均值 IC。"""
    if matrix is None or matrix.empty or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        return None

    fig, ax = plt.subplots(figsize=(5.2, 2.6))
    vmax = max(abs(float(matrix.values.min())), abs(float(matrix.values.max())), 1e-9)
    image = ax.imshow(matrix.values, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")

    ax.set_xticks(range(matrix.shape[1]))
    ax.set_xticklabels(matrix.columns, rotation=30, ha="right", fontsize=_TICK)
    ax.set_yticks(range(matrix.shape[0]))
    ax.set_yticklabels(matrix.index, fontsize=_TICK)
    ax.tick_params(length=0)

    for row in range(matrix.shape[0]):
        for col in range(matrix.shape[1]):
            value = matrix.iat[row, col]
            if pd.isna(value):
                continue
            ax.text(
                col, row, f"{value:.2f}",
                ha="center", va="center", fontsize=_TICK, color="#111111",
            )

    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04, ticks=[-vmax, 0, vmax])
    return _to_uri(fig)


def quantile_curve_png(dates: Sequence, quantiles: dict[str, Sequence[float]], spy: Sequence[float] | None) -> str | None:
    if not quantiles or not len(dates):
        return None
    fig, ax = plt.subplots(figsize=(4.6, 2.0))
    ordered = sorted(quantiles.items(), key=lambda kv: kv[0])
    for i, (name, series) in enumerate(ordered):
        shade = _GRAYS[min(i, len(_GRAYS) - 1)]
        width = 1.8 if i == len(ordered) - 1 else 0.9
        ax.plot(dates, series, color=shade, linewidth=width, label=name)
    if spy is not None and len(spy):
        ax.plot(dates, spy, color="#111111", linewidth=1.0, linestyle="--", label="SPY")
    ax.margins(x=0)
    ax.tick_params(labelsize=_TICK)
    ax.legend(fontsize=_LEG, ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.32))
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

_LINE_STYLES = ['-','--','-.',':']

def ic_multi_series_png(
        series: Sequence[dict],
        *,
        window: int = 20,
        max_lines: int = 8,
) -> str | None:
    usable = [
        item
        for item in series
        if item.get('dates') and item.get('ic')
    ][:max_lines]
    if not usable:
        return None

    fig, ax = plt.subplots(figsize = (5.2, 2.2))
    ax.axhline(0, color = '#cccccc', linewidth = 0.8)
    for i, item in enumerate(usable):
        rolling = pd.Series(item['ic']).rolling(window, min_periods = 1).mean()
        ax.plot(
            item['dates'],
            rolling,
            color = _GRAYS[min(i, len(_GRAYS)-1)],
            linestyle = _LINE_STYLES[i % len(_LINE_STYLES)],
            linewidth = 1.2,
            label = item['label'],
        )
    ax.margins(x=0)
    ax.tick_params(labelsize = _TICK)
    ax.xaxis.set_major_locator(plt.MaxNLocator(6))
    ax.legend(fontsize = _LEG, ncol=3, frameon= False, loc = 'upper center', bbox_to_anchor = (0.5, -0.32))
    ax.spines[['top', 'right']].set_visible(False)
    return _to_uri(fig)
