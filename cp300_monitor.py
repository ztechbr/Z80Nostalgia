# -*- coding: utf-8 -*-
"""
CP-300 MONITOR  -  reimplementacao em Python (SEM emulacao de CPU)
==================================================================
Recria o comportamento do "MONITOR VERSAO 1.1  1982 - PROLOGICA" gravado no
fim da ROM 27C128cp300.BIN (a partir de ~3D00h). NAO executa os opcodes Z80;
reimplementa em Python um monitor de linguagem de maquina classico:

  * Carrega a ROM REAL em 0000-3FFF, para o aluno inspecionar o firmware.
  * Mostra/edita a "memoria" (64 KB) em hexadecimal.
  * Mostra/edita os registradores do Z80 - o MESMO conjunto listado na ROM
    (string em 3DB7h): A B C D E F H L I A' B' C' D' E' F' H' L' IX IY PC SP.
  * Desassembla qualquer regiao (usa o z80dasm.py que escrevemos).
  * Salva/carrega BLOCOS no formato da ROM:  NOME  END.INICIO  QTOS BYTES.

No monitor TODOS os numeros sao em HEXADECIMAL (como no original).

Uso:   python cp300_monitor.py
"""
import sys, os, re, subprocess
from z80dasm import disasm

ROM_FILE = "27C128cp300.BIN"

# --------------------------------------------------------------------------
# Memoria de 64 KB. A ROM real fica em 0000-3FFF; o resto e RAM (zerada).
# --------------------------------------------------------------------------
MEM = bytearray(0x10000)
def carregar_rom():
    if os.path.exists(ROM_FILE):
        data = open(ROM_FILE, "rb").read()
        MEM[0:len(data)] = data
        return len(data)
    return 0

# --------------------------------------------------------------------------
# Registradores do Z80 (exatamente os exibidos pelo monitor da ROM).
# --------------------------------------------------------------------------
REGS8  = ["A","B","C","D","E","F","H","L","I",
          "A'","B'","C'","D'","E'","F'","H'","L'"]
REGS16 = ["IX","IY","PC","SP"]
REG = {r:0 for r in REGS8}
REG.update({r:0 for r in REGS16})
REG["SP"] = 0x42F8       # topo de pilha tipico do firmware
REG["PC"] = 0x3015       # entrada do cold start

# tabela de blocos "salvos" (simula a fita): nome -> (inicio, qtd)
BLOCOS = {}

def out(s=""): sys.stdout.write(s + "\n"); sys.stdout.flush()

def parse_hex(tok, default=None):
    tok = tok.strip().rstrip("H").rstrip("h")
    if tok == "":
        if default is not None: return default
        raise ValueError
    return int(tok, 16) & 0xFFFF

# ==========================================================================
# COMANDOS DO MONITOR
# ==========================================================================
def cmd_registradores(args):
    """R  -> mostra tudo;  R <reg> <valor> -> altera."""
    if args:
        nome = args[0].upper()
        if nome not in REG:
            out("?reg"); return
        if len(args) >= 2:
            val = parse_hex(args[1])
            REG[nome] = val & (0xFFFF if nome in REGS16 else 0xFF)
        else:
            out(f"{nome} = {REG[nome]:0{4 if nome in REGS16 else 2}X}")
        return
    # cabecalho de 8 bits (em duas metades: principais e alternativos)
    out("A  B  C  D  E  F  H  L  I   A' B' C' D' E' F' H' L'")
    linha = " ".join(f"{REG[r]:02X}" for r in REGS8)
    out(linha)
    out("IX   IY   PC   SP")
    out(" ".join(f"{REG[r]:04X}" for r in REGS16))
    # flags decodificadas a partir de F
    f = REG["F"]
    flags = "".join(n for b,n in zip((7,6,4,2,1,0),"S Z H PV N C".split()) if f & (1<<b))
    out(f"Flags(F={REG['F']:02X}): " + (flags if flags else "-"))

def cmd_dump(args, estado):
    """D [end] [qtd] -> dump hexadecimal + ASCII."""
    addr = parse_hex(args[0], estado["addr"]) if args else estado["addr"]
    qtd  = parse_hex(args[1]) if len(args) > 1 else 0x80
    fim = addr + qtd
    while addr < fim:
        linha = MEM[addr:addr+16]
        hexa = " ".join(f"{b:02X}" for b in linha)
        txt  = "".join(chr(b) if 32 <= b < 127 else "." for b in linha)
        out(f"{addr:04X}  {hexa:<47}  {txt}")
        addr += 16
    estado["addr"] = addr & 0xFFFF

