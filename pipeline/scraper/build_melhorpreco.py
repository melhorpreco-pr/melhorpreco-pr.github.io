# -*- coding: utf-8 -*-
"""Agrega os JSONL brutos nos JSONs do site melhorpreco-pr.github.io.

Lê TODOS os data/raw/ofertas_*.jsonl (dedup por id), limpa registros-isca
residuais e produz três arquivos para os dois nichos:

  <repo>/data/nichos.json       # índice das abas do carrinho
  <repo>/data/nicho_<id>.json   # produtos + ofertas de cada nicho (carrinho)
  <repo>/data/industria.json    # monitor de marca
  <repo>/data/meta.json

Uso:
  py -3 pipeline/scraper/build_melhorpreco.py [--repo .] [--max-dias 30]
"""
import argparse
import collections
import datetime
import json
import pathlib
import re
import unicodedata

# Abas do carrinho: id -> (nome, categorias). Uma categoria pode estar em
# mais de um nicho (ex.: 43 materiais elétricos serve obra e eletrônicos).
NICHOS = {
    "mercado": ("Mercado", {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 22, 54, 55,
                            58, 60, 61, 63}),
    "farmacia": ("Farmácia", {19, 21, 62}),
    "construcao": ("Construção", {16, 18, 20, 23, 26, 29, 39, 40, 42, 43}),
    "eletronicos": ("Eletrônicos", {43, 48}),
    "pet": ("Pet", {14}),
    "casa": ("Casa e jardim", {3, 35, 52}),
}
CATS_INDUSTRIA = {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 21, 22, 54, 55, 62, 63}
MAX_OFERTAS_POR_PRODUTO = 25  # folga para o filtro por município
PRECO_MAXIMO_PLAUSIVEL = 100_000.0
MIN_OFERTAS = 300  # abaixo disso a coleta falhou (ex.: IP em isca); não publica

# Marcas com fábrica ou sede no Paraná (destaque do nicho 2)
MARCAS_PR = [
    "FRIMESA", "COAMO", "COPACOL", "C VALE", "CVALE", "LAR", "CASTROLANDA",
    "BATAVO", "FRISIA", "INTEGRADA", "COCAMAR", "COROL", "CONFEPAR",
    "NUTRIMENTAL", "WITMARSUM", "DAMASCO", "IGUACU", "OURO FINO", "PRIMATO",
]
MARCAS_NACIONAIS = [
    "NESTLE", "ITALAC", "PIRACANJUBA", "ITAMBE", "DANONE", "VIGOR", "PARMALAT",
    "ELEGE", "TIROL", "AURORA", "SADIA", "PERDIGAO", "SEARA", "FRIBOI", "SWIFT",
    "MAGGI", "KNORR", "HELLMANNS", "HEINZ", "FUGINI", "QUERO", "ELEFANTE",
    "POMAROLA", "UNIAO", "CAMIL", "TIO JOAO", "URBANO", "YOKI", "DONA BENTA",
    "RENATA", "GALO", "ADRIA", "BARILLA", "ISABELA", "PANCO", "BAUDUCCO",
    "MARILAN", "NISSIN", "VITARELLA", "GAROTO", "LACTA", "ARCOR", "HERSHEYS",
    "COCA COLA", "PEPSI", "ANTARCTICA", "SKOL", "BRAHMA", "HEINEKEN", "AMSTEL",
    "BUDWEISER", "ITAIPAVA", "PETRA", "CRYSTAL", "DEL VALLE", "MAGUARY",
    "NATURAL ONE", "MELITTA", "3 CORACOES", "PILAO", "OMO", "ARIEL", "TIXAN",
    "YPE", "LIMPOL", "MINUANO", "VEJA", "PINHO SOL", "QBOA", "BOMBRIL",
    "ASSOLAN", "DOWNY", "COMFORT", "VANISH", "COLGATE", "ORAL B", "SORRISO",
    "CLOSE UP", "PROTEX", "DOVE", "LUX", "NIVEA", "REXONA", "HUGGIES",
    "PAMPERS", "MILI", "PANTENE", "SEDA", "CLEAR", "HHEAD SHOULDERS",
]

