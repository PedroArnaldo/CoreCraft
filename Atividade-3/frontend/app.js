async function apiGet(path) {
  const r = await fetch(path);
  const data = await r.json();
  if (!data.ok) {
    throw new Error(
      data?.error?.message +
        (data?.error?.details ? " | " + data.error.details : ""),
    );
  }
  return data.data;
}

function fmtTime(unix) {
  if (!unix) return "-";
  const d = new Date(unix * 1000);
  return d.toLocaleString();
}

function satToBTC(sats) {
  if (sats === null || sats === undefined) return "-";
  return (sats / 1e8).toFixed(8);
}

function setKV(el, obj) {
  el.innerHTML = "";
  for (const [k, v] of Object.entries(obj)) {
    const box = document.createElement("div");
    box.innerHTML = `<div class="k">${k}</div><div class="v">${v}</div>`;
    el.appendChild(box);
  }
}

function showError(el, msg) {
  el.textContent = msg;
  el.classList.remove("hidden");
}

function hideError(el) {
  el.textContent = "";
  el.classList.add("hidden");
}

// ----------- handlers -----------

async function refreshNode() {
  const nodeEl = document.getElementById("nodeState");
  const mpEl = document.getElementById("mempoolState");
  const errEl = document.getElementById("nodeError");

  hideError(errEl);

  try {
    const data = await apiGet("/api/node");

    setKV(nodeEl, {
      chain: data.chain,
      blocks: data.blocks,
      headers: data.headers,
      difficulty: data.difficulty,
      bestblockhash: data.bestblockhash,
    });

    setKV(mpEl, {
      txcount: data.mempool.txcount,
      usage_bytes: data.mempool.usage,
      bytes: data.mempool.bytes,
      maxmempool: data.mempool.maxmempool,
      mempoolminfee: data.mempool.mempoolminfee,
    });
  } catch (e) {
    showError(errEl, e.message);
  }
}

async function loadRecent() {
  const n = document.getElementById("recentN").value;
  const tbody = document.querySelector("#recentTable tbody");
  const infoEl = document.getElementById("recentInfo");
  const errEl = document.getElementById("recentError");

  hideError(errEl);
  tbody.innerHTML = "";
  infoEl.textContent = "Carregando...";

  try {
    const data = await apiGet(`/api/blocks/recent?n=${encodeURIComponent(n)}`);
    infoEl.textContent = `Tip: ${data.tip} — mostrando ${data.items.length} blocos`;

    for (const b of data.items) {
      const tr = document.createElement("tr");

      const hashShort = b.hash.slice(0, 16) + "…" + b.hash.slice(-8);

      tr.innerHTML = `
        <td>${b.height}</td>
        <td>${b.txs ?? "-"}</td>
        <td>${b.avgfeerate ?? "-"}</td>
        <td>${b.totalfee !== undefined ? satToBTC(b.totalfee) + " BTC" : "-"}</td>
        <td>${fmtTime(b.time)}</td>
        <td><a class="hash" href="#" data-hash="${b.hash}">${hashShort}</a></td>
      `;

      tbody.appendChild(tr);
    }

    // Clique no hash abre consulta de bloco
    document.querySelectorAll("a.hash").forEach((a) => {
      a.addEventListener("click", async (ev) => {
        ev.preventDefault();
        const h = ev.target.getAttribute("data-hash");
        document.getElementById("blockHashInput").value = h;
        await consultBlock();
      });
    });
  } catch (e) {
    infoEl.textContent = "";
    showError(errEl, e.message);
  }
}

async function refreshMempoolSummary() {
  const el = document.getElementById("mempoolSummary");
  const errEl = document.getElementById("mempoolSummaryError");

  hideError(errEl);

  try {
    const data = await apiGet("/api/mempool/summary");

    setKV(el, {
      tx_count: data.tx_count,
      avg_fee_rate: data.avg_fee_rate,
      low: data.fee_distribution.low,
      medium: data.fee_distribution.medium,
      high: data.fee_distribution.high,
    });
  } catch (e) {
    showError(errEl, e.message);
  }
}

