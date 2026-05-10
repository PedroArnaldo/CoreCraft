# CoreCraft

Exercício prático de integração com Bitcoin Core. O projeto roda um **node Bitcoin na rede Signet** e expõe um **painel web (Flask + HTML/JS)** que conversa com o node por **JSON-RPC** e por **ZeroMQ (ZMQ)**, mostrando estado da blockchain, mempool, blocos recentes, transações e eventos em tempo real.

---

## O que tem no projeto

O repositório está dividido em três aulas/atividades, cada uma evoluindo o painel, mais uma camada de infraestrutura para subir tudo via Docker.

### `Atividade-1/` — RPC como fotografia do estado
Primeiro contato com Bitcoin Core via JSON-RPC. Endpoints implementados em [Atividade-1/backend/app.py](Atividade-1/backend/app.py):
- `GET /api/node` — `getblockchaininfo` + `getmempoolinfo` + `getnetworkinfo` (chain, blocks, headers, dificuldade, conexões).
- `GET /api/blocks/recent?n=N` — últimos N blocos via `getblockcount` + `getblockhash` + `getblockheader` + `getblockstats`.
- `GET /api/block/<hash>` — resumo de um bloco específico via `getblock(hash, 1)`.
- `GET /api/mempool/summary` — agrega `getrawmempool` + `getmempoolinfo` em estatísticas (fee rate médio, distribuição low/medium/high).
- `GET /api/blockchain/lag` — diferença entre `blocks` e `headers` (sinal de sincronização).
- `GET /api/tx/<txid>` — `getrawtransaction(txid, true)` (depende de `txindex` ou da tx estar em mempool/wallet).

Cliente RPC minimalista em [Atividade-1/backend/rpc.py](Atividade-1/backend/rpc.py) com suporte a `RPC_USER`/`RPC_PASS` ou cookie auth (`~/.bitcoin/<rede>/.cookie`).

### `Atividade-2/` — Eventos em tempo real (ZMQ)
Adiciona um **listener ZeroMQ** ([Atividade-2/backend/zmq_listener.py](Atividade-2/backend/zmq_listener.py)) que escuta `hashblock` e `hashtx` em background numa thread daemon e guarda os eventos num [EventStore](Atividade-2/backend/event_store.py) em memória (deque com lock).

Novos endpoints:
- `GET /api/events/summary` — total de blocos e txs observados, tx/segundo, último timestamp.
- `GET /api/events/latest` — listas brutas de blocos e txs recebidos por ZMQ.
- `GET /api/events/state-comparison` — compara `getbestblockhash` (RPC) com o último bloco visto via ZMQ; sinaliza divergência.

