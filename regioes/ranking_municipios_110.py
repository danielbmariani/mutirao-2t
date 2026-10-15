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
mun = mun[["cd_mun", "nm_mun", "uf", "votos_validos_2022t1", "pct_lula_2022t1", "pct_bolsonaro_2022t1",
           "votos_validos_2022t2", "pct_lula_2022t2", "pct_bolsonaro_2022t2",
           "votos_validos_2026t1", "pct_lula_2026t1", "pct_flavio_2026t1", "pct_outros_2026t1"]]
depara = pd.read_csv(DADOS / "brutos/tse_ibge.csv")[["codigo_tse", "codigo_ibge"]]

def abst(arq):
    return con.sql(f"""
      SELECT NR_TURNO AS turno, CD_MUNICIPIO AS codigo_tse,
             sum(QT_APTOS) AS aptos, sum(QT_ABSTENCOES) AS abst, sum(QT_COMPARECIMENTO) AS comp,
             sum(QT_VOTOS_NOMINAIS) AS nominais, sum(QT_VOTOS_BRANCOS) AS brancos, sum(QT_VOTOS_NULOS) AS nulos
      FROM read_csv('{arq}', delim=';', header=true, encoding='latin-1', ignore_errors=true)
      WHERE CD_CARGO = 1 AND SG_UF <> 'ZZ' GROUP BY 1, 2""").df()

a26 = abst(TSE / "detalhe_votacao_secao_2026_BR.csv")
a22 = abst(TSE / "detalhe_votacao_secao_2022_BR.csv")
def por_mun(d, turno, suf):
    d = d[d.turno == turno].merge(depara, on="codigo_tse", how="inner")
    g = d.groupby("codigo_ibge")[["aptos", "abst", "comp", "nominais", "brancos", "nulos"]].sum()
    return pd.DataFrame({f"aptos_{suf}": g.aptos, f"abst_{suf}_pct": (100 * g.abst / g.aptos).round(2),
                         f"comp_{suf}": g.comp, f"nominais_{suf}": g.nominais, f"bn_{suf}": g.brancos + g.nulos})
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

# ==== OUTROS MODELOS DO GRUPO (pedido 15/10: "todos os indicadores de todos os modelos")
# (a) Colmeia, indicadores atuais por LOCAL de votação, agregados por cidade no
#     índice dados/prioritarios/<UF>.json e em dados/municipios/<UF>/<cd>.json
#     (commit de 12/10/2026; consolidado em dados/brutos/colmeia/)
col = pd.read_parquet(DADOS / "brutos/colmeia/colmeia_municipios_2026-10-12.parquet")
col = pd.DataFrame({"cd_mun": col.cd_mun,
    "colmeia_ativar_locais": col.ativar_locais, "colmeia_ativar_votos": col.ativar_votos,
    "colmeia_ativar_eleitorado_pct": col["at"],
    "colmeia_reconquistar_locais": col.reconquistar_locais,
    "colmeia_reconquistar_perda_por100": col.reconquistar_perda_por100,
    "colmeia_reconquistar_votos": col.reconquistar_votos,
    "colmeia_votos_para_vencer": col.vm, "colmeia_mob_pp": col.mob})
t = t.merge(col, on="cd_mun", how="left")

# (b) Painel da campanha ("metodologia da Amanda", 12/10): território prioritário
#     por microrregião, a partir da planilha de locais compartilhada no grupo
#     (3.236 municípios em 20 UFs), e as réguas do painel recalculadas do TSE
GI = DADOS / "brutos/grupo_indicadores"
L = pd.read_excel(GI / "impulsionamento_locais_prioritarios.xlsx", sheet_name="Locais",
                  usecols=["Estado", "Microrregião", "Município", "Código do local",
                           "Prioridade (metodologia da Amanda, 12/10)", "Lado", "Onde começar? (etiqueta de 09/10)"])
