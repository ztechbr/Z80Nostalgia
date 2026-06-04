# -*- coding: utf-8 -*-
"""
CP-300 BASIC  -  reimplementacao em Python (SEM emulacao de CPU)
================================================================
Este programa NAO executa os bytes Z80 da ROM 27C128cp300.BIN. Em vez disso,
ele REIMPLEMENTA em Python o COMPORTAMENTO do firmware: a tela de abertura
(com as strings reais extraidas da ROM), o prompt READY, o editor de linhas e
um interpretador BASIC nivel-II compativel, com os comandos da tabela de
palavras-chave da ROM e os codigos de erro de 2 letras do TRS-80/CP-300.

Uso:   python cp300_basic.py
Saia:  digite  SYSTEM  ou  BYE  (ou Ctrl-C).

Exemplo de programa para testar:
   10 FOR I=1 TO 5
   20 PRINT I, I*I
   30 NEXT I
   40 PRINT "FIM"
   RUN
"""
import sys, os, math, random, re

# --------------------------------------------------------------------------
# Codigos de erro: as mesmas 2 letras gravadas na ROM (tabela em 18C9h).
# --------------------------------------------------------------------------
ERROS = {
 "NF":"NEXT sem FOR",        "SN":"erro de Sintaxe",     "RG":"RETURN sem GOSUB",
 "OD":"sem DATA (Out of Data)","FC":"argumento de Funcao","OV":"estouro (Overflow)",
 "OM":"sem Memoria",         "UL":"Linha inexistente",   "BS":"indice fora da faixa",
 "DD":"matriz Redimensionada","/0":"Divisao por zero",   "ID":"comando Direto ilegal",
 "TM":"Tipos incompativeis", "OS":"String sem espaco",   "LS":"String longa demais",
 "ST":"formula complexa",    "CN":"CONT impossivel",     "DL":"linha Duplicada",
}
class BasicError(Exception):
    def __init__(self, code): self.code = code

# --------------------------------------------------------------------------
# Terminal: limpar tela e imprimir (a ROM controla o video; aqui usamos o
# terminal do PC).
# --------------------------------------------------------------------------
def cls():
    os.system("cls" if os.name == "nt" else "clear")

def out(s="", end="\n"):
    sys.stdout.write(s + end); sys.stdout.flush()

# ==========================================================================
# ANALISADOR DE EXPRESSOES  (numeros, strings, variaveis, funcoes, operadores)
# ==========================================================================
TOKEN_RE = re.compile(r"""
   \s*(?:
     (?P<num>\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+)
   | (?P<str>"[^"]*")
   | (?P<op><=|>=|<>|[-+*/^()=<>,;:])
   | (?P<id>[A-Za-z][A-Za-z0-9]*\$?)
   )""", re.VERBOSE)

def lex(s):
    toks, i = [], 0
    while i < len(s):
        m = TOKEN_RE.match(s, i)
        if not m or m.end() == i:
            if s[i:].strip() == "": break
            raise BasicError("SN")
        i = m.end()
        if m.group("num"):   toks.append(("num", float(m.group("num"))))
        elif m.group("str"): toks.append(("str", m.group("str")[1:-1]))
        elif m.group("op"):  toks.append(("op", m.group("op")))
        elif m.group("id"):  toks.append(("id", m.group("id").upper()))
    toks.append(("eof", None))
    return toks

FUNCS1 = {"ABS","INT","SGN","SQR","SIN","COS","TAN","ATN","EXP","LOG","RND",
          "LEN","ASC","VAL","CHR$","STR$","INKEY$","TAB"}

