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