L["codigo_tse"] = L["Código do local"].str.split("-").str[1].astype(int)
L = L.merge(depara, on="codigo_tse", how="left")
print("locais da campanha sem de-para:", int(L.codigo_ibge.isna().sum()))
gl = L.groupby("codigo_ibge")
camp = pd.DataFrame({
    "camp_microrregiao": gl["Microrregião"].first(),
    "camp_prioridade": gl["Prioridade (metodologia da Amanda, 12/10)"].first(),
    "camp_locais": gl.size(),
    "camp_locais_prioridade1": gl["Onde começar? (etiqueta de 09/10)"].apply(lambda s: int((s == "Prioridade 1").sum())),
    "camp_locais_ativar": gl["Lado"].apply(lambda s: int((s == "ativar").sum())),
    "camp_locais_conter": gl["Lado"].apply(lambda s: int((s == "conter").sum())),
    "_uf": gl["Estado"].first()}).reset_index().rename(columns={"codigo_ibge": "cd_mun"})
camp["cd_mun"] = camp.cd_mun.astype(int)
Mi = pd.read_excel(GI / "impulsionamento_locais_prioritarios.xlsx", sheet_name="Microrregiões", header=3)
Mi = Mi.rename(columns={"Estado": "_uf", "Microrregião": "camp_microrregiao",
    "Metodologia da Amanda: ação principal": "camp_acao_microrregiao",
    "Metodologia da Amanda: votos a buscar": "camp_votos_a_buscar_microrregiao",
    "Metodologia da Amanda: quanto rende (votos)": "camp_quanto_rende_microrregiao"})
Mi = Mi[["_uf", "camp_microrregiao", "camp_acao_microrregiao", "camp_votos_a_buscar_microrregiao", "camp_quanto_rende_microrregiao"]].dropna(subset=["camp_microrregiao"])
camp = camp.merge(Mi, on=["_uf", "camp_microrregiao"], how="left").drop(columns="_uf")
for c in ("camp_votos_a_buscar_microrregiao", "camp_quanto_rende_microrregiao"):
    camp[c] = pd.to_numeric(camp[c], errors="coerce").round(0)
for c in ("camp_microrregiao", "camp_prioridade", "camp_acao_microrregiao"):
    camp[c] = camp[c].astype("string")
t = t.merge(camp, on="cd_mun", how="left")
# réguas do painel, do resultado oficial (TSE)
lula22t2 = t.pct_lula_2022t2 / 100 * t.votos_validos_2022t2
lula26 = t.pct_lula_2026t1 / 100 * t.votos_validos_2026t1
t["camp_votos_lula_perdidos_2022t2"] = (lula22t2 - lula26).round(0)
t["camp_outros_candidatos_votos"] = (t.pct_outros_2026t1 / 100 * t.votos_validos_2026t1).round(0)
t["camp_variacao_diferenca_pp"] = ((t.pct_lula_2026t1 - t.pct_flavio_2026t1) - (t.pct_lula_2022t2 - t.pct_bolsonaro_2022t2)).round(2)
t["camp_desempenho_2022t2_pct"] = (100 * t.pct_lula_2022t2 / (t.pct_lula_2022t2 + t.pct_bolsonaro_2022t2)).round(2)
t["camp_desempenho_2026_pct"] = (100 * t.pct_lula_2026t1 / (t.pct_lula_2026t1 + t.pct_flavio_2026t1)).round(2)
t["camp_variacao_desempenho_pp"] = (t.camp_desempenho_2026_pct - t.camp_desempenho_2022t2_pct).round(2)

