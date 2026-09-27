/* Carrinho por nicho — uma aba por nicho (data/nichos.json), busca
   client-side em data/nicho_<id>.json e otimização do carrinho:
   ranking de loja única, melhor dupla de lojas e melhor combinação,
   sempre com o endereço de onde comprar. */
"use strict";

const LIMITE_GRATIS = 10;
const fmt = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const $ = (id) => document.getElementById(id);

let NICHOS = [];
let nicho = null;                 // nicho ativo {id, nome, municipios}
const dados = new Map();          // id -> {categorias, produtos}
const carrinhos = new Map();      // id -> Map(idx produto -> {produto, qtd})
let catAtiva = null;

const norm = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase();
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const plural = (n, s, p) => `${n} ${n === 1 ? s : p}`;
const carrinho = () => carrinhos.get(nicho.id);
const mapa = (of) => "https://www.google.com/maps/search/?api=1&query=" +
  encodeURIComponent(`${of.fan}, ${of.end}, ${of.mun} - PR`);
const local = (of) =>
  `<small class="local">${esc(of.end)} · ${esc(of.mun)} · <a href="${mapa(of)}" target="_blank" rel="noopener">ver no mapa</a></small>`;

if (typeof document !== "undefined") fetch("../data/nichos.json")
  .then((r) => r.json())
  .then((n) => {
    NICHOS = n;
    const abas = $("abas");
    for (const x of NICHOS) {
      carrinhos.set(x.id, new Map());
      const b = document.createElement("button");
      b.className = "aba";
      b.dataset.id = x.id;
      b.innerHTML = `${esc(x.nome)} <span class="num">${x.n_produtos.toLocaleString("pt-BR")}</span>`;
      b.onclick = () => { location.hash = x.id; };
      abas.appendChild(b);
    }
    window.addEventListener("hashchange", abrirDoHash);
    abrirDoHash();
  })
  .catch(erroCarga);

function erroCarga() {
  $("resultados").innerHTML =
    "<p style='color:var(--alerta)'>Não foi possível carregar os dados. Recarregue a página.</p>";
}

function abrirDoHash() {
  const id = location.hash.slice(1);
  nicho = NICHOS.find((x) => x.id === id) || NICHOS[0];
  catAtiva = null;
  $("busca").value = "";
  document.querySelectorAll(".aba").forEach((b) =>
    b.classList.toggle("ativo", b.dataset.id === nicho.id));
  $("nome-nicho").textContent = nicho.nome;
  const sel = $("municipio");
  const atual = sel.value;
  sel.innerHTML = `<option value="">Todo o Paraná</option>` +
    nicho.municipios.map((m) => `<option>${esc(m)}</option>`).join("");
  sel.value = nicho.municipios.includes(atual) ? atual : "";
  carregar(nicho.id).then(() => { montarChips(); buscar(); atualizar(); }).catch(erroCarga);
}

function carregar(id) {
  if (dados.has(id)) return Promise.resolve();
  $("resultados").innerHTML = "<p class='dica'>Carregando…</p>";
  return fetch(`../data/nicho_${id}.json`).then((r) => r.json()).then((d) => {
    d.produtos = d.produtos.map((p, i) => ({ ...p, i, busca: norm(p.desc) }));
    dados.set(id, d);
  });
}

function montarChips() {
  const box = $("chips-cat");
  box.innerHTML = "";
  for (const [cid, nome] of Object.entries(dados.get(nicho.id).categorias)) {
    const b = document.createElement("button");
    b.className = "chip";
    b.textContent = nome;
    b.dataset.cid = cid;
    b.onclick = () => {
      catAtiva = catAtiva === cid ? null : cid;
      box.querySelectorAll(".chip").forEach((c) =>
        c.classList.toggle("ativo", c.dataset.cid === catAtiva));
      buscar();
    };
    box.appendChild(b);
  }
}

/* ofertas do produto dentro do município escolhido (já ordenadas por preço) */
function ofertasDe(p) {
  const mun = $("municipio").value;
  return mun ? p.ofertas.filter((o) => o.mun === mun) : p.ofertas;
}

function buscar() {
  const termos = norm($("busca").value).split(/\s+/).filter(Boolean);
  if (!termos.length && !catAtiva) { render([]); return; }
  let res = dados.get(nicho.id).produtos.filter((p) =>
    termos.every((t) => p.busca.includes(t)) && ofertasDe(p).length);
  if (catAtiva) res = res.filter((p) => String(p.cat) === catAtiva);
  res.sort((a, b) => ofertasDe(b).length - ofertasDe(a).length || ofertasDe(a)[0].v - ofertasDe(b)[0].v);
  render(res.slice(0, 30));
}
if (typeof document !== "undefined") {
  $("busca").addEventListener("input", buscar);
  $("municipio").addEventListener("change", () => { buscar(); atualizar(); });
  $("fechar-modal").onclick = () => $("modal-limite").close();
}

