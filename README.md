# Melhor Preço PR

Inteligência de preços do varejo paranaense a partir de dados públicos de
notas fiscais (programa Menor Preço / Nota Paraná, SEFA-PR).

Site estático publicado em <https://melhorpreco-pr.github.io>.

## Produtos

| Nicho | Ferramenta | Modelo |
|---|---|---|
| Material de construção | **Orçamento de Obra Otimizado** (`/construcao/`) — melhor loja única + melhor combinação de lojas para a lista da obra | Grátis até 10 itens · completo R$ 29–49 · painel do lojista R$ 199–499/mês |
| Indústria regional (alimentos, bebidas, limpeza) | **Monitor da Marca** (`/industria/`) — presença e preço da marca por rede e município | R$ 500–2.000/mês por marca |

## Estrutura

```
index.html            landing
construcao/           nicho 1 — orçamento de obra
industria/            nicho 2 — monitor de marca
assets/css|js/        design system + apps client-side (sem framework)
data/                 JSONs gerados pelo pipeline (não editar à mão)
```

## Dados

Os JSONs em `data/` são gerados fora deste repositório pelo pipeline
`bestprice/scraper/build_melhorpreco.py`, que lê a coleta bruta da API
pública do Menor Preço (malha de 30+ polos urbanos, raio de 20 km,
ritmo controlado) e:

- deduplica ofertas por id e limpa registros-isca do anti-bot;
- nicho 1: agrupa por produto (GTIN/descrição) nas 10 categorias de
  construção, guardando as 10 ofertas mais baratas (uma por loja física);
- nicho 2: detecta ~110 marcas conhecidas na descrição (indústrias do PR
  em destaque) e agrega preço min/mediana/máx por rede varejista e
  presença por município.

Nenhum dado pessoal é coletado ou publicado: apenas produto, loja e preço.

## Publicar atualização de dados

```bash
py -3 scraper/build_melhorpreco.py   # no repo bestprice
cd melhorpreco-pr.github.io
git add data && git commit -m "chore: atualiza dados" && git push
```
