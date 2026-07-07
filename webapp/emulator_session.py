# -*- coding: utf-8 -*-
"""
emulator_session - ponte entre os scripts de terminal (cp300_basic.py e
cp300_monitor.py) e a interface web.

Os scripts originais NAO sao alterados: cada sessao apenas inicia um processo
Python separado (python -u cp300_basic.py / cp300_monitor.py), le a saida
caractere a caractere (para capturar prompts sem quebra de linha, como
"z80> " ou "* ") e escreve linhas na entrada padrao dele, exatamente como um
terminal local faria.
"""
import os
import subprocess
import sys
import threading
import time


class EmulatorSession:
    """Mantem um processo do emulador vivo e seu buffer de saida."""

    def __init__(self, mode, script_path, cwd):
        self.mode = mode
        self.script_path = str(script_path)
        self.cwd = str(cwd)

        self._buffer = []            # lista de caracteres recebidos (historico completo)
        self._buffer_lock = threading.Lock()
        self.last_active = time.time()
        self.started_at = time.time()

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"

        self.proc = subprocess.Popen(
            [sys.executable, "-u", self.script_path],
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )

        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    # -- leitura em segundo plano, caractere a caractere -------------------
    def _read_loop(self):
        stdout = self.proc.stdout
        try:
            while True:
                ch = stdout.read(1)
                if ch == "":
                    break
                with self._buffer_lock:
                    self._buffer.append(ch)
        except (ValueError, OSError):
            pass

    # -- API usada pelas rotas Flask ---------------------------------------
    def is_alive(self):
        return self.proc.poll() is None

    def read_since(self, pos):
        with self._buffer_lock:
            total = len(self._buffer)
            if pos < 0:
                pos = 0
            text = "".join(self._buffer[pos:]) if pos < total else ""
        self.last_active = time.time()
        return text, total, self.is_alive()

    def send_line(self, text):
        if not self.is_alive():
            raise RuntimeError("o processo do emulador ja foi encerrado")
        self.last_active = time.time()
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()

    def kill(self):
        try:
            self.proc.terminate()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


class SessionManager:
    """Guarda uma EmulatorSession por (id_de_sessao_do_navegador, modo)."""

    IDLE_TIMEOUT_SECONDS = 30 * 60

    def __init__(self, scripts, data_dir):
        self.scripts = scripts
        self.data_dir = data_dir
        self._sessions = {}
        self._lock = threading.Lock()
        self._reaper = threading.Thread(target=self._reap_loop, daemon=True)
        self._reaper.start()

    def get(self, sid, mode):
        with self._lock:
            return self._sessions.get((sid, mode))

    def get_or_create(self, sid, mode):
        key = (sid, mode)
        with self._lock:
            es = self._sessions.get(key)
            if es is not None and not es.is_alive():
                es = None
            if es is None:
                es = EmulatorSession(mode, self.scripts[mode], self.data_dir)
                self._sessions[key] = es
            return es

    def restart(self, sid, mode):
        key = (sid, mode)
        with self._lock:
            old = self._sessions.pop(key, None)
        if old:
            old.kill()
        return self.get_or_create(sid, mode)

    def stop(self, sid, mode):
        key = (sid, mode)
        with self._lock:
            old = self._sessions.pop(key, None)
        if old:
            old.kill()

    def _reap_loop(self):
        while True:
            time.sleep(60)
            now = time.time()
            with self._lock:
                stale = [
                    key for key, es in self._sessions.items()
                    if (now - es.last_active) > self.IDLE_TIMEOUT_SECONDS
                    or not es.is_alive()
                ]
                for key in stale:
                    es = self._sessions.pop(key)
                    es.kill()
