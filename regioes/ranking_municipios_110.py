# Tabela por MUNICÍPIO para ranquear o déficit de Lula e a abstenção por
# duas réguas cada (pedido Daniel 15/10/2026, p/ grupo Indicadores/Colmeia):
#   déficit  (a) vs o ESPERADO pelo modelo (modelo_lula_72: esperado − real)
#            (b) vs 2022, 1º turno (fatia 2022 T1 − fatia 2026 T1, oficial TSE)
#   abstenção(a) vs a ESPERADA pelo modelo irmão (modelo_abst_75)
#            (b) vs 2022, 2º turno ("quem votou no 2T de 2022 e não votou
#                agora", régua do Rodrigo/NIELE e do painel da campanha)
# + cobertura de programas federais em % da população (municipio_extra_108)
# + ranking nacional em cada métrica (1 = mais votos a recuperar / maior
#   cobertura; valores negativos ficam no fim).
# Moeda comum: votos de Lula. Nas réguas de 2022: pontos × válidos (ou
# aptos) de 2026; na abstenção vs 2022, eleitores a mais em casa × fatia
# de Lula em 2026 (só a parte "dele"; a coluna de eleitores vem junto).
# Saídas: dados/processados/eleitores/ranking_municipios.{csv,parquet}
#         embed_eleitores/dados/ranking_municipios.{json,csv}
import json
import sys
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DADOS, DIR_PROC, DIR_SITES

E = DIR_PROC / "eleitores"
M = DIR_PROC / "municipio"
TSE = DADOS / "brutos/tse/detalhe"
SITE = DIR_SITES / "embed_eleitores/dados"
con = duckdb.connect()
con.sql("SET threads TO 8")

# ---- oficial TSE: fatias de Lula (município) e abstenção por turno
mun = pd.read_csv(DIR_PROC / "dashboard/municipios_eleicao.csv", dtype={"cd_mun": int})
mun = mun[["cd_mun", "nm_mun", "uf", "votos_validos_2022t1", "pct_lula_2022t1", "pct_lula_2022t2",
           "votos_validos_2026t1", "pct_lula_2026t1", "pct_flavio_2026t1"]]
depara = pd.read_csv(DADOS / "brutos/tse_ibge.csv")[["codigo_tse", "codigo_ibge"]]

def abst(arq):
    return con.sql(f"""
      SELECT NR_TURNO AS turno, CD_MUNICIPIO AS codigo_tse,
             sum(QT_APTOS) AS aptos, sum(QT_ABSTENCOES) AS abst
      FROM read_csv('{arq}', delim=';', header=true, encoding='latin-1', ignore_errors=true)
      WHERE CD_CARGO = 1 AND SG_UF <> 'ZZ' GROUP BY 1, 2""").df()

a26 = abst(TSE / "detalhe_votacao_secao_2026_BR.csv")
a22 = abst(TSE / "detalhe_votacao_secao_2022_BR.csv")
def por_mun(d, turno, suf):
    d = d[d.turno == turno].merge(depara, on="codigo_tse", how="inner")
    g = d.groupby("codigo_ibge")[["aptos", "abst"]].sum()
    return pd.DataFrame({f"aptos_{suf}": g.aptos, f"abst_{suf}_pct": (100 * g.abst / g.aptos).round(2)})
ab = por_mun(a26, 1, "2026").join(por_mun(a22, 2, "2022t2")).join(por_mun(a22, 1, "2022t1"))
ab.index.name = "cd_mun"
mun = mun.merge(ab.reset_index(), on="cd_mun", how="left")
falta = set(a26.codigo_tse) - set(depara.codigo_tse)
print("municípios TSE sem de-para:", falta, a26[a26.codigo_tse.isin(falta)][["aptos"]].sum().to_dict())

# ---- modelo de voto (setor -> município, soma de votos)
v = con.sql(f"""
  SELECT cd_mun, sum(validos) AS validos_set,
         sum(pct_lula * validos) / sum(validos) AS pl_set,
         sum(esperado * validos) / sum(validos) AS esperado_pct,
         sum(deficit_votos) AS def_modelo_votos
  FROM '{E / "setor_deficit_lula.parquet"}' WHERE validos > 0 GROUP BY 1""").df()
