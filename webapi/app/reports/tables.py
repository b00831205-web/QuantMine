"""Standalone SVG table renderers for the PDF report.

Tables are drawn as SVG images (base64 data URIs) with hand-tuned column
widths instead of HTML ``<table>`` elements. Each table is rendered on its own
so the column density fits the A4 portrait width, then embedded in the PDF as
a picture -- no browser auto-layout surprises.
"""

from __future__ import annotations

import base64
import html

_FONT = "Noto Sans, Noto Sans CJK SC, DejaVu Sans, sans-serif"


def _esc(value: object) -> str:
    return html.escape(str(value))


def _to_uri(svg: str) -> str:
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"

def _fmt(value, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and value != value):  # NaN
        return "—"
    return f"{value:.{digits}f}"


def _pct2(value, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "—"
    return f"{value * 100:.{digits}f}%"


def render_table_svg(
    headers: list[str],
    rows: list,
    widths: list[float],
    aligns: list[str],
    *,
    font_size: float = 9.0,
    header_h: float = 18.0,
    row_h: float = 15.0,
    pad_x: float = 4.0,
) -> str:
    """rows items: ``list[str]`` for a normal row, or ``{'band': text}`` for
    a full-width group band (used by the backtest table)."""
    total_w = sum(widths)
    total_h = header_h + row_h * len(rows)
    xs: list[float] = []
    x = 0.0
    for w in widths:
        xs.append(x)
        x += w

    parts = [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" width="{tw:.1f}" height="{th:.1f}" '
            'viewBox="0 0 {tw:.1f} {th:.1f}" font-family="{font}" font-size="{fs:.1f}">'
        ).format(tw=total_w, th=total_h, font=_FONT, fs=font_size),
        '<rect width="{tw:.1f}" height="{th:.1f}" fill="white"/>'.format(tw=total_w, th=total_h),
    ]

    for i, label in enumerate(headers):
        left = aligns[i] == "l"
        tx = xs[i] + pad_x if left else xs[i] + widths[i] - pad_x
        parts.append(
            '<rect x="{x:.1f}" y="0" width="{w:.1f}" height="{h:.1f}" fill="#f4f4f4"/>'.format(
                x=xs[i], w=widths[i], h=header_h
            )
        )
        parts.append(
            '<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="{a}" fill="#666666" '
            'font-weight="600">{label}</text>'.format(
                tx=tx, ty=header_h - 6, a="start" if left else "end", label=_esc(label)
            )
        )
    parts.append(
        '<line x1="0" y1="{h:.1f}" x2="{tw:.1f}" y2="{h:.1f}" stroke="#000000" '
        'stroke-width="1.2"/>'.format(h=header_h, tw=total_w)
    )

    y = header_h
    for r_i, row in enumerate(rows):
        if isinstance(row, dict) and "band" in row:
            parts.append(
                '<rect x="0" y="{y:.1f}" width="{tw:.1f}" height="{h:.1f}" fill="#f4f4f4"/>'.format(
                    y=y, tw=total_w, h=row_h
                )
            )
            parts.append(
                '<text x="{x:.1f}" y="{ty:.1f}" fill="#666666" font-weight="700">{text}</text>'.format(
                    x=pad_x, ty=y + row_h - 4, text=_esc(row["band"])
                )
            )
        else:
            for c_i, val in enumerate(row):
                left = aligns[c_i] == "l"
                tx = xs[c_i] + pad_x if left else xs[c_i] + widths[c_i] - pad_x
                parts.append(
                    '<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="{a}" fill="#111111">{v}</text>'.format(
                        tx=tx, ty=y + row_h - 4, a="start" if left else "end", v=_esc(val)
                    )
                )
        if r_i < len(rows) - 1:
            parts.append(
                '<line x1="0" y1="{y:.1f}" x2="{tw:.1f}" y2="{y:.1f}" stroke="#cccccc" '
                'stroke-width="0.6"/>'.format(y=y + row_h, tw=total_w)
            )
        y += row_h

    parts.append("</svg>")
    return "".join(parts)


def ic_table(rows: list[dict], L: dict) -> str:
    if not rows:
        return ""
    headers = [
        L["col_variant"], L["col_factor"], L["col_period"], L["col_method"],
        L["col_ic_mean"], L["col_ic_std"], L["col_ir"], L["col_ic_pos"], L["col_n"],
        L["col_t"], L["col_p"], L["col_bonf"], L["col_bh"],
    ]
    widths = [76.0, 76.0, 32.0, 55.0] + [49.0] * 9
    aligns = ["l", "l", "r", "l"] + ["r"] * 9
    data = [
        [r["variant"], r["factor"], r["period"], r["method"], r["ic_mean"], r["ic_std"],
         r["ir"], r["ic_pos"], r["n"], r["t"], r["p"], r["bonf"], r["bh"]]
        for r in rows
    ]
    return _to_uri(render_table_svg(headers, data, widths, aligns))


