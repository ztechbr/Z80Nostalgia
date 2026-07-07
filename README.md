# Z80Nostalgia

> Engenharia reversa, reimplementação e **emulação** da ROM BASIC do
> **CP-300** — o microcomputador brasileiro da **Prológica (1981/1982)**,
> um clone do TRS-80 com CPU **Zilog Z80**.

Material **didático** completo para ensinar **linguagem de máquina e
arquitetura de computadores** a partir de um firmware real de 16 KB. O projeto
ataca a mesma ROM em **três níveis complementares**:

| Nível | O que faz | Arquivos |
|------|-----------|----------|
| 📖 **Ler** | Disassembly Z80 + explicação bloco a bloco | `z80dasm.py`, `disassembly_full.txt`, `ENGENHARIA_REVERSA_CP300.pdf` |
| ⌨️ **Usar** | Reimplementação do BASIC e do Monitor em Python | `cp300_basic.py`, `cp300_monitor.py` |
| ⚙️ **Executar** | Emulador Z80 que roda os **opcodes reais** da ROM | `emucp.py` |

---

## 🧩 O hardware

- **Máquina:** Prológica CP-300 (clone do TRS-80)
- **CPU:** Zilog Z80
- **ROM:** EPROM 27C128 = 16 KB (`27C128cp300.BIN`); também há a 2716 (2 KB)
- **Assinaturas internas:** `PROLOGICA  1981  BASIC`, `MONITOR VERSAO 1.1  1982`

---

## 📖 1. Engenharia reversa (ler o firmware)

**`z80dasm.py`** — um disassembler Z80 escrito do zero (base + prefixos
CB/ED/DD/FD).

```bash
python z80dasm.py 27C128cp300.BIN 0 > disassembly_full.txt
```

**`ENGENHARIA_REVERSA_CP300.pdf`** (218 páginas) — documento didático com:
- índice clicável e marcadores;
- a ROM **comentada linha a linha** (explicador automático de cada instrução
  Z80 + comentários especializados nas rotinas-chave);
- mapa de memória, rotinas de cassete, **tokenizador (CRUNCH)**, cold start, etc.

Regere o PDF com `python gera_pdf.py`.

---

## ⌨️ 2. Reimplementação (usar a máquina)

Recriam em Python o **comportamento** do firmware (sem emular a CPU).

### CP-300 BASIC
```bash
python cp300_basic.py
```
Interpretador BASIC nível-II compatível: `PRINT`, `INPUT`, `FOR/NEXT`,
`IF/THEN/ELSE`, `GOSUB`, `DIM`, `READ/DATA`, funções (`SQR`, `LEFT$`, `MID$`…)
e os **códigos de erro de 2 letras** do TRS-80/CP-300 (`SN`, `/0`, `BS`…).
Há um programa de exemplo: `python cp300_basic.py < exemplo.bas`.

### CP-300 Monitor
```bash
python cp300_monitor.py
```
Recria o `MONITOR VERSAO 1.1 1982`. Carrega a **ROM real** em `0000-3FFF` para
você inspecionar e desassemblar o firmware de dentro do monitor: `D` (dump),
`L` (disassembly), `R` (registradores Z80), `G`, blocos `NOME END.INICIO QTOS BYTES`.

---

## ⚙️ 3. Emulação (executar os opcodes reais)

**`emucp.py`** — um emulador de CPU **Z80** que lê os bytes da ROM e **executa
cada instrução**, como o chip faria.

```bash
python emucp.py --test       # autoteste que prova que o núcleo Z80 está correto
python emucp.py --trace 30   # executa o firmware do reset e mostra 30 passos
python emucp.py              # depurador interativo
```

O trace bate **byte a byte** com o disassembly. No boot, o emulador executa
~590 mil instruções reais, configura as portas de hardware e **monta a tabela
de ganchos na RAM** (visível em `d 4000`), exatamente como o hardware.

> **Limite honesto:** a execução dos opcodes é 100% real, mas chegar a uma tela
> de BASIC interativa exigiria os detalhes de vídeo/teclado do CP-300 (que não
> estão na ROM). O emulador foca em **executar e depurar** o firmware.

---

## 🌐 4. Interface Web (BASIC e MONITOR no navegador)

A pasta **`webapp/`** expõe o BASIC e o MONITOR numa página web (Flask +
Tailwind), com visual de terminal CRT verde-fósforo estilo TRS-80. Ela **não
altera** `cp300_basic.py` / `cp300_monitor.py` / `emucp.py` — apenas os
executa como processos, como no terminal local.

```bash
pip install -r webapp/requirements.txt
python webapp/app.py
```

Abra `http://127.0.0.1:5000`. Detalhes (pasta de arquivos `.bas`/`.blk` fora
do repositório, como funciona a ponte terminal↔web) em `webapp/README.md`.

---

## 🗂️ Estrutura

```
27C128cp300.BIN / 2716cp300.BIN   ROMs originais
z80dasm.py                        disassembler Z80
disassembly_full.txt              ROM em Assembly
gera_pdf.py                       gerador do PDF didático
ENGENHARIA_REVERSA_CP300.pdf      apostila comentada (218 págs)
EXPLICACAO_BLOCOS_*.txt           explicação resumida dos blocos
cp300_basic.py                    BASIC (reimplementação)
cp300_monitor.py                  Monitor (reimplementação)
emucp.py                          emulador Z80
exemplo.bas                       programa BASIC de demonstração
LEIA-ME_cp300_basic.txt           manual das ferramentas
webapp/                           interface web (Flask + Tailwind) do BASIC/MONITOR
```

## ✅ Requisitos
- Python 3.8+
- Para regerar o PDF: `pip install fpdf2`

---

## 📜 Licença e aviso

O **código-fonte** deste repositório (disassembler, BASIC, monitor, emulador,
gerador de PDF) é distribuído sob a licença **MIT** (ver `LICENSE`).

⚠️ **As ROMs** (`27C128cp300.BIN`, `2716cp300.BIN`) e os artefatos derivados
delas (disassembly, PDF) são **firmware da Prológica S.A.** (empresa brasileira
extinta) e permanecem propriedade de seus detentores de direitos. São incluídos
aqui apenas para fins de **preservação histórica e educação**. Se você for
detentor dos direitos e desejar a remoção, abra uma *issue*.

---

*Projeto educacional — preservando a memória da computação brasileira dos anos 80.*