function render(res) {
  const box = $("resultados");
  box.innerHTML = "";
  if (!res.length) {
    box.innerHTML = "<p class='dica'>" + (($("busca").value || catAtiva)
      ? "Nada encontrado nesta aba e cidade. Tente outro termo."
      : "Digite o produto ou escolha uma categoria acima.") + "</p>";
    return;
  }
  for (const p of res) {
    const ofs = ofertasDe(p);
    const menor = ofs[0].v, maior = ofs[ofs.length - 1].v;
    const div = document.createElement("div");
    div.className = "item-res";
    div.innerHTML =
      `<span class="desc">${esc(p.desc)}</span>` +
      `<span class="faixa-preco">${menor === maior ? fmt.format(menor) : `${fmt.format(menor)} – ${fmt.format(maior)}`}</span>` +
      `<span class="n-lojas">${plural(ofs.length, "loja", "lojas")}</span>`;
    const b = document.createElement("button");
    b.className = "btn btn-vazado";
    b.style.cssText = "padding:5px 12px;font-size:0.78rem";
    b.textContent = carrinho().has(p.i) ? "no carrinho ✓" : "+ carrinho";
    b.disabled = carrinho().has(p.i);
    b.onclick = () => adicionar(p);
    div.appendChild(b);
    box.appendChild(div);
  }
}

function adicionar(p) {
  if (carrinho().size >= LIMITE_GRATIS) { $("modal-limite").showModal(); return; }
  carrinho().set(p.i, { produto: p, qtd: 1 });
  atualizar();
  buscar();
}
function atualizar() {
  const ul = $("lista");
  ul.innerHTML = "";
  $("lista-vazia").hidden = carrinho().size > 0;
  $("n-itens").textContent = carrinho().size;
  for (const [i, item] of carrinho()) {
    const li = document.createElement("li");
    li.innerHTML =
      `<div class="qtd"><button aria-label="menos">−</button><span>${item.qtd}</span><button aria-label="mais">+</button></div>
       <span style="flex:1">${esc(item.produto.desc)}</span>
       <button class="rm" aria-label="remover">×</button>`;
    const [menos, mais] = li.querySelectorAll(".qtd button");
    menos.onclick = () => { item.qtd = Math.max(1, item.qtd - 1); atualizar(); };
    mais.onclick = () => { item.qtd += 1; atualizar(); };
    li.querySelector(".rm").onclick = () => { carrinho().delete(i); atualizar(); buscar(); };
    ul.appendChild(li);
  }
  mostrarVeredito();
}

/* ---- otimização (pura: recebe itens [{ofertas, qtd}], devolve números) ---- */
const chaveLoja = (of) => `${of.fan}|${of.end}|${of.mun}`;

function otimizar(itens) {
  // preço de cada item em cada loja física
  const lojas = new Map();
  itens.forEach((it, idx) => {
    for (const of of it.ofertas) {
      const k = chaveLoja(of);
      if (!lojas.has(k)) lojas.set(k, { of, precos: new Map() });
      const reg = lojas.get(k);
      if (!reg.precos.has(idx) || of.v < reg.precos.get(idx)) reg.precos.set(idx, of.v);
    }
  });
  const custo = (conj) => {
    let cobre = 0, total = 0;
    itens.forEach((it, idx) => {
      const vs = conj.map((l) => l.precos.get(idx)).filter((v) => v !== undefined);
      if (vs.length) { cobre++; total += Math.min(...vs) * it.qtd; }
    });
    return { cobre, total };
  };
  const melhorQue = (a, b) => a.cobre > b.cobre || (a.cobre === b.cobre && a.total < b.total);

  const ranking = [...lojas.values()].map((l) => ({ lojas: [l], ...custo([l]) }))
    .sort((a, b) => (melhorQue(a, b) ? -1 : melhorQue(b, a) ? 1 : 0));

  // melhor dupla: só entre as 40 lojas mais bem ranqueadas (ponytail: O(n²), basta p/ 10 itens)
  const top = ranking.slice(0, 40).map((r) => r.lojas[0]);
  let dupla = null;
  for (let a = 0; a < top.length; a++)
    for (let b = a + 1; b < top.length; b++) {
      const c = { lojas: [top[a], top[b]], ...custo([top[a], top[b]]) };
      if (!dupla || melhorQue(c, dupla)) dupla = c;
    }

  // combinação livre: cada item na loja mais barata
  const grupos = new Map();
  const semOferta = [];
  let total = 0, pior = 0;
  itens.forEach((it, idx) => {
    if (!it.ofertas.length) { semOferta.push(idx); return; }
    const m = it.ofertas[0];
    total += m.v * it.qtd;
    pior += it.ofertas[it.ofertas.length - 1].v * it.qtd;
    const k = chaveLoja(m);
    if (!grupos.has(k)) grupos.set(k, { of: m, itens: [], total: 0 });
    const g = grupos.get(k);
    g.itens.push({ idx, v: m.v });
    g.total += m.v * it.qtd;
  });
  return { ranking, dupla, combo: { grupos: [...grupos.values()], total, pior, semOferta } };
}