v["cd_mun"] = v.cd_mun.astype(int)
# ---- modelo de abstenção
a = con.sql(f"""
  SELECT cd_mun, sum(aptos) AS aptos_set,
         sum(abstencao * aptos) / sum(aptos) AS abst_set,
         sum(esperada * aptos) / sum(aptos) AS abst_esperada_pct,
         sum(vperd) AS abst_modelo_votos_lula, sum(vnet) AS abst_modelo_saldo
  FROM '{E / "setor_abst_lula.parquet"}' WHERE aptos > 0 GROUP BY 1""").df()
a["cd_mun"] = a.cd_mun.astype(int)
t = mun.merge(v, on="cd_mun", how="left").merge(a, on="cd_mun", how="left")

# conferência: as somas por setor batem com o oficial?
dv = (t.validos_set / t.votos_validos_2026t1 - 1).abs()
da = (t.aptos_set / t.aptos_2026 - 1).abs()
print(f"válidos setor vs oficial: mediana {dv.median():.4f}, p99 {dv.quantile(.99):.4f}, máx {dv.max():.3f}")
print(f"aptos setor vs oficial:   mediana {da.median():.4f}, p99 {da.quantile(.99):.4f}, máx {da.max():.3f}")
print("piores aptos:", t.assign(d=da).sort_values("d", ascending=False)[["nm_mun","uf","aptos_2026","aptos_set","d"]].head(5).to_string(index=False))
print(f"abst setor vs oficial: máx |dif| {(t.abst_set - t.abst_2026_pct).abs().max():.2f} pp, p99 {(t.abst_set - t.abst_2026_pct).abs().quantile(.99):.2f}")
print(f"fatia Lula setor vs oficial: máx |dif| {(t.pl_set - t.pct_lula_2026t1).abs().max():.2f} pp")

# ---- as quatro réguas (positivo = votos a recuperar)
t["def_modelo_pp"] = (t.esperado_pct - t.pct_lula_2026t1).round(2)
t["def_modelo_votos"] = t.def_modelo_votos.round(0)
t["def_2022_pp"] = (t.pct_lula_2022t1 - t.pct_lula_2026t1).round(2)
t["def_2022_votos"] = (t.def_2022_pp / 100 * t.votos_validos_2026t1).round(0)
t["abst_modelo_pp"] = (t.abst_set - t.abst_esperada_pct).round(2)  # mesma base (setores)
t["abst_modelo_votos_lula"] = t.abst_modelo_votos_lula.round(0)
t["abst_2022_pp"] = (t.abst_2026_pct - t.abst_2022t2_pct).round(2)
t["abst_2022_eleitores"] = (t.abst_2022_pp / 100 * t.aptos_2026).round(0)
t["abst_2022_votos_lula"] = (t.abst_2022_eleitores * t.pct_lula_2026t1 / 100).round(0)
t["lula_lidera"] = t.pct_lula_2026t1 > t.pct_flavio_2026t1

# ---- programas, % da população (Censo 2022)
x = pd.read_parquet(M / "municipio_extra.parquet")
b = pd.read_parquet(M / "base_municipio.parquet")[["cd_mun", "pop_censo_2022"]]
prog = pd.DataFrame({
    "cd_mun": x.cd_mun,
    "bolsa_familia_pct_pop": x.bf_pct_pop,
    "cadunico_pct_pop": x.cad_pct_pop,
    "bpc_pct_pop": (x.bpc_por_mil / 10).round(2),
    "farmacia_popular_pct_pop": x.farm_pct_pop,
    "pe_de_meia_pct_pop": (x.pedemeia_por_mil / 10).round(2),
    "mei_pct_pop": x.mei_pct_pop,
    "emprego_formal_pct_pop": x.emprego_pct_pop,
    "mcmv_por_100hab": (x.mcmv_por_mil / 10).round(2),
})
t = t.merge(b, on="cd_mun", how="left").merge(prog, on="cd_mun", how="left")

# ---- rankings nacionais (1 = maior)
def rk(col):
    return t[col].rank(ascending=False, method="min").astype("Int64")
