from dash import html


def help_icon(tip: str, left: bool = False) -> html.Div:
    cls = "help-icon help-icon-abs" + (" tip-left" if left else "")
    return html.Div("?", className=cls, **{"data-tip": tip})


def help_card(content: list, tip: str, style: dict | None = None,
              left: bool = False) -> html.Div:
    base = {
        "backgroundColor": "var(--surface)",
        "border": "1px solid var(--border)",
        "borderRadius": "4px",
        "padding": "16px",
        "marginBottom": "12px",
        "position": "relative",
    }
    if style:
        base.update(style)
    return html.Div(
        [help_icon(tip, left=left)] + content,
        style=base,
        className="help-card",
    )