function mostrarVeredito() {
  const box = $("veredito");
  if (!carrinho().size) { box.hidden = true; return; }
  box.hidden = false;
  const itens = [...carrinho().values()].map((x) => ({ ...x, ofertas: ofertasDe(x.produto) }));
  const { ranking, dupla, combo } = otimizar(itens);
  const n = itens.length;
  const falta = (c) => n - c.cobre
    ? `<br><small class="falta">não tem ${plural(n - c.cobre, "item", "itens")} do carrinho</small>` : "";

  // 1. onde o carrinho inteiro sai mais barato (loja única)
  $("loja-unica").innerHTML = ranking.length
    ? `<h4 class="sub">Uma loja só</h4>` + ranking.slice(0, 3).map((r, k) =>
      `<div class="linha${k === 0 ? " vencedor" : ""}"><span>${k + 1}º ${esc(r.lojas[0].of.fan)}
         <br>${local(r.lojas[0].of)}${falta(r)}</span><b class="num">${fmt.format(r.total)}</b></div>`).join("")
    : "";

  // 2. melhor dupla, quando a combinação livre pede mais de 2 lojas
  $("dupla").innerHTML = dupla && combo.grupos.length > 2
    ? `<h4 class="sub">Duas lojas</h4><div class="linha"><span>` +
      dupla.lojas.map((l) => `${esc(l.of.fan)}<br>${local(l.of)}`).join("<br>") +
      `${falta(dupla)}</span><b class="num">${fmt.format(dupla.total)}</b></div>`
    : "";

  // 3. menor preço item a item
  const comboDiv = $("combo");
  comboDiv.innerHTML =
    `<h4 class="sub">Menor preço item a item</h4><div class="linha"><span>${plural(combo.grupos.length, "loja", "lojas")}</span>` +
    `<b class="num">${fmt.format(combo.total)}</b></div>`;
  for (const g of combo.grupos.sort((a, b) => b.total - a.total)) {
    const gd = document.createElement("div");
    gd.className = "grupo-loja";
    gd.innerHTML = `<h4>${esc(g.of.fan)}<span class="num">${fmt.format(g.total)}</span></h4>${local(g.of)}` +
      `<ul>${g.itens.map((x) => `<li><span>${itens[x.idx].qtd}× ${esc(itens[x.idx].produto.desc)}</span>` +
        `<span class="num">${fmt.format(x.v * itens[x.idx].qtd)}</span></li>`).join("")}</ul>`;
    comboDiv.appendChild(gd);
  }
  if (combo.semOferta.length) {
    comboDiv.insertAdjacentHTML("beforeend", `<p class="falta">Sem oferta em ${esc($("municipio").value || "nenhuma loja")}: ` +
      combo.semOferta.map((i) => esc(itens[i].produto.desc)).join("; ") + "</p>");
  }

  const eco = combo.pior - combo.total;
  $("economia").innerHTML = eco > 0.01
    ? `Comprando nos lugares certos você economiza até <b class="num">${fmt.format(eco)}</b>
       (${Math.round((eco / combo.pior) * 100)}% sobre o pior preço observado).`
    : "Preços praticamente iguais entre as lojas para este carrinho.";
}

/* self-check: node assets/js/carrinho.js --teste  (sem DOM) */
if (typeof window === "undefined") {
  const A = { fan: "A", end: "r1", mun: "X" }, B = { fan: "B", end: "r2", mun: "X" }, C = { fan: "C", end: "r3", mun: "X" };
  const o = (l, v) => ({ ...l, v });
  const r = otimizar([
    { qtd: 2, ofertas: [o(A, 1), o(B, 2)] },
    { qtd: 1, ofertas: [o(B, 5), o(A, 9)] },
    { qtd: 1, ofertas: [o(C, 3)] },
  ]);
  const assert = (c, m) => { if (!c) throw new Error(m); };
  assert(r.ranking[0].lojas[0].of.fan === "B" && r.ranking[0].total === 9, "loja única: B cobre 2 por 9");
  assert(r.dupla.cobre === 3 && r.dupla.total === 12 && r.dupla.lojas.map((l) => l.of.fan).join() === "B,C", "dupla B+C");
  assert(r.combo.total === 10 && r.combo.grupos.length === 3 && r.combo.pior === 16, "combo");
  console.log("ok");
}