def cmd_lista(args, estado):
    """L [end] [qtd] -> desassembly Z80 (usa z80dasm)."""
    addr = parse_hex(args[0], estado["addr"]) if args else estado["addr"]
    qtd  = parse_hex(args[1]) if len(args) > 1 else 0x30
    bloco = bytes(MEM[addr:addr+qtd+4])
    n = 0
    for a, raw, txt in disasm(bloco, addr):
        if a >= addr + qtd: break
        out(f"{a:04X}  {raw:<11}  {txt}")
        n = a + len(raw.split())
    estado["addr"] = n & 0xFFFF

def cmd_modifica(args, estado):
    """M <end> -> examina/edita byte a byte. Enter=proximo, '-'=anterior, '.'=sai."""
    if not args: out("?end"); return
    addr = parse_hex(args[0])
    out("(Enter=proximo  -=anterior  .=sai)")
    while True:
        try:
            resp = input(f"{addr:04X}  {MEM[addr]:02X}  : ").strip()
        except EOFError:
            break
        if resp in (".", "Q", "q"): break
        if resp == "-":
            addr = (addr - 1) & 0xFFFF; continue
        if resp == "":
            addr = (addr + 1) & 0xFFFF; continue
        try:
            MEM[addr] = parse_hex(resp) & 0xFF
            addr = (addr + 1) & 0xFFFF
        except ValueError:
            out("?hex")
    estado["addr"] = addr

def cmd_escreve(args, estado):
    """E <end> b b b ... -> escreve bytes na memoria."""
    if len(args) < 2: out("?args"); return
    addr = parse_hex(args[0])
    for tok in args[1:]:
        MEM[addr] = parse_hex(tok) & 0xFF
        addr = (addr + 1) & 0xFFFF
    estado["addr"] = addr

def cmd_preenche(args):
    """F <ini> <fim> <byte> -> preenche um intervalo."""
    if len(args) < 3: out("?args"); return
    ini, fim, b = parse_hex(args[0]), parse_hex(args[1]), parse_hex(args[2]) & 0xFF
    for a in range(ini, fim + 1): MEM[a & 0xFFFF] = b
    out(f"Preenchido {ini:04X}-{fim:04X} com {b:02X}")

def cmd_copia(args):
    """C <orig> <dst> <qtd> -> copia bloco (move)."""
    if len(args) < 3: out("?args"); return
    orig, dst, qtd = parse_hex(args[0]), parse_hex(args[1]), parse_hex(args[2])
    bloco = bytes(MEM[orig:orig+qtd])
    MEM[dst:dst+len(bloco)] = bloco
    out(f"Copiados {qtd:X} bytes de {orig:04X} para {dst:04X}")

def cmd_procura(args):
    """H <ini> <fim> b b ... -> procura uma sequencia de bytes."""
    if len(args) < 3: out("?args"); return
    ini, fim = parse_hex(args[0]), parse_hex(args[1])
    alvo = bytes(parse_hex(t) & 0xFF for t in args[2:])
    achou = 0
    a = ini
    while a <= fim - len(alvo):
        if MEM[a:a+len(alvo)] == alvo:
            out(f"  achado em {a:04X}"); achou += 1
        a += 1
    out(f"{achou} ocorrencia(s).")

def cmd_go(args):
    """G <end> -> 'executa' a partir do endereco (sem emulacao)."""
    addr = parse_hex(args[0]) if args else REG["PC"]
    REG["PC"] = addr
    out(f"G {addr:04X}: o Z80 saltaria para {addr:04X} e executaria a partir dai.")
    out("(Esta versao NAO emula a CPU; mostrando as proximas instrucoes:)")
    bloco = bytes(MEM[addr:addr+12])
    for a, raw, txt in disasm(bloco, addr):
        if a >= addr + 8: break
        out(f"  {a:04X}  {raw:<11}  {txt}")

def cmd_salva(args):
    """S <nome> <ini> <fim> -> salva um bloco (simula gravacao em fita)."""
    if len(args) < 3: out("?args"); return
    nome = args[0].upper()[:6]
    ini, fim = parse_hex(args[1]), parse_hex(args[2])
    qtd = fim - ini + 1
    with open(f"{nome}.blk", "wb") as f:
        f.write(bytes(MEM[ini:fim+1]))
    BLOCOS[nome] = (ini, qtd)
    out(f"Gravado: {nome}  inicio {ini:04X}  {qtd} bytes")

