# Mutirão do 2º turno: onde Lula ficou abaixo do esperado

Mapa interativo com as regiões do Brasil onde Lula ficou abaixo do
esperado no 1º turno de 2026, por três caminhos: migração de voto,
abstenção acima da esperada e queda da fatia dele em relação ao 1º turno
de 2022. Feito para orientar o esforço de campanha
entre os turnos (o 2º turno é em 25/10/2026).

Versão de referência no ar: https://mutirao-2t.vercel.app

Este repositório existe para que qualquer grupo (em particular o
pessoal do Colmeia) possa hospedar a própria cópia e para que qualquer
pessoa possa entender e reproduzir os modelos.

## O que o site mostra

Três visões, com a mesma mecânica de regiões:

1. **Votos que faltaram**: um modelo prevê o voto esperado de Lula em
   cada um dos 468 mil setores censitários a partir da eleição de 2022
   (1º e 2º turnos, abstenção e brancos), de 2018 e do perfil do Censo
   2022 (renda, idade, alfabetização, cor, religião, ensino superior,
   urbanização, porte). O déficit é o esperado menos o real. Bolsa
   nacional: cerca de 745 mil votos, já limitada pelo teto aritmético
   de cada lugar.
2. **Abstenção excedente**: um modelo irmão prevê a abstenção esperada
   de cada setor a partir do histórico de 2018 e 2022, do perfil
   demográfico e da cobertura do recadastramento biométrico do
   município (cadastro limpo derruba a abstenção estrutural; sem essa
   variável, eleitor fantasma viraria falso sinal). Votos perdidos =
   excesso de abstenção × aptos × fatia de Lula. As regiões desta visão
   só aceitam áreas onde Lula lidera, porque reverter abstenção devolve
   votos de todos os lados; a ficha mostra também o ganho líquido.
3. **Queda de 2022** (13/10): sem modelo. Compara a fatia de Lula no
   1º turno de 2026 com a do 1º turno de 2022 no mesmo território;
   votos perdidos = queda em pontos × válidos de 2026 (quantos votos
   ele teria a mais se mantivesse a fatia de 2022 no eleitorado de
   hoje). No país a fatia caiu de 48,4% para 45,2%; a visão realça onde
   a queda foi bem maior (regiões: ao menos 6 pontos e 2 mil votos no
   corte padrão). Setores só recebem queda quando a atribuição de locais
   de votação é estável entre os dois anos (94% dos votos); subdistritos,
   distritos e municípios usam a soma de votos, em que a reatribuição se
   cancela. Script: `modelos/swing_lula_93.py` + `regioes/regioes_swing_94.py`.

O seletor **Unidade** (13/10) escolhe a área em que os números são
somados e ranqueados: **município** (padrão, 5.570), **distrito**
censitário (10,7 mil) ou **região** (as manchas abaixo). Município e
distrito usam a soma direta dos setores nas mesmas fórmulas das visões
(`regioes/areas_95.py` → `site/dados/areas_{mun,dist}.json`, uma linha
por área com as três moedas); o contorno vem do próprio tileset.

As regiões são grupos contíguos de subdistritos censitários acima de um
limiar de sinal e de volume, divididas em escala de agenda (até ~60 km),
ranqueadas por votos absolutos, com três cortes pré-computados (menos,
padrão, mais). Navegação por Brasil, estado e município, busca de
endereço que encontra a região mais próxima, e perfil socioeconômico de
cada região.

## Hospedar a sua versão

O site é 100% estático. Três passos:

1. **Conta Mapbox própria** (o mapa usa tiles vetoriais do Mapbox):
   crie um token público (pk) restrito ao seu domínio, e um token
   secreto (sk) com escopo de uploads.
2. **Tileset**: baixe o arquivo `mapa_lula_v5.mbtiles` da
   [Release v1.1 deste repositório](../../releases) e suba para a sua conta:
   `python tiles/upload_mapbox_35.py mapa_lula_v5.mbtiles SEU_TILESET
   "Nome"` (o script lê o sk de um arquivo; ajuste o caminho no topo).
   Alternativa: Mapbox Studio aceita o upload manual do mbtiles.
3. **Site**: em `site/index.html`, troque as constantes `TOKEN` (seu
   pk) e `TILESET_ID` (`seu_usuario.seu_tileset`). Publique a pasta
   `site/` em qualquer hospedagem estática (Vercel, Netlify, GitHub
   Pages). O `vercel.json` incluso configura cache e CORS dos dados.

A auditoria de interface (`site/bateria_eleitores.cjs`, Puppeteer) roda
30 verificações contra qualquer URL: `node bateria_eleitores.cjs
https://sua-url/`.

## Estrutura

```
site/            o site pronto (index.html + dados pré-computados)
  dados/         regioes*.json/geojson (3 visões × 3 cortes),
                 areas_mun.json / areas_dist.json (catálogos por unidade),
                 municipios.json (busca), regioes*.geojson (contornos)
modelos/         modelo_lula_72.py (voto), modelo_abst_75.py (abstenção),
                 swing_lula_93.py (queda 2022→2026, sem modelo)
regioes/         geradores de regiões das três visões + areas_95.py
                 (catálogos por município e distrito)
tiles/           gerador do tileset + uploader Mapbox
dados_modelo/    SAÍDAS dos modelos por setor censitário (parquet):
                 permitem regenerar regiões e tiles sem o pipeline TSE
metricas/        bateria de validação dos modelos (JSON)
pesquisa/        revisão de literatura (inferência ecológica,
                 transferência de votos, GOTV)
```

## Os modelos, em detalhe técnico

