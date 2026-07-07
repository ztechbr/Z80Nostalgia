# -*- coding: utf-8 -*-
"""
Z80Nostalgia Web - interface web (Flask) para o BASIC e o MONITOR do CP-300.

Este arquivo NAO altera cp300_basic.py / cp300_monitor.py / emucp.py: ele
apenas executa esses scripts como processos separados (igual ao terminal
local) e liga a entrada/saida deles a paginas web com visual de TRS-80
(tela preta, texto verde fosforo).

Uso:
    pip install -r webapp/requirements.txt
    python webapp/app.py
    -> abra http://127.0.0.1:5000
"""
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

from flask import (
    Flask, abort, jsonify, render_template, request, send_from_directory, session,
)

from emulator_session import SessionManager

BASE_DIR = Path(__file__).resolve().parent.parent  # raiz do repositorio Z80Nostalgia

SCRIPTS = {
    "basic": BASE_DIR / "cp300_basic.py",
    "monitor": BASE_DIR / "cp300_monitor.py",
}
MODE_LABELS = {"basic": "BASIC", "monitor": "MONITOR"}

# Pasta FORA da raiz do projeto onde os arquivos .bas/.blk do usuario ficam.
# Pode ser sobrescrita com a variavel de ambiente Z80_DATA_DIR.
DATA_DIR = Path(os.environ.get("Z80_DATA_DIR") or (Path(tempfile.gettempdir()) / "Z80Nostalgia_Arquivos"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# cp300_monitor.py carrega a ROM por um caminho RELATIVO ("27C128cp300.BIN").
# Como os processos rodam com cwd=DATA_DIR (para que S/P gravem/leiam os
# blocos ali), copiamos as ROMs para essa pasta tambem - sem isso, o
# monitor rodaria "sem ROM". Nao mexe nos arquivos originais do repositorio.
for _rom_name in ("27C128cp300.BIN", "2716cp300.BIN"):
    _src = BASE_DIR / _rom_name
    _dst = DATA_DIR / _rom_name
    if _src.exists() and (not _dst.exists() or _dst.stat().st_size != _src.stat().st_size):
        try:
            shutil.copy2(_src, _dst)
        except OSError:
            pass

ALLOWED_UPLOAD_EXT = {".bas", ".blk", ".txt"}

app = Flask(__name__)
app.secret_key = os.environ.get("Z80_SECRET_KEY", uuid.uuid4().hex)

manager = SessionManager(SCRIPTS, DATA_DIR)


def get_session_id():
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    return session["sid"]


def require_mode(mode):
    if mode not in SCRIPTS:
        abort(404, "modo invalido (use 'basic' ou 'monitor')")


def safe_filename(name):
    name = os.path.basename((name or "").strip())
    if not name or name in (".", ".."):
        raise ValueError("nome de arquivo invalido")
    return name


# ---------------------------------------------------------------------------
# Paginas
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/terminal/<mode>")
def terminal(mode):
    require_mode(mode)
    return render_template(
        "terminal.html",
        mode=mode,
        mode_label=MODE_LABELS[mode],
        other_mode="monitor" if mode == "basic" else "basic",
        other_label=MODE_LABELS["monitor" if mode == "basic" else "basic"],
    )


@app.route("/arquivos")
def arquivos():
    return render_template("files.html")


# ---------------------------------------------------------------------------
# API do terminal (processo do emulador)
# ---------------------------------------------------------------------------
@app.route("/api/start", methods=["POST"])
def api_start():
    mode = (request.get_json(silent=True) or {}).get("mode")
    require_mode(mode)
    sid = get_session_id()
    es = manager.get_or_create(sid, mode)
    text, pos, alive = es.read_since(0)
    return jsonify(output=text, pos=pos, alive=alive)


@app.route("/api/output")
def api_output():
    mode = request.args.get("mode")
    require_mode(mode)
    since = request.args.get("since", "0")
    try:
        since = int(since)
    except ValueError:
        since = 0
    sid = get_session_id()
    es = manager.get(sid, mode)
    if es is None:
        return jsonify(error="sessao nao iniciada"), 400
    text, pos, alive = es.read_since(since)
    return jsonify(output=text, pos=pos, alive=alive)


@app.route("/api/input", methods=["POST"])
def api_input():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode")
    require_mode(mode)
    text = data.get("text", "")
    sid = get_session_id()
    es = manager.get(sid, mode)
    if es is None:
        return jsonify(error="sessao nao iniciada"), 400
    try:
        es.send_line(text)
    except RuntimeError as e:
        return jsonify(error=str(e)), 400
    return jsonify(ok=True)


@app.route("/api/restart", methods=["POST"])
def api_restart():
    mode = (request.get_json(silent=True) or {}).get("mode")
    require_mode(mode)
    sid = get_session_id()
    es = manager.restart(sid, mode)
    text, pos, alive = es.read_since(0)
    return jsonify(output=text, pos=pos, alive=alive)


@app.route("/api/stop", methods=["POST"])
def api_stop():
    mode = (request.get_json(silent=True) or {}).get("mode")
    require_mode(mode)
    sid = get_session_id()
    manager.stop(sid, mode)
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# API de arquivos (pasta temporaria fora da raiz do projeto)
# ---------------------------------------------------------------------------
_HIDDEN_FILES = {"27C128cp300.BIN", "2716cp300.BIN"}


@app.route("/api/files")
def api_files():
    files = []
    for p in sorted(DATA_DIR.iterdir()):
        if p.is_file() and p.name not in _HIDDEN_FILES:
            st = p.stat()
            files.append({"name": p.name, "size": st.st_size, "mtime": st.st_mtime})
    return jsonify(files=files, dir=str(DATA_DIR))


@app.route("/api/files/content/<path:name>")
def api_file_content(name):
    try:
        name = safe_filename(name)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    p = DATA_DIR / name
    if not p.exists() or not p.is_file():
        return jsonify(error="arquivo nao encontrado"), 404
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return jsonify(error=str(e)), 500
    return jsonify(name=name, content=content)


@app.route("/api/files/download/<path:name>")
def api_file_download(name):
    try:
        name = safe_filename(name)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if not (DATA_DIR / name).exists():
        abort(404)
    return send_from_directory(DATA_DIR, name, as_attachment=True)


@app.route("/api/files/upload", methods=["POST"])
def api_file_upload():
    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify(error="nenhum arquivo enviado"), 400
    try:
        name = safe_filename(f.filename)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXT:
        return jsonify(error=f"extensao '{ext}' nao permitida (use .bas, .blk ou .txt)"), 400
    f.save(DATA_DIR / name)
    return jsonify(ok=True, name=name)


@app.route("/api/files/save_text", methods=["POST"])
def api_file_save_text():
    data = request.get_json(silent=True) or {}
    try:
        name = safe_filename(data.get("name", ""))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    ext = Path(name).suffix.lower()
    if ext not in (".bas", ".txt"):
        return jsonify(error="use extensao .bas ou .txt"), 400
    content = data.get("content", "")
    (DATA_DIR / name).write_text(content, encoding="utf-8")
    return jsonify(ok=True, name=name)


@app.route("/api/files/<path:name>", methods=["DELETE"])
def api_file_delete(name):
    try:
        name = safe_filename(name)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    p = DATA_DIR / name
    if not p.exists() or not p.is_file():
        return jsonify(error="arquivo nao encontrado"), 404
    p.unlink()
    return jsonify(ok=True)


if __name__ == "__main__":
    print(f"Pasta de arquivos do usuario (fora do repositorio): {DATA_DIR}")
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), threaded=True, debug=False)
