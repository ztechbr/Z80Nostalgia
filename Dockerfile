# Z80Nostalgia Web - imagem para publicar em EasyPanel/Docker
#
# Empacota a interface web (webapp/) junto com os scripts do emulador
# (cp300_basic.py, cp300_monitor.py, emucp.py) e as ROMs originais, sem
# alterar nenhum desses arquivos.
FROM python:3.12-slim

# ncurses-bin fornece o comando "clear", que cp300_basic.py/cp300_monitor.py
# chamam via os.system() na tela de abertura (boot/cls). Sem isso o comando
# simplesmente falharia silenciosamente (a tela so nao seria limpa).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ncurses-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia so o requirements primeiro para aproveitar o cache de camadas do Docker.
COPY webapp/requirements.txt webapp/requirements.txt
RUN pip install --no-cache-dir -r webapp/requirements.txt

# Copia o restante do repositorio (scripts do emulador, ROMs, app web).
COPY . .

ENV TERM=xterm-256color \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    Z80_DATA_DIR=/data \
    PORT=5000

# Usuario nao-root + pasta de dados persistente (arquivos .bas/.blk do usuario).
RUN useradd -m -u 1000 z80 \
    && mkdir -p /data \
    && chown -R z80:z80 /app /data
USER z80

VOLUME ["/data"]
EXPOSE 5000

WORKDIR /app/webapp

# --workers 1: o estado de cada sessao (o processo do emulador) fica em
# memoria no processo do servidor - ver webapp/wsgi.py para o porque.
CMD ["gunicorn", "--workers", "1", "--threads", "8", "--timeout", "60", \
     "--bind", "0.0.0.0:5000", "wsgi:app"]
