# -*- coding: utf-8 -*-
"""
PDF didatico DETALHADO da ROM 27C128cp300.BIN (CP-300 / Z80).
- Indice clicavel (TOC) + marcadores (bookmarks) do PDF.
- Comentario LINHA A LINHA em todos os trechos de codigo:
  explicador automatico de cada instrucao Z80 + comentarios especializados
  de engenharia reversa nas rotinas-chave (cassete, tokenizador, cold start...).
"""
from fpdf import FPDF
from z80dasm import disasm

ROM = open("27C128cp300.BIN", "rb").read()
FULL = disasm(ROM, 0)                       # lista (addr, raw, txt)

# ===========================================================================
# 1) EXPLICADOR AUTOMATICO: traduz cada mnemonico Z80 para portugues
# ===========================================================================
REG8 = {"A","B","C","D","E","H","L"}
COND = {"NZ":"se nao for zero (NZ)","Z":"se for zero (Z)",
        "NC":"se nao houve carry (NC)","C":"se houve carry (C)",
        "PO":"se paridade impar (PO)","PE":"se paridade par (PE)",
        "P":"se positivo (P)","M":"se negativo (M)"}

def operand(tok):
    if tok is None: return ""
    t=tok.strip()
    if t=="A": return "A (acumulador)"
    if t in REG8: return f"o registrador {t}"
    if t in ("BC","DE","HL","SP","IX","IY","AF","AF'","HL'"): return f"o par {t}"
    if t=="(HL)": return "o byte apontado por HL"
    if t=="(DE)": return "o byte apontado por DE"
    if t=="(BC)": return "o byte apontado por BC"
    if t.startswith("(IX") or t.startswith("(IY"): return f"o byte em {t[1:-1]}"
    if t=="(C)": return "a porta indicada por C"
    if t.startswith("(") and t.endswith(")"): return f"a memoria no endereco {t[1:-1]}"
    if t.endswith("H"): return f"o valor {t}"
    return t

def split2(arg):
    if not arg: return (None,None)
    depth=0
    for i,ch in enumerate(arg):
        if ch=="(":depth+=1
        elif ch==")":depth-=1
        elif ch=="," and depth==0:
            return (arg[:i].strip(),arg[i+1:].strip())
    return (arg.strip(),None)

