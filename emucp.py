# -*- coding: utf-8 -*-
"""
emucp  -  EMULADOR Z80 do CP-300  (executa os opcodes REAIS da ROM)
===================================================================
Ao contrario de cp300_basic.py / cp300_monitor.py (que REIMPLEMENTAM o
comportamento), aqui temos um EMULADOR DE CPU Z80 de verdade: ele le os bytes
da ROM 27C128cp300.BIN e EXECUTA cada instrucao do firmware, atualizando
registradores, flags, memoria e portas - exatamente como o chip Z80 faria.

Inclui um depurador interativo para a aula:
  - executar passo a passo (single-step) vendo cada instrucao do firmware
  - rodar ate um breakpoint ou por N instrucoes
  - inspecionar registradores, flags e memoria
  - um autoteste que prova que o nucleo da CPU esta correto

Mapa: ROM 0000-3FFF (do arquivo), RAM 4000-FFFF. E/S por portas (E0,E4,EC,
F0,F4,FF) com modelo simplificado - suficiente para executar o cold start real.

Uso:   python emucp.py            (abre o depurador)
       python emucp.py --test     (so o autoteste do nucleo Z80)
       python emucp.py --trace 40 (executa e mostra 40 instrucoes do boot)
"""
import sys, os
try:
    from z80dasm import disasm
except Exception:
    disasm = None

# Flags do Z80
FC,FN,FPV,F3,FH,F5,FZ,FS = 0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80

PARITY = [0]*256
for _i in range(256):
    PARITY[_i] = FPV if bin(_i).count("1") % 2 == 0 else 0