for c in ["pop_censo_2022", "pct_lula_2026t1", "pct_lula_2022t1", "esperado_pct", "abst_2026_pct",
          "def_modelo_votos", "def_modelo_pp", "def_2022_votos", "def_2022_pp",
          "abst_modelo_votos_lula", "abst_modelo_pp", "abst_2022_votos_lula", "abst_2022_pp",
          "bolsa_familia_pct_pop", "cadunico_pct_pop", "bpc_pct_pop", "farmacia_popular_pct_pop",
          "pe_de_meia_pct_pop", "mei_pct_pop", "emprego_formal_pct_pop", "mcmv_por_100hab"]:
    t["rk_" + c] = rk(c)

# ---- textos "mastigados" (pedido 15/10: lugar, por quê, o que fazer, o que o
# governo faz ali). Mesmas regras no CSV e na página (a página só exibe).
QUEDA_BR = 3.28  # queda nacional da fatia de Lula, 1T 2022 -> 1T 2026
N = len(t)
from decimal import Decimal, ROUND_HALF_UP
# arredondamento "meio para cima" sobre a representação decimal curta, como o
# Intl.NumberFormat do navegador (2,15 -> 2,2; Python daria 2,1): CSV = página
def _r(v, casas): return Decimal(repr(float(v))).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)
def f1(v): return f"{_r(v, 1):,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
def fi(v): return f"{_r(v, 0):,.0f}".replace(",", ".")
def mil(v):
    v = abs(v)
    if v >= 1e6: return f1(v / 1e6) + " mi"
    if v >= 1e4: return fi(v / 1e3) + " mil"
    if v >= 1e3: return f1(v / 1e3) + " mil"
    return fi(v)
def porque(r):
    s = []
    pp, pl = r.def_modelo_pp, r.pct_lula_2026t1
    if pd.isna(pp): s.append(f"Lula teve {f1(pl)}%.")
    elif pp >= 1: s.append(f"Lula teve {f1(pl)}%, {f1(pp)} pontos abaixo do esperado para o perfil da cidade ({mil(r.def_modelo_votos)} votos, {fi(r.rk_def_modelo_votos)}º do país).")
    elif pp > -1: s.append(f"Lula teve {f1(pl)}%, dentro do esperado para o perfil da cidade.")
    else: s.append(f"Lula teve {f1(pl)}%, {f1(-pp)} pontos acima do esperado para o perfil da cidade.")
    qd = r.def_2022_pp
    if qd >= 1:
        raz = qd / QUEDA_BR
        comp = ("mais que o dobro da queda nacional" if raz >= 2 else "acima da queda nacional de 3,3" if raz >= 1.3
                else "parecido com a queda nacional de 3,3" if raz >= 0.7 else "menos que a queda nacional de 3,3")
        s.append(f"Caiu {f1(qd)} pontos desde o 1º turno de 2022, {comp} ({mil(r.def_2022_votos)} votos).")
    elif qd > -1: s.append("Fatia igual à do 1º turno de 2022.")
    else: s.append(f"Subiu {f1(-qd)} pontos desde o 1º turno de 2022.")
    ex, ab, lid = r.abst_modelo_pp, r.abst_2026_pct, bool(r.lula_lidera)
    if pd.isna(ex): s.append(f"Abstenção de {f1(ab)}%.")
    elif ex >= 1 and lid: s.append(f"Abstenção de {f1(ab)}%, {f1(ex)} pontos acima da esperada, e Lula lidera ({f1(pl)} a {f1(r.pct_flavio_2026t1)}): {mil(r.abst_modelo_votos_lula)} votos dele ficaram em casa.")
    elif ex >= 1: s.append(f"Abstenção de {f1(ab)}%, {f1(ex)} pontos acima da esperada, mas Flávio lidera: levar todo mundo à urna devolve mais voto a ele.")
    elif ex > -1: s.append(f"Abstenção de {f1(ab)}%, dentro do esperado.")
    else: s.append(f"Abstenção de {f1(ab)}%, {f1(-ex)} pontos abaixo da esperada.")
    d = r.abst_2022_pp
    if d >= 0.5: s.append(f"{mil(r.abst_2022_eleitores)} eleitores a mais em casa que no 2º turno de 2022.")
    elif d > -0.5: s.append("Abstenção igual à do 2º turno de 2022.")
    else: s.append(f"Menos abstenção que no 2º turno de 2022 ({f1(-d)} pontos).")
    return " ".join(s)
