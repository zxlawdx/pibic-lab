from __future__ import annotations

from vela.template_engine.engine import render_template


def lab_view(params: dict) -> str:
    return render_template(
        "apps/lab/templates/index.html",
        context={"title": "PIBIC LAB"},
        router=params["router"],
    )