# Nome de exibição (com acento) das marcas normalizadas
MARCA_DISPLAY = {
    "C VALE": "C.Vale", "IGUACU": "Café Iguaçu", "PERDIGAO": "Perdigão",
    "NESTLE": "Nestlé", "ELEGE": "Elegê", "ITAMBE": "Itambé", "UNIAO": "União",
    "TIO JOAO": "Tio João", "3 CORACOES": "3 Corações", "PILAO": "Pilão",
    "YPE": "Ypê", "HELLMANNS": "Hellmann's", "ORAL B": "Oral-B",
    "HERSHEYS": "Hershey's", "CLOSE UP": "Close Up", "ATACADAO": "Atacadão",
    "SADIA": "Sadia", "AMIGAO": "Amigão", "FRISIA": "Frísia",
}

# Redes de varejo conhecidas (normalização de nm_fan/nm_emp)
REDES = [
    ("CONDOR", "Condor"),
    ("MUFFATO", "Grupo Muffato"),
    ("MAX ATACADISTA", "Grupo Muffato"),
    ("FESTVAL", "Festval"),
    ("BEAL", "Festval"),
    ("ASSAI", "Assaí"),
    ("ATACADAO", "Atacadão"),
    ("CARREFOUR", "Carrefour"),
    ("SAMS CLUB", "Sam's Club"),
    ("JACOMAR", "Jacomar"),
    ("TISSI", "Tissi"),
    ("VISCARDI", "Viscardi"),
    ("AMIGAO", "Amigão"),
    ("CIDADE CANCAO", "Cidade Canção"),
    ("SUPER PAO", "Superpão"),
    ("SUPERPAO", "Superpão"),
    ("VERDE MAIS", "Verde Mais"),
    ("COPACOL", "Copacol (varejo)"),
    ("LAR COOPERATIVA", "Lar (varejo)"),
    ("HAVAN", "Havan"),
    ("BALAROTI", "Balaroti"),
    ("CASSOL", "Cassol"),
    ("LEROY MERLIN", "Leroy Merlin"),
    ("OBARA", "Obara"),
    ("TELHANORTE", "Telhanorte"),
]