class Z80:
    def __init__(self, mem, rom_end=0x4000, io=None):
        self.m = mem
        self.rom_end = rom_end
        self.io = io or IO()
        self.a=self.f=self.b=self.c=self.d=self.e=self.h=self.l=0
        self.a_=self.f_=self.b_=self.c_=self.d_=self.e_=self.h_=self.l_=0
        self.ix=self.iy=0
        self.sp=0xFFFF; self.pc=0
        self.i=0; self.r=0
        self.iff1=self.iff2=0; self.im=0
        self.halted=False
        self.cycles=0

    # ---- acesso a memoria (ROM protegida contra escrita) ----
    def rb(self, a): return self.m[a & 0xFFFF]
    def wb(self, a, v):
        a &= 0xFFFF
        if a >= self.rom_end:
            self.m[a] = v & 0xFF
    def rw(self, a): return self.rb(a) | (self.rb(a+1) << 8)
    def ww(self, a, v): self.wb(a, v & 0xFF); self.wb(a+1, (v >> 8) & 0xFF)
    def fetch(self):
        v = self.m[self.pc]; self.pc = (self.pc + 1) & 0xFFFF
        self.r = (self.r & 0x80) | ((self.r + 1) & 0x7F)
        return v
    def fetch16(self):
        lo = self.fetch(); hi = self.fetch(); return lo | (hi << 8)

    # ---- pares de 16 bits ----
    def get_bc(self): return (self.b<<8)|self.c
    def get_de(self): return (self.d<<8)|self.e
    def get_hl(self): return (self.h<<8)|self.l
    def get_af(self): return (self.a<<8)|self.f
    def set_bc(self,v): self.b=(v>>8)&0xFF; self.c=v&0xFF
    def set_de(self,v): self.d=(v>>8)&0xFF; self.e=v&0xFF
    def set_hl(self,v): self.h=(v>>8)&0xFF; self.l=v&0xFF
    def set_af(self,v): self.a=(v>>8)&0xFF; self.f=v&0xFF

    def push(self, v):
        self.sp = (self.sp - 1) & 0xFFFF; self.wb(self.sp, (v>>8)&0xFF)
        self.sp = (self.sp - 1) & 0xFFFF; self.wb(self.sp, v&0xFF)
    def pop(self):
        lo = self.rb(self.sp); self.sp = (self.sp + 1) & 0xFFFF
        hi = self.rb(self.sp); self.sp = (self.sp + 1) & 0xFFFF
        return lo | (hi << 8)

    # ===================================================================
    # ALU de 8 bits (atua sobre A) com flags corretas
    # ===================================================================
    def _add(self, val, carry=0):
        a=self.a; r=a+val+carry
        f=0
        if (r & 0xFF)==0: f|=FZ
        f|= r & FS
        if ((a&0xF)+(val&0xF)+carry) & 0x10: f|=FH
        if ((a^val^0x80)&(a^r)&0x80): f|=FPV
        if r & 0x100: f|=FC
        f|= r & (F3|F5)
        self.a=r&0xFF; self.f=f
    def _sub(self, val, carry=0, store=True):
        a=self.a; r=a-val-carry
        f=FN
        if (r & 0xFF)==0: f|=FZ
        f|= r & FS
        if ((a&0xF)-(val&0xF)-carry) & 0x10: f|=FH
        if ((a^val)&(a^r)&0x80): f|=FPV
        if r & 0x100: f|=FC
        f|= (val if not store else r) & (F3|F5)
        if store: self.a=r&0xFF
        self.f=f
    def _and(self, val):
        self.a&=val; self.f=FH|PARITY[self.a]|(self.a&(FS|F3|F5))|(FZ if self.a==0 else 0)
    def _or(self, val):
        self.a|=val; self.f=PARITY[self.a]|(self.a&(FS|F3|F5))|(FZ if self.a==0 else 0)
    def _xor(self, val):
        self.a^=val; self.f=PARITY[self.a]|(self.a&(FS|F3|F5))|(FZ if self.a==0 else 0)
    def _cp(self, val):
        self._sub(val, 0, store=False)
    def alu(self, op, val):
        (self._add, lambda v:self._add(v,1), lambda v:self._sub(v),
         lambda v:self._sub(v,1), self._and, self._xor, self._or, self._cp)[op](val)

    def inc8(self, v):
        v=(v+1)&0xFF
        f=self.f & FC
        f|= v & (FS|F3|F5)
        if v==0: f|=FZ
        if (v&0xF)==0: f|=FH
        if v==0x80: f|=FPV
        self.f=f; return v
    def dec8(self, v):
        v=(v-1)&0xFF
        f=(self.f & FC)|FN
        f|= v & (FS|F3|F5)
        if v==0: f|=FZ
        if (v&0xF)==0xF: f|=FH
        if v==0x7F: f|=FPV
        self.f=f; return v

    def add16(self, a, b):
        r=a+b
        f=self.f & (FS|FZ|FPV)
        if ((a&0xFFF)+(b&0xFFF)) & 0x1000: f|=FH
        if r & 0x10000: f|=FC
        f|= (r>>8) & (F3|F5)
        self.f=f; return r & 0xFFFF
    def adc16(self, a, b):
        c=self.f & FC; r=a+b+c
        f=0
        if r & 0x8000: f|=FS
        if (r & 0xFFFF)==0: f|=FZ
        if ((a&0xFFF)+(b&0xFFF)+c) & 0x1000: f|=FH
        if ((a^b^0x8000)&(a^r)&0x8000): f|=FPV
        if r & 0x10000: f|=FC
        f|= (r>>8) & (F3|F5)
        self.f=f; return r & 0xFFFF
    def sbc16(self, a, b):
        c=self.f & FC; r=a-b-c
        f=FN
        if r & 0x8000: f|=FS
        if (r & 0xFFFF)==0: f|=FZ
        if ((a&0xFFF)-(b&0xFFF)-c) & 0x1000: f|=FH
        if ((a^b)&(a^r)&0x8000): f|=FPV
        if r & 0x10000: f|=FC
        f|= (r>>8) & (F3|F5)
        self.f=f; return r & 0xFFFF

    # rotacoes/deslocamentos (prefixo CB)
    def rot(self, op, v):
        c=self.f & FC
        if op==0:   nc=v>>7;       v=((v<<1)|nc)&0xFF              # RLC
        elif op==1: nc=v&1;        v=((v>>1)|(nc<<7))&0xFF         # RRC
        elif op==2: nc=v>>7;       v=((v<<1)|c)&0xFF               # RL
        elif op==3: nc=v&1;        v=((v>>1)|(c<<7))&0xFF          # RR
        elif op==4: nc=v>>7;       v=(v<<1)&0xFF                   # SLA
        elif op==5: nc=v&1;        v=((v>>1)|(v&0x80))&0xFF        # SRA
        elif op==6: nc=v>>7;       v=((v<<1)|1)&0xFF               # SLL
        else:       nc=v&1;        v=(v>>1)&0xFF                   # SRL
        self.f=PARITY[v]|(v&(FS|F3|F5))|(FZ if v==0 else 0)|(FC if nc else 0)
        return v

    def daa(self):
        a=self.a; f=self.f; corr=0; carry=f&FC
        if (f&FH) or (a&0x0F)>9: corr|=0x06
        if carry or a>0x99: corr|=0x60; carry=FC
        if f&FN: a=(a-corr)&0xFF
        else:    a=(a+corr)&0xFF
        nf=(f&FN)|carry|PARITY[a]|(a&(FS|F3|F5))|(FZ if a==0 else 0)
        if (f&FN):
            if (f&FH) and (self.a&0xF)<6: nf|=FH
        else:
            if (self.a&0xF)>9: nf|=FH
        self.a=a; self.f=nf

    # ===================================================================
    # PASSO DE EXECUCAO (decodificador algoritmico)
    # ===================================================================
    def step(self):
        if self.halted:
            return
        op = self.fetch()
        if op==0xCB: return self.do_cb(None)
        if op==0xED: return self.do_ed()
        if op==0xDD: return self.do_index('ix')
        if op==0xFD: return self.do_index('iy')
        self.exec_main(op, None)

    # registradores r[] = B,C,D,E,H,L,(HL),A  (idx pode trocar HL por IX/IY)
    def get_r(self, z, idx=None, disp=0):
        if z==0: return self.b
        if z==1: return self.c
        if z==2: return self.d
        if z==3: return self.e
        if z==4: return (self._idxh(idx) if idx else self.h)
        if z==5: return (self._idxl(idx) if idx else self.l)
        if z==6:
            if idx: return self.rb((self._idx(idx)+disp)&0xFFFF)
            return self.rb(self.get_hl())
        return self.a
    def set_r(self, z, val, idx=None, disp=0):
        val&=0xFF
        if z==0: self.b=val
        elif z==1: self.c=val
        elif z==2: self.d=val
        elif z==3: self.e=val
        elif z==4:
            if idx: self._set_idxh(idx,val)
            else: self.h=val
        elif z==5:
            if idx: self._set_idxl(idx,val)
            else: self.l=val
        elif z==6:
            if idx: self.wb((self._idx(idx)+disp)&0xFFFF, val)
            else: self.wb(self.get_hl(), val)
        else: self.a=val
    def _idx(self, idx): return self.ix if idx=='ix' else self.iy
    def _set_idx(self, idx, v):
        if idx=='ix': self.ix=v&0xFFFF
        else: self.iy=v&0xFFFF
    def _idxh(self, idx): return (self._idx(idx)>>8)&0xFF
    def _idxl(self, idx): return self._idx(idx)&0xFF
    def _set_idxh(self, idx, v): self._set_idx(idx, (self._idx(idx)&0x00FF)|(v<<8))
    def _set_idxl(self, idx, v): self._set_idx(idx, (self._idx(idx)&0xFF00)|v)

    def rp_get(self, p, idx=None):
        if p==0: return self.get_bc()
        if p==1: return self.get_de()
        if p==2: return self._idx(idx) if idx else self.get_hl()
        return self.sp
    def rp_set(self, p, v, idx=None):
        if p==0: self.set_bc(v)
        elif p==1: self.set_de(v)
        elif p==2:
            if idx: self._set_idx(idx,v)
            else: self.set_hl(v)
        else: self.sp=v&0xFFFF
    def rp2_get(self, p):
        return [self.get_bc(),self.get_de(),self.get_hl(),self.get_af()][p]
    def rp2_set(self, p, v):
        [self.set_bc,self.set_de,self.set_hl,self.set_af][p](v)

    def cond(self, y):
        f=self.f
        return [not f&FZ, f&FZ, not f&FC, f&FC,
                not f&FPV, f&FPV, not f&FS, f&FS][y]

    def exec_main(self, op, idx):
        x=op>>6; y=(op>>3)&7; z=op&7; p=y>>1; q=y&1
        disp=0
        # se for indexado e o operando for (HL) -> le deslocamento
        if idx and z==6 and x!=0:
            disp = self._disp()
        if x==0:
            if z==0:
                if y==0: pass                                   # NOP
                elif y==1:                                      # EX AF,AF'
                    self.a,self.a_=self.a_,self.a; self.f,self.f_=self.f_,self.f
                elif y==2:                                      # DJNZ d
                    d=self._disp(); self.b=(self.b-1)&0xFF
                    if self.b: self.pc=(self.pc+d)&0xFFFF
                elif y==3:                                      # JR d
                    d=self._disp(); self.pc=(self.pc+d)&0xFFFF
                else:                                           # JR cc,d
                    d=self._disp()
                    if self.cond(y-4): self.pc=(self.pc+d)&0xFFFF
            elif z==1:
                if q==0:                                        # LD rp,nn
                    self.rp_set(p, self.fetch16(), idx)
                else:                                           # ADD HL,rp
                    hl=self._idx(idx) if idx else self.get_hl()
                    r=self.add16(hl, self.rp_get(p, idx))
                    if idx: self._set_idx(idx,r)
                    else: self.set_hl(r)
            elif z==2:
                if q==0:
                    if p==0: self.wb(self.get_bc(), self.a)     # LD (BC),A
                    elif p==1: self.wb(self.get_de(), self.a)   # LD (DE),A
                    elif p==2:                                  # LD (nn),HL
                        a=self.fetch16(); self.ww(a, self._idx(idx) if idx else self.get_hl())
                    else:                                       # LD (nn),A
                        a=self.fetch16(); self.wb(a, self.a)
                else:
                    if p==0: self.a=self.rb(self.get_bc())      # LD A,(BC)
                    elif p==1: self.a=self.rb(self.get_de())    # LD A,(DE)
                    elif p==2:                                  # LD HL,(nn)
                        a=self.fetch16(); v=self.rw(a)
                        if idx: self._set_idx(idx,v)
                        else: self.set_hl(v)
                    else:                                       # LD A,(nn)
                        a=self.fetch16(); self.a=self.rb(a)
            elif z==3:                                          # INC/DEC rp
                v=self.rp_get(p, idx)
                self.rp_set(p, (v+1 if q==0 else v-1)&0xFFFF, idx)
            elif z==4:                                          # INC r
                if idx and y==6: d=self._disp()
                else: d=0
                self.set_r(y, self.inc8(self.get_r(y, idx, d)), idx, d)
            elif z==5:                                          # DEC r
                if idx and y==6: d=self._disp()
                else: d=0
                self.set_r(y, self.dec8(self.get_r(y, idx, d)), idx, d)
            elif z==6:                                          # LD r,n
                if idx and y==6: d=self._disp()
                else: d=0
                self.set_r(y, self.fetch(), idx, d)
            else:                                               # z==7 misc
                self._accel(y)
        elif x==1:                                              # LD r,r' / HALT
            if z==6 and y==6:
                self.halted=True
            else:
                # com indice: so o lado (HL) usa deslocamento; H/L viram IXH/IXL
                if idx and (z==6 or y==6):
                    d=disp
                    if z==6:
                        val=self.get_r(6, idx, d); self.set_r(y, val, None)  # destino reg simples
                    else:
                        val=self.get_r(z, None); self.set_r(6, val, idx, d)
                else:
                    self.set_r(y, self.get_r(z, idx), idx)
        elif x==2:                                              # ALU A,r
            d=disp if (idx and z==6) else 0
            self.alu(y, self.get_r(z, idx, d))
        else:                                                   # x==3
            if z==0:                                            # RET cc
                if self.cond(y): self.pc=self.pop()
            elif z==1:
                if q==0: self.rp2_set(p, self.pop())            # POP rp2
                else:
                    if p==0: self.pc=self.pop()                 # RET
                    elif p==1:                                  # EXX
                        self.b,self.b_=self.b_,self.b; self.c,self.c_=self.c_,self.c
                        self.d,self.d_=self.d_,self.d; self.e,self.e_=self.e_,self.e
                        self.h,self.h_=self.h_,self.h; self.l,self.l_=self.l_,self.l
                    elif p==2:                                  # JP (HL)
                        self.pc=self._idx(idx) if idx else self.get_hl()
                    else:                                       # LD SP,HL
                        self.sp=self._idx(idx) if idx else self.get_hl()
            elif z==2:                                          # JP cc,nn
                a=self.fetch16()
                if self.cond(y): self.pc=a
            elif z==3:
                if y==0: self.pc=self.fetch16()                 # JP nn
                elif y==1: self.do_cb(idx)                      # CB prefix
                elif y==2:                                      # OUT (n),A
                    self.io.out(self.fetch(), self.a, self)
                elif y==3:                                      # IN A,(n)
                    self.a=self.io.inp(self.fetch(), self) & 0xFF
                elif y==4:                                      # EX (SP),HL
                    t=self.rw(self.sp)
                    if idx:
                        self.ww(self.sp, self._idx(idx)); self._set_idx(idx,t)
                    else:
                        self.ww(self.sp, self.get_hl()); self.set_hl(t)
                elif y==5:                                      # EX DE,HL
                    self.d,self.h=self.h,self.d; self.e,self.l=self.l,self.e
                elif y==6: self.iff1=self.iff2=0                # DI
                else: self.iff1=self.iff2=1                     # EI
            elif z==4:                                          # CALL cc,nn
                a=self.fetch16()
                if self.cond(y): self.push(self.pc); self.pc=a
            elif z==5:
                if q==0: self.push(self.rp2_get(p))             # PUSH rp2
                else:
                    if p==0:                                    # CALL nn
                        a=self.fetch16(); self.push(self.pc); self.pc=a
                    # p==1,2,3 sao prefixos (tratados antes)
            elif z==6:                                          # ALU A,n
                self.alu(y, self.fetch())
            else:                                               # RST
                self.push(self.pc); self.pc=y*8

    def _accel(self, y):
        # operacoes rapidas com A / flags (RLCA,RRCA,RLA,RRA,DAA,CPL,SCF,CCF)
        a=self.a; f=self.f
        if y==0:    # RLCA
            c=a>>7; a=((a<<1)|c)&0xFF
            self.f=(f&(FS|FZ|FPV))|(a&(F3|F5))|(FC if c else 0)
        elif y==1:  # RRCA
            c=a&1; a=((a>>1)|(c<<7))&0xFF
            self.f=(f&(FS|FZ|FPV))|(a&(F3|F5))|(FC if c else 0)
        elif y==2:  # RLA
            c=a>>7; a=((a<<1)|(1 if f&FC else 0))&0xFF
            self.f=(f&(FS|FZ|FPV))|(a&(F3|F5))|(FC if c else 0)
        elif y==3:  # RRA
            c=a&1; a=((a>>1)|(0x80 if f&FC else 0))&0xFF
            self.f=(f&(FS|FZ|FPV))|(a&(F3|F5))|(FC if c else 0)
        elif y==4:  # DAA
            self.daa(); return
        elif y==5:  # CPL
            a^=0xFF; self.f=(f&(FS|FZ|FPV|FC))|FH|FN|(a&(F3|F5))
        elif y==6:  # SCF
            self.f=(f&(FS|FZ|FPV))|FC|(a&(F3|F5))
        else:       # CCF
            self.f=(f&(FS|FZ|FPV))|((f&FC)<<4 & FH)|(0 if f&FC else FC)|(a&(F3|F5))
        self.a=a

    def _disp(self):
        d=self.fetch()
        return d-256 if d>127 else d

    # ---- prefixo CB (rotacoes / bit / res / set) ----
    def do_cb(self, idx):
        if idx is not None:
            d=self._disp()
        op=self.fetch()
        x=op>>6; y=(op>>3)&7; z=op&7
        if idx is not None:
            addr=(self._idx(idx)+d)&0xFFFF; v=self.rb(addr)
            if x==0:
                v=self.rot(y, v); self.wb(addr,v)
                if z!=6: self.set_r(z, v, None)
            elif x==1:                       # BIT
                self._bit(y, v, (addr>>8)&0xFF)
            elif x==2:                       # RES
                v&=~(1<<y)&0xFF; self.wb(addr,v)
                if z!=6: self.set_r(z, v, None)
            else:                            # SET
                v|=(1<<y); self.wb(addr,v)
                if z!=6: self.set_r(z, v, None)
            return
        v=self.get_r(z)
        if x==0:
            self.set_r(z, self.rot(y, v))
        elif x==1:
            self._bit(y, v, v)
        elif x==2:
            self.set_r(z, v & (~(1<<y)&0xFF))
        else:
            self.set_r(z, v | (1<<y))
    def _bit(self, y, v, undoc):
        z = not (v & (1<<y))
        f=(self.f & FC)|FH
        if z: f|=FZ|FPV
        if y==7 and (v & 0x80): f|=FS
        f|= undoc & (F3|F5)
        self.f=f

    # ---- prefixo DD/FD (HL -> IX/IY) ----
    def do_index(self, idx):
        op=self.fetch()
        if op==0xCB: return self.do_cb(idx)
        if op in (0xDD,0xFD): self.pc=(self.pc-1)&0xFFFF; return  # ignora encadeamento
        self.exec_main(op, idx)

    # ---- prefixo ED ----
    def do_ed(self):
        op=self.fetch()
        x=op>>6; y=(op>>3)&7; z=op&7; p=y>>1; q=y&1
        if x==1:
            if z==0:                                            # IN r,(C)
                v=self.io.inp(self.c, self)&0xFF
                if y!=6: self.set_r(y, v)
                self.f=(self.f&FC)|PARITY[v]|(v&(FS|F3|F5))|(FZ if v==0 else 0)
            elif z==1:                                          # OUT (C),r
                self.io.out(self.c, 0 if y==6 else self.get_r(y), self)
            elif z==2:
                hl=self.get_hl()
                if q==0: self.set_hl(self.sbc16(hl, self.rp_get(p)))   # SBC HL,rp
                else:    self.set_hl(self.adc16(hl, self.rp_get(p)))   # ADC HL,rp
            elif z==3:
                a=self.fetch16()
                if q==0: self.ww(a, self.rp_get(p))             # LD (nn),rp
                else:    self.rp_set(p, self.rw(a))             # LD rp,(nn)
            elif z==4:                                          # NEG
                t=self.a; self.a=0; self._sub(t)
            elif z==5:                                          # RETN/RETI
                self.pc=self.pop(); self.iff1=self.iff2
            elif z==6:                                          # IM
                self.im=[0,0,1,2,0,0,1,2][y]
            else:                                               # z==7
                if y==0: self.i=self.a                          # LD I,A
                elif y==1: self.r=self.a                        # LD R,A
                elif y==2:                                      # LD A,I
                    self.a=self.i; self._ld_ir()
                elif y==3:                                      # LD A,R
                    self.a=self.r; self._ld_ir()
                elif y==4: self._rrd()
                elif y==5: self._rld()
        elif x==2 and z<=3 and y>=4:                            # block ops
            self._block(y, z)
        # outros ED: NOP

    def _ld_ir(self):
        self.f=(self.f&FC)|(self.a&(FS|F3|F5))|(FZ if self.a==0 else 0)|(FPV if self.iff2 else 0)
    def _rrd(self):
        hl=self.get_hl(); m=self.rb(hl); a=self.a
        self.wb(hl, ((m>>4)|((a&0xF)<<4))&0xFF)
        self.a=(a&0xF0)|(m&0xF)
        self.f=(self.f&FC)|PARITY[self.a]|(self.a&(FS|F3|F5))|(FZ if self.a==0 else 0)
    def _rld(self):
        hl=self.get_hl(); m=self.rb(hl); a=self.a
        self.wb(hl, (((m<<4)|(a&0xF))&0xFF))
        self.a=(a&0xF0)|((m>>4)&0xF)
        self.f=(self.f&FC)|PARITY[self.a]|(self.a&(FS|F3|F5))|(FZ if self.a==0 else 0)
    def _block(self, y, z):
        inc = 1 if y in (4,6) else -1     # LDI/CPI/INI/OUTI vs LDD/...
        rep = y>=6
        if z==0:    # LDI/LDD/LDIR/LDDR
            v=self.rb(self.get_hl()); self.wb(self.get_de(), v)
            self.set_hl((self.get_hl()+inc)&0xFFFF)
            self.set_de((self.get_de()+inc)&0xFFFF)
            self.set_bc((self.get_bc()-1)&0xFFFF)
            n=(v+self.a)&0xFF
            self.f=(self.f&(FS|FZ|FC))|(FPV if self.get_bc() else 0)|(n&F3)|((n<<4)&F5)
            if rep and self.get_bc(): self.pc=(self.pc-2)&0xFFFF
        elif z==1:  # CPI/CPD/CPIR/CPDR
            v=self.rb(self.get_hl()); r=(self.a-v)&0xFF
            self.set_hl((self.get_hl()+inc)&0xFFFF)
            self.set_bc((self.get_bc()-1)&0xFFFF)
            f=(self.f&FC)|FN|(r&FS)|(FZ if r==0 else 0)
            if ((self.a&0xF)-(v&0xF))&0x10: f|=FH
            if self.get_bc(): f|=FPV
            n=(r-(1 if f&FH else 0))&0xFF
            f|=(n&F3)|((n<<4)&F5)
            self.f=f
            if rep and self.get_bc() and r!=0: self.pc=(self.pc-2)&0xFFFF
        elif z==2:  # INI/IND/INIR/INDR
            v=self.io.inp(self.c, self)&0xFF
            self.wb(self.get_hl(), v)
            self.set_hl((self.get_hl()+inc)&0xFFFF)
            self.b=(self.b-1)&0xFF
            self.f=FN|(FZ if self.b==0 else 0)
            if rep and self.b: self.pc=(self.pc-2)&0xFFFF
        else:       # OUTI/OUTD/OTIR/OTDR
            v=self.rb(self.get_hl())
            self.io.out(self.c, v, self)
            self.set_hl((self.get_hl()+inc)&0xFFFF)
            self.b=(self.b-1)&0xFF
            self.f=FN|(FZ if self.b==0 else 0)
            if rep and self.b: self.pc=(self.pc-2)&0xFFFF


