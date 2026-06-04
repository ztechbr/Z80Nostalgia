# -*- coding: utf-8 -*-
"""
Disassembler Z80 minimalista, porem completo (base, CB, ED, DD, FD).
Uso: python z80dasm.py arquivo.BIN base_org > saida.txt
"""
import sys

# Tabela principal de opcodes. {} = byte imediato (n), %% = palavra (nn),
# @ = deslocamento relativo (e), $ = indice (d) para DD/FD.
MAIN = {
0x00:"NOP",0x01:"LD BC,%%",0x02:"LD (BC),A",0x03:"INC BC",0x04:"INC B",0x05:"DEC B",
0x06:"LD B,{}",0x07:"RLCA",0x08:"EX AF,AF'",0x09:"ADD HL,BC",0x0A:"LD A,(BC)",0x0B:"DEC BC",
0x0C:"INC C",0x0D:"DEC C",0x0E:"LD C,{}",0x0F:"RRCA",
0x10:"DJNZ @",0x11:"LD DE,%%",0x12:"LD (DE),A",0x13:"INC DE",0x14:"INC D",0x15:"DEC D",
0x16:"LD D,{}",0x17:"RLA",0x18:"JR @",0x19:"ADD HL,DE",0x1A:"LD A,(DE)",0x1B:"DEC DE",
0x1C:"INC E",0x1D:"DEC E",0x1E:"LD E,{}",0x1F:"RRA",
0x20:"JR NZ,@",0x21:"LD HL,%%",0x22:"LD (%%),HL",0x23:"INC HL",0x24:"INC H",0x25:"DEC H",
0x26:"LD H,{}",0x27:"DAA",0x28:"JR Z,@",0x29:"ADD HL,HL",0x2A:"LD HL,(%%)",0x2B:"DEC HL",
0x2C:"INC L",0x2D:"DEC L",0x2E:"LD L,{}",0x2F:"CPL",
0x30:"JR NC,@",0x31:"LD SP,%%",0x32:"LD (%%),A",0x33:"INC SP",0x34:"INC (HL)",0x35:"DEC (HL)",
0x36:"LD (HL),{}",0x37:"SCF",0x38:"JR C,@",0x39:"ADD HL,SP",0x3A:"LD A,(%%)",0x3B:"DEC SP",
0x3C:"INC A",0x3D:"DEC A",0x3E:"LD A,{}",0x3F:"CCF",
}
# bloco 0x40-0x7F: LD r,r'  (0x76 = HALT)
R = ["B","C","D","E","H","L","(HL)","A"]
for o in range(0x40,0x80):
    if o==0x76:
        MAIN[o]="HALT"; continue
    MAIN[o]=f"LD {R[(o>>3)&7]},{R[o&7]}"
# bloco 0x80-0xBF: ALU A,r
ALU=["ADD A,","ADC A,","SUB ","SBC A,","AND ","XOR ","OR ","CP "]
for o in range(0x80,0xC0):
    MAIN[o]=ALU[(o>>3)&7]+R[o&7]
# restante 0xC0-0xFF
MAIN.update({
0xC0:"RET NZ",0xC1:"POP BC",0xC2:"JP NZ,%%",0xC3:"JP %%",0xC4:"CALL NZ,%%",0xC5:"PUSH BC",
0xC6:"ADD A,{}",0xC7:"RST 00H",0xC8:"RET Z",0xC9:"RET",0xCA:"JP Z,%%",0xCC:"CALL Z,%%",
0xCD:"CALL %%",0xCE:"ADC A,{}",0xCF:"RST 08H",
0xD0:"RET NC",0xD1:"POP DE",0xD2:"JP NC,%%",0xD3:"OUT ({}),A",0xD4:"CALL NC,%%",0xD5:"PUSH DE",
0xD6:"SUB {}",0xD7:"RST 10H",0xD8:"RET C",0xD9:"EXX",0xDA:"JP C,%%",0xDB:"IN A,({})",
0xDC:"CALL C,%%",0xDE:"SBC A,{}",0xDF:"RST 18H",
0xE0:"RET PO",0xE1:"POP HL",0xE2:"JP PO,%%",0xE3:"EX (SP),HL",0xE4:"CALL PO,%%",0xE5:"PUSH HL",
0xE6:"AND {}",0xE7:"RST 20H",0xE8:"RET PE",0xE9:"JP (HL)",0xEA:"JP PE,%%",0xEB:"EX DE,HL",
0xEC:"CALL PE,%%",0xEE:"XOR {}",0xEF:"RST 28H",
0xF0:"RET P",0xF1:"POP AF",0xF2:"JP P,%%",0xF3:"DI",0xF4:"CALL P,%%",0xF5:"PUSH AF",
0xF6:"OR {}",0xF7:"RST 30H",0xF8:"RET M",0xF9:"LD SP,HL",0xFA:"JP M,%%",0xFB:"EI",
0xFC:"CALL M,%%",0xFE:"CP {}",0xFF:"RST 38H",
})