Ambos são `HistGradientBoostingRegressor` (scikit-learn) por setor
censitário, ponderados pelos votos válidos (ou aptos) do setor, com
predição **out-of-fold** em validação cruzada de 5 blocos agrupada por
município: o modelo nunca viu o município ao prever nele, senão
decoraria a política local e o resíduo (que é o produto) morreria.
Coordenadas ficam fora das variáveis: diferenças regionais de
comportamento permanecem no resíduo de propósito. Nada de 2026 entra
como variável além do alvo (na visão de abstenção, nem abstenção nem
brancos de 2026, que são exatamente o que um mutirão recupera).

Bateria de validação (os números completos estão em `metricas/`):

| | Voto | Abstenção |
|---|---|---|
| R² fora da amostra (setor) | 0,967 | 0,33 |
| R² fora da amostra (distrito, nível de decisão) | — | 0,686 |
| Erro médio (pp) | 2,07 | 2,23 |
| Viés global (pp) | −0,12 | +0,01 |
| Baseline Ridge (mesmo esquema) | 0,958 | 0,07 |
| Redução do erro vs baseline | 20% | 27% |
| Estabilidade entre seeds (Spearman do ranking) | 0,978 | 0,968 |

A abstenção é estruturalmente mais ruidosa que o voto (chuva, filas,
eventos locais); por isso a predição dela é um ensemble de 4 seeds e o
gate de estabilidade é medido no ranking agregado por distrito, o nível
em que o site decide. O viés por UF é reportado nos JSONs e tratado
como achado, não como erro: política estadual deve ficar no resíduo.

Salvaguardas aritméticas (método dos limites de Duncan e Davis): o
déficit recuperável de cada bloco não excede o eleitorado não-Lula; na
abstenção, não excede a abstenção total × fatia de Lula, e só entram
blocos onde Lula lidera.

## Usar os dados e os modelos direto (Python e R)

`dados_modelo/setores_completo.{parquet,csv.gz}` tem UMA linha por
setor censitário (468 mil) com: real, esperado e déficit das visões
de voto e abstenção, fatia de Lula em 2022 e 2026 e a queda entre elas
(`queda_2022_2026_pp`, `votos_perdidos_desde_2022`, só onde
`comparacao_estavel`), válidos/aptos e, quando o setor pertence a uma
região de interesse do corte padrão, o número dela (`regiao_voto`,
`regiao_abstencao`, `regiao_queda`). Os modelos treinados estão em
`modelos/treinados/*.joblib` (scikit-learn; versão em `META.json`; a
predição da abstenção é a média do ensemble de 4). Exemplos prontos de
carga em `exemplos/carregar.py` e `exemplos/carregar.R` (R via
reticulate). Atenção: os números publicados vêm das predições fora da
amostra; os joblib são o ajuste final em todos os dados, para aplicar a
dados novos e inspecionar.

## Reproduzir do zero

O mapa completo de insumos (o que está neste repositório, o que está na
Release, o que é público com URL) está em [INSUMOS.md](INSUMOS.md). Em
resumo: com `dados_modelo/` + as geometrias da Release + dois parquets
públicos do dashboard do projeto, TUDO é regenerável, inclusive o
retreino dos modelos a partir dos dados públicos do TSE, porque a
relação local de votação → setor está incluída.

### Comandos

Com os parquets de `dados_modelo/` você regenera regiões e tileset sem
tocar nos dados brutos:

```bash
python -m venv .venv && .venv/bin/pip install duckdb pandas numpy \
    scikit-learn scipy geopandas shapely pyarrow requests boto3
# ajuste os caminhos no topo dos scripts (eles vêm de um pipeline maior)
.venv/bin/python regioes/regioes_lula_73.py            # padrão
.venv/bin/python regioes/regioes_lula_73.py 1.5 2000 _menos
.venv/bin/python regioes/regioes_lula_73.py 0.6 500 _mais
.venv/bin/python regioes/regioes_abst_76.py 1.5 1000   # etc.
.venv/bin/python tiles/tiles_lula_74.py                # exige tippecanoe
```

Para refazer os MODELOS a partir dos dados brutos é preciso o pipeline
completo de agregação eleitoral por setor censitário: resultados por
seção do TSE agregados por local de votação e repartidos entre os
setores vizinhos por proximidade e população, cada eleitor contado
uma única vez (`modelos/distribuicao_85.py`, modelo gravitacional
com ajuste iterativo — desde 12/10/2026; antes, peso inverso à
distância, metodologia do
[deltafolha](https://github.com/deltafolha/eleicoes-por-setores-censitarios),
inspirada no Pindograma), mais a malha e os agregados do Censo 2022 do
IBGE e o detalhe de votação por seção (aptos e abstenções). Os insumos
intermediários necessários estão descritos no topo de cada script. Os
dados de origem são todos públicos (TSE Dados Abertos e IBGE/FTP).

## Limitações que a sua versão deve manter visíveis

O déficit é medida de território, não contagem de pessoas; a passagem
seção → setor é estimativa por proximidade; parte do déficit de voto se
recupera por mobilização e parte por convencimento, e o modelo não
separa os canais; o R² baixo por setor na abstenção é esperado, decisões
devem ficar no nível de região. A validação real está agendada: depois
de 25/10, comparar o crescimento de Lula t1→t2 com o déficit previsto
aqui, por setor (desenho na pesquisa inclusa).

## Créditos

Daniel Mariani (modelos, dados e site). Metodologia de setores
censitários: deltafolha e Pindograma. Dados: TSE e IBGE. Código sob
licença MIT; dados derivados são públicos.
