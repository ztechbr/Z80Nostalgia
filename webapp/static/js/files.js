// Z80Nostalgia Web - gerenciador de arquivos (pasta temporaria fora do repo)
// Funciona sozinho (pagina /arquivos) e tambem embutido no terminal do BASIC,
// onde ganha os botoes extras "carregar no emulador" e "salvar programa".

(function () {
  const listEl = document.getElementById("file-list");
  const uploadForm = document.getElementById("upload-form");
  const uploadInput = document.getElementById("upload-input");
  const uploadMsg = document.getElementById("upload-msg");
  const dirLabel = document.getElementById("data-dir-label");
  const canLoadToBasic = window.TERMINAL_MODE === "basic" && !!window.z80Terminal;

  function fmtSize(n) {
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / (1024 * 1024)).toFixed(1) + " MB";
  }

  async function refreshFiles() {
    const r = await fetch("/api/files");
    const data = await r.json();
    if (dirLabel) dirLabel.textContent = data.dir;
    listEl.innerHTML = "";
    if (!data.files.length) {
      listEl.innerHTML = '<div class="phosphor-dim text-sm py-2">(pasta vazia)</div>';
      return;
    }
    for (const f of data.files) {
      const row = document.createElement("div");
      row.className = "flex items-center justify-between gap-2 border-b border-green-900/40 py-1.5 text-sm";

      const nameSpan = document.createElement("span");
      nameSpan.className = "phosphor truncate";
      nameSpan.textContent = `${f.name}  (${fmtSize(f.size)})`;
      row.appendChild(nameSpan);

      const btns = document.createElement("div");
      btns.className = "flex gap-2 shrink-0";

      if (canLoadToBasic && f.name.toLowerCase().endsWith(".bas")) {
        const loadBtn = document.createElement("button");
        loadBtn.className = "btn-retro px-2 py-0.5 text-xs";
        loadBtn.textContent = "carregar";
        loadBtn.title = "Digitar este programa dentro do BASIC em execucao";
        loadBtn.addEventListener("click", () => loadIntoBasic(f.name));
        btns.appendChild(loadBtn);
      }

      const dl = document.createElement("a");
      dl.className = "btn-retro px-2 py-0.5 text-xs";
      dl.href = `/api/files/download/${encodeURIComponent(f.name)}`;
      dl.textContent = "baixar";
      btns.appendChild(dl);

      const del = document.createElement("button");
      del.className = "btn-retro px-2 py-0.5 text-xs";
      del.textContent = "apagar";
      del.addEventListener("click", () => deleteFile(f.name));
      btns.appendChild(del);

      row.appendChild(btns);
      listEl.appendChild(row);
    }
  }

  async function deleteFile(name) {
    if (!confirm(`Apagar "${name}"?`)) return;
    await fetch(`/api/files/${encodeURIComponent(name)}`, { method: "DELETE" });
    refreshFiles();
  }

  async function loadIntoBasic(name) {
    const r = await fetch(`/api/files/content/${encodeURIComponent(name)}`);
    const data = await r.json();
    if (data.error) {
      alert("Erro ao ler arquivo: " + data.error);
      return;
    }
    const lines = data.content.split(/\r?\n/).filter((l) => l.trim() !== "");
    for (const line of lines) {
      await window.z80Terminal.sendCommand(line);
      await new Promise((res) => setTimeout(res, 120));
    }
    window.z80Terminal.appendOutput(`\n(carregado: ${name}, ${lines.length} linha(s))\n`);
  }

  if (uploadForm) {
    uploadForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!uploadInput.files.length) return;
      const fd = new FormData();
      fd.append("file", uploadInput.files[0]);
      uploadMsg.textContent = "enviando...";
      const r = await fetch("/api/files/upload", { method: "POST", body: fd });
      const data = await r.json();
      if (data.error) {
        uploadMsg.textContent = "erro: " + data.error;
      } else {
        uploadMsg.textContent = "enviado: " + data.name;
        uploadInput.value = "";
        refreshFiles();
      }
    });
  }

  // ---- salvar o programa BASIC atual (via LIST) como .bas ----
  const saveBtn = document.getElementById("btn-save-basic");
  if (saveBtn && canLoadToBasic) {
    saveBtn.addEventListener("click", async () => {
      const name = prompt("Salvar programa como (ex.: meujogo.bas):", "programa.bas");
      if (!name) return;
      const fname = name.toLowerCase().endsWith(".bas") ? name : name + ".bas";

      window.z80Terminal.appendOutput("LIST\n");
      const capturePromise = window.z80Terminal.captureUntilQuiet(600, 5000);
      await window.z80Terminal.sendRaw("LIST");
      let listing = await capturePromise;

      listing = listing.replace(/\f/g, "");
      listing = listing.replace(/>\s*$/, "").trim() + "\n";

      if (!listing.trim()) {
        alert("Nao ha programa em memoria (ou LIST nao retornou nada).");
        return;
      }

      const r = await fetch("/api/files/save_text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: fname, content: listing }),
      });
      const data = await r.json();
      if (data.error) {
        alert("Erro ao salvar: " + data.error);
      } else {
        alert("Programa salvo em: " + fname);
        refreshFiles();
      }
    });
  }

  document.getElementById("btn-refresh-files") &&
    document.getElementById("btn-refresh-files").addEventListener("click", refreshFiles);

  refreshFiles();
})();
