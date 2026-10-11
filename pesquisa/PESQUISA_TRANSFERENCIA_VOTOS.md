# Pesquisa: estimar transferência de votos a partir de dados agregados
### Fundamentos, métodos, evidência brasileira e onde o site "aliados" se situa
Preparado em 10-11/10/2026, entre os turnos. Pedido do Daniel: pesquisa
profunda sobre o assunto do site (onde aliados de esquerda podem buscar
voto para Lula no 2º turno).

## 1. O problema fundamental

O voto é secreto: nenhum dado oficial cruza o voto de uma pessoa em dois
cargos ou dois turnos. Toda estimativa de "eleitor de X que não votou em
Y" parte de agregados territoriais — e inferir comportamento individual
de agregados é o problema clássico da **falácia ecológica**, nomeado por
[Robinson (1950)](https://www.researchgate.net/publication/23959445_Ecological_Correlations_and_the_Behavior_of_Individuals):
nos EUA de 1930, estados com mais imigrantes tinham MAIS alfabetizados
(correlação +0,53), mas o imigrante individual era MENOS alfabetizado
(−0,11) — imigrantes moravam em estados ricos. Qualquer leitura
individual de números agregados precisa carregar essa cicatriz.

## 2. A caixa de ferramentas clássica

- **Limites de Duncan & Davis (1953)**: sem suposição nenhuma, a
  aritmética restringe a célula desconhecida. No nosso caso: eleitores
  de Marina sem Lula num local estão entre max(0, vM−vL) e
  min(vM, não-Lula). Honesto e inatacável, mas os intervalos são largos
  ([revisão](https://gking.harvard.edu/files/eiintro.pdf)).
- **Regressão ecológica de Goodman (1953)**: regride o agregado de Y na
  composição de X entre territórios, supondo comportamento constante.
  Pode gerar estimativas impossíveis (<0 ou >100%)
  ([Goodman→King](https://www.researchgate.net/publication/249036705_Ecological_Inference_from_Goodman_to_King)).
- **EI de King (1997)**: combina limites + regressão num modelo
  estatístico ("[A Solution to the Ecological Inference Problem](https://gking.harvard.edu/files/ecinf04.pdf)").
  Virou padrão em processos de voting rights nos EUA. A crítica dura de
  [Freedman et al.](https://www.stat.berkeley.edu/~census/515.pdf)
  ([síntese](https://math.nyu.edu/~greengar/coursepages/ecological_fallacy.pdf)):
  em bases onde a verdade individual era conhecida, o EI errou tanto
  quanto a regressão simples e seus diagnósticos não avisam quando o
  modelo falha. Lição: métodos ecológicos funcionam quando a suposição
  de homogeneidade contextual é plausível — e não há teste interno
  confiável disso.
- **RxC (Rosen, Jiang, King & Tanner, 2001)** e o pacote
  [eiPack](https://cran.r-project.org/web/packages/eiPack/eiPack.pdf):
  generalizam para tabelas candidato×candidato (exatamente o caso de
  transferência entre turnos), via Multinomial-Dirichlet hierárquico.
  [Avaliações com verdade conhecida](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5847155/)
  mostram desempenho razoável mas sensível a efeitos contextuais, e
  [convergência de MCMC difícil](https://journal.r-project.org/articles/RJ-2016-035/)
  em escala. O caso de split-ticket é justamente o exemplo canônico dos
  **limites** da EI em
  [Burden & Kimball](https://tam.cas.vanderbilt.edu/papers/bkajps.pdf).
- **A tradição francesa dos "reports de voix"**: a imprensa usa
  majoritariamente pesquisas declaradas, mas há linha ativa de estimação
  estatística por **bureau de vote** — p.ex. a
  [abordagem bayesiana de Girondot](https://comptes-rendus.academie-sciences.fr/mathematique/item/10.5802/crmath.401.pdf)
  modelando o 1º→2º turno como problema inverso, por grupos de seções
  ([panorama ENSAE](https://www.ensae.org/global/gene/link.php?doc_id=1279)).
  É o paralelo mais próximo do que faremos quando sair o 2º turno
  brasileiro (§6).

## 3. Evidência brasileira: voto cruzado é a regra, não exceção

- [Ames, Baker & Renno (2009)](https://www.sciencedirect.com/science/article/abs/pii/S0261379408000875):
  split-ticket como regra — perto de 70% dos votos brasileiros cruzam
  partidos entre cargos no mesmo ano; "governo dividido permanente".
- [Samuels (2000)](http://mattgolder.com/files/interactions/samuels.pdf):
  no Brasil o coattail relevante historicamente é o do GOVERNADOR, não o
  do presidente — candidaturas estaduais estruturam o voto legislativo.
- [Borges & Turgeon (2019)](https://journals.sagepub.com/doi/10.1177/1354068817702283):
  coattails presidenciais em presidencialismo de coalizão operam via
  alianças — transferência não é automática nem simétrica.
- [Ames (1994)](https://www.cambridge.org/core/journals/american-political-science-review/article/abs/the-reverse-coattails-effect-local-party-organization-in-the-1989-brazilian-presidential-election/4F2D8D3F4BE75E3534B11456523333A8)
  e a literatura de [reverse coattails municipais](https://www.sciencedirect.com/science/article/abs/pii/S0261379420301219):
  organização local importa e flui "de baixo para cima".

Implicação direta para o site: a premissa de que existe um estoque
grande de eleitores de aliados de esquerda que NÃO votou em Lula é bem
fundamentada — o eleitor brasileiro cruza voto rotineiramente, e 2026
confirmou (válidos de senador ÷ 2 ≠ válidos de presidente candidato a
candidato; Tebet-PSB com 8,3 mi em SP contra Lula com ~38% dos votantes).

## 4. Onde o nosso método se situa

Cronologia do site (10/10): (a) proporcionalidade local
("conversíveis = vX × (1−pLula)") — rejeitada pelo Daniel com razão: é a
suposição de Goodman no pior caso, com eleitorados correlacionados
(eleitor de aliado de esquerda é mais lulista que a média → superestima);
(b) **modelo de déficit** (atual): gradient boosting prevê o Lula
esperado por setor dado o voto do aliado + perfil (renda, idade,
alfabetização, religião, superior, urbanização, porte), com predição
out-of-fold agrupada por município; déficit = esperado − real.

Características que defendem o desenho:

1. **A afirmação é agregada, não individual**: não dizemos "N pessoas
   votaram em X e não em Lula" (célula ecológica, alvo da crítica de
   Freedman); dizemos "neste território faltaram N votos a Lula em
   relação ao que o perfil e o voto do aliado preveem". É a gramática
   dos "underperformance maps" do jornalismo de dados americano, não a
   da EI de células.
2. **Resíduo honesto por construção**: validação cruzada em blocos por
   município impede o modelo de decorar a política local (o análogo do
   data leakage espacial); sem coordenadas nas features, a política
   regional permanece NO resíduo — é o sinal, não o ruído.
3. **Herda as fraquezas conhecidas**: MAUP (resultados dependem do
   recorte territorial), efeitos contextuais (o déficit pode refletir
   candidato local, chuva, abstenção diferencial — não só "resistência a
   Lula"), e o smoothing LV→setor do pipeline. Documentadas na
   metodologia do site.

## 5. O que a campanha consegue fazer com isso — a literatura de efeitos

A ferramenta diz ONDE; a literatura experimental diz O QUE funciona lá:

- [Kalla & Broockman (2018)](https://www.cambridge.org/core/journals/american-political-science-review/article/abs/minimal-persuasive-effects-of-campaign-contact-in-general-elections-evidence-from-49-field-experiments/753665A313C4AB433DBF7110299B7433):
  meta-análise de 49 experimentos — o efeito persuasivo médio do contato
  de campanha em eleição geral é ~zero; exceções: contatos muito cedo e
  temas de baixa cristalização.
- [Gerber & Green (panorama)](https://www.povertyactionlab.org/sites/default/files/research-paper/Gerber%20Green%20Handbook.pdf):
  MOBILIZAÇÃO (fazer simpatizante votar) tem efeitos replicáveis;
  persuasão é cara e rara ([resumo WaPo](https://www.povertyactionlab.org/sites/default/files/2017.10.11-gotv-wapo.pdf)).
- A engenharia da Obama 2012 ([uplift/persuasion modeling](https://www.predictiveanalyticsworld.com/machinelearningtimes/how-uplift-modeling-helped-obamas-campaign-and-can-aid-marketers/2613/),
  [Technology Review](https://www.technologyreview.com/2012/12/19/114510/how-obamas-team-used-big-data-to-rally-voters/),
  Issenberg, [The Victory Lab](https://www.motherjones.com/politics/2012/10/sasha-issenberg-goes-inside-21st-century-campaign/);
  [campanhas aprendem com experimentos próprios](https://www.cambridge.org/core/journals/american-political-science-review/article/how-experiments-help-campaigns-persuade-voters-evidence-from-ff5be6ed1553475f8321f7c4209357f7))
  é o precedente direto do nosso produto: score de priorização
  geográfica + mensageiro certo. Nosso déficit é um "persuadable score"
  territorial com o ALIADO como mensageiro — e a literatura sugere que o
  mensageiro de alta credibilidade local é justamente o caso em que
  persuasão tem chance.
- Nuance importante: entre turnos, parte do déficit pode ser recuperada
  por MOBILIZAÇÃO (abstenção/brancos de simpatizantes), não conversão —
  nosso déficit não separa os dois canais. Vale nota editorial.

## 6. Validação real em 25/10 (proposta)

O 2º turno dá um teste out-of-sample verdadeiro, raro na literatura:

1. Congelar hoje as previsões: déficit por setor/distrito por candidato.
2. Após 25/10, medir ΔLula = pct Lula t2 − t1 por setor (pipeline já
   reexecuta t2; filtro de estabilidade LV existente).
3. Testar: ΔLula é maior onde o déficit era alto? (regressão ponderada,
   controles de UF); comparar regiões top-5 vs resto da circunscrição.
4. Publicável: "onde o mutirão rendeu" — e a validação (ou não) do
   método vira matéria por si, no espírito dos reports de voix franceses
   por seção.

## 7. Recomendações editoriais

- Nunca publicar déficit como contagem de pessoas; sempre "votos abaixo
  do esperado pelo modelo" com R² da circunscrição à vista.
- Manter os limites de Duncan-Davis como checagem interna (nenhuma
  região pode ter déficit recuperável acima de min(vX, não-Lula)).
- Se houver tempo antes de 25/10: rodar eiPack/RxC numa UF como
  robustez — se a célula "eleitor de aliado → não-Lula" estimada pelo
  RxC concordar em ordenação com o déficit, a confiança sobe.
- Guardar a matriz de validação do §6 no runbook do 2º turno.
