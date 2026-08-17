/* Monitor da Marca — nicho 2
   Dashboard client-side sobre data/industria.json: presença e preço
   da marca por rede e município. */
"use strict";

const fmt = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const $ = (id) => document.getElementById(id);

let MARCAS = [];

fetch("../data/industria.json")
  .then((r) => r.json())
  .then((d) => {
    MARCAS = d.marcas;
    montarSeletor();
    if (MARCAS.length) mostrar(MARCAS[0]);
  })
  .catch(() => {
    $("grade-marcas").innerHTML =
      "<p style='color:var(--alerta)'>Não foi possível carregar os dados. Recarregue a página.</p>";
  });

function montarSeletor() {
  const box = $("grade-marcas");
  for (const m of MARCAS) {
    const b = document.createElement("button");
    b.className = "btn-marca";
    b.innerHTML = m.marca + (m.pr ? ' <span class="selo-pr">PR</span>' : "");
    b.onclick = () => {
      box.querySelectorAll(".btn-marca").forEach((x) => x.classList.remove("ativo"));
      b.classList.add("ativo");
      mostrar(m);
    };
    box.appendChild(b);
  }
  const primeiro = box.querySelector(".btn-marca");
  if (primeiro) primeiro.classList.add("ativo");
}

function mostrar(m) {
  $("painel-marca").hidden = false;
  const f = (n) => n.toLocaleString("pt-BR");
  $("k-ofertas").textContent = f(m.n_ofertas);
  $("k-lojas").textContent = f(m.n_lojas);
  $("k-redes").textContent = f(Object.keys(m.redes).length);
  $("k-muns").textContent = f(m.n_muns);
  $("muns-marca").textContent = m.muns.join(" · ");

  // barras: preço mediano por rede
  const barras = $("barras-redes");
  barras.innerHTML = "";
  const redes = Object.entries(m.redes)
    .sort((a, b) => b[1].n - a[1].n).slice(0, 12)
    .sort((a, b) => a[1].med - b[1].med);
  const maxMed = Math.max(...redes.map(([, r]) => r.med));
  for (const [nome, r] of redes) {
    const linha = document.createElement("div");
    linha.className = "barra-linha";
    const pct = Math.max(4, (r.med / maxMed) * 100);
    linha.innerHTML =
      `<span class="rotulo" title="${nome}">${nome}</span>
       <div class="barra-trilho"><div class="barra-fill" style="width:${pct}%"></div></div>
       <span class="valor" title="mín ${fmt.format(r.min)} · máx ${fmt.format(r.max)} · ${r.n} ofertas">${fmt.format(r.med)}</span>`;
    barras.appendChild(linha);
  }

  // matriz produto × rede (menor preço observado)
  const redesCol = Object.entries(m.redes)
    .sort((a, b) => b[1].n - a[1].n).slice(0, 6).map(([nome]) => nome);
  const tab = $("matriz");
  const head = "<thead><tr><th>Produto</th>" +
    redesCol.map((r) => `<th>${r}</th>`).join("") + "</tr></thead>";
  const linhas = m.produtos.slice(0, 25).map((p) => {
    const precos = redesCol.map((r) => p.redes[r] ? p.redes[r].min : null);
    const validos = precos.filter((v) => v !== null);
    const menor = validos.length ? Math.min(...validos) : null;
    const tds = precos.map((v) =>
      v === null ? "<td>—</td>"
        : `<td class="${v === menor && validos.length > 1 ? "melhor" : ""}">${fmt.format(v)}</td>`
    ).join("");
    return `<tr><td>${p.desc}</td>${tds}</tr>`;
  }).join("");
  tab.innerHTML = head + "<tbody>" + linhas + "</tbody>";
}