def explain(m):
    if m.startswith("DB"): return "Bytes de DADOS (nao e codigo executavel)."
    sp=m.split(None,1); op=sp[0]; arg=sp[1].strip() if len(sp)>1 else ""
    a,b=split2(arg)
    if op=="NOP": return "Nao faz nada; passa para a proxima instrucao."
    if op=="HALT": return "Para a CPU ate ocorrer uma interrupcao."
    if op=="DI": return "Desliga (proibe) as interrupcoes."
    if op=="EI": return "Liga (permite) as interrupcoes."
    if op=="LD": return f"Copia {operand(b)} para {operand(a)}."
    if op=="PUSH": return f"Empilha {operand(a)} (salva na pilha)."
    if op=="POP": return f"Desempilha da pilha para {operand(a)}."
    if op=="JP":
        if b is None:
            if a=="(HL)": return "Salta para o endereco contido em HL."
            return f"Salta (incondicional) para {a}."
        return f"Salta para {b} {COND.get(a,a)}; senao continua."
    if op=="JR":
        if b is None: return f"Salto curto (relativo) para {a}."
        return f"Salto curto para {b} {COND.get(a,a)}; senao continua."
    if op=="DJNZ": return f"Decrementa B; se B<>0 repete em {a} (controle de laco)."
    if op=="CALL":
        if b is None: return f"Chama a sub-rotina {a} (guarda o retorno na pilha)."
        return f"Chama a sub-rotina {b} {COND.get(a,a)}."
    if op=="RET":
        return "Retorna da sub-rotina." if not arg else f"Retorna {COND.get(arg,arg)}."
    if op=="RST": return f"Servico rapido: chama o endereco fixo {a}."
    if op=="INC": return f"Soma 1 a {operand(a)}."
    if op=="DEC": return f"Subtrai 1 de {operand(a)}."
    if op=="ADD":
        return (f"Soma {operand(b)} a {a}." if a in ("HL","IX","IY")
                else f"Soma {operand(b)} ao acumulador A.")
    if op=="ADC": return f"Soma {operand(b)} mais o carry a {operand(a)}."
    if op=="SUB": return f"Subtrai {operand(a)} do acumulador A."
    if op=="SBC": return f"Subtrai {operand(b)} mais o carry de {operand(a)}."
    if op=="AND": return f"E-logico (AND) bit a bit entre A e {operand(a)}."
    if op=="OR":  return f"OU-logico (OR) bit a bit entre A e {operand(a)}."
    if op=="XOR": return ("XOR de A com ele mesmo: ZERA o acumulador A." if a=="A"
                          else f"OU-exclusivo (XOR) entre A e {operand(a)}.")
    if op=="CP":  return f"Compara A com {operand(a)} (subtrai sem guardar; so ajusta flags)."
    if op=="BIT": return f"Testa o bit {a} de {operand(b)} (flag Z liga se o bit for 0)."
    if op=="SET": return f"Liga (=1) o bit {a} de {operand(b)}."
    if op=="RES": return f"Zera (=0) o bit {a} de {operand(b)}."
    if op in ("RLC","RL","RLCA","RLA"): return f"Rotaciona {operand(a) if a else 'A'} para a ESQUERDA."
    if op in ("RRC","RR","RRCA","RRA"): return f"Rotaciona {operand(a) if a else 'A'} para a DIREITA."
    if op=="SLA": return f"Desloca {operand(a)} a esquerda (x2)."
    if op in ("SRA","SRL"): return f"Desloca {operand(a)} a direita (/2)."
    if op=="IN":  return f"LE {operand(b)} e guarda em {operand(a)} (entrada de hardware)."
    if op=="OUT": return f"ESCREVE {operand(b)} em {operand(a)} (saida de hardware)."
    if op=="EX":  return f"Troca {operand(a)} com {operand(b)}."
    if op=="EXX": return "Troca BC,DE,HL pelos registradores alternativos."
    if op=="LDIR":return "Copia um BLOCO: (HL)->(DE), repetindo BC vezes (ascendente)."
    if op=="LDDR":return "Copia um bloco (HL)->(DE), BC vezes (descendente)."
    if op=="LDI": return "Copia 1 byte (HL)->(DE); avanca HL,DE; decrementa BC."
    if op=="LDD": return "Copia 1 byte (HL)->(DE); recua HL,DE; decrementa BC."
    if op=="CPIR":return "Busca: compara A com (HL) avancando ate achar ou BC=0."
    if op=="CPDR":return "Busca para tras: compara A com (HL) recuando ate achar ou BC=0."
    if op=="CPI": return "Compara A com (HL); avanca HL; decrementa BC."
    if op=="CPD": return "Compara A com (HL); recua HL; decrementa BC."
    if op=="DAA": return "Ajuste decimal de A (aritmetica BCD)."
    if op=="CPL": return "Inverte todos os bits de A (complemento de 1)."
    if op=="NEG": return "A = 0 - A (complemento de 2; troca o sinal)."
    if op=="SCF": return "Liga a flag de carry."
    if op=="CCF": return "Inverte a flag de carry."
    if op=="IM":  return f"Seleciona o modo de interrupcao {a}."
    if op in ("RETI","RETN"): return "Retorna de uma interrupcao."
    if op in ("RRD","RLD"): return "Rotaciona digitos BCD entre A e (HL)."
    return "(instrucao Z80)"

