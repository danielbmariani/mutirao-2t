# Insumos: o que cada script precisa e onde está

Cada script declara caminhos no topo (vêm de um pipeline maior); ajuste
as constantes para os arquivos abaixo. Tudo o que o repositório não
contém está na Release ou em fonte pública com URL.

## Neste repositório (pasta `dados_modelo/`)

| Arquivo | O que é |
|---|---|
| `setor_deficit_lula.parquet` | saída do modelo de voto por setor (real, esperado, déficit, válidos) |
| `setor_abst_lula.parquet` | saída do modelo de abstenção por setor (real, esperada, excesso, aptos, vperd, vnet) |
| `biometria_municipio.parquet` | cobertura biométrica municipal 2022/2026 e variação (insumo do modelo de abstenção) |
| `relacao_malha2022_2026_t1_lv.parquet` | a relação local de votação → setor censitário com distâncias (peça-chave: com ela os modelos são retreináveis só com dados públicos do TSE) |
| `distritos_eleicao.parquet` | nomes e agregados eleitorais por distrito censitário (nomes das regiões) |

## Na Release v1.0 deste repositório

| Arquivo | O que é | Precisa para |
|---|---|---|
| `mapa_lula_v3.mbtiles` | tileset pronto (atributos d e a) | hospedar sem rebuild |
| `subdistritos_2022.parquet` | geometria dos 11.311 subdistritos (dissolve da malha IBGE) | gerar regiões |
| `municipios_2022.parquet` | geometria municipal | gerar tileset |
| `distritos_2022.parquet` | geometria distrital | gerar tileset |
| `malha_2022.parquet` | geometria dos 468 mil setores (geoparquet) | gerar tileset |

## Público, já hospedado (dashboard do projeto)

| URL | O que é | Precisa para |
|---|---|---|
| https://dados-eleicoes.danielmariani.com.br/dados/setores_eleicao_renda.parquet | eleições 2010-2026 + Censo por setor (variáveis dos modelos, perfis das regiões) | modelos e regiões |
| https://dados-eleicoes.danielmariani.com.br/dados/apond_completo.parquet | áreas de ponderação (religião, superior, renda pc) | modelos e perfis |

## Público, fonte primária (TSE Dados Abertos e IBGE)

| Fonte | O que é | Precisa para |
|---|---|---|
| TSE `votacao_secao_2026_BR` | votos por seção (presidente) | retreinar modelos (válidos por LV) |
| TSE `detalhe_votacao_secao_2026` | aptos e abstenções por seção | modelo de abstenção |
| TSE `perfil_eleitorado_{2022,2026}` | biometria por município | refazer `biometria_municipio.parquet` |
| IBGE malha de setores CD2022 (geoftp) | shapefiles originais | refazer as geometrias da Release |

## O que exige o pipeline upstream completo

Somente refazer a PRÓPRIA `relacao_malha2022_2026_t1_lv.parquet` (a
geolocalização dos locais de votação e o pareamento com a malha), pela
metodologia do [deltafolha](https://github.com/deltafolha/eleicoes-por-setores-censitarios).
Como ela está incluída neste repositório, nenhum passo depende disso.