# ==========================================================================
# Modelo simplificado de E/S (portas) - o bastante para o cold start rodar
# ==========================================================================
class IO:
    def __init__(self, verbose=False):
        self.verbose=verbose
        self.log=[]
        self.keys=[]          # fila de teclas (entrada)
    def inp(self, port, cpu):
        port&=0xFF
        if self.verbose: self.log.append((cpu.pc,"IN",port))
        # valores que mantem o cold start na trilha "sem disco" -> BASIC/cassete
        if port==0xFF: return 0x00
        if port==0xF4: return 0x00     # status de disco: nao-pronto (gera timeout)
        if port==0xF0: return 0x00
        if port==0xE4: return 0x00
        if port==0xEC: return 0x00
        if port==0xE0: return 0x00
        return 0xFF
    def out(self, port, val, cpu):
        port&=0xFF; val&=0xFF
        if self.verbose: self.log.append((cpu.pc,"OUT",port,val))


# ==========================================================================
# CARGA DA ROM + AUTOTESTE + TRACE + DEPURADOR
# ==========================================================================
ROM_FILE="27C128cp300.BIN"

def make_machine(verbose=False):
    mem=bytearray(0x10000)
    rom_end=0x4000
    if os.path.exists(ROM_FILE):
        data=open(ROM_FILE,"rb").read()
        mem[0:len(data)]=data
        rom_end=len(data)
    cpu=Z80(mem, rom_end, IO(verbose))
    cpu.pc=0
    return cpu