async function refreshSyncStatus() {
  const el = document.getElementById("syncStatus");
  const errEl = document.getElementById("syncStatusError");

  hideError(errEl);

  try {
    const data = await apiGet("/api/blockchain/lag");

    setKV(el, {
      lag: data.lag,
    });
  } catch (e) {
    showError(errEl, e.message);
  }
}

async function refreshEventActivity() {
  const el = document.getElementById("eventActivity");
  const errEl = document.getElementById("eventActivityError");

  hideError(errEl);

  try {
    const r = await fetch("/api/events/summary");
    const data = await r.json();

    setKV(el, {
      tx_observed: data.tx_observed,
      blocks_observed: data.blocks_observed,
      tx_per_second: data.tx_per_second,
    });
  } catch (e) {
    showError(errEl, e.message);
  }
}

// ----------- wallets -----------

let currentWallet = null;

async function loadWallets() {
  const errEl = document.getElementById("walletError");
  const select = document.getElementById("walletSelect");
  hideError(errEl);

  try {
    const r = await fetch("/api/wallets");
    const data = await r.json();

    select.innerHTML = "";
    const available = data.available_wallets || [];

    if (available.length === 0) {
      const opt = document.createElement("option");
      opt.textContent = "Nenhuma wallet disponível";
      opt.disabled = true;
      select.appendChild(opt);
      currentWallet = null;
      return;
    }

    for (const name of available) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      select.appendChild(opt);
    }

    // Decide qual selecionar:
    //   1. a já marcada como ativa no backend, se existir
    //   2. a única, quando há apenas uma wallet
    //   3. a primeira da lista, como fallback
    let pick = data.selected_wallet;
    if (!pick) pick = available[0];
    select.value = pick;

    await selectWallet(pick);
  } catch (e) {
    showError(errEl, e.message);
  }
}

async function selectWallet(name) {
  const errEl = document.getElementById("walletError");
  const infoEl = document.getElementById("walletInfo");
  hideError(errEl);

  try {
    const r = await fetch("/api/wallet/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ wallet: name }),
    });
    const data = await r.json();
    if (data.error) throw new Error(data.error);

    currentWallet = data.selected_wallet;
    setKV(infoEl, {
      walletname: data.wallet_info.walletname,
      balance: data.wallet_info.balance,
      txcount: data.wallet_info.txcount,
    });

    // Status interpretado das txs depende da wallet ativa,
    // então re-renderiza a lista para refletir o novo contexto.
    renderTracked();
  } catch (e) {
    showError(errEl, e.message);
  }
}

// ----------- tracked transactions -----------

const TRACKED_STORAGE_KEY = "tracked_txs";

function loadTracked() {
  try {
    return JSON.parse(localStorage.getItem(TRACKED_STORAGE_KEY)) || [];
  } catch {
    return [];
  }
}

function saveTracked(list) {
  localStorage.setItem(TRACKED_STORAGE_KEY, JSON.stringify(list));
}

function addTrackedTx() {
  const input = document.getElementById("trackTxidInput");
  const errEl = document.getElementById("trackedError");
  hideError(errEl);

  const txid = input.value.trim();
  if (!txid) return showError(errEl, "Informe um txid.");
  if (!/^[0-9a-fA-F]{64}$/.test(txid))
    return showError(errEl, "txid inválido (precisa ser hex de 64 caracteres).");
  if (!currentWallet)
    return showError(errEl, "Selecione uma wallet antes de rastrear uma transação.");

  const list = loadTracked();
  if (list.some((t) => t.txid === txid))
    return showError(errEl, "Esta transação já está sendo rastreada.");

  list.push({ txid, wallet: currentWallet });
  saveTracked(list);
  input.value = "";
  renderTracked();
}

function removeTrackedTx(txid) {
  const list = loadTracked().filter((t) => t.txid !== txid);
  saveTracked(list);
  renderTracked();
}