def cb(o):
    ops=["RLC","RRC","RL","RR","SLA","SRA","SLL","SRL"]
    r=R[o&7]
    if o<0x40: return f"{ops[(o>>3)&7]} {r}"
    bit=(o>>3)&7
    if o<0x80: return f"BIT {bit},{r}"
    if o<0xC0: return f"RES {bit},{r}"
    return f"SET {bit},{r}"

ED = {
0x40:"IN B,(C)",0x41:"OUT (C),B",0x42:"SBC HL,BC",0x43:"LD (%%),BC",0x44:"NEG",0x45:"RETN",
0x46:"IM 0",0x47:"LD I,A",0x48:"IN C,(C)",0x49:"OUT (C),C",0x4A:"ADC HL,BC",0x4B:"LD BC,(%%)",
0x4D:"RETI",0x4F:"LD R,A",
0x50:"IN D,(C)",0x51:"OUT (C),D",0x52:"SBC HL,DE",0x53:"LD (%%),DE",0x56:"IM 1",0x57:"LD A,I",
0x58:"IN E,(C)",0x59:"OUT (C),E",0x5A:"ADC HL,DE",0x5B:"LD DE,(%%)",0x5E:"IM 2",0x5F:"LD A,R",
0x60:"IN H,(C)",0x61:"OUT (C),H",0x62:"SBC HL,HL",0x67:"RRD",
0x68:"IN L,(C)",0x69:"OUT (C),L",0x6A:"ADC HL,HL",0x6F:"RLD",
0x72:"SBC HL,SP",0x73:"LD (%%),SP",0x78:"IN A,(C)",0x79:"OUT (C),A",0x7A:"ADC HL,SP",0x7B:"LD SP,(%%)",
0xA0:"LDI",0xA1:"CPI",0xA2:"INI",0xA3:"OUTI",0xA8:"LDD",0xA9:"CPD",0xAA:"IND",0xAB:"OUTD",
0xB0:"LDIR",0xB1:"CPIR",0xB2:"INIR",0xB3:"OTIR",0xB8:"LDDR",0xB9:"CPDR",0xBA:"INDR",0xBB:"OTDR",
}

def disasm(data, org):
    out=[]
    i=0
    n=len(data)
    while i<n:
        addr=org+i
        b=data[i]; start=i; i+=1
        txt=None
        if b==0xCB:
            op=data[i]; i+=1; txt=cb(op)
        elif b==0xED:
            op=data[i]; i+=1
            t=ED.get(op,f"DB 0EDH,{op:02X}H")
            while "%%" in t:
                lo=data[i]; hi=data[i+1]; i+=2
                t=t.replace("%%",f"{hi<<8|lo:04X}H",1)
            txt=t
        elif b in (0xDD,0xFD):
            ix="IX" if b==0xDD else "IY"
            op=data[i]; i+=1
            if op==0xCB:
                d=data[i]; i+=1; sub=data[i]; i+=1
                dd=d-256 if d>127 else d
                base=cb(sub)
                txt=base.replace("(HL)",f"({ix}{dd:+d})")
            else:
                t=MAIN.get(op,f"DB {op:02X}H")
                t=t.replace("HL",ix).replace("(IX)",f"({ix})").replace("(IY)",f"({ix})")
                # tratar deslocamento $ presente em (IX+d)
                if "(HL)" in MAIN.get(op,""):
                    pass
                # (HL) ja foi trocado por (IX); precisa de deslocamento
                if f"({ix})" in t and op not in (0xE9,0xF9,0x21,0x2A,0x22,0x09,0x19,0x29,0x39,0x23,0x2B,0xE1,0xE5,0xE3):
                    d=data[i]; i+=1
                    dd=d-256 if d>127 else d
                    t=t.replace(f"({ix})",f"({ix}{dd:+d})")
                while "{}" in t:
                    v=data[i]; i+=1; t=t.replace("{}",f"{v:02X}H",1)
                while "%%" in t:
                    lo=data[i]; hi=data[i+1]; i+=2; t=t.replace("%%",f"{hi<<8|lo:04X}H",1)
                txt=t
        else:
            t=MAIN[b]
            if "@" in t:
                e=data[i]; i+=1
                ee=e-256 if e>127 else e
                dest=org+i+ee
                t=t.replace("@",f"{dest:04X}H")
            while "{}" in t:
                v=data[i]; i+=1; t=t.replace("{}",f"{v:02X}H",1)
            while "%%" in t:
                lo=data[i]; hi=data[i+1]; i+=2; t=t.replace("%%",f"{hi<<8|lo:04X}H",1)
            txt=t
        raw=" ".join(f"{x:02X}" for x in data[start:i])
        out.append((addr,raw,txt))
    return out

if __name__=="__main__":
    fn=sys.argv[1]; org=int(sys.argv[2],0) if len(sys.argv)>2 else 0
    data=open(fn,"rb").read()
    for addr,raw,txt in disasm(data,org):
        print(f"{addr:04X}  {raw:<11}  {txt}")