# ===========================================================================
# 2) COMENTARIOS ESPECIALIZADOS (engenharia reversa) - sobrepoem o automatico
# ===========================================================================
CMT = {
 0x0000:"PARTIDA: ao ligar, o Z80 comeca SEMPRE no endereco 0000h. DI deixa a maquina em estado seguro.",
 0x0001:"XOR A: zera A em 1 byte (mais curto/rapido que LD A,0).",
 0x0002:"Desvia para o cold start em 3015h.",
 0x0005:"RST 08 -> gancho na RAM (4000h): o usuario pode redirecionar este servico.",
 0x0038:"VETOR DA INTERRUPCAO (modo 1): 60x/segundo o Z80 corre para 4012h.",
 0x0075:"DE=4080h: destino na RAM da tabela de ganchos.",
 0x0078:"HL=18F7h: tabela-modelo gravada na ROM.",
 0x007B:"BC=27h (39): numero de bytes a copiar.",
 0x007E:"LDIR: copia 39 bytes ROM->RAM de uma vez (o hardware faz o laco).",
 0x0096:"Grava C3h = OPCODE de JP: o programa ESCREVE codigo na RAM em tempo real!",
 0x0099:"Grava a parte baixa do endereco-destino do JP.",
 0x009B:"Grava a parte alta do endereco-destino.",
 0x009D:"DJNZ: repete, montando varios JP -> a tabela de ganchos.",
 0x00AC:"Define o topo da PILHA do sistema (SP=42F8h).",
 0x00AF:"Chama a inicializacao do BASIC (1B8Fh).",
 # tokenizador (CRUNCH)
 0x1BC0:"TOKENIZADOR (CRUNCH): comeca aqui. Converte o texto digitado em TOKENS de 1 byte.",
 0x1BC6:"HL aponta o buffer onde esta a linha digitada pelo usuario.",
 0x1BCC:"Le um caractere do buffer.",
 0x1BCD:"E espaco (20h)? trata separado.",
 0x1BD3:"E aspas (22h)? entao e uma string: copia literal, sem tokenizar.",
 0x1BF6:"DE=164Fh: aponta a TABELA DE PALAVRAS-CHAVE (RESET,PRINT,...) na ROM.",
 0x1C00:"Pega o caractere atual para comparar com a tabela.",
 0x1C09:"AND 5Fh: converte letra MINUSCULA em MAIUSCULA (truque de 1 instrucao).",
 0x1C0B:"Regrava o caractere ja maiusculo no buffer.",
 # cassete - gravacao de bit
 0x31A5:"CASSETE/GRAVA BIT: liga a saida (nivel 1) na porta FFh.",
 0x31A7:"OUT (FFh),A: o bit vai para o gravador de fita.",
 0x31A9:"LD B,0Dh + DJNZ abaixo: laco de TEMPORIZACAO (largura do pulso).",
 0x31AD:"Troca o nivel da saida (nivel 2): forma a borda do pulso.",
 0x31B1:"Outro laco de espera: completa a duracao do bit.",
 0x31B5:"CALL 31F3h: atraso fino que calibra a VELOCIDADE de gravacao.",
 0x31B8:"Intervalo entre um bit e o proximo.",
 0x31BC:"RET: bit gravado; volta para gravar o seguinte.",
 0x31C5:"IN A,(FFh): LE a porta do cassete (sinal vindo da fita na leitura).",
 # cassete - cold start ports
 0x3455:"COLD START: IM 1 escolhe o modo de interrupcao (vetor fixo em 0038h).",
 0x3457:"Posiciona a pilha (SP=407Dh).",
 0x345A:"OUT (E4h),A: programa a mascara de interrupcoes.",
 0x345E:"OUT (ECh),A: configura o modo de video/sistema.",
 0x3462:"OUT (F4h),A: inicializa o controlador (disco/IRQ).",
 0x3466:"OUT (F0h),A: comando de RESET ao controlador de disquete.",
 0x346D:"OUT (E0h),A: define a mascara de interrupcoes.",
 0x347C:"LDIR: instala em 4000h a tabela de ganchos (os JP da RAM).",
 0x3487:"LDIR: copia rotinas/vetores adicionais para a RAM.",
 0x3489:"IN A,(FFh): le status do cassete/teclado.",
 0x3494:"IN A,(F4h): le o status do controlador de disco.",
 0x34A2:"Se deu timeout (sem disco), vai para a rotina sem-disco (37AFh).",
 # cassete - busca de comando
 0x375E:"Procura o nome do comando na tabela (CPIR) e devolve seu endereco.",
 0x3764:"CPIR: varre 15 entradas da tabela em 376Ch comparando.",
 # monitor
 0x3D39:"[TEXTO] 'BASIC (S ou N)': pergunta na partida do Monitor.",
 0x3DB7:"[TEXTO] Lista dos registradores Z80 que o Monitor mostra na tela.",
 0x3DF7:"[TEXTO] Assinatura: 'MONITOR VERSAO 1.1  1982'.",
}