def backtest_table(groups: list[dict], L: dict) -> str:
    if not groups:
        return ""
    headers = [
        L["col_group"], L["col_ann"], L["col_vol"], L["col_sharpe"],
        L["col_mdd"], L["col_win"], L["col_turnover"],
    ]
    widths = [60.0] + [103.4] * 6
    aligns = ["l"] + ["r"] * 6
    rows: list = []
    for g in groups:
        rows.append({"band": g["label"]})
        for r in g["rows"]:
            rows.append([r["group"], r["ann"], r["vol"], r["sharpe"], r["mdd"], r["win"], r["turnover"]])
    return _to_uri(render_table_svg(headers, rows, widths, aligns))


def monotonicity_table(groups: list[dict], L: dict) -> str:
    if not groups:
        return ""
    headers = [L["col_group"], L["col_mono_corr"], L["col_p"], L["col_mono_daily"], L["col_mono_pos"]]
    widths = [200.0, 120.0, 120.0, 120.0, 120.0]
    aligns = ["l", "r", "r", "r", "r"]
    rows = [
        [g["label"], g["mono"]["corr"], g["mono"]["p"], g["mono"]["daily"], g["mono"]["pos"]]
        for g in groups
    ]
    return _to_uri(render_table_svg(headers, rows, widths, aligns))


def attribution_tables(attribution: list[dict] | None, L: dict) -> list[str]:
    if not attribution:
        return []
    headers = [
        L["col_term"], L["col_coef"], L["col_stderr"], L["col_hac_t"],
        L["col_p"], L["col_ci_lo"], L["col_ci_hi"],
    ]
    widths = [90.0] + [98.3] * 6
    aligns = ["l"] + ["r"] * 6
    uris = []
    for a in attribution:
        rows = [
            [t["term"], t["coef"], t["stderr"], t["t"], t["p"], t["ci_lo"], t["ci_hi"]]
            for t in a["terms"]
        ]
        uris.append(_to_uri(render_table_svg(headers, rows, widths, aligns)))
    return uris


def summary_table(rows: list[dict], L: dict) -> str:
    if not rows:
        return ""
    headers = [L["col_dim"], L["col_metric"], L["col_value"], L["col_sample"]]
    widths = [110.0, 300.0, 140.0, 130.0]
    aligns = ["l", "l", "r", "l"]
    data = [[r["dim"], r["metric"], r["value"], r["sample"]] for r in rows]
    return _to_uri(render_table_svg(headers, data, widths, aligns))

def yearly_ic_table(rows: list[dict], L: dict) -> str:
    if not rows:
        return ""
    headers = [
        L["col_year"], L["col_factor"], L["col_period"],
        L["col_ic_mean"], L["col_ic_std"], L["col_ir"], L["col_ic_pos"], L["col_n"],
    ]
    widths = [45.0, 80.0, 32.0, 55.0, 55.0, 50.0, 60.0, 40.0]
    aligns = ["r", "l", "r", "r", "r", "r", "r", "r"]
    data = [
        [r["year"], r["factor"], r["period"],
         _fmt(r["ic_mean"], 4), _fmt(r["ic_std"], 3), _fmt(r["ir"], 3),
         _pct2(r["ic_pos"]), str(r["n"] or "")]
        for r in rows
    ]
    return _to_uri(render_table_svg(headers, data, widths, aligns))


def _chunk_rows(rows: list, size: int = 25) -> list[list]:
    """把长表按行数切块，避免单张 SVG 超高被 PDF 截断。"""
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def yearly_ic_tables(rows: list[dict], L: dict) -> list[str]:
    """分年度 IC 表：按 25 行一组拆成多张 SVG。"""
    headers = [
        L["col_year"], L["col_factor"], L["col_period"],
        L["col_ic_mean"], L["col_ic_std"], L["col_ir"], L["col_ic_pos"], L["col_n"],
    ]
    widths = [45.0, 80.0, 32.0, 55.0, 55.0, 50.0, 60.0, 40.0]
    aligns = ["r", "l", "r", "r", "r", "r", "r", "r"]
    uris = []
    for chunk in _chunk_rows(rows):
        data = [
            [r["year"], r["factor"], r["period"],
             _fmt(r["ic_mean"], 4), _fmt(r["ic_std"], 3), _fmt(r["ir"], 3),
             _pct2(r["ic_pos"]), str(r["n"] or "")]
            for r in chunk
        ]
        uris.append(_to_uri(render_table_svg(headers, data, widths, aligns)))
    return uris


