/* Orçamento de Obra — nicho 1
   Busca client-side sobre data/construcao.json, lista de obra com
   quantidades e otimização: melhor loja única + melhor combinação. */
"use strict";

const LIMITE_GRATIS = 10;
const fmt = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

let PRODUTOS = [];
let CATEGORIAS = {};
let catAtiva = null;
const lista = new Map(); // idx produto -> {produto, qtd}

const $ = (id) => document.getElementById(id);

function norm(s) {
  return (s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
}

fetch("../data/construcao.json")
  .then((r) => r.json())
  .then((d) => {
    CATEGORIAS = d.categorias;
    PRODUTOS = d.produtos.map((p, i) => ({ ...p, i, busca: norm(p.desc) }));
    montarChips();
    render([]);
  })
  .catch(() => {
    $("resultados").innerHTML =
      "<p style='color:var(--alerta)'>Não foi possível carregar os dados. Recarregue a página.</p>";
  });

function montarChips() {
  const box = $("chips-cat");
  for (const [cid, nome] of Object.entries(CATEGORIAS)) {
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

function buscar() {
  const termos = norm($("busca").value).split(/\s+/).filter(Boolean);
  if (!termos.length && !catAtiva) { render([]); return; }
  let res = PRODUTOS.filter((p) => termos.every((t) => p.busca.includes(t)));
  if (catAtiva) res = res.filter((p) => String(p.cat) === catAtiva);
  res.sort((a, b) => b.ofertas.length - a.ofertas.length || a.menor - b.menor);
  render(res.slice(0, 30));
}
$("busca").addEventListener("input", buscar);

function render(res) {
  const box = $("resultados");
  box.innerHTML = "";
  if (!res.length) {
    box.innerHTML = "<p style='font-size:0.85rem;color:var(--tinta-fraca)'>" +
      (($("busca").value || catAtiva)
        ? "Nada encontrado. Tente outro termo (ex.: “cimento”, “tinta”, “tubo”)."
        : "Digite o material ou escolha uma categoria acima.") + "</p>";
    return;
  }
  for (const p of res) {
    const div = document.createElement("div");
    div.className = "item-res";
    const faixa = p.menor === p.maior
      ? fmt.format(p.menor)
      : `${fmt.format(p.menor)} – ${fmt.format(p.maior)}`;
    div.innerHTML =
      `<span class="desc">${p.desc}</span>` +
      `<span class="faixa-preco">${faixa}</span>` +
      `<span class="n-lojas">${p.ofertas.length} loja${p.ofertas.length > 1 ? "s" : ""}</span>`;
    const b = document.createElement("button");
    b.className = "btn btn-vazado";
    b.style.cssText = "padding:5px 12px;font-size:0.78rem";
    b.textContent = lista.has(p.i) ? "na lista ✓" : "+ lista";
    b.disabled = lista.has(p.i);
    b.onclick = () => adicionar(p);
    div.appendChild(b);
    box.appendChild(div);
  }
}

function adicionar(p) {
  if (lista.size >= LIMITE_GRATIS) { $("modal-limite").showModal(); return; }
  lista.set(p.i, { produto: p, qtd: 1 });
  atualizar();
  buscar();
}

$("fechar-modal").onclick = () => $("modal-limite").close();

function atualizar() {
  const ul = $("lista");
  ul.innerHTML = "";
  $("lista-vazia").hidden = lista.size > 0;
  $("n-itens").textContent = lista.size;
  for (const [i, item] of lista) {
    const li = document.createElement("li");
    li.innerHTML =
      `<div class="qtd">
         <button aria-label="menos">−</button><span>${item.qtd}</span><button aria-label="mais">+</button>
       </div>
       <span style="flex:1">${item.produto.desc}</span>
       <button class="rm" aria-label="remover">×</button>`;
    const [menos, mais] = li.querySelectorAll(".qtd button");
    menos.onclick = () => { item.qtd = Math.max(1, item.qtd - 1); atualizar(); };
    mais.onclick = () => { item.qtd += 1; atualizar(); };
    li.querySelector(".rm").onclick = () => { lista.delete(i); atualizar(); buscar(); };
    ul.appendChild(li);
  }
  otimizar();
}

/* ---- otimização ---- */
function otimizar() {
  const box = $("veredito");
  if (!lista.size) { box.hidden = true; return; }
  box.hidden = false;

  const itens = [...lista.values()];

  // melhor loja única: loja física (fan+end) que cobre mais itens, menor total
  const porLoja = new Map();
  itens.forEach((item, idx) => {
    for (const of of item.produto.ofertas) {
      const k = `${of.fan}|${of.end}|${of.mun}`;
      let reg = porLoja.get(k);
      if (!reg) { reg = { of, itens: new Map() }; porLoja.set(k, reg); }
      const atual = reg.itens.get(idx);
      if (!atual || of.v < atual) reg.itens.set(idx, of.v);
    }
  });
  let melhor = null;
  for (const reg of porLoja.values()) {
    let total = 0;
    for (const [idx, v] of reg.itens) total += v * itens[idx].qtd;
    const cand = { reg, cobre: reg.itens.size, total };
    if (!melhor || cand.cobre > melhor.cobre ||
        (cand.cobre === melhor.cobre && cand.total < melhor.total)) melhor = cand;
  }

  const luDiv = $("loja-unica");
  if (melhor) {
    const faltam = itens.length - melhor.cobre;
    luDiv.innerHTML =
      `<div class="linha"><span>Melhor loja única
         <br><small style="color:var(--tinta-fraca)">${melhor.reg.of.fan} — ${melhor.reg.of.mun}</small>
         ${faltam ? `<br><small style="color:var(--alerta)">não tem ${faltam} ite${faltam > 1 ? "ns" : "m"} da lista</small>` : ""}
       </span><b class="num">${fmt.format(melhor.total)}</b></div>`;
  } else luDiv.innerHTML = "";

  // melhor combinação: menor preço por item, agrupado por loja
  const grupos = new Map();
  let totalCombo = 0, totalPior = 0;
  itens.forEach((item) => {
    const ofs = item.produto.ofertas;
    const melhorOf = ofs[0]; // já ordenado por preço no build
    const piorOf = ofs[ofs.length - 1];
    totalCombo += melhorOf.v * item.qtd;
    totalPior += piorOf.v * item.qtd;
    const k = `${melhorOf.fan} — ${melhorOf.mun}`;
    if (!grupos.has(k)) grupos.set(k, { itens: [], total: 0 });
    const g = grupos.get(k);
    g.itens.push({ desc: item.produto.desc, v: melhorOf.v, qtd: item.qtd });
    g.total += melhorOf.v * item.qtd;
  });

  const comboDiv = $("combo");
  comboDiv.innerHTML =
    `<div class="linha" style="margin-top:8px"><span>Melhor combinação
       <br><small style="color:var(--tinta-fraca)">${grupos.size} loja${grupos.size > 1 ? "s" : ""}</small>
     </span><b class="num">${fmt.format(totalCombo)}</b></div>`;
  for (const [nome, g] of grupos) {
    const gd = document.createElement("div");
    gd.className = "grupo-loja";
    gd.innerHTML = `<h4>${nome}<span class="num">${fmt.format(g.total)}</span></h4>` +
      `<ul>${g.itens.map((x) =>
        `<li><span>${x.qtd}× ${x.desc}</span><span class="num">${fmt.format(x.v * x.qtd)}</span></li>`).join("")}</ul>`;
    comboDiv.appendChild(gd);
  }

  const eco = totalPior - totalCombo;
  $("economia").innerHTML = eco > 0.01
    ? `Comprando nos lugares certos você economiza até
       <b class="num">${fmt.format(eco)}</b> nesta lista
       (${Math.round((eco / totalPior) * 100)}% sobre o pior cenário observado).`
    : "Preços praticamente iguais entre as lojas para esta lista.";
}
