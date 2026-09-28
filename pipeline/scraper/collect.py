# -*- coding: utf-8 -*-
"""Coletor de ofertas do Menor Preço para Curitiba + RMC.

Varre categorias (termo vazio) e combustíveis a partir de pontos de coleta
com raio de 20 km, deduplicando por id da oferta.

Uso:
  py -3 scraper/collect.py --sample            # amostra: 3 páginas por consulta
  py -3 scraper/collect.py                     # coleta completa
  py -3 scraper/collect.py --categorias 6 7    # só as categorias indicadas
  py -3 scraper/collect.py --termos --pontos curitiba_centro   # busca por termo

Por que --termos: a varredura por categoria com termo vazio devolve só as
~500 ofertas mais baratas da categoria (hambúrguer 56 g, steak 100 g...), então
itens caros como picanha nunca entram. A busca por termo (data/termos.json)
alcança esses produtos.

Saída: data/raw/ofertas_YYYYMMDD.jsonl (uma oferta por linha, UTF-8)
"""
import argparse
import datetime
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from menorpreco_api import (  # noqa: E402
    RITMO_SEGURO, RespostaEnvenenada, TP_COMB, geohash_encode, iter_ofertas,
)

# Pontos de coleta cobrindo as cidades-polo do Paraná (raio 20 km cada).
# A malha prioriza concentração de varejo, não cobertura geográfica total:
# 20 km em torno de cada polo alcança a quase totalidade dos CNPJs emissores.
PONTOS = {
    "curitiba_centro": (-25.4284, -49.2733),
    "rmc_norte": (-25.2400, -49.2200),      # Colombo / Alm. Tamandaré / Rio Branco do Sul
    "rmc_sul": (-25.6600, -49.2000),        # Fazenda Rio Grande / Mandirituba / SJP sul
    "rmc_oeste": (-25.4600, -49.5300),      # Campo Largo / Balsa Nova / Araucária
    "rmc_leste": (-25.4400, -49.0300),      # Piraquara / Quatro Barras / Campina Grande do Sul
    "paranagua": (-25.5205, -48.5095),      # litoral
    "ponta_grossa": (-25.0945, -50.1633),
    "castro": (-24.7891, -50.0110),
    "telemaco_borba": (-24.3245, -50.6176),
    "irati": (-25.4697, -50.6510),
    "uniao_da_vitoria": (-26.2273, -51.0870),
    "guarapuava": (-25.3907, -51.4628),
    "laranjeiras_do_sul": (-25.4079, -52.4160),
    "pato_branco": (-26.2292, -52.6706),
    "francisco_beltrao": (-26.0812, -53.0550),
    "dois_vizinhos": (-25.7338, -53.0570),
    "cascavel": (-24.9578, -53.4595),
    "foz_do_iguacu": (-25.5478, -54.5882),
    "medianeira": (-25.2955, -54.0938),
    "toledo": (-24.7199, -53.7433),
    "guaira": (-24.0798, -54.2575),
    "umuarama": (-23.7661, -53.3250),
    "cianorte": (-23.6634, -52.6050),
    "campo_mourao": (-24.0463, -52.3780),
    "paranavai": (-23.0816, -52.4617),
    "maringa": (-23.4205, -51.9331),
    "apucarana": (-23.5507, -51.4635),
    "arapongas": (-23.4153, -51.4259),
    "londrina": (-23.3045, -51.1696),
    "cornelio_procopio": (-23.1810, -50.6474),
    "santo_antonio_platina": (-23.2950, -50.0774),
    "jacarezinho": (-23.1609, -49.9739),
    "ivaipora": (-24.2485, -51.6754),
}