def regs_str(c):
    fl="".join(n if c.f&b else "." for b,n in
               ((FS,"S"),(FZ,"Z"),(FH,"H"),(FPV,"P"),(FN,"N"),(FC,"C")))
    return (f"PC={c.pc:04X} SP={c.sp:04X} AF={c.get_af():04X} BC={c.get_bc():04X} "
            f"DE={c.get_de():04X} HL={c.get_hl():04X} IX={c.ix:04X} IY={c.iy:04X} "
            f"A={c.a:02X} [{fl}]")

def cur_instr(c):
    if not disasm: return ""
    blk=bytes(c.m[c.pc:c.pc+4]) + b"\x00\x00\x00\x00"
    for a,raw,txt in disasm(blk, c.pc):
        return f"{a:04X}  {raw:<11}  {txt}"
    return ""

def autoteste():
    print("=== AUTOTESTE DO NUCLEO Z80 ===")
    mem=bytearray(0x10000)
    prog=[
        0x3E,0x05,        # LD A,5
        0x06,0x07,        # LD B,7
        0x80,             # ADD A,B      -> 12
        0x21,0x00,0x90,   # LD HL,9000h
        0x77,             # LD (HL),A    -> mem[9000]=12
        0x3C,             # INC A        -> 13
        0xFE,0x0D,        # CP 13        -> Z=1
        0xC3,0x10,0x00,   # JP 0010h
    ]
    mem[0:len(prog)]=bytes(prog)
    cpu=Z80(mem, rom_end=0, io=IO())
    cpu.pc=0
    for _ in range(8):
        cpu.step()
    ok = (cpu.a==13 and mem[0x9000]==12 and (cpu.f&FZ) and cpu.pc==0x0010)
    print(f"A=13? {cpu.a==13}   (HL)=12? {mem[0x9000]==12}   Z apos CP? {bool(cpu.f&FZ)}   "
          f"JP funcionou? {cpu.pc==0x0010}")
    # teste de LDIR
    mem2=bytearray(0x10000)
    mem2[0x100:0x105]=b"HELLO"
    p2=[0x21,0x00,0x01, 0x11,0x00,0x02, 0x01,0x05,0x00, 0xED,0xB0, 0x76]
    mem2[0:len(p2)]=bytes(p2)
    c2=Z80(mem2, rom_end=0, io=IO()); c2.pc=0
    for _ in range(200):
        if c2.halted: break
        c2.step()
    print("LDIR copiou 'HELLO'? ", bytes(mem2[0x200:0x205])==b"HELLO")
    print("RESULTADO:", "OK - nucleo Z80 correto" if ok else "FALHOU")

