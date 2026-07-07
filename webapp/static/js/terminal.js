// Z80Nostalgia Web - terminal (polling em cima de /api/output e /api/input)
// Nao existe execucao de codigo no navegador: tudo roda no processo Python
// real (cp300_basic.py / cp300_monitor.py) do lado do servidor.

(function () {
  const outEl = document.getElementById("output");
  const inputEl = document.getElementById("cmdline");
  const ledEl = document.getElementById("led");
  const ledLabel = document.getElementById("led-label");
  const mode = window.TERMINAL_MODE;

  let pos = 0;
  let fullText = ""; // historico completo (nao e limpo por CLS), usado por salvar-programa
  let polling = false;
  let capturing = null; // {marker, resolve}

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function setAlive(alive) {
    if (alive) {
      ledEl.className = "led led-on";
      ledLabel.textContent = "ATIVO";
    } else {
      ledEl.className = "led led-off";
      ledLabel.textContent = "PARADO";
    }
  }

  function appendOutput(text) {
    if (!text) return;
    fullText += text;

    // 0x0C (form feed) e o que os scripts emitem quando chamam cls() ->
    // tratamos como "limpar tela", igual a um terminal real.
    if (text.indexOf("\f") !== -1) {
      const parts = text.split("\f");
      outEl.textContent = "";
      text = parts[parts.length - 1];
    }
    outEl.appendChild(document.createTextNode(text));
    outEl.scrollTop = outEl.scrollHeight;

    if (capturing) {
      capturing.check();
    }
  }

  async function pollOnce() {
    const r = await fetch(`/api/output?mode=${mode}&since=${pos}`);
    const data = await r.json();
    if (data.output) appendOutput(data.output);
    pos = data.pos;
    setAlive(data.alive);
  }

  async function pollLoop() {
    polling = true;
    while (polling) {
      try {
        await pollOnce();
      } catch (e) {
        // rede momentaneamente indisponivel: ignora e tenta de novo
      }
      await sleep(250);
    }
  }

  async function startSession() {
    outEl.textContent = "";
    fullText = "";
    const r = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    });
    const data = await r.json();
    pos = data.pos;
    appendOutput(data.output);
    setAlive(data.alive);
    if (!polling) pollLoop();
  }

  async function restartSession() {
    await fetch("/api/restart", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode }) })
      .then((r) => r.json())
      .then((data) => {
        outEl.textContent = "";
        fullText = "";
        pos = data.pos;
        appendOutput(data.output);
        setAlive(data.alive);
      });
  }

  async function sendRaw(text) {
    return fetch("/api/input", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, text }),
    });
  }

  async function sendCommand(text) {
    appendOutput(text + "\n"); // eco local: o processo nao ecoa (stdin nao e um tty)
    await sendRaw(text);
  }

  // Espera a saida "estabilizar" (sem novos caracteres por `quietMs`) e
  // devolve tudo que chegou depois do marcador atual em fullText.
  function captureUntilQuiet(quietMs, timeoutMs) {
    return new Promise((resolve) => {
      const marker = fullText.length;
      let lastLen = marker;
      let lastChange = Date.now();
      const started = Date.now();
      capturing = {
        check() {
          if (fullText.length !== lastLen) {
            lastLen = fullText.length;
            lastChange = Date.now();
          }
        },
      };
      const iv = setInterval(() => {
        const quiet = Date.now() - lastChange >= quietMs;
        const timedOut = Date.now() - started >= timeoutMs;
        if (quiet || timedOut) {
          clearInterval(iv);
          capturing = null;
          resolve(fullText.slice(marker));
        }
      }, 100);
    });
  }

  // ---- ligacoes de UI ----
  inputEl.addEventListener("keydown", async (e) => {
    if (e.key === "Enter") {
      const text = inputEl.value;
      inputEl.value = "";
      await sendCommand(text);
    }
  });

  document.getElementById("btn-restart").addEventListener("click", async () => {
    if (!confirm("Reiniciar a sessao? O programa/estado atual sera perdido.")) return;
    await restartSession();
    inputEl.focus();
  });

  document.addEventListener("click", () => inputEl.focus());

  window.addEventListener("beforeunload", () => {
    // best-effort: nao bloqueia o fechamento da aba
    navigator.sendBeacon &&
      navigator.sendBeacon(
        "/api/stop",
        new Blob([JSON.stringify({ mode })], { type: "application/json" })
      );
  });

  // Exposto para files.js (carregar/salvar programas .bas dentro do terminal)
  window.z80Terminal = { sendCommand, sendRaw, captureUntilQuiet, appendOutput };

  startSession().then(() => inputEl.focus());
})();
