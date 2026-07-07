# Z80Nostalgia Web

Interface web (Flask + Tailwind) para o BASIC e o MONITOR do CP-300, com
visual de terminal CRT verde-fósforo estilo TRS-80 dos anos 80.

Não altera nenhum arquivo do emulador: `cp300_basic.py`, `cp300_monitor.py`
e `emucp.py` continuam funcionando exatamente como antes no terminal local.
Esta pasta apenas os executa como processos (igual a rodar `python
cp300_basic.py` num terminal) e liga a entrada/saída deles à página web.

## Como rodar

```bash
pip install -r webapp/requirements.txt
python webapp/app.py
```

Abra **http://127.0.0.1:5000** no navegador. Escolha **BASIC** ou
**MONITOR**; cada aba do navegador tem sua própria sessão (seu próprio
processo Python rodando o emulador).

> Servidor de desenvolvimento, sem autenticação — pensado para uso local.
> Não exponha esta porta diretamente na internet.

## Arquivos do usuário

Como o BASIC e o MONITOR reimplementados não têm um "disco" próprio, a
interface web cria uma **pasta temporária fora da raiz do projeto**
(por padrão em `%TEMP%\Z80Nostalgia_Arquivos` no Windows, ou
`$TMPDIR/Z80Nostalgia_Arquivos`) onde ficam os arquivos `.bas`/`.blk`:

- No **MONITOR**, os comandos `S <nome> <ini> <fim>` (salvar bloco) e
  `P <nome> [end]` (carregar bloco) já leem/gravam nessa pasta, porque o
  processo do monitor é iniciado com essa pasta como diretório de trabalho
  — sem nenhuma mudança em `cp300_monitor.py`.
- No **BASIC**, a página web adiciona dois botões que não existem no
  terminal local: "carregar" (digita as linhas de um `.bas` dentro do
  interpretador em execução, uma por uma, como se você as tivesse digitado)
  e "salvar programa" (manda `LIST`, captura a saída e grava como `.bas`).
- A pasta também pode ser gerenciada em `/arquivos` (upload, download,
  apagar).

Para usar outra pasta, defina a variável de ambiente `Z80_DATA_DIR` antes
de iniciar o servidor.

## Como funciona por baixo dos panos

`emulator_session.py` inicia `python -u cp300_basic.py` (ou
`cp300_monitor.py`) como subprocesso, lê a saída **caractere a caractere**
(para capturar prompts como `z80> ` ou `* ` que não terminam em quebra de
linha) e escreve linhas na entrada padrão dele quando você digita um
comando na página — exatamente como um terminal local faria. O navegador
consulta `/api/output` a cada ~250ms (long-ish polling simples, sem
WebSocket) e envia comandos via `/api/input`.
