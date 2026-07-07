# -*- coding: utf-8 -*-
"""Ponto de entrada WSGI (gunicorn) para o Z80Nostalgia Web.

Uso em producao (dentro do container):
    gunicorn --workers 1 --threads 8 --bind 0.0.0.0:5000 wsgi:app

Importante: --workers 1. Cada sessao de emulador (processo do
cp300_basic.py / cp300_monitor.py) fica guardada em memoria no processo
Python do servidor (veja emulator_session.py). Com mais de um worker,
requisicoes da mesma sessao poderiam cair em processos diferentes e nao
encontrariam o emulador correspondente. Escalar horizontalmente exigiria
um backend de sessao compartilhado, fora do escopo deste projeto didatico.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app  # noqa: E402

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