def carregar_taxonomia(data_dir: pathlib.Path) -> dict:
    path = data_dir / "categorias.json"
    if not path.exists():
        raise SystemExit("Rode antes: py -3 scraper/discover_taxonomy.py")
    return {int(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="limita a 3 páginas por consulta")
    ap.add_argument("--max-paginas", type=int, default=None)
    ap.add_argument("--categorias", type=int, nargs="*", default=None)
    ap.add_argument("--sem-combustivel", action="store_true")
    ap.add_argument("--fatia", default=None,
                    help="i/n: só os termos de índice i mod n (divide a coleta entre execuções)")
    ap.add_argument("--termos", action="store_true",
                    help="coleta pelos termos de data/termos.json (máx 2 páginas/termo)")
    ap.add_argument("--pontos", nargs="*", default=None,
                    help=f"subconjunto de pontos: {', '.join(PONTOS)}")
    ap.add_argument("--pausa", type=float, default=RITMO_SEGURO,
                    help="pausa entre requisições (s); < 3 s dispara o anti-bot")
    args = ap.parse_args()

    max_paginas = 3 if args.sample else args.max_paginas
    if args.termos and max_paginas is None:
        max_paginas = 2  # ordem=0 traz o mais barato primeiro; 2 páginas bastam

    base = pathlib.Path(__file__).parent.parent
    data_dir = base / "data"
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    taxonomia = carregar_taxonomia(data_dir)
    cat_ids = args.categorias if args.categorias else sorted(taxonomia)

    hoje = datetime.date.today().strftime("%Y%m%d")
    sufixo = "_sample" if args.sample else "_termos" if args.termos else ""
    out_path = raw_dir / f"ofertas_{hoje}{sufixo}.jsonl"
    ckpt_path = raw_dir / f"checkpoint_{hoje}{sufixo}.json"

    # retomada: recarrega ids já gravados e consultas já concluídas
    vistos = set()
    feitas = set()
    if out_path.exists():
        with out_path.open(encoding="utf-8") as fh:
            for linha in fh:
                try:
                    vistos.add(json.loads(linha).get("id"))
                except json.JSONDecodeError:
                    pass
    if ckpt_path.exists():
        feitas = set(json.loads(ckpt_path.read_text(encoding="utf-8")))
        print(f"Retomando: {len(feitas)} consultas concluídas, {len(vistos)} ofertas já gravadas")

    def marcar_feita(chave):
        feitas.add(chave)
        ckpt_path.write_text(json.dumps(sorted(feitas)), encoding="utf-8")

    n_gravadas = 0
    t0 = time.time()
    with out_path.open("a", encoding="utf-8") as fh:
        def gravar(oferta, ponto, tipo, tipo_id, tipo_desc, termo=""):
            nonlocal n_gravadas
            oid = oferta.get("id")
            if oid in vistos:
                return
            vistos.add(oid)
            oferta["_ponto"] = ponto
            oferta["_tipo"] = tipo               # "categoria" | "combustivel"
            oferta["_tipo_id"] = tipo_id
            oferta["_tipo_desc"] = tipo_desc
            if termo:
                oferta["_termo"] = termo
            oferta["_coletado_em"] = datetime.datetime.now().isoformat(timespec="seconds")
            fh.write(json.dumps(oferta, ensure_ascii=False) + "\n")
            n_gravadas += 1

        pontos = {k: v for k, v in PONTOS.items()
                  if args.pontos is None or k in args.pontos}
        consultas = []
        termos = []
        if args.termos:
            seeds = json.loads((data_dir / "termos.json").read_text(encoding="utf-8"))
            termos = [(int(cid), t) for cid, ts in seeds.items() if cid.isdigit() for t in ts]
            if args.fatia:
                i, n = map(int, args.fatia.split("/"))
                termos = termos[i::n]
        for ponto, (lat, lon) in pontos.items():
            local = geohash_encode(lat, lon, 9)
            if args.termos:
                for cid, termo in termos:
                    consultas.append((ponto, local, "termo", cid, termo))
                continue
            for cid in cat_ids:
                consultas.append((ponto, local, "categoria", cid,
                                  taxonomia.get(cid, f"cat{cid}")))
            if not args.sem_combustivel:
                for tp, tp_desc in TP_COMB.items():
                    consultas.append((ponto, local, "combustivel", tp, tp_desc))

        for ponto, local, tipo, tid, desc in consultas:
            chave = f"{ponto}|{tipo}|{desc if tipo == 'termo' else tid}"
            if chave in feitas:
                continue
            antes = n_gravadas
            if tipo == "termo":
                kwargs = {"termo": desc}
            elif tipo == "categoria":
                kwargs = {"categoria": tid, "termo": ""}
            else:
                kwargs = {"tp_comb": tid}
            try:
                for oferta in iter_ofertas(local, max_paginas=max_paginas,
                                           pausa=args.pausa, **kwargs):
                    if tipo == "termo":
                        gravar(oferta, ponto, tipo, tid, taxonomia.get(tid, f"cat{tid}"), desc)
                    else:
                        gravar(oferta, ponto, tipo, tid, desc)
            except RespostaEnvenenada as e:
                fh.flush()
                print(f"\nANTI-BOT DISPAROU: {e}")
                print(f"Coleta interrompida com {n_gravadas} ofertas novas gravadas. "
                      f"Aguarde o cooldown e rode de novo o mesmo comando para retomar.")
                sys.exit(2)
            except RuntimeError as e:
                print(f"  ! {ponto}/{tipo}{tid} ({desc}): {e}")
            marcar_feita(chave)
            print(f"{ponto} | {desc}: +{n_gravadas - antes} (acum {n_gravadas}, "
                  f"{time.time()-t0:.0f}s)", flush=True)
            time.sleep(args.pausa)

    print(f"\n{n_gravadas} ofertas únicas em {out_path} ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