class Expr:
    """Avaliador recursivo. Numeros sao float; strings sao str Python."""
    def __init__(self, interp, toks):
        self.it = interp; self.t = toks; self.p = 0
    def peek(self): return self.t[self.p]
    def take(self):
        tk = self.t[self.p]; self.p += 1; return tk
    def expect(self, val):
        if self.t[self.p] == ("op", val): self.p += 1
        else: raise BasicError("SN")

    def parse(self):
        v = self.p_or()
        return v
    # OR
    def p_or(self):
        v = self.p_and()
        while self.peek() == ("id","OR"):
            self.take(); r = self.p_and()
            v = float(self._int(v) | self._int(r))
        return v
    # AND
    def p_and(self):
        v = self.p_not()
        while self.peek() == ("id","AND"):
            self.take(); r = self.p_not()
            v = float(self._int(v) & self._int(r))
        return v
    def p_not(self):
        if self.peek() == ("id","NOT"):
            self.take(); r = self.p_not()
            return float(-(self._int(r) + 1))
        return self.p_rel()
    # relacionais  -> retorna -1 (verdadeiro) ou 0 (falso), como no BASIC
    def p_rel(self):
        v = self.p_add()
        while self.peek()[0]=="op" and self.peek()[1] in ("=","<>","<",">","<=",">="):
            op = self.take()[1]; r = self.p_add()
            if isinstance(v,str) or isinstance(r,str):
                a,b = str(v), str(r)
            else: a,b = v, r
            res = {"=":a==b,"<>":a!=b,"<":a<b,">":a>b,"<=":a<=b,">=":a>=b}[op]
            v = -1.0 if res else 0.0
        return v
    def p_add(self):
        v = self.p_mul()
        while self.peek()[0]=="op" and self.peek()[1] in ("+","-"):
            op = self.take()[1]; r = self.p_mul()
            if op=="+" and (isinstance(v,str) or isinstance(r,str)):
                if not (isinstance(v,str) and isinstance(r,str)): raise BasicError("TM")
                v = v + r
            else:
                self._num(v); self._num(r)
                v = v + r if op=="+" else v - r
        return v
    def p_mul(self):
        v = self.p_pow()
        while self.peek()[0]=="op" and self.peek()[1] in ("*","/"):
            op = self.take()[1]; r = self.p_pow()
            self._num(v); self._num(r)
            if op=="*": v = v * r
            else:
                if r == 0: raise BasicError("/0")
                v = v / r
        return v
    def p_pow(self):
        v = self.p_unary()
        if self.peek() == ("op","^"):
            self.take(); r = self.p_pow()
            self._num(v); self._num(r)
            try: v = float(v) ** float(r)
            except (ValueError, OverflowError): raise BasicError("FC")
        return v
    def p_unary(self):
        if self.peek() == ("op","-"):
            self.take(); return -self._asnum(self.p_unary())
        if self.peek() == ("op","+"):
            self.take(); return self.p_unary()
        return self.p_atom()
    def p_atom(self):
        tk = self.take()
        if tk[0]=="num": return tk[1]
        if tk[0]=="str": return tk[1]
        if tk[0]=="op" and tk[1]=="(":
            v = self.p_or(); self.expect(")"); return v
        if tk[0]=="id":
            name = tk[1]
            # funcoes com argumentos entre parenteses
            if name in FUNCS1 or name in ("LEFT$","RIGHT$","MID$","STRING$","INSTR","POINT","POS"):
                return self.call(name)
            # constantes/keywords sem valor de expressao -> erro de sintaxe
            if name in ("TO","STEP","THEN","ELSE"): raise BasicError("SN")
            # variavel (com indices = matriz)
            if self.peek() == ("op","("):
                self.take(); idx=[int(self._asnum(self.p_or()))]
                while self.peek()==("op",","):
                    self.take(); idx.append(int(self._asnum(self.p_or())))
                self.expect(")")
                return self.it.get_array(name, idx)
            return self.it.get_var(name)
        raise BasicError("SN")

    def args(self, n_min, n_max=None):
        self.expect("(")
        a=[self.p_or()]
        while self.peek()==("op",","):
            self.take(); a.append(self.p_or())
        self.expect(")")
        if len(a) < n_min or (n_max and len(a) > n_max): raise BasicError("FC")
        return a
    def call(self, f):
        if f in ("LEFT$","RIGHT$"):
            a=self.args(2,2); s=self._asstr(a[0]); n=int(self._asnum(a[1]))
            if n<0: raise BasicError("FC")
            return s[:n] if f=="LEFT$" else (s[-n:] if n else "")
        if f=="MID$":
            a=self.args(2,3); s=self._asstr(a[0]); start=int(self._asnum(a[1]))
            if start<1: raise BasicError("FC")
            ln=int(self._asnum(a[2])) if len(a)==3 else len(s)
            return s[start-1:start-1+ln]
        if f=="STRING$":
            a=self.args(2,2); n=int(self._asnum(a[0]))
            ch=a[1]; ch=chr(int(ch)) if not isinstance(ch,str) else ch[:1]
            return ch*max(0,n)
        if f=="INSTR":
            a=self.args(2,3)
            if len(a)==3: start=int(self._asnum(a[0])); s=self._asstr(a[1]); sub=self._asstr(a[2])
            else: start=1; s=self._asstr(a[0]); sub=self._asstr(a[1])
            return float(s.find(sub,start-1)+1)
        # funcoes numericas/string de 1 argumento
        a=self.args(1,1); x=a[0]
        if f=="ABS": return abs(self._asnum(x))
        if f=="INT": return float(math.floor(self._asnum(x)))
        if f=="SGN": v=self._asnum(x); return float((v>0)-(v<0))
        if f=="SQR":
            v=self._asnum(x)
            if v<0: raise BasicError("FC")
            return math.sqrt(v)
        if f=="SIN": return math.sin(self._asnum(x))
        if f=="COS": return math.cos(self._asnum(x))
        if f=="TAN": return math.tan(self._asnum(x))
        if f=="ATN": return math.atan(self._asnum(x))
        if f=="EXP":
            try: return math.exp(self._asnum(x))
            except OverflowError: raise BasicError("OV")
        if f=="LOG":
            v=self._asnum(x)
            if v<=0: raise BasicError("FC")
            return math.log(v)
        if f=="RND":
            n=self._asnum(x)
            if n==0: return self.it.last_rnd
            self.it.last_rnd = float(random.randint(1,max(1,int(n))))
            return self.it.last_rnd
        if f=="LEN": return float(len(self._asstr(x)))
        if f=="ASC":
            s=self._asstr(x)
            if not s: raise BasicError("FC")
            return float(ord(s[0]))
        if f=="CHR$": return chr(int(self._asnum(x)) & 0xFF)
        if f=="STR$": return fmt_num(self._asnum(x))
        if f=="VAL":
            s=self._asstr(x).strip()
            m=re.match(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
            return float(m.group()) if m else 0.0
        if f=="TAB": return ("\tTAB", int(self._asnum(x)))   # tratado no PRINT
        if f=="INKEY$": return self.it.inkey()
        raise BasicError("SN")

    # ---- conferencias de tipo ----
    def _num(self,v):
        if isinstance(v,str): raise BasicError("TM")
    def _asnum(self,v):
        if isinstance(v,str): raise BasicError("TM")
        return float(v)
    def _asstr(self,v):
        if not isinstance(v,str): raise BasicError("TM")
        return v
    def _int(self,v):
        return int(self._asnum(v)) & 0xFFFF if v>=0 else int(self._asnum(v))

# --------------------------------------------------------------------------
# Formatacao de numeros igual ao BASIC: inteiro sem ponto; espaco a esquerda
# em positivos; ~6 digitos significativos.
# --------------------------------------------------------------------------
def fmt_num(v):
    if v == int(v) and abs(v) < 1e15:
        s = str(int(v))
    else:
        s = f"{v:.6g}"
    return (" " + s) if v >= 0 else s

# ==========================================================================
# O INTERPRETADOR
# ==========================================================================
class CP300:
    def __init__(self):
        self.prog = {}          # numero_linha -> texto da linha
        self.order = []         # numeros ordenados
        self.vars = {}          # variaveis escalares
        self.arrays = {}        # matrizes: nome -> (dims, lista)
        self.last_rnd = random.random()
        self.reset_run()

    def reset_run(self):
        self.gosub = []         # pilha de GOSUB -> (li, si)
        self.fors = {}          # FOR ativos: var -> (end, step, li, si)
        self.for_order = []
        self.data = []; self.dptr = 0
        self.pc = None          # (indice_de_linha, indice_de_instrucao)

    # ---- gerencia de variaveis ----
    def get_var(self, name):
        if name.endswith("$"): return self.vars.get(name, "")
        return self.vars.get(name, 0.0)
    def set_var(self, name, value):
        if name.endswith("$"):
            if not isinstance(value,str): raise BasicError("TM")
        else:
            if isinstance(value,str): raise BasicError("TM")
            value=float(value)
        self.vars[name]=value
    def dim(self, name, dims):
        size=1; sizes=[d+1 for d in dims]
        for s in sizes: size*=s
        fill = "" if name.endswith("$") else 0.0
        self.arrays[name]=(sizes,[fill]*size)
    def _flat(self, sizes, idx):
        if len(idx)!=len(sizes): raise BasicError("BS")
        off=0
        for i,s in zip(idx,sizes):
            if i<0 or i>=s: raise BasicError("BS")
            off=off*s+i
        return off
    def get_array(self, name, idx):
        if name not in self.arrays: self.dim(name,[10]*len(idx))
        sizes,buf=self.arrays[name]; return buf[self._flat(sizes,idx)]
    def set_array(self, name, idx, value):
        if name not in self.arrays: self.dim(name,[10]*len(idx))
        sizes,buf=self.arrays[name]
        if name.endswith("$") and not isinstance(value,str): raise BasicError("TM")
        if not name.endswith("$") and isinstance(value,str): raise BasicError("TM")
        buf[self._flat(sizes,idx)]=value

    def inkey(self):
        return ""   # sem leitura nao-bloqueante portavel; INKEY$ devolve vazio

    # ---- edicao do programa ----
    def store_line(self, num, text):
        if text.strip()=="":
            self.prog.pop(num, None)
        else:
            self.prog[num]=text
        self.order=sorted(self.prog)

    def list_prog(self, lo=None, hi=None):
        for n in self.order:
            if (lo is None or n>=lo) and (hi is None or n<=hi):
                out(f"{n} {self.prog[n]}")

    # ---- coleta de DATA antes de rodar ----
    def collect_data(self):
        self.data=[]
        for n in self.order:
            for st in split_stmts(self.prog[n]):
                s=st.strip()
                if s.upper().startswith("DATA"):
                    payload=s[4:].strip()
                    for item in split_top(payload, ","):
                        item=item.strip()
                        if item.startswith('"') and item.endswith('"'):
                            self.data.append(item[1:-1])
                        else:
                            try: self.data.append(float(item))
                            except ValueError: self.data.append(item)
        self.dptr=0

    # ---- execucao do programa ----
    def run(self, start=None):
        self.vars.clear(); self.arrays.clear()
        self.reset_run()
        self.collect_data()
        if not self.order: return
        li = 0
        if start is not None:
            if start not in self.prog: raise BasicError("UL")
            li = self.order.index(start)
        self.pc=[li,0]
        self.execute()

    def execute(self):
        while self.pc is not None:
            li, si = self.pc
            if li >= len(self.order):
                self.pc=None; break
            line_no = self.order[li]
            stmts = split_stmts(self.prog[line_no])
            if si >= len(stmts):
                self.pc=[li+1, 0]; continue
            self.cur_line = line_no
            action = self.exec_stmt(stmts[si])
            if action is None:
                self.pc=[li, si+1]
            # se exec_stmt mexeu em self.pc (GOTO/GOSUB/NEXT), ele ja ajustou.

    def goto_line(self, n):
        if n not in self.prog: raise BasicError("UL")
        self.pc=[self.order.index(n), 0]; return "jumped"

    # ---- execucao de UMA instrucao ----
    def exec_stmt(self, stmt):
        s=stmt.strip()
        if s=="": return None
        up=s.upper()
        # comando = primeira palavra
        m=re.match(r"[A-Z][A-Z]*\$?", up)
        kw = m.group() if m else ""
        rest = s[m.end():].strip() if m else s

        if kw in ("REM",) or s.startswith("'"): return None
        if kw=="END" or kw=="STOP":
            self.pc=None; return "stop"
        if kw=="PRINT" or kw=="?":
            self.do_print(s[m.end():] if kw=="PRINT" else s[1:]); return None
        if kw=="LET":
            self.do_assign(rest); return None
        if kw=="INPUT":
            self.do_input(rest); return None
        if kw=="GOTO":
            return self.goto_line(int(self.num(rest)))
        if kw=="GOSUB":
            li,si=self.pc; self.gosub.append([li,si+1])
            return self.goto_line(int(self.num(rest)))
        if kw=="RETURN":
            if not self.gosub: raise BasicError("RG")
            self.pc=self.gosub.pop(); return "jumped"
        if kw=="IF":
            return self.do_if(rest)
        if kw=="FOR":
            return self.do_for(rest)
        if kw=="NEXT":
            return self.do_next(rest)
        if kw=="ON":
            return self.do_on(rest)
        if kw=="DIM":
            self.do_dim(rest); return None
        if kw=="READ":
            self.do_read(rest); return None
        if kw=="DATA":
            return None
        if kw=="RESTORE":
            self.dptr=0; return None
        if kw=="CLS":
            cls(); return None
        if kw=="CLEAR":
            self.vars.clear(); self.arrays.clear(); return None
        if kw=="RUN":
            n=int(self.num(rest)) if rest.strip() else None
            self.run(n); self.pc=None; return "stop"
        if kw=="END": self.pc=None; return "stop"
        # atribuicao implicita:  X=...   ou  A$="..."
        if "=" in s and (m and (s[m.end():].lstrip().startswith("=") or
                                 re.match(r"[A-Z][A-Z0-9]*\$?\s*(\(|=)", up))):
            self.do_assign(s); return None
        raise BasicError("SN")

    # ---- avaliacao de expressao a partir de texto ----
    def eval(self, text):
        e=Expr(self, lex(text)); v=e.parse()
        if e.peek()[0]!="eof": raise BasicError("SN")
        return v
    def num(self, text):
        v=self.eval(text)
        if isinstance(v,str): raise BasicError("TM")
        return v
    def eval_prefix(self, toks_text):
        """avalia o inicio de uma expressao e devolve (valor, resto_texto)."""
        toks=lex(toks_text); e=Expr(self,toks); v=e.parse()
        # reconstroi o texto restante a partir do indice
        return v, e, toks

    # ---- PRINT ----
    def do_print(self, arg):
        arg=arg.strip()
        if arg=="":
            out(); return
        nonl = arg.endswith(";")
        line=""
        col=0
        for piece, sep in split_print(arg):
            piece=piece.strip()
            if piece=="":
                pass
            else:
                v=self.eval(piece)
                if isinstance(v,tuple) and v and v[0]=="\tTAB":
                    target=v[1]-1
                    if target>len(line): line+=" "*(target-len(line))
                    sep=""  # TAB nao adiciona separador
                    continue
                line += v if isinstance(v,str) else (fmt_num(v)+" ")
            if sep==",":
                # zona de 16 colunas
                nxt=(len(line)//16 +1)*16
                line += " "*(nxt-len(line))
        out(line, end="" if nonl else "\n")

    # ---- atribuicao ----
    def do_assign(self, s):
        if s.upper().startswith("LET"): s=s[3:]
        # nome [ (idx) ] = expr
        m=re.match(r"\s*([A-Za-z][A-Za-z0-9]*\$?)\s*(\(.*?\))?\s*=", s)
        if not m: raise BasicError("SN")
        name=m.group(1).upper(); idxpart=m.group(2); rhs=s[m.end():]
        val=self.eval(rhs)
        if idxpart:
            idx=[int(self.num(x)) for x in split_top(idxpart[1:-1],",")]
            self.set_array(name, idx, val)
        else:
            self.set_var(name, val)

    # ---- INPUT ----
    def do_input(self, rest):
        prompt="? "
        m=re.match(r'\s*"([^"]*)"\s*;?\s*', rest)
        if m: prompt=m.group(1)+"? "; rest=rest[m.end():]
        varnames=[v.strip().upper() for v in split_top(rest,",") if v.strip()]
        try:
            data=input(prompt)
        except EOFError:
            data=""
        vals=split_top(data,",")
        for i,vn in enumerate(varnames):
            raw = vals[i].strip() if i<len(vals) else ""
            if vn.endswith("$"):
                self.set_var(vn, raw)
            else:
                try: self.set_var(vn, float(raw) if raw else 0.0)
                except ValueError: raise BasicError("SN")

    # ---- IF ----
    def do_if(self, rest):
        up=rest.upper()
        i=up.find("THEN")
        if i<0:
            # IF cond GOTO n   (forma sem THEN)
            g=up.find("GOTO")
            if g<0: raise BasicError("SN")
            cond=rest[:g]; thenpart="GOTO"+rest[g+4:]; elsepart=None
        else:
            cond=rest[:i]; after=rest[i+4:]
            eidx=split_else(after)
            if eidx is None: thenpart=after; elsepart=None
            else: thenpart=after[:eidx]; elsepart=after[eidx+4:]
        if self.truth(cond):
            return self.run_clause(thenpart)
        elif elsepart is not None:
            return self.run_clause(elsepart)
        return None
    def truth(self, cond):
        v=self.eval(cond)
        if isinstance(v,str): raise BasicError("TM")
        return v!=0
    def run_clause(self, clause):
        clause=clause.strip()
        if re.fullmatch(r"\d+", clause):          # THEN <linha>
            return self.goto_line(int(clause))
        # executa as instrucoes da clausula
        for st in split_stmts(clause):
            a=self.exec_stmt(st)
            if a in ("jumped","stop"): return a
        return None

    # ---- FOR / NEXT ----
    def do_for(self, rest):
        m=re.match(r"\s*([A-Za-z][A-Za-z0-9]*)\s*=", rest)
        if not m: raise BasicError("SN")
        var=m.group(1).upper(); body=rest[m.end():]
        up=body.upper(); ti=up.find("TO")
        if ti<0: raise BasicError("SN")
        start=self.num(body[:ti]); after=body[ti+2:]
        up2=after.upper(); si=up2.find("STEP")
        if si<0: end=self.num(after); step=1.0
        else: end=self.num(after[:si]); step=self.num(after[si+4:])
        self.set_var(var, start)
        li,sidx=self.pc
        if var in self.fors: self.for_order.remove(var)
        self.fors[var]=(end,step,li,sidx+1)
        self.for_order.append(var)
        # se o laco ja deveria terminar de cara
        if (step>=0 and start>end) or (step<0 and start<end):
            self.skip_for(var); return "jumped"
        return None
    def skip_for(self, var):
        """avanca pc para depois do NEXT correspondente."""
        li,si=self.pc
        depth=0
        idx=li
        while idx<len(self.order):
            stmts=split_stmts(self.prog[self.order[idx]])
            start_s = si if idx==li else 0
            for j in range(start_s,len(stmts)):
                u=stmts[j].strip().upper()
                if u.startswith("FOR"): depth+=1
                elif u.startswith("NEXT"):
                    if depth==0:
                        self.fors.pop(var,None)
                        if var in self.for_order: self.for_order.remove(var)
                        self.pc=[idx, j+1]; return
                    depth-=1
            idx+=1
        self.pc=None
    def do_next(self, rest):
        names=[v.strip().upper() for v in rest.split(",") if v.strip()]
        var = names[0] if names else (self.for_order[-1] if self.for_order else None)
        if var is None or var not in self.fors: raise BasicError("NF")
        end,step,li,sidx=self.fors[var]
        nv=self.get_var(var)+step
        self.set_var(var,nv)
        if (step>=0 and nv<=end) or (step<0 and nv>=end):
            self.pc=[li,sidx]; return "jumped"
        else:
            self.fors.pop(var,None); self.for_order.remove(var)
            return None

    # ---- ON x GOTO/GOSUB ----
    def do_on(self, rest):
        up=rest.upper()
        for kwd in ("GOSUB","GOTO"):
            i=up.find(kwd)
            if i>=0:
                sel=int(self.num(rest[:i]))
                targets=[int(t) for t in split_top(rest[i+len(kwd):],",")]
                if 1<=sel<=len(targets):
                    n=targets[sel-1]
                    if kwd=="GOSUB":
                        li,si=self.pc; self.gosub.append([li,si+1])
                    return self.goto_line(n)
                return None
        raise BasicError("SN")

    # ---- DIM ----
    def do_dim(self, rest):
        for decl in split_top(rest,","):
            m=re.match(r"\s*([A-Za-z][A-Za-z0-9]*\$?)\s*\((.*)\)\s*$", decl)
            if not m: raise BasicError("SN")
            name=m.group(1).upper()
            dims=[int(self.num(x)) for x in split_top(m.group(2),",")]
            self.dim(name, dims)

    # ---- READ ----
    def do_read(self, rest):
        for vn in split_top(rest,","):
            vn=vn.strip().upper()
            if self.dptr>=len(self.data): raise BasicError("OD")
            val=self.data[self.dptr]; self.dptr+=1
            m=re.match(r"([A-Za-z][A-Za-z0-9]*\$?)\s*(\((.*)\))?$", vn)
            if not m: raise BasicError("SN")
            name=m.group(1)
            if m.group(3) is not None:
                idx=[int(self.num(x)) for x in split_top(m.group(3),",")]
                self.set_array(name, idx, val if (name.endswith("$")==isinstance(val,str)) else self._coerce(name,val))
            else:
                self.set_var(name, self._coerce(name,val))
    def _coerce(self,name,val):
        if name.endswith("$"): return val if isinstance(val,str) else fmt_num(val).strip()
        if isinstance(val,str):
            try: return float(val)
            except ValueError: raise BasicError("SN")
        return val

# --------------------------------------------------------------------------
# Utilidades de separacao de texto respeitando aspas e parenteses
# --------------------------------------------------------------------------
def split_top(s, sep):
    parts=[]; depth=0; q=False; cur=""
    for ch in s:
        if ch=='"': q=not q
        if not q and ch=="(": depth+=1
        if not q and ch==")": depth-=1
        if ch==sep and depth==0 and not q:
            parts.append(cur); cur=""
        else: cur+=ch
    parts.append(cur); return parts

def split_stmts(line):
    return split_top(line, ":")

def split_print(arg):
    """devolve lista de (pedaco, separador) onde separador e ';' ',' ou ''."""
    items=[]; depth=0; q=False; cur=""
    i=0
    while i<len(arg):
        ch=arg[i]
        if ch=='"': q=not q
        if not q and ch=="(": depth+=1
        if not q and ch==")": depth-=1
        if not q and depth==0 and ch in ";,":
            items.append((cur, ch)); cur=""
        else:
            cur+=ch
        i+=1
    items.append((cur, ""))
    return items

def split_else(after):
    up=after.upper(); depth=0; q=False
    i=0
    while i<len(after):
        ch=after[i]
        if ch=='"': q=not q
        if not q and up[i:i+4]=="ELSE": return i
        i+=1
    return None

# ==========================================================================
# TELA DE ABERTURA (strings reais da ROM) + LACO PRINCIPAL (READY)
# ==========================================================================
BANNER_MEM   = "Mem. usada"
BANNER_TITLE = "PROLOGICA  1981  BASIC"

def boot():
    cls()
    free = 47104   # numero ilustrativo de bytes livres
    out()
    out(f"{BANNER_MEM} {free}")
    out(BANNER_TITLE)
    out()
    out("READY")

def repl():
    it = CP300()
    boot()
    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            out("\nReady"); break
        if line.strip()=="":
            continue
        cmd = line.strip()
        upc = cmd.upper()
        # ---- comandos diretos especiais ----
        if upc in ("SYSTEM","BYE","MON","MONITOR"):
            out("Saindo do BASIC."); break
        if upc=="NEW":
            it.prog.clear(); it.order=[]; it.vars.clear(); it.arrays.clear(); continue
        # ---- linha que comeca por numero: edita o programa ----
        m=re.match(r"\s*(\d+)\s?(.*)$", line)
        if m:
            num=int(m.group(1)); txt=m.group(2)
            it.store_line(num, txt)
            continue
        # ---- comando direto (modo imediato) ----
        try:
            if upc=="RUN" or upc.startswith("RUN "):
                start=int(cmd[3:]) if cmd[3:].strip() else None
                it.run(start); out("READY")
            elif upc=="LIST" or upc.startswith("LIST"):
                arg=cmd[4:].strip()
                lo=hi=None
                if arg:
                    if "-" in arg:
                        a,b=arg.split("-",1); lo=int(a) if a.strip() else None; hi=int(b) if b.strip() else None
                    else: lo=hi=int(arg)
                it.list_prog(lo,hi)
            elif upc=="CONT":
                out("?CN Erro")
            else:
                # executa instrucao(oes) em modo imediato
                it.reset_run()
                for st in split_stmts(cmd):
                    a=it.exec_stmt(st)
                    if a=="stop": break
        except BasicError as e:
            naliha = ""
            if it.pc is not None and getattr(it,"cur_line",None) is not None:
                naliha=f" na {it.cur_line}"
            out(f"?{e.code} Erro{naliha}")
            it.pc=None
        except KeyboardInterrupt:
            out("\nBreak"); it.pc=None
        except RecursionError:
            out("?ST Erro"); it.pc=None

if __name__ == "__main__":
    repl()