def acao(r):
    C = (not pd.isna(r.def_modelo_pp)) and r.def_modelo_pp >= 1
    A = (not pd.isna(r.abst_modelo_pp)) and r.abst_modelo_pp >= 1
    lid = bool(r.lula_lidera)
    if C and A and lid: return ("Convencer e levar à urna", "faltou voto e faltou gente: as duas frentes rendem aqui.")
    if C and A: return ("Convencer quem saiu", "o voto é que faltou. A abstenção também está alta, mas Flávio lidera: mobilização só com conhecidos.")
    if C: return ("Convencer quem saiu", "o voto é que faltou; a abstenção está no padrão.")
    if A and lid: return ("Levar à urna", "Lula lidera e a abstenção ficou acima do esperado; o voto está no padrão.")
    if A: return ("Só com conhecidos", "abstenção acima do esperado, mas Flávio lidera: mobilização geral devolve mais voto a ele.")
    if r.def_2022_pp >= 1.3 * QUEDA_BR: return ("Maré nacional, não local", "caiu mais que o país desde 2022, mas o resultado é o esperado para lugares com esse perfil: resolve-se com mensagem geral, não com mutirão.")
    return ("Manter", "Lula dentro ou acima do esperado e abstenção no padrão.")
PROGS = [("bolsa_familia_pct_pop", "Bolsa Família", "% da pop."), ("cadunico_pct_pop", "CadÚnico", "% da pop."),
         ("bpc_pct_pop", "BPC", "% da pop."), ("farmacia_popular_pct_pop", "Farmácia Popular", "% atendidos no ano"),
         ("pe_de_meia_pct_pop", "Pé-de-Meia", "% da pop."), ("mei_pct_pop", "MEI", "% da pop."),
         ("emprego_formal_pct_pop", "Emprego formal", "% da pop."), ("mcmv_por_100hab", "Minha Casa Minha Vida", " moradias por 100 hab.")]
def faixa(q): return "10% mais altos do país" if q <= .10 else "25% mais altos" if q <= .25 else "metade de cima" if q <= .5 else None
def governo(r):
    itens = []
    for k, nome, un in PROGS:
        v, rk = r[k], r["rk_" + k]
        if pd.isna(v) or pd.isna(rk): continue
        q = rk / N
        itens.append((q, nome, v, un))
    itens.sort(key=lambda x: x[0])  # estável: empates mantêm a ordem de PROGS, como no front
    top = [x for x in itens if x[0] <= .25][:3] or [x for x in itens if x[0] <= .5][:2]
    if not top:
        if not itens: return "Sem dados de programas."
        q, nome, v, un = itens[0]
        return f"Cobertura abaixo da mediana nacional em todos os programas; o mais alto é {nome}, {f1(v)}{un} ({fi(round(100*q))}º percentil)."
    return "; ".join(f"{nome} {f1(v)}{un} ({faixa(q)})" for q, nome, v, un in top) + "."
t["porque"] = t.apply(porque, axis=1)
ac = t.apply(acao, axis=1)
t["acao"] = [a for a, _ in ac]; t["acao_motivo"] = [m for _, m in ac]
t["governo"] = t.apply(governo, axis=1)
print(t.acao.value_counts().to_string())

COLS = ["cd_mun", "nm_mun", "uf", "pop_censo_2022", "rk_pop_censo_2022", "aptos_2026", "votos_validos_2026t1",
        "pct_lula_2026t1", "rk_pct_lula_2026t1", "pct_flavio_2026t1", "lula_lidera", "pct_lula_2022t1", "rk_pct_lula_2022t1", "pct_lula_2022t2",
        "esperado_pct", "rk_esperado_pct", "def_modelo_pp", "def_modelo_votos", "rk_def_modelo_votos", "rk_def_modelo_pp",
        "def_2022_pp", "def_2022_votos", "rk_def_2022_votos", "rk_def_2022_pp",
        "abst_2026_pct", "rk_abst_2026_pct", "abst_esperada_pct", "abst_modelo_pp", "abst_modelo_votos_lula",
        "abst_modelo_saldo", "rk_abst_modelo_votos_lula", "rk_abst_modelo_pp",
        "abst_2022t2_pct", "abst_2022t1_pct", "abst_2022_pp", "abst_2022_eleitores", "abst_2022_votos_lula",
        "rk_abst_2022_votos_lula", "rk_abst_2022_pp",
        "bolsa_familia_pct_pop", "rk_bolsa_familia_pct_pop", "cadunico_pct_pop", "rk_cadunico_pct_pop",
        "bpc_pct_pop", "rk_bpc_pct_pop", "farmacia_popular_pct_pop", "rk_farmacia_popular_pct_pop",
        "pe_de_meia_pct_pop", "rk_pe_de_meia_pct_pop", "mei_pct_pop", "rk_mei_pct_pop",
        "emprego_formal_pct_pop", "rk_emprego_formal_pct_pop", "mcmv_por_100hab", "rk_mcmv_por_100hab",
        "acao", "acao_motivo", "porque", "governo"]