async function renderTracked() {
  const container = document.getElementById("trackedList");
  const list = loadTracked();
  container.innerHTML = "";

  if (list.length === 0) {
    container.innerHTML =
      '<p class="muted">Nenhuma transação rastreada ainda.</p>';
    return;
  }

  for (const tracked of list) {
    const item = document.createElement("div");
    item.className = "tracked-item";
    const txidShort =
      tracked.txid.slice(0, 16) + "…" + tracked.txid.slice(-8);

    item.innerHTML = `
      <div class="head">
        <span class="status-badge status-loading">consultando…</span>
        <button class="btn remove" data-txid="${tracked.txid}">Remover</button>
      </div>
      <div class="meta">wallet: <strong>${tracked.wallet}</strong></div>
      <div class="txid">${txidShort}</div>
      <div class="msg muted">consultando status…</div>
    `;
    container.appendChild(item);

    fetchTrackedStatus(item, tracked);
  }

  container.querySelectorAll(".remove").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      removeTrackedTx(ev.currentTarget.getAttribute("data-txid"));
    });
  });
}

async function fetchTrackedStatus(item, tracked) {
  try {
    const r = await fetch(`/api/tx/${encodeURIComponent(tracked.txid)}`);
    const data = await r.json();

    const status = data.status || "unknown";
    const badge = item.querySelector(".status-badge");
    badge.className = `status-badge status-${status}`;
    badge.textContent = status;

    const msgEl = item.querySelector(".msg");
    msgEl.classList.remove("muted");
    msgEl.textContent = data.message || "(sem mensagem)";

    if (data.warning) {
      const warn = document.createElement("div");
      warn.className = "warn";
      warn.textContent = "Aviso: " + data.warning;
      item.appendChild(warn);
    }

    if (data.confirmations !== undefined && data.confirmations !== null) {
      const conf = document.createElement("div");
      conf.className = "meta";
      conf.textContent = `confirmations: ${data.confirmations}`;
      item.appendChild(conf);
    }

    if (data.block_hash) {
      const bh = document.createElement("div");
      bh.className = "meta";
      bh.textContent = `block_hash: ${data.block_hash}`;
      item.appendChild(bh);
    }
  } catch (e) {
    const msgEl = item.querySelector(".msg");
    msgEl.classList.remove("muted");
    msgEl.textContent = "Erro ao consultar status: " + e.message;
  }
}

async function consultBlock() {
  const input = document.getElementById("blockHashInput");
  const out = document.getElementById("blockResult");
  const errEl = document.getElementById("blockError");

  hideError(errEl);
  out.textContent = "";

  const h = input.value.trim();
  if (!h) return showError(errEl, "Informe um blockhash.");

  try {
    const data = await apiGet(`/api/block/${encodeURIComponent(h)}`);
    out.textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    showError(errEl, e.message);
  }
}

async function consultTx() {
  const input = document.getElementById("txidInput");
  const out = document.getElementById("txResult");
  const errEl = document.getElementById("txError");

  hideError(errEl);
  out.textContent = "";

  const txid = input.value.trim();
  if (!txid) return showError(errEl, "Informe um txid.");

  try {
    const data = await apiGet(`/api/tx/${encodeURIComponent(txid)}`);
    out.textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    showError(errEl, e.message);
  }
}

document.getElementById("btnRefresh").addEventListener("click", () => {
  refreshNode();
  refreshMempoolSummary();
  refreshSyncStatus();
  refreshEventActivity();
  renderTracked();
});
document.getElementById("btnRecent").addEventListener("click", loadRecent);
document.getElementById("btnBlock").addEventListener("click", consultBlock);
document.getElementById("btnTx").addEventListener("click", consultTx);

document.getElementById("walletSelect").addEventListener("change", (ev) => {
  selectWallet(ev.target.value);
});
document.getElementById("btnTrackTx").addEventListener("click", addTrackedTx);
document.getElementById("trackTxidInput").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") addTrackedTx();
});
document
  .getElementById("btnRefreshTracked")
  .addEventListener("click", renderTracked);

// Carrega algo ao abrir
loadWallets();
refreshNode();
refreshMempoolSummary();
refreshSyncStatus();
refreshEventActivity();
loadRecent();
renderTracked();
