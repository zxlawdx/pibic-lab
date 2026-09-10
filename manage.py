#!/usr/bin/env python
"""CLI local do projeto PIBIC LAB baseado no Vela Framework."""
from __future__ import annotations

import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)


def _patch_tailwind_cli_on_windows() -> None:
    """Corrige a chamada do Tailwind CLI do Vela no Windows.

    O npm cria dois shims em ``node_modules/.bin`` no Windows: um arquivo
    POSIX sem extensão e ``tailwindcss.cmd``. O Vela fixado pelo projeto
    chama o arquivo sem extensão diretamente via ``subprocess.run()``, o que
    faz o CreateProcess do Windows retornar WinError 193. Aqui trocamos apenas
    a função interna de compilação para usar o shim ``.cmd`` no Windows.

    A correção fica no projeto para preservar o snapshot fixado do Vela e
    pode ser removida quando o framework incorporar o tratamento nativo de
    ``os.name == 'nt'``.
    """
    if os.name != "nt":
        return

    import vela.cli.collectstatic as collectstatic

    def _compile_tailwind_windows(
        project_root: str,
        input_css: str,
        output_css: str,
        minify: bool,
        verbose: bool,
    ) -> bool:
        local_bin = os.path.join(
            project_root,
            "node_modules",
            ".bin",
            "tailwindcss.cmd",
        )

        cmd = [local_bin, "-i", input_css, "-o", output_css]
        if minify:
            cmd.append("--minify")

        if verbose:
            mode = "minificado" if minify else "desenvolvimento"
            print(f"    -> Compilando Tailwind ({mode})...")

        try:
            result = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except FileNotFoundError:
            if verbose:
                print(
                    "    x Tailwind CLI do Windows não encontrado em "
                    "node_modules/.bin/tailwindcss.cmd"
                )
            return False
        except subprocess.TimeoutExpired:
            if verbose:
                print("    x Tailwind CLI expirou (timeout 60s).")
            return False
        except OSError as exc:
            if verbose:
                print(f"    x Erro ao executar Tailwind CLI: {exc}")
            return False

        if result.returncode != 0:
            if verbose:
                print(f"    x Tailwind CLI falhou:\n{result.stderr}")
            return False

        if verbose:
            try:
                size_kb = os.path.getsize(output_css) / 1024
                print(f"    * vela.bundle.css gerado ({size_kb:.1f} KB)")
            except OSError:
                print("    * vela.bundle.css gerado")

        return True

    collectstatic._compile_tailwind = _compile_tailwind_windows


_patch_tailwind_cli_on_windows()

from vela.cli.commands import CommandRunner  # noqa: E402


def main() -> None:
    runner = CommandRunner()
    runner.execute(sys.argv[1:])


if __name__ == "__main__":
    main()
