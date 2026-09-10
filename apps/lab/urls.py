from __future__ import annotations

from vela.urls import path

from apps.lab.views.lab import lab_view

urlpatterns = [path("/", lab_view)]