def cmd_carrega(args):
    """P <nome> [end] -> carrega um bloco de arquivo (simula leitura de fita)."""
    if not args: out("?nome"); return
    nome = args[0].upper()[:6]
    caminho = f"{nome}.blk"
    if not os.path.exists(caminho): out(f"?{nome} nao achado"); return
    data = open(caminho, "rb").read()
    ini = parse_hex(args[1]) if len(args) > 1 else BLOCOS.get(nome, (0x4300, 0))[0]
    MEM[ini:ini+len(data)] = data
    BLOCOS[nome] = (ini, len(data))
    out(f"Carregado: {nome} em {ini:04X}  ({len(data)} bytes)")

def cmd_tabela(args):
    """V -> tabela de blocos (formato da ROM)."""
    out("NOME    END.INICIO  QTOS BYTES")
    if not BLOCOS:
        out("(vazio)"); return
    for nome, (ini, qtd) in BLOCOS.items():
        out(f"{nome:<6}    {ini:04X}        {qtd}")

def cmd_basic():
    """B -> entra no BASIC (chama cp300_basic.py)."""
    aqui = os.path.dirname(os.path.abspath(__file__))
    alvo = os.path.join(aqui, "cp300_basic.py")
    if os.path.exists(alvo):
        subprocess.call([sys.executable, alvo])
    else:
        out("cp300_basic.py nao encontrado nesta pasta.")

AJUDA = """\
COMANDOS DO MONITOR  (todos os numeros em HEXADECIMAL)
  R                mostra os registradores do Z80
  R <reg> <val>    altera um registrador     ex.:  R PC 3015
  D [end] [qtd]    dump hexadecimal + ASCII  ex.:  D 0000 40
  L [end] [qtd]    desassembly (lista) Z80   ex.:  L 3455 30
  M <end>          examina/edita memoria byte a byte
  E <end> b b ...  escreve bytes             ex.:  E 4300 3E 0D CD 33 00
  F <ini> <fim> b  preenche intervalo        ex.:  F 4400 44FF 00
  C <org> <dst> q  copia bloco               ex.:  C 0000 8000 4000
  H <ini> <fim> b. procura bytes             ex.:  H 0000 3FFF C3 15 30
  G <end>          'executa' a partir de end (sem emulacao)
  S <nome> <i> <f> salva bloco (NOME END.INICIO QTOS BYTES)
  P <nome> [end]   carrega bloco salvo
  V                tabela de blocos salvos
  B                vai para o BASIC
  ? ou H?          esta ajuda
  Q ou X           sai do monitor
"""

# ==========================================================================
# ABERTURA + LACO PRINCIPAL
# ==========================================================================
def boot():
    os.system("cls" if os.name == "nt" else "clear")
    n = carregar_rom()
    out("MONITOR VERSAO 1.1  1982")
    out("PROLOGICA")
    out()
    if n:
        out(f"ROM {ROM_FILE} carregada em 0000-{n-1:04X} ({n} bytes).")
    else:
        out(f"(ROM {ROM_FILE} nao encontrada - memoria iniciada em zero.)")
    out()

def laco():
    boot()
    # prompt fiel da ROM: BASIC (S ou N)?
    try:
        r = input("BASIC (S ou N)? ").strip().upper()
    except EOFError:
        r = "N"
    if r.startswith("S"):
        cmd_basic()
        return
    out("Monitor pronto. Digite ? para a ajuda.")
    estado = {"addr": 0x0000}
    DISPATCH = {
        "R": lambda a: cmd_registradores(a),
        "D": lambda a: cmd_dump(a, estado),
        "L": lambda a: cmd_lista(a, estado),
        "M": lambda a: cmd_modifica(a, estado),
        "E": lambda a: cmd_escreve(a, estado),
        "F": lambda a: cmd_preenche(a),
        "C": lambda a: cmd_copia(a),
        "H": lambda a: cmd_procura(a),
        "G": lambda a: cmd_go(a),
        "S": lambda a: cmd_salva(a),
        "P": lambda a: cmd_carrega(a),
        "V": lambda a: cmd_tabela(a),
        "B": lambda a: cmd_basic(),
    }
    while True:
        try:
            linha = input("* ").strip()
        except (EOFError, KeyboardInterrupt):
            out(); break
        if not linha:
            continue
        partes = linha.split()
        cmd = partes[0].upper()
        args = partes[1:]
        if cmd in ("Q", "X", "BYE", "SYSTEM"):
            out("Saindo do monitor."); break
        if cmd in ("?", "AJUDA", "HELP") or linha == "H?":
            out(AJUDA); continue
        fn = DISPATCH.get(cmd)
        if fn is None:
            out("?cmd  (digite ? para ajuda)"); continue
        try:
            fn(args)
        except ValueError:
            out("?hex  (use numeros hexadecimais)")
        except Exception as e:
            out(f"?erro {e}")

if __name__ == "__main__":
    laco()