### `Atividade-3/` — Wallets e rastreamento de transações
Adiciona seleção dinâmica de wallet e rastreamento de status de tx. Em [Atividade-3/backend/app.py](Atividade-3/backend/app.py):
- `GET /api/wallets` — `listwalletdir` + `listwallets` + wallet selecionada atualmente.
- `POST /api/wallet/select` — body `{"wallet": "<nome>"}`. Carrega via `loadwallet` se necessário e marca como ativa no `WalletState` ([rpc.py](Atividade-3/backend/rpc.py#L113)).
- `GET /api/wallet/status` — saldo (`getbalances`) + nº de UTXOs (`listunspent`).
- `GET /api/tx/<txid>` — interpreta o status da tx no contexto da wallet ativa: `confirmed` / `mempool` / `broadcast` / `unknown`, com idade em segundos e warnings (ex.: tx parada na mempool > 2 min).

Frontend correspondente em [Atividade-3/frontend/index.html](Atividade-3/frontend/index.html) com cards para wallet, estado do node, mempool, blocos recentes, consulta de bloco/tx, transações rastreadas e atividade ZMQ.

### `infra/` — Empacotamento Docker (Atividade-3)
- [infra/docker-compose.yml](infra/docker-compose.yml) — dois serviços, ambos em `network_mode: host`:
  - `bitcoin` — `ruimarinho/bitcoin-core:24` rodando Signet, com `bitcoin.conf` montado read-only e volume nomeado `bitcoin-data` para persistência.
  - `flask` — build a partir de [infra/flask/Dockerfile](infra/flask/Dockerfile), serve a Atividade-3 via Gunicorn na porta `8181`.
- [infra/bitcoin/bitcoin.conf](infra/bitcoin/bitcoin.conf) — Signet ativado, RPC em `127.0.0.1:58443` (user/pass `teste`/`teste`), publishers ZMQ em `28332`/`28333`/`28334` (na verdade `58331`/`58334`/`58335` no `.conf` atual — confira se vai mexer).
- [infra/.env.example](infra/.env.example) — variáveis lidas pelo container Flask (`RPC_HOST`, `RPC_PORT`, `RPC_USER`, `RPC_PASS`, `BTC_NETWORK=signet`, etc.).

---

## Como rodar

### Pré-requisitos
- Docker + Docker Compose plugin (`docker compose ...`).
- Portas livres no host: `8181` (Flask), `58443` (RPC), `58445` (P2P Signet), `58331/58334/58335` (ZMQ).

### Passo a passo

```bash
cd infra

# 1. cria o .env a partir do exemplo (ajuste senhas se quiser)
cp .env.example .env

# 2. sobe os dois containers (bitcoin + flask)
docker compose up -d --build

# 3. acompanha os logs (o node Signet leva alguns minutos para sincronizar)
docker compose logs -f bitcoin
docker compose logs -f flask
```

> Como ambos os containers usam `network_mode: host`, o Flask alcança o Bitcoin Core via `127.0.0.1` direto na máquina hospedeira. Não há rede Docker isolada nem mapeamento `-p`.

### Sanity checks

```bash
# RPC do node respondendo?
curl -u teste:teste --data-binary \
  '{"jsonrpc":"1.0","id":"x","method":"getblockchaininfo","params":[]}' \
  -H 'content-type: application/json' http://127.0.0.1:58443/

# API Flask respondendo?
curl http://127.0.0.1:8181/api/node
```

### Parar / atualizar

```bash
docker compose down              # para os containers (mantém o volume bitcoin-data)
docker compose down -v           # também apaga o volume (perde dados sincronizados!)
docker compose up -d --build     # reconstrói após mudar código da Atividade-3
```

### Rodar local sem Docker (modo aula)

Cada Atividade roda standalone com Flask de desenvolvimento, apontando para um `bitcoind` local:

```bash
cd Atividade-3/backend
python -m venv ../../venv && source ../../venv/bin/activate
pip install -r ../../infra/flask/requirements.txt
export RPC_HOST=127.0.0.1 RPC_PORT=58443 RPC_USER=teste RPC_PASS=teste BTC_NETWORK=signet
python app.py        # sobe em http://127.0.0.1:8080
```

---

## Como acessar pela VPS (`38.244.199.123`)

A stack do Compose está pronta para rodar na VPS exatamente do mesmo jeito:

1. **Subir o projeto na VPS**
   ```bash
   ssh usuario@38.244.199.123
   git clone <url-do-repo> CoreCraft && cd CoreCraft/infra
   cp .env.example .env
   docker compose up -d --build
   ```

2. **Liberar a porta 8181 no firewall** (UFW por padrão na maioria das VPS):
   ```bash
   sudo ufw allow 8181/tcp
   sudo ufw reload
   ```
   Se houver firewall do provedor (cloud firewall / security group), libere `8181/tcp` lá também.

3. **Acessar o painel no navegador**
   ```
   http://38.244.199.123:8181/
   ```
   Endpoints úteis para conferir do seu PC:
   ```
   http://38.244.199.123:8181/api/node
   http://38.244.199.123:8181/api/blocks/recent?n=10
   http://38.244.199.123:8181/api/mempool/summary
   http://38.244.199.123:8181/api/events/summary
   http://38.244.199.123:8181/api/wallets
   ```

### Avisos importantes para exposição pública

- **RPC e ZMQ NÃO devem ser expostos** para a internet. O `bitcoin.conf` já restringe RPC a `127.0.0.1` (`rpcbind=127.0.0.1` + `rpcallowip=127.0.0.1`), então só o Flask no próprio host enxerga o node — mantenha assim.
- **Só abra `8181/tcp` no firewall** — qualquer outra porta exposta (especialmente `58443`) é risco de segurança.
- O painel atual **não tem autenticação**. Em VPS pública, qualquer um com o IP consegue listar wallets e selecionar wallet ativa. Para uso real, ponha um proxy reverso com auth (Nginx + Basic Auth, Caddy, Cloudflare Access, etc.) na frente do `8181`.
- Trocar `RPC_USER`/`RPC_PASS` no `.env` e no [infra/bitcoin/bitcoin.conf](infra/bitcoin/bitcoin.conf) para algo não trivial antes de subir em produção.
- Signet é uma rede de teste; o node sincroniza rápido (poucos GB), mas ainda assim leva alguns minutos na primeira execução. Acompanhe `docker compose logs -f bitcoin` até `Loaded best chain` aparecer.