def acf_tables(rows: list[dict], L: dict) -> list[str]:
    """ACF 表：按 25 行一组拆成多张 SVG。"""
    headers = [L["col_factor"], L["col_period"], L["col_lag"], L["col_acf"]]
    widths = [140.0, 90.0, 90.0, 120.0]
    aligns = ["l", "r", "r", "r"]
    uris = []
    for chunk in _chunk_rows(rows):
        data = [[r["factor"], r["period"], r["lag"], _fmt(r["acf"], 4)] for r in chunk]
        uris.append(_to_uri(render_table_svg(headers, data, widths, aligns)))
    return uris


def acf_table(rows: list[dict], L: dict) -> str:
    if not rows:
        return ""
    headers = [L["col_factor"], L["col_period"], L["col_lag"], L["col_acf"]]
    widths = [140.0, 90.0, 90.0, 120.0]
    aligns = ["l", "r", "r", "r"]
    data = [[r["factor"], r["period"], r["lag"], _fmt(r["acf"], 4)] for r in rows]
    return _to_uri(render_table_svg(headers, data, widths, aligns))


def sanity_table(rows: list[dict], L: dict) -> str:
    if not rows:
        return ""
    headers = [
        L["col_factor"], L["col_period"], L["col_scenario"],
        L["col_mean_diff"], L["col_std_diff"], L["col_mean_to_std"],
    ]
    widths = [90.0, 55.0, 85.0, 90.0, 90.0, 90.0]
    aligns = ["l", "r", "l", "r", "r", "r"]
    data = [
        [r["factor"], r["period"], r["scenario"],
         _fmt(r["mean_diff"], 4), _fmt(r["std_diff"], 4), _fmt(r["mean_to_std"], 3)]
        for r in rows
    ]
    return _to_uri(render_table_svg(headers, data, widths, aligns))

def alpha_beta_table(rows: list[dict], L: dict) -> str:
    if not rows:
        return ""
    headers = [L["col_alpha"], L["col_beta"], "n"]
    widths = [180.0, 140.0, 120.0]
    aligns = ["r", "r", "r"]
    data = [[_fmt(r["alpha"], 4), _fmt(r["beta"], 4), str(r["n"])] for r in rows]
    return _to_uri(render_table_svg(headers, data, widths, aligns))


def turnover_table(rows: list[dict], L: dict) -> str:
    if not rows:
        return ""
    headers = [L["col_factor"], L["col_period"], L["col_group"], L["col_turnover"]]
    widths = [150.0, 80.0, 100.0, 110.0]
    aligns = ["l", "r", "r", "r"]
    data = [
        [r["factor"], r["period"], "LS" if r["rank"] == 0 else f"Q{r['rank']}",
         _pct2(r["turnover"], 2)]
        for r in rows
    ]
    return _to_uri(render_table_svg(headers, data, widths, aligns))


def factor_autocorr_table(rows: list[dict], L: dict) -> str:
    if not rows:
        return ""
    headers = [L["col_factor"], L["col_autocorr"]]
    widths = [300.0, 140.0]
    aligns = ["l", "r"]
    data = [[r["factor"], _fmt(r["autocorr"], 4)] for r in rows]
    return _to_uri(render_table_svg(headers, data, widths, aligns))


def gross_table(rows: list[dict], L: dict) -> str:
    if not rows:
        return ""
    headers = [
        L["col_factor"], L["col_period"], L["col_group"],
        L["col_total_return"], L["col_ann"], L["col_vol"],
        L["col_sharpe"], L["col_mdd"], L["col_win"],
    ]
    widths = [80.0, 32.0, 50.0, 55.0, 55.0, 45.0, 45.0, 45.0, 40.0]
    aligns = ["l", "r", "r", "r", "r", "r", "r", "r", "r"]
    data = [
        [r["factor"], r["period"], "LS" if r["rank"] == 0 else f"Q{r['rank']}",
         _pct2(r["total_return"], 2), _pct2(r["yearly_return"], 2),
         _pct2(r["volatility"], 2), _fmt(r["sharpe"], 2),
         _pct2(r["mdd"], 2), _pct2(r["win"], 1)]
        for r in rows
    ]
    return _to_uri(render_table_svg(headers, data, widths, aligns))