# ===========================================================================
# 3) REGIOES DE DADOS (texto/tabelas) - renderizadas como ASCII, nao codigo
# ===========================================================================
DATA = [
 (0x0105,0x012D,"Mensagens de abertura ('Mem. usada', 'PROLOGICA 1981 BASIC')"),
 (0x0202,0x020F,"Espacos / texto curto"),
 (0x0279,0x0283,"Texto 'Diskette?'"),
 (0x1625,0x1790,"TABELA DE PALAVRAS-CHAVE do BASIC (cada comando vira 1 token)"),
 (0x18C9,0x1941,"Codigos de erro de 2 letras + 'Erro' 'READY' 'Break'"),
 (0x3044,0x3146,"Tabelas de conversao de caracteres (teclado/video)"),
 (0x376C,0x377A,"Mini-tabela de nomes de comando do cassete"),
 (0x3D39,0x3D72,"Mensagens do Monitor ('BASIC (S ou N)', cabecalho de listagem)"),
 (0x3DB7,0x3DE1,"Nomes dos registradores Z80 exibidos pelo Monitor"),
 (0x3DF7,0x3E1B,"Assinatura: MONITOR VERSAO 1.1 1982 / PROLOGICA"),
]
def data_at(addr):
    for s,e,d in DATA:
        if s<=addr<e: return (s,e,d)
    return None

# ===========================================================================
# 4) MARCADORES de secao (indice/bookmarks).  (addr, nivel, titulo)
# ===========================================================================
MARKERS = [
 (0x0000,0,"Parte I - Vetores RST e partida da CPU"),
 (0x0013,1,"Tratadores de RST (servicos rapidos)"),
 (0x0040,1,"Rotinas de E/S, teclado e video"),
 (0x0075,1,"Montagem dos ganchos na RAM (auto-modificacao)"),
 (0x0105,1,"[DADOS] Mensagens de abertura"),
 (0x012D,0,"Parte II - Interpretador BASIC"),
 (0x1625,1,"[DADOS] Tabela de palavras-chave (tokens)"),
 (0x1790,1,"Rotinas auxiliares do BASIC"),
 (0x18C9,1,"[DADOS] Tabela de codigos de erro"),
 (0x1941,1,"Tratamento de erro, prompt READY e edicao de linha"),
 (0x1BC0,1,"Tokenizador (CRUNCH): texto -> tokens"),
 (0x1C5B,1,"Armazenamento e listagem de linhas (LIST)"),
 (0x2000,1,"Executores de comandos e avaliacao de expressoes"),
 (0x3012,0,"Parte III - Baixo nivel: drivers e hardware"),
 (0x3044,1,"[DADOS] Tabelas de caracteres"),
 (0x3146,1,"Rotinas de video e conversao"),
 (0x31A5,1,"Cassete: gravacao de bit (porta FFh)"),
 (0x3340,1,"Cassete: leitura de bit e sincronismo"),
 (0x3455,1,"Cold start: inicializacao do hardware"),
 (0x3680,1,"Rotinas de sistema"),
 (0x3739,1,"Cassete/disquete: rotinas de arquivo"),
 (0x37C0,1,"Selecao de dispositivo (cassete x disco)"),
 (0x3D00,0,"Parte IV - Programa MONITOR (1982)"),
 (0x3D39,1,"[DADOS] Mensagens do Monitor"),
 (0x3DB7,1,"[DADOS] Nomes dos registradores Z80"),
 (0x3DF7,1,"[DADOS] Assinatura do Monitor"),
]

# ===========================================================================
# 5) MONTAGEM DO PDF
# ===========================================================================
def S(t):
    return str(t).encode("latin-1","replace").decode("latin-1")

class PDF(FPDF):
    def multi_cell(self, w, h=None, text="", **kw):
        kw.setdefault("new_x","LMARGIN"); kw.setdefault("new_y","NEXT")
        return super().multi_cell(w, h, text, **kw)
    def header(self):
        if self.page_no()==1: return
        self.set_font("Helvetica","I",7); self.set_text_color(120)
        self.cell(0,5,"Engenharia reversa - ROM 27C128cp300.BIN (CP-300 / Z80)")
        self.cell(0,5,f"pag. {self.page_no()}",align="R")
        self.ln(6); self.set_text_color(0)

pdf=PDF(format="A4")
pdf.set_auto_page_break(True, margin=14)
pdf.set_margins(14,14,14)

def h1(t):
    pdf.ln(1); pdf.set_font("Helvetica","B",15); pdf.set_text_color(0,0,130)
    pdf.multi_cell(0,8,S(t)); pdf.set_text_color(0); pdf.ln(1)
def h2(t):
    pdf.set_font("Helvetica","B",11); pdf.set_text_color(30,30,30)
    pdf.multi_cell(0,6,S(t)); pdf.set_text_color(0); pdf.ln(0.3)
def para(t):
    pdf.set_font("Helvetica","",10); pdf.multi_cell(0,5.1,S(t)); pdf.ln(1)
