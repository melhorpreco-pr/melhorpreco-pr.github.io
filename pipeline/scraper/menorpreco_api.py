# -*- coding: utf-8 -*-
"""Cliente da API pública do Menor Preço Nota Paraná.

Endpoints descobertos em 2026-08-17 (sem autenticação):
  GET /api/v1/categorias?local=<geohash>&termo=<busca>&raio=<km>
  GET /api/v1/produtos?local=<geohash>&termo=<busca>&categoria=<id>&offset=<n>&raio=<km>&data=-1&ordem=0
  GET /api/v1/produtos?local=<geohash>&raio=<km>&data=-1&ordem=0&tp_comb=<1..5>

Limites observados: raio máximo efetivo 20 km; ~34 itens por página via offset.

ANTI-BOT (descoberto 2026-08-17): após ~150-170 requisições em poucos minutos,
o servidor passa a devolver DADOS-ISCA por IP: descrições genéricas, preços
aleatórios (inclusive negativos), nomes de loja embaralhados e 'datahora' com
milissegundos idênticos (.669Z) em todos os itens. O bloqueio persiste por um
tempo após parar. Use pausas longas (RITMO_SEGURO) e valide cada página com
pagina_envenenada() — aborte a coleta imediatamente ao detectar isca.
"""
import json
import re
import time
import urllib.parse
import urllib.request

BASE = "https://menorpreco.notaparana.pr.gov.br/api/v1"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) bestprice-research/0.1"

TP_COMB = {
    1: "Gasolina Comum",
    2: "Gasolina Aditivada",
    3: "Etanol",
    4: "Diesel",
    5: "GNV",
}

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def geohash_encode(lat: float, lon: float, precision: int = 9) -> str:
    """Codifica lat/lon em geohash (base32), sem dependências externas."""
    lat_r = (-90.0, 90.0)
    lon_r = (-180.0, 180.0)
    bits = []
    even = True
    while len(bits) < precision * 5:
        if even:
            mid = (lon_r[0] + lon_r[1]) / 2
            if lon > mid:
                bits.append(1)
                lon_r = (mid, lon_r[1])
            else:
                bits.append(0)
                lon_r = (lon_r[0], mid)
        else:
            mid = (lat_r[0] + lat_r[1]) / 2
            if lat > mid:
                bits.append(1)
                lat_r = (mid, lat_r[1])
            else:
                bits.append(0)
                lat_r = (lat_r[0], mid)
        even = not even
    chars = []
    for i in range(0, len(bits), 5):
        chunk = bits[i:i + 5]
        idx = 0
        for b in chunk:
            idx = (idx << 1) | b
        chars.append(_BASE32[idx])
    return "".join(chars)


def _get_json(url: str, retries: int = 4, backoff: float = 2.0, timeout: int = 40):
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - retry em qualquer falha de rede
            last_err = e
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"Falha após {retries} tentativas: {url} -> {last_err}")


RITMO_SEGURO = 3.0  # segundos entre requisições; abaixo disso o anti-bot dispara

_MS_RE = re.compile(r"\.(\d{3})Z$")


class RespostaEnvenenada(RuntimeError):
    """O anti-bot passou a devolver dados-isca; interrompa e aguarde cooldown."""


def pagina_envenenada(itens: list) -> bool:
    """Heurística de isca: todos os 'datahora' com os mesmos milissegundos,
    ou qualquer valor negativo. Páginas reais têm ms variados."""
    if not itens:
        return False
    sufixos = set()
    for it in itens:
        m = _MS_RE.search(it.get("datahora") or "")
        if m:
            sufixos.add(m.group(1))
        try:
            if float(it.get("valor") or 0) < 0:
                return True
        except (TypeError, ValueError):
            pass
    return len(itens) >= 3 and len(sufixos) == 1


def categorias(local: str, termo: str = "", raio: int = 20) -> list:
    qs = urllib.parse.urlencode({"local": local, "termo": termo, "raio": raio})
    data = _get_json(f"{BASE}/categorias?{qs}")
    return data.get("categorias", [])


def produtos(local: str, termo: str = "", categoria: int | None = None,
             tp_comb: int | None = None, offset: int = 0, raio: int = 20,
             ordem: int = 0) -> dict:
    """Uma página de ofertas. Retorna dict com 'produtos', 'total', 'precos'."""
    params = {"local": local, "offset": offset, "raio": raio, "data": -1, "ordem": ordem}
    if tp_comb is not None:
        params["tp_comb"] = tp_comb
    else:
        params["termo"] = termo
        if categoria is not None:
            params["categoria"] = categoria
    qs = urllib.parse.urlencode(params)
    return _get_json(f"{BASE}/produtos?{qs}")


def iter_ofertas(local: str, termo: str = "", categoria: int | None = None,
                 tp_comb: int | None = None, raio: int = 20,
                 max_paginas: int | None = None, pausa: float = RITMO_SEGURO):
    """Itera todas as páginas de uma consulta, respeitando 'total'.

    Levanta RespostaEnvenenada se o anti-bot começar a devolver isca.
    """
    offset = 0
    paginas = 0
    while True:
        page = produtos(local, termo=termo, categoria=categoria,
                        tp_comb=tp_comb, offset=offset, raio=raio)
        itens = page.get("produtos") or []
        if pagina_envenenada(itens):
            raise RespostaEnvenenada(
                f"dados-isca detectados (local={local}, categoria={categoria}, "
                f"tp_comb={tp_comb}, offset={offset})")
        if not itens:
            return
        yield from itens
        paginas += 1
        offset += len(itens)
        total = page.get("total") or 0
        if offset >= total:
            return
        if max_paginas is not None and paginas >= max_paginas:
            return
        time.sleep(pausa)
