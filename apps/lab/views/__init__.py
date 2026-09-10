from __future__ import annotations

from apps.lab.views.lab import lab_view


def register_routes(router) -> None:
    router.add(
        "/",
        lab_view,
        name="pibic_lab_home",
        title="PIBIC LAB",
        icon="",
        layout="blank",
        show_in_sidebar=False,
    )
