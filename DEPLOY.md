# Publicando o Z80Nostalgia Web no EasyPanel

Este projeto já traz `Dockerfile` + `docker-compose.yml` na raiz do
repositório, prontos para o EasyPanel buildar e rodar. Nada em
`cp300_basic.py` / `cp300_monitor.py` / `emucp.py` é alterado — a imagem só
empacota esses scripts junto com a interface web (`webapp/`).

## Testado localmente

```bash
docker build -t z80nostalgia-web .
docker run -p 5000:5000 -e Z80_SECRET_KEY=alguma-chave-secreta z80nostalgia-web
```

ou

```bash
docker compose up --build
```

Abra `http://localhost:5000`.

## Passo a passo no EasyPanel

1. **Suba o repositório** para o GitHub/GitLab (já está em
   `github.com/ztechbr/Z80Nostalgia`, então basta apontar para ele).

2. **Criar app** no EasyPanel:
   - *Source*: Git → informe a URL do repositório e a branch (`main`).
   - *Build method*: **Dockerfile** (o EasyPanel vai achar o `Dockerfile` na
     raiz automaticamente). Se preferir, ele também consegue importar o
     `docker-compose.yml`.
   - *Porta*: **5000** (é a porta que o `gunicorn` escuta dentro do
     container — o `EXPOSE 5000` do Dockerfile já avisa isso).

3. **Variáveis de ambiente** (aba *Environment*):
   - `Z80_SECRET_KEY` → gere uma string aleatória e fixa (ex.:
     `openssl rand -hex 32`). Sem isso, a cada reinício do container as
     sessões dos navegadores expiram (o app ainda funciona, só desloga todo
     mundo).
   - Não é preciso mexer em `Z80_DATA_DIR` — já vem fixado em `/data` no
     Dockerfile.

4. **Volume persistente** (aba *Volumes* / *Mounts*):
   - *Mount path*: `/data`
   - É aqui que ficam os arquivos `.bas`/`.blk` que os usuários salvam pela
     interface web e os blocos gravados pelo comando `S` do MONITOR. **Sem
     esse volume, tudo é perdido a cada novo deploy/restart.**

5. **Deploy**. O EasyPanel builda a imagem a partir do `Dockerfile` e sobe o
   container; ele mesmo cuida do proxy reverso/HTTPS pelo domínio que você
   configurar.

## Por que só 1 worker do gunicorn?

O `Dockerfile` roda `gunicorn --workers 1 --threads 8 ...`. Cada sessão do
emulador é um processo Python (`cp300_basic.py`/`cp300_monitor.py`) guardado
em memória no processo do servidor (veja `webapp/emulator_session.py`). Com
mais de um worker, requisições da mesma aba do navegador poderiam cair em
processos diferentes do gunicorn e "perder" o emulador correspondente. Um
worker com várias threads já dá conta de várias sessões simultâneas sem esse
problema — para escalar horizontalmente seria preciso um backend de sessão
compartilhado (Redis, etc.), fora do escopo deste projeto didático.

## Escalando recursos

O emulador é leve (scripts Python puros, sem gráficos), então a configuração
mínima do EasyPanel (ex.: 0.5 vCPU / 256–512 MB RAM) já é suficiente para uso
por poucos usuários simultâneos.