# (c) NIELE (Rodrigo Mahlmeister), "Onde Lula perdeu voto": decomposição LMDI de
#     L = c·v·r·q (votos de Lula por eleitor) entre comparecimento, brancos/nulos,
#     terceira via e reconversão, contra o 1T e o 2T de 2022. Versão MUNICIPAL
#     com o resultado oficial, sem o ajuste de ruído nem o pareamento de locais
#     do original (branch niele/onde-lula-perdeu do repositório indicadores).
def lmdi(base):
    ap, co, va = t[f"aptos_{base}"], t[f"comp_{base}"], t[f"votos_validos_{base}"]
    pl = t[f"pct_lula_{base}"] / 100
    pa = (t["pct_bolsonaro_2022t1"] if base == "2022t1" else t["pct_bolsonaro_2022t2"]) / 100
    Lb, Ab = pl * va, pa * va
    cb, vb, rb, qb = co / ap, va / co, (Lb + Ab) / va, Lb / (Lb + Ab)
    ap6, co6, va6 = t.aptos_2026, t.comp_2026, t.votos_validos_2026t1
    L6, A6 = t.pct_lula_2026t1 / 100 * va6, t.pct_flavio_2026t1 / 100 * va6
    c6, v6, r6, q6 = co6 / ap6, va6 / co6, (L6 + A6) / va6, L6 / (L6 + A6)
    Yb, Y6 = cb * vb * rb * qb, c6 * v6 * r6 * q6          # votos de Lula por eleitor
    with np.errstate(divide="ignore", invalid="ignore"):
        lm = np.where(np.isclose(Y6, Yb), Y6, (Y6 - Yb) / (np.log(Y6) - np.log(Yb)))
        parc = {k: -lm * np.log(x6 / xb) * ap6 for k, x6, xb in
                [("comparecimento", c6, cb), ("brancos_nulos", v6, vb), ("terceira_via", r6, rb), ("reconversao", q6, qb)]}
    out = pd.DataFrame(parc).round(0)
    out["total"] = ((Yb - Y6) * ap6).round(0)        # = soma das parcelas (perda positiva)
    return out
for base, suf in (("2022t1", "1t"), ("2022t2", "2t")):
    d = lmdi(base)
    for c in d.columns: t[f"niele_{suf}_{c}"] = d[c]
t["niele_persuasao_votos"] = (t.niele_1t_reconversao + t.niele_1t_terceira_via + t.niele_1t_brancos_nulos).round(0)
t["niele_mobilizacao_votos"] = t.niele_2t_comparecimento.clip(lower=0).round(0)
t["niele_total_votos"] = (t.niele_persuasao_votos.clip(lower=0) + t.niele_mobilizacao_votos).round(0)
t["niele_votos_por_mil"] = (1000 * t.niele_total_votos / t.aptos_2026).round(1)
t["niele_estrategia"] = np.where(t.niele_mobilizacao_votos > t.niele_persuasao_votos, "Mobilização",
                        np.where(t.niele_2t_terceira_via > t.niele_2t_reconversao, "Terceira via", "Reconversão"))
chk = (t.niele_1t_total - (t.niele_1t_comparecimento + t.niele_1t_brancos_nulos + t.niele_1t_terceira_via + t.niele_1t_reconversao)).abs().max()
print(f"LMDI fecha? máx |total − soma| = {chk:.1f} voto(s); Brasil 1T (mil): total {t.niele_1t_total.sum()/1e3:.0f}, "
      f"comp {t.niele_1t_comparecimento.sum()/1e3:.0f}, bn {t.niele_1t_brancos_nulos.sum()/1e3:.0f}, "
      f"3ª via {t.niele_1t_terceira_via.sum()/1e3:.0f}, reconv {t.niele_1t_reconversao.sum()/1e3:.0f} | "
      f"2T: total {t.niele_2t_total.sum()/1e3:.0f}, comp {t.niele_2t_comparecimento.sum()/1e3:.0f}, 3ª via {t.niele_2t_terceira_via.sum()/1e3:.0f}, reconv {t.niele_2t_reconversao.sum()/1e3:.0f}")

# (d) Fernando Barbalho, classificação G4 (711 municípios em que Lula liderou no
#     1T de 2022 e deixou de liderar em 2026): demanda baixa × oferta alta de
#     programas federais, por dimensão
G = pd.read_excel(GI / "classificacao_711_sete_dimensoes_G4_com_votos_lula.xlsx", sheet_name="Classificacao_711")
G = pd.DataFrame({"cd_mun": G.IBGE.astype(int), "g4_n": G["Nº G4"], "g4_dimensoes": G["Dimensões G4"].astype("string"), "g4_perfil": G["Perfil final (G4)"].astype("string")})
t = t.merge(G, on="cd_mun", how="left")