def mono(t,size=8.5):
    pdf.set_font("Courier","",size); pdf.multi_cell(0,4.6,S(t)); pdf.ln(1)

# ---- CAPA ----
pdf.add_page(); pdf.ln(28)
pdf.set_font("Helvetica","B",22); pdf.multi_cell(0,11,S("Engenharia Reversa da ROM"),align="C")
pdf.set_font("Helvetica","B",16); pdf.multi_cell(0,9,S("27C128cp300.BIN"),align="C"); pdf.ln(3)
pdf.set_font("Helvetica","",13)
pdf.multi_cell(0,7,S("Microcomputador CP-300 (Prologica, 1981/1982)\n"
                     "Clone do TRS-80  -  CPU Zilog Z80  -  EPROM 16 KB"),align="C"); pdf.ln(8)
pdf.set_font("Helvetica","I",11)
pdf.multi_cell(0,6,S("Disassembly completo, comentado linha a linha,\ncom indice clicavel"),align="C"); pdf.ln(16)
pdf.set_font("Helvetica","",10)
pdf.multi_cell(0,6,S("Material didatico - Linguagem de Maquina / Arquitetura\n\nData: 04/06/2026"),align="C")

# ---- INDICE CLICAVEL (placeholder; preenchido ao final com bookmarks) ----
def render_toc(pdf, outline):
    pdf.set_font("Helvetica","B",16); pdf.set_text_color(0,0,130)
    pdf.multi_cell(0,10,S("Indice"),new_x="LMARGIN",new_y="NEXT")
    pdf.set_text_color(0); pdf.ln(2)
    for s in outline:
        lvl=s.level
        pdf.set_font("Helvetica","B" if lvl==0 else "",11 if lvl==0 else 9.5)
        if lvl==0: pdf.ln(1.5)
        link=pdf.add_link(); pdf.set_link(link, page=s.page_number)
        pdf.set_x(14+lvl*6)
        name=S(s.name)
        pdf.cell(150-lvl*6,5.6,name,link=link)
        pdf.cell(0,5.6,str(s.page_number),align="R",link=link,
                 new_x="LMARGIN",new_y="NEXT")

pdf.add_page()
pdf.insert_toc_placeholder(render_toc, pages=2, allow_extra_pages=True)

# ---- INTRODUCAO ----
pdf.add_page()
pdf.start_section("Como ler este documento",0)
h1("Como ler este documento")
para("A EPROM guarda apenas NUMEROS (bytes). A CPU Z80 le esses numeros e os "
"interpreta como ORDENS. Fazer o disassembly e o caminho inverso - traduzir os "
"numeros de volta para Assembly. Isso e ENGENHARIA REVERSA: sem o codigo-fonte, "
"deduzimos o que o programa faz lendo so o binario.")
h2("Anatomia de cada par de linhas da listagem comentada")
mono("31A5  3E 01        LD A,01H\n"
"        ; CASSETE/GRAVA BIT: liga a saida (nivel 1) na porta FFh.\n"
"  |       |            |\n"
"  |       |            +-- MNEMONICO (Assembly Z80)\n"
"  |       +--------------- BYTES crus em hexadecimal (como estao na ROM)\n"
"  +----------------------- ENDERECO do 1o byte (hex)\n"
"  e a 2a linha (apos ';') e o COMENTARIO explicando o que a instrucao faz.")
para("O Z80 tem instrucoes de 1 a 4 bytes. Ha regioes que NAO sao codigo, e sim "
"DADOS (textos/tabelas): essas aparecem com o rotulo [DADOS] e sao mostradas "
"como texto. O mesmo byte 50h vale 'LD D,B' (codigo) ou a letra 'P' (texto): o "
"contexto decide.")
h2("Mini-glossario Z80")
mono("A=acumulador  B C D E H L=8 bits  BC DE HL=pares 16 bits  SP=pilha  PC=ponteiro\n"
"LD copia   JP/JR salta   CALL/RET sub-rotina   RST servico rapido\n"
"PUSH/POP pilha   IN/OUT portas de hardware   CP/AND/OR/XOR logica\n"
"DJNZ laco (B)   LDIR copia bloco   DI/EI interrupcoes   IM modo de IRQ",7.8)