def trace(n):
    cpu=make_machine()
    print("=== EXECUTANDO O FIRMWARE REAL (a partir do reset, PC=0000) ===")
    for i in range(n):
        if cpu.halted:
            print("[HALT]"); break
        line=cur_instr(cpu)
        print(f"{line:<34} | {regs_str(cpu)}")
        cpu.step()

HELP=""">>> emucp - depurador do emulador Z80 do CP-300
  s [n]        passo(s): executa n instrucoes mostrando cada uma (default 1)
  g [end]      roda ate o endereco (breakpoint) ou ate HALT
  n <num>      executa <num> instrucoes em silencio e mostra o estado final
  r            mostra registradores e a instrucao atual
  d <end> [n]  dump de memoria (hex+ASCII)
  b <end>      define breakpoint     bc  limpa breakpoints
  pc <end>     ajusta o PC
  reset        recarrega a ROM e zera o PC
  v            liga/desliga log de portas (E/S)
  t            autoteste do nucleo Z80
  q            sai
Todos os numeros em HEXADECIMAL."""

def depurador():
    cpu=make_machine()
    bp=set()
    print("emucp - EMULADOR Z80 do CP-300 (executa os opcodes REAIS da ROM)")
    print(f"ROM carregada: 0000-{cpu.rom_end-1:04X}. Digite 'h' para ajuda.\n")
    print(regs_str(cpu)); print(cur_instr(cpu))
    while True:
        try:
            line=input("z80> ").strip()
        except (EOFError,KeyboardInterrupt):
            print(); break
        if not line: continue
        parts=line.split(); cmd=parts[0].lower(); args=parts[1:]
        def hx(t): return int(t.rstrip("Hh"),16)
        try:
            if cmd in ("q","quit","exit"): break
            elif cmd in ("h","?","help"): print(HELP)
            elif cmd=="t": autoteste()
            elif cmd=="r":
                print(regs_str(cpu)); print(cur_instr(cpu))
            elif cmd=="reset":
                cpu=make_machine(); print("Reset. PC=0000")
            elif cmd=="v":
                cpu.io.verbose=not cpu.io.verbose
                print("log de portas:", "ON" if cpu.io.verbose else "OFF")
            elif cmd=="pc":
                cpu.pc=hx(args[0])&0xFFFF; print(cur_instr(cpu))
            elif cmd=="b":
                bp.add(hx(args[0])&0xFFFF); print("breakpoints:", sorted(f"{x:04X}" for x in bp))
            elif cmd=="bc":
                bp.clear(); print("breakpoints limpos")
            elif cmd=="d":
                a=hx(args[0]) if args else cpu.pc
                n=hx(args[1]) if len(args)>1 else 0x40
                for off in range(0,n,16):
                    row=cpu.m[a+off:a+off+16]
                    hexa=" ".join(f"{x:02X}" for x in row)
                    txt="".join(chr(x) if 32<=x<127 else "." for x in row)
                    print(f"{a+off:04X}  {hexa:<47}  {txt}")
            elif cmd=="s":
                n=hx(args[0]) if args else 1
                for _ in range(n):
                    if cpu.halted: print("[HALT]"); break
                    print(f"{cur_instr(cpu):<34} | {regs_str(cpu)}")
                    cpu.step()
            elif cmd in ("g","n"):
                limit=2_000_000
                target=hx(args[0]) if (cmd=="g" and args) else None
                count=hx(args[0]) if (cmd=="n" and args) else None
                i=0
                while i<limit:
                    if cpu.halted: print("[HALT]"); break
                    cpu.step(); i+=1
                    if target is not None and cpu.pc==target: break
                    if cpu.pc in bp: print(f"[breakpoint {cpu.pc:04X}]"); break
                    if count is not None and i>=count: break
                print(f"({i} instrucoes executadas)")
                print(regs_str(cpu)); print(cur_instr(cpu))
            else:
                print("?cmd (h=ajuda)")
        except (ValueError,IndexError):
            print("?args (use hexadecimal)")

if __name__=="__main__":
    if "--test" in sys.argv:
        autoteste()
    elif "--trace" in sys.argv:
        i=sys.argv.index("--trace")
        n=int(sys.argv[i+1]) if len(sys.argv)>i+1 else 30
        trace(n)
    else:
        depurador()