# (e) o que o SITE do mutirão mostra por município (com teto aritmético e regra
#     "só onde Lula lidera" na abstenção): areas_95.py -> areas_mun.json
A = json.load(open(SITE / "areas_mun.json"))["areas"]
A = pd.DataFrame({"cd_mun": [int(a["cd"]) for a in A],
                  "site_def_votos_teto": [a.get("v", {}).get("conv") for a in A],
                  "site_abst_votos_teto": [a.get("a", {}).get("conv") for a in A],
                  "site_abst_saldo": [a.get("a", {}).get("net") for a in A]})
t = t.merge(A, on="cd_mun", how="left")

# ---- rankings nacionais (1 = maior)
def rk(col):
    return t[col].rank(ascending=False, method="min").astype("Int64")
for c in ["pop_censo_2022", "pct_lula_2026t1", "pct_lula_2022t1", "esperado_pct", "abst_2026_pct",
          "def_modelo_votos", "def_modelo_pp", "def_2022_votos", "def_2022_pp",
          "abst_modelo_votos_lula", "abst_modelo_pp", "abst_2022_votos_lula", "abst_2022_pp",
          "bolsa_familia_pct_pop", "cadunico_pct_pop", "bpc_pct_pop", "farmacia_popular_pct_pop",
          "pe_de_meia_pct_pop", "mei_pct_pop", "emprego_formal_pct_pop", "mcmv_por_100hab",
          "colmeia_ativar_votos", "colmeia_reconquistar_votos", "camp_votos_lula_perdidos_2022t2",
          "camp_outros_candidatos_votos", "niele_total_votos", "niele_votos_por_mil", "site_def_votos_teto", "site_abst_votos_teto"]:
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
        "acao", "acao_motivo", "porque", "governo",
        "site_def_votos_teto", "rk_site_def_votos_teto", "site_abst_votos_teto", "rk_site_abst_votos_teto", "site_abst_saldo",
        "colmeia_ativar_locais", "colmeia_ativar_votos", "rk_colmeia_ativar_votos", "colmeia_ativar_eleitorado_pct",
        "colmeia_reconquistar_locais", "colmeia_reconquistar_perda_por100", "colmeia_reconquistar_votos", "rk_colmeia_reconquistar_votos",
        "colmeia_votos_para_vencer", "colmeia_mob_pp",
        "camp_microrregiao", "camp_prioridade", "camp_acao_microrregiao", "camp_votos_a_buscar_microrregiao", "camp_quanto_rende_microrregiao",
        "camp_locais", "camp_locais_prioridade1", "camp_locais_ativar", "camp_locais_conter",
        "camp_votos_lula_perdidos_2022t2", "rk_camp_votos_lula_perdidos_2022t2", "camp_outros_candidatos_votos", "rk_camp_outros_candidatos_votos",
        "camp_variacao_diferenca_pp", "camp_desempenho_2022t2_pct", "camp_desempenho_2026_pct", "camp_variacao_desempenho_pp",
        "niele_1t_total", "niele_1t_reconversao", "niele_1t_terceira_via", "niele_1t_brancos_nulos", "niele_1t_comparecimento",
        "niele_2t_total", "niele_2t_reconversao", "niele_2t_terceira_via", "niele_2t_brancos_nulos", "niele_2t_comparecimento",
        "niele_persuasao_votos", "niele_mobilizacao_votos", "niele_total_votos", "rk_niele_total_votos", "niele_votos_por_mil", "rk_niele_votos_por_mil", "niele_estrategia",
        "g4_n", "g4_dimensoes", "g4_perfil"]
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
DIC = {
 "cd_mun": ("Código IBGE do município (7 dígitos)", "IBGE"), "municipio": ("Nome", "IBGE"), "uf": ("UF", "IBGE"),
 "pop_2022": ("População, Censo 2022", "IBGE"), "aptos_2026": ("Eleitores aptos, 1T 2026", "TSE"), "validos_2026": ("Votos válidos para presidente, 1T 2026", "TSE"),
 "lula_2026_pct": ("Fatia de Lula nos válidos, 1T 2026 (%)", "TSE"), "flavio_2026_pct": ("Fatia de Flávio, 1T 2026 (%)", "TSE"), "lula_lidera": ("Lula à frente de Flávio em 2026", "TSE"),
 "lula_2022t1_pct": ("Fatia de Lula, 1T 2022 (%)", "TSE"), "lula_2022t2_pct": ("Fatia de Lula, 2T 2022 (%)", "TSE"),
 "lula_esperado_pct": ("Fatia esperada pelo modelo de voto do mutirão (soma dos setores)", "modelo_lula_72"),
 "def_modelo_pp": ("Esperado − real, pontos (positivo = faltaram votos)", "modelo_lula_72"), "def_modelo_votos": ("Déficit em votos: Σ (esperado − real) × válidos dos setores", "modelo_lula_72"),
 "def_2022_pp": ("Fatia 1T 2022 − fatia 1T 2026, pontos", "TSE"), "def_2022_votos": ("Queda em pontos × válidos de 2026", "TSE"),
 "abst_2026_pct": ("Abstenção oficial, 1T 2026 (% dos aptos)", "TSE"), "abst_esperada_pct": ("Abstenção esperada pelo modelo (soma dos setores)", "modelo_abst_75"),
 "abst_modelo_pp": ("Abstenção real − esperada, pontos, na base de setores do modelo", "modelo_abst_75"), "abst_modelo_votos_lula": ("Σ excesso × aptos × fatia de Lula dos setores", "modelo_abst_75"),
 "abst_modelo_saldo_lula_flavio": ("Σ excesso × aptos × (Lula − Flávio)", "modelo_abst_75"),
 "abst_2022t2_pct": ("Abstenção oficial, 2T 2022 (%)", "TSE"), "abst_2022t1_pct": ("Abstenção oficial, 1T 2022 (%)", "TSE"),
 "abst_2022_pp": ("Abstenção 2026 − abstenção 2T 2022, pontos", "TSE"), "abst_2022_eleitores": ("Eleitores a mais em casa: excesso × aptos 2026", "TSE"), "abst_2022_votos_lula": ("Eleitores a mais em casa × fatia de Lula 2026", "TSE"),
 "bolsa_familia_pct_pop": ("Pessoas em famílias do Bolsa Família, % da pop. (ago/2026)", "MDS"), "cadunico_pct_pop": ("Pessoas no CadÚnico, % da pop. (ago/2026)", "MDS"), "bpc_pct_pop": ("Beneficiários do BPC, % da pop. (ago/2026)", "MDS"),
 "farmacia_popular_pct_pop": ("Atendidos pela Farmácia Popular no ano, % da pop. (até ago/2026)", "ComunicaBR/MS"), "pe_de_meia_pct_pop": ("Estudantes no Pé-de-Meia, % da pop. (até mar/2026)", "ComunicaBR/MEC"),
 "mei_pct_pop": ("MEI cadastrados, % da pop. (até jun/2026)", "ComunicaBR/MF"), "emprego_formal_pct_pop": ("Empregos formais, % da pop. (até jul/2026)", "ComunicaBR/MTE"), "mcmv_por_100hab": ("Moradias do MCMV desde 2023 por 100 hab. (até jul/2026)", "ComunicaBR/MCID"),
 "acao": ("O que fazer (regra na página /municipios)", "mutirão"), "acao_motivo": ("Motivo curto da ação", "mutirão"), "porque": ("As quatro réguas em frases", "mutirão"), "governo": ("Programas em que o município está mais alto no país", "mutirão"),
 "site_def_votos_teto": ("Votos a recuperar como o site mostra: déficit do modelo cortado em zero e no teto aritmético", "mutirão/areas_95"),
 "site_abst_votos_teto": ("Votos na abstenção excedente como o site mostra: com teto e só onde Lula lidera (0 onde não lidera)", "mutirão/areas_95"), "site_abst_saldo": ("Saldo Lula − Flávio da abstenção excedente, só onde Lula lidera", "mutirão/areas_95"),
 "colmeia_ativar_locais": ("Locais de votação do indicador Ativar (Lula forte e abstenção subiu desde 1T 2022, por local)", "Colmeia 12/10"),
 "colmeia_ativar_votos": ("Simulação do Ativar: votos que Lula teria se os ausentes adicionais votassem como o local, somando os locais da cidade", "Colmeia 12/10"),
 "colmeia_ativar_eleitorado_pct": ("Parcela do eleitorado da cidade em locais do Ativar (%)", "Colmeia 12/10"),
 "colmeia_reconquistar_locais": ("Linhas do Reconquistar (setores/locais onde Lula perdeu parcela desde o 1T 2022)", "Colmeia 12/10"),
 "colmeia_reconquistar_perda_por100": ("Perda de parcela de Lula, votos a cada 100 eleitores, ajustada pelo ruído (média da cidade)", "Colmeia 12/10"),
 "colmeia_reconquistar_votos": ("Perda de parcela em votos (queda × quem compareceu em 2026)", "Colmeia 12/10"),
 "colmeia_votos_para_vencer": ("Votos que faltam a Lula para vencer Flávio na cidade (0 onde já vence)", "Colmeia 12/10"),
 "colmeia_mob_pp": ("100 × abstenção/aptos × (Lula − Flávio)/válidos: margem que a abstenção devolveria votando como a cidade", "Colmeia 12/10"),
 "camp_microrregiao": ("Microrregião IBGE da cidade no painel da campanha (só o território prioritário: 3.236 municípios, 20 UFs)", "painel da campanha 12/10"),
 "camp_prioridade": ("Prioridade da metodologia da Amanda (12/10): microrregião prioritária / estado inteiro / estado inteiro, por onde começar", "painel da campanha 12/10"),
 "camp_acao_microrregiao": ("Ação principal da microrregião na ficha da coordenação (Mobilização, Conversão, Reconversão, Abstenção do Flávio)", "painel da campanha 12/10"),
 "camp_votos_a_buscar_microrregiao": ("Meta de votos a buscar da MICRORREGIÃO (não é da cidade; não somar)", "painel da campanha 12/10"), "camp_quanto_rende_microrregiao": ("Quanto rende (votos) da microrregião", "painel da campanha 12/10"),
 "camp_locais": ("Locais de votação da cidade na planilha do painel", "painel da campanha 12/10"), "camp_locais_prioridade1": ("Locais com etiqueta 'Prioridade 1' (onde começar, 09/10)", "painel da campanha 12/10"),
 "camp_locais_ativar": ("Locais do lado 'ativar' (Lula na frente em 2026)", "painel da campanha 12/10"), "camp_locais_conter": ("Locais do lado 'conter' (Flávio na frente)", "painel da campanha 12/10"),
 "camp_votos_lula_perdidos_2022t2": ("Régua do painel 'Votos que o Lula perdeu': votos de Lula no 2T 2022 − 1T 2026", "TSE"),
 "camp_outros_candidatos_votos": ("Régua 'Outros candidatos': votos de 2026 fora Lula e Flávio (Conversão)", "TSE"),
 "camp_variacao_diferenca_pp": ("Régua 'Variação da diferença': (Lula − Flávio 2026) − (Lula − Jair 2T 2022), pontos (Reconversão)", "TSE"),
 "camp_desempenho_2022t2_pct": ("Régua 'Desempenho': Lula ÷ (Lula + Jair), 2T 2022 (%)", "TSE"), "camp_desempenho_2026_pct": ("Lula ÷ (Lula + Flávio), 1T 2026 (%)", "TSE"), "camp_variacao_desempenho_pp": ("Variação do desempenho, pontos", "TSE"),
 "niele_1t_total": ("NIELE: perda de votos de Lula contra o 1T 2022 (LMDI, versão municipal oficial; positivo = perdeu)", "método NIELE, calc. mutirão"),
 "niele_1t_reconversao": ("Parcela da perda por reconversão (q = Lula/(Lula+adversário)), base 1T 2022", "método NIELE, calc. mutirão"), "niele_1t_terceira_via": ("Parcela terceira via (r = (Lula+adv)/válidos), base 1T 2022", "método NIELE, calc. mutirão"),
 "niele_1t_brancos_nulos": ("Parcela brancos e nulos (v = válidos/comparecimento), base 1T 2022", "método NIELE, calc. mutirão"), "niele_1t_comparecimento": ("Parcela comparecimento (c = comparecimento/aptos), base 1T 2022", "método NIELE, calc. mutirão"),
 "niele_2t_total": ("Perda contra o 2T 2022 (potencial)", "método NIELE, calc. mutirão"), "niele_2t_reconversao": ("Reconversão, base 2T 2022", "método NIELE, calc. mutirão"), "niele_2t_terceira_via": ("Terceira via (voto em aberto), base 2T 2022", "método NIELE, calc. mutirão"),
 "niele_2t_brancos_nulos": ("Brancos e nulos, base 2T 2022", "método NIELE, calc. mutirão"), "niele_2t_comparecimento": ("Comparecimento, base 2T 2022", "método NIELE, calc. mutirão"),
 "niele_persuasao_votos": ("Persuasão = reconversão + terceira via + brancos/nulos, base 1T 2022", "método NIELE, calc. mutirão"), "niele_mobilizacao_votos": ("Mobilização = parcela comparecimento contra o 2T 2022, cortada em zero", "método NIELE, calc. mutirão"),
 "niele_total_votos": ("Persuasão (≥0) + mobilização", "método NIELE, calc. mutirão"), "niele_votos_por_mil": ("Total por mil eleitores aptos (critério de ranking do NIELE)", "método NIELE, calc. mutirão"),
 "niele_estrategia": ("Mobilização se supera a persuasão; senão Terceira via se, contra o 2T, supera a reconversão; senão Reconversão", "método NIELE, calc. mutirão"),
 "g4_n": ("Nº de dimensões em G4 (demanda baixa, oferta alta) entre 7; só os 711 municípios do universo", "Fernando Barbalho, 13/10"),
 "g4_dimensoes": ("Dimensões em G4", "Fernando Barbalho, 13/10"), "g4_perfil": ("Perfil final (A a K)", "Fernando Barbalho, 13/10"),
}
dic = []
for c in t.columns:
    base = c[3:] if c.startswith("rk_") else c
    if base not in DIC: raise SystemExit(f"coluna sem dicionário: {c}")
    d, f = DIC[base]
    dic.append({"coluna": c, "descricao": ("Posição nacional (1 = maior) em: " + d) if c.startswith("rk_") else d, "fonte": f})
pd.DataFrame(dic).to_csv(E / "ranking_municipios_dicionario.csv", index=False)
pd.DataFrame(dic).to_csv(SITE / "ranking_municipios_dicionario.csv", index=False)

# JSON compacto para a página (arrays; None onde falta)
def cell(v):
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA: return None
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating, float)): return float(v)
    if isinstance(v, (np.bool_, bool)): return bool(v)
    return v
FORA_JSON = {"porque", "acao_motivo", "governo", "camp_quanto_rende_microrregiao", "g4_dimensoes",
             "niele_1t_brancos_nulos", "niele_1t_comparecimento", "niele_2t_brancos_nulos", "niele_2t_reconversao", "niele_2t_terceira_via",
             "abst_2022t1_pct", "lula_2022t2_pct", "camp_desempenho_2022t2_pct", "camp_desempenho_2026_pct"}
tj = t[[c for c in t.columns if not c.startswith("rk_") and c not in FORA_JSON]]  # textos: a página gera com as mesmas regras
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