def sem_acento(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in t if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    return " ".join(sem_acento(texto).upper().replace("-", " ")
                    .replace("'", "").replace(".", " ").split())


_MARCA_RE = None


def detectar_marca(desc_norm: str) -> tuple[str, bool] | None:
    """Retorna (marca, eh_pr) se alguma marca conhecida aparece na descrição."""
    global _MARCA_RE
    if _MARCA_RE is None:
        todas = sorted(MARCAS_PR + MARCAS_NACIONAIS, key=len, reverse=True)
        _MARCA_RE = re.compile(r"\b(" + "|".join(re.escape(m) for m in todas) + r")\b")
    m = _MARCA_RE.search(desc_norm)
    if not m:
        return None
    marca = m.group(1)
    if marca == "CVALE":
        marca = "C VALE"
    return marca, marca in MARCAS_PR


def rede_de(est: dict) -> str:
    nome = normalizar(est.get("nm_fan") or est.get("nm_emp") or "")
    for chave, rede in REDES:
        if chave in nome:
            return rede
    return (est.get("nm_fan") or est.get("nm_emp") or "Independente").title()


def endereco(est: dict) -> str:
    partes = [est.get("tp_logr", ""), est.get("nm_logr", "")]
    rua = " ".join(p for p in partes if p).title()
    nr = est.get("nr_logr", "")
    bairro = (est.get("bairro") or "").title()
    return ", ".join(p for p in [f"{rua} {nr}".strip(), bairro] if p)


def oferta_valida(o: dict) -> bool:
    try:
        v = float(o.get("valor") or 0)
    except (TypeError, ValueError):
        return False
    if not (0 < v <= PRECO_MAXIMO_PLAUSIVEL):
        return False
    # isca: milissegundos .669Z constantes em lote envenenado
    dh = o.get("datahora") or ""
    if dh.endswith(".669Z"):
        return False
    return True


def produtos_por_categoria(ofertas: list[dict]) -> list[dict]:
    """Agrupa ofertas por produto (GTIN ou descrição), 1 oferta por loja física."""
    produtos = {}
    for o in ofertas:
        cid = o.get("_tipo_id")
        est = o.get("estabelecimento") or {}
        mun = (est.get("mun") or "").title()
        if not mun or mun.isdigit():
            continue
        gtin = (o.get("gtin") or "").strip()
        chave = gtin if gtin and gtin != "SEM GTIN" else "D:" + normalizar(o.get("desc"))
        p = produtos.setdefault((cid, chave), {
            "gtin": gtin or None, "desc": (o.get("desc") or "").strip(), "cat": cid,
            "ofertas": []})
        p["ofertas"].append({
            "v": round(float(o.get("valor")), 2),
            "loja": rede_de(est),
            "fan": (est.get("nm_fan") or est.get("nm_emp") or "").title(),
            "mun": mun,
            "end": endereco(est),
            "dt": (o.get("datahora") or "")[:10],
        })
    lista = []
    for p in produtos.values():
        p["ofertas"].sort(key=lambda x: x["v"])
        unicas, chaves = [], set()
        for of in p["ofertas"]:
            k = (of["fan"], of["end"], of["mun"])
            if k in chaves:
                continue
            chaves.add(k)
            unicas.append(of)
            if len(unicas) >= MAX_OFERTAS_POR_PRODUTO:
                break
        p["ofertas"] = unicas
        p["menor"] = unicas[0]["v"]
        p["maior"] = unicas[-1]["v"]
        lista.append(p)
    lista.sort(key=lambda p: (p["cat"], p["desc"]))
    return lista


def main():
    ap = argparse.ArgumentParser()
    base = pathlib.Path(__file__).parent.parent
    ap.add_argument("--repo", default=str(base.parent))
    ap.add_argument("--max-dias", type=int, default=None,
                    help="descarta ofertas (e apaga arquivos brutos) mais velhas que N dias")
    args = ap.parse_args()
    corte = ""
    if args.max_dias:
        corte = (datetime.date.today() - datetime.timedelta(days=args.max_dias)).isoformat()
    out_dir = pathlib.Path(args.repo) / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    vistos = set()
    ofertas = []
    n_lidas = n_descartadas = 0
    for raw in sorted((base / "data" / "raw").glob("ofertas_*.jsonl")):
        data_arq = raw.stem.split("_")[1]  # ofertas_YYYYMMDD[_sufixo]
        if corte and f"{data_arq[:4]}-{data_arq[4:6]}-{data_arq[6:8]}" < corte:
            raw.unlink()
            raw.with_name(raw.name.replace("ofertas_", "checkpoint_").replace(".jsonl", ".json")).unlink(missing_ok=True)
            continue
        with raw.open(encoding="utf-8") as fh:
            for linha in fh:
                try:
                    o = json.loads(linha)
                except json.JSONDecodeError:
                    continue
                n_lidas += 1
                if o.get("id") in vistos or o.get("_tipo") not in ("categoria", "termo"):
                    continue
                vistos.add(o.get("id"))
                if not oferta_valida(o) or (o.get("datahora") or "")[:10] < corte:
                    n_descartadas += 1
                    continue
                ofertas.append(o)

    if len(ofertas) < MIN_OFERTAS:
        raise SystemExit(f"só {len(ofertas)} ofertas válidas (< {MIN_OFERTAS}); "
                         "mantendo os dados publicados")

    # ---------- carrinhos por nicho ----------
    produtos = produtos_por_categoria(ofertas)
    cats_nomes = json.loads((base / "data" / "categorias.json").read_text(encoding="utf-8"))
    indice = []
    for nid, (nome, cats) in NICHOS.items():
        lista = [p for p in produtos if p["cat"] in cats]
        if not lista:
            continue
        muns = sorted({of["mun"] for p in lista for of in p["ofertas"]} - {""})
        (out_dir / f"nicho_{nid}.json").write_text(json.dumps({
            "categorias": {k: v for k, v in cats_nomes.items() if int(k) in cats},
            "produtos": lista,
        }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        indice.append({"id": nid, "nome": nome, "n_produtos": len(lista), "municipios": muns})
    (out_dir / "nichos.json").write_text(
        json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------- nicho 2: indústria ----------
    marcas = {}
    redes_geral = collections.Counter()
    muns_geral = collections.Counter()
    for o in ofertas:
        cid = o.get("_tipo_id")
        if cid not in CATS_INDUSTRIA:
            continue
        est = o.get("estabelecimento") or {}
        rede = rede_de(est)
        mun = (est.get("mun") or "").title()
        redes_geral[rede] += 1
        muns_geral[mun] += 1
        det = detectar_marca(normalizar(o.get("desc")))
        if not det:
            continue
        nome, eh_pr = det
        v = round(float(o.get("valor")), 2)
        m = marcas.setdefault(nome, {
            "marca": MARCA_DISPLAY.get(nome, nome.title()), "pr": eh_pr, "n_ofertas": 0,
            "lojas": set(), "muns": set(), "redes": {}, "produtos": {}})
        m["n_ofertas"] += 1
        m["lojas"].add((est.get("nm_fan") or "", est.get("nr_logr") or "", mun))
        m["muns"].add(mun)
        r = m["redes"].setdefault(rede, [])
        r.append(v)
        gtin = (o.get("gtin") or "").strip()
        pk = gtin if gtin and gtin != "SEM GTIN" else "D:" + normalizar(o.get("desc"))
        prod = m["produtos"].setdefault(pk, {"desc": o.get("desc"), "redes": {}})
        pr = prod["redes"].setdefault(rede, [])
        pr.append(v)

    lista_m = []
    for m in marcas.values():
        if m["n_ofertas"] < 5:
            continue
        redes_out = {}
        for rede, vals in m["redes"].items():
            vals.sort()
            redes_out[rede] = {
                "n": len(vals),
                "min": vals[0],
                "med": round(vals[len(vals) // 2], 2),
                "max": vals[-1],
            }
        prods = []
        for prod in m["produtos"].values():
            linhas = {rede: {"min": min(v), "max": max(v), "n": len(v)}
                      for rede, v in prod["redes"].items()}
            todas = [x for v in prod["redes"].values() for x in v]
            prods.append({"desc": prod["desc"], "redes": linhas,
                          "min": min(todas), "max": max(todas), "n": len(todas)})
        prods.sort(key=lambda p: -p["n"])
        lista_m.append({
            "marca": m["marca"], "pr": m["pr"], "n_ofertas": m["n_ofertas"],
            "n_lojas": len(m["lojas"]), "n_muns": len(m["muns"]),
            "muns": sorted(m["muns"]), "redes": redes_out,
            "produtos": prods[:40],
        })
    lista_m.sort(key=lambda m: (-m["pr"], -m["n_ofertas"]))

    (out_dir / "industria.json").write_text(json.dumps({
        "marcas": lista_m,
        "redes": dict(redes_geral.most_common(30)),
        "municipios": dict(muns_geral.most_common(60)),
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    muns_cobertos = sorted({(o.get("estabelecimento") or {}).get("mun", "").title()
                            for o in ofertas} - {""})
    (out_dir / "meta.json").write_text(json.dumps({
        "fonte": "Menor Preço Nota Paraná (SEFA-PR) — notas fiscais reais",
        "atualizado_em": datetime.date.today().isoformat(),
        "n_ofertas": len(ofertas),
        "n_produtos": len(produtos),
        "nichos": {n["id"]: n["n_produtos"] for n in indice},
        "n_marcas": len(lista_m),
        "n_municipios": len(muns_cobertos),
        "municipios": muns_cobertos,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{n_lidas} lidas | {n_descartadas} descartadas (isca/inválidas) | "
          f"{len(ofertas)} válidas")
    print(" | ".join(f"{n['id']}: {n['n_produtos']}" for n in indice))
    print(f"indústria: {len(lista_m)} marcas | "
          f"{len(muns_cobertos)} municípios")
    for f in [f"nicho_{n['id']}.json" for n in indice] + ["industria.json", "meta.json"]:
        kb = (out_dir / f).stat().st_size / 1024
        print(f"  {f}: {kb:.0f} KB")


if __name__ == "__main__":
    main()