t = t[COLS].rename(columns={"nm_mun": "municipio", "pop_censo_2022": "pop_2022",
                            "votos_validos_2026t1": "validos_2026", "pct_lula_2026t1": "lula_2026_pct",
                            "pct_flavio_2026t1": "flavio_2026_pct", "pct_lula_2022t1": "lula_2022t1_pct",
                            "pct_lula_2022t2": "lula_2022t2_pct", "esperado_pct": "lula_esperado_pct",
                            "rk_pop_censo_2022": "rk_pop_2022", "rk_pct_lula_2026t1": "rk_lula_2026_pct",
                            "rk_pct_lula_2022t1": "rk_lula_2022t1_pct", "rk_esperado_pct": "rk_lula_esperado_pct",
                            "abst_modelo_saldo": "abst_modelo_saldo_lula_flavio"})
for c in ["esperado_pct", "lula_esperado_pct", "abst_esperada_pct", "abst_2026_pct"]:
    if c in t: t[c] = t[c].round(2)
t = t.sort_values("rk_def_modelo_votos")
t.to_csv(E / "ranking_municipios.csv", index=False)
t.to_parquet(E / "ranking_municipios.parquet", index=False)
t.to_csv(SITE / "ranking_municipios.csv", index=False)

# JSON compacto para a página (arrays; None onde falta)
def cell(v):
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA: return None
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating, float)): return float(v)
    if isinstance(v, (np.bool_, bool)): return bool(v)
    return v
tj = t[[c for c in t.columns if not c.startswith("rk_") and c not in ("porque", "acao_motivo", "governo")]]  # textos: a página gera com as mesmas regras
rows = [[cell(v) for v in r] for r in tj.itertuples(index=False)]
tot = {"def_modelo_votos": float(t.def_modelo_votos.clip(lower=0).sum()),
       "def_2022_votos": float(t.def_2022_votos.clip(lower=0).sum()),
       "abst_modelo_votos_lula": float(t.abst_modelo_votos_lula.clip(lower=0).sum()),
       "abst_2022_votos_lula": float(t.abst_2022_votos_lula.clip(lower=0).sum())}
json.dump({"meta": {"gerado": date.today().isoformat(), "n": len(t), "soma_positivos": tot},
           "cols": list(tj.columns), "rows": rows},
          open(SITE / "ranking_municipios.json", "w"), ensure_ascii=False, separators=(",", ":"))
print(len(t), "municípios;", (SITE / "ranking_municipios.json").stat().st_size // 1024, "KB json")
print("faltantes:", t.isna().sum()[t.isna().sum() > 0].to_dict())
print("somas dos positivos:", {k: round(v / 1e3) for k, v in tot.items()}, "(mil)")
print("\nTop 10 por déficit do modelo:")
print(t[["municipio", "uf", "def_modelo_votos", "rk_def_2022_votos", "def_2022_votos", "abst_modelo_votos_lula", "rk_abst_modelo_votos_lula", "abst_2022_votos_lula", "rk_abst_2022_votos_lula", "bolsa_familia_pct_pop"]].head(10).to_string(index=False))
print("\nTop 10 por queda de 2022:")
print(t.sort_values("rk_def_2022_votos")[["municipio", "uf", "def_2022_votos", "rk_def_modelo_votos", "def_modelo_votos"]].head(10).to_string(index=False))
print("\nSpearman entre réguas (votos):")
print(t[["def_modelo_votos", "def_2022_votos", "abst_modelo_votos_lula", "abst_2022_votos_lula"]].corr("spearman").round(2).to_string())
print("Spearman entre réguas (pp):")
print(t[["def_modelo_pp", "def_2022_pp", "abst_modelo_pp", "abst_2022_pp"]].corr("spearman").round(2).to_string())