# ---- MAPA DE MEMORIA ----
pdf.start_section("Mapa de memoria da ROM",0)
h1("Mapa de memoria da ROM")
mapa=[("0000-003F","Vetores RST + partida","CODIGO"),
("0040-012C","E/S, teclado, video, init","CODIGO"),
("0105/0111","'Mem. usada' / 'PROLOGICA 1981 BASIC'","DADOS"),
("012D-15FF","Nucleo do interpretador BASIC","CODIGO"),
("1625-178F","Tabela de palavras-chave","DADOS"),
("18C9-1940","Codigos de erro / READY / Break","DADOS"),
("1941-2FFF","Executores de comandos / tokenizador","CODIGO"),
("3044-3145","Tabelas de caracteres","DADOS"),
("31A5-3370","Rotinas de cassete (porta FFh)","CODIGO"),
("3455+","Cold start / inicializacao","CODIGO"),
("3739-3Cxx","Cassete / disquete (arquivos)","CODIGO"),
("3D00-3FFF","MONITOR versao 1.1 (1982)","COD+DADOS")]
pdf.set_font("Courier","",8.2)
pdf.multi_cell(0,4.6,S(f"{'FAIXA':<12}{'CONTEUDO':<36}TIPO"))
for f,c,t in mapa: pdf.multi_cell(0,4.6,S(f"{f:<12}{c:<36}{t}"))
pdf.ln(1)
para("A ROM mistura o BASIC (1981) com um MONITOR de linguagem de maquina (1982) "
"- por isso ha dois conjuntos de mensagens no mesmo chip.")
h2("Exemplo: decodificando bytes a mao  (F3 AF C3 15 30)")
mono("F3       -> DI      (1 byte)\nAF       -> XOR A   (1 byte)\n"
"C3 15 30 -> JP 3015H (3 bytes)  <- little-endian: '15 30' = endereco 3015h")

# ===========================================================================
# 6) LISTAGEM COMENTADA LINHA A LINHA (todo o codigo)
# ===========================================================================
mi=0
dumped=set()
i=0
N=len(FULL)
LH=3.1
while i<N:
    addr,raw,txt=FULL[i]
    # ---- emite marcadores de secao pendentes ----
    while mi<len(MARKERS) and addr>=MARKERS[mi][0]:
        ma,lvl,title=MARKERS[mi]
        if lvl==0:
            pdf.add_page()
            pdf.start_section(S(title),0)
            pdf.set_font("Helvetica","B",14); pdf.set_text_color(0,0,130)
            pdf.multi_cell(0,8,S(title)); pdf.set_text_color(0); pdf.ln(1)
        else:
            pdf.ln(1.5)
            pdf.start_section(S(title),1)
            pdf.set_font("Helvetica","B",10.5); pdf.set_text_color(30,30,30)
            pdf.multi_cell(0,5.6,S(">> "+title)); pdf.set_text_color(0); pdf.ln(0.4)
        mi+=1
    # ---- regiao de DADOS? ----
    d=data_at(addr)
    if d:
        s,e,desc=d
        if s not in dumped:
            dumped.add(s)
            pdf.set_font("Helvetica","I",8.5); pdf.set_text_color(110,60,0)
            pdf.multi_cell(0,4.4,S(f"[DADOS {s:04X}-{e-1:04X}] {desc}"))
            pdf.set_text_color(0)
            pdf.set_font("Courier","",7.6)
            row=[]; st=s
            for x in range(s,e):
                c=ROM[x]; row.append(chr(c) if 32<=c<127 else ".")
                if len(row)==32:
                    pdf.multi_cell(0,3.4,S(f"{st:04X}: {''.join(row)}")); row=[]; st=x+1
            if row: pdf.multi_cell(0,3.4,S(f"{st:04X}: {''.join(row)}"))
            pdf.ln(1)
        # avanca i ate sair da regiao de dados
        while i<N and FULL[i][0]<e: i+=1
        continue
    # ---- instrucao normal: linha + comentario ----
    cm=CMT.get(addr) or explain(txt)
    special=addr in CMT
    pdf.set_font("Courier","B" if special else "",7.0)
    pdf.multi_cell(0,LH,S(f"{addr:04X}  {raw:<11}  {txt}"))
    pdf.set_font("Courier","I",6.3)
    pdf.set_text_color(95,95,95) if not special else pdf.set_text_color(150,40,40)
    pdf.multi_cell(0,LH-0.2,S(f"        ; {cm}"))
    pdf.set_text_color(0)
    i+=1

out="ENGENHARIA_REVERSA_CP300.pdf"
pdf.output(out)
print("PDF gerado:", out)
