# Regiões de QUEDA DE LULA 2022 -> 2026 (3ª visão do site eleitores,
# 13/10): mesma máquina do regioes_lula_73, moeda = votos que Lula teria a
# mais se mantivesse no eleitorado de 2026 a fatia do 1º turno de 2022
# (swing_lula_93). Sem modelo: a régua é a própria eleição passada.
# Bloco quente = queda da fatia >= LIMIAR_PP (pontos), medida pela SOMA de
# votos do bloco nos dois anos (a reatribuição de locais de votação entre
# setores se cancela no subdistrito); blocos com eleitorado instável
# (razão de válidos fora de 2/3..1,5 ou < 100 votos) ficam fora.
# Blocos = SUBDISTRITOS censitários (11.311); componentes contíguos
# (STRtree); alongadas (>60 km) particionadas por sementes >=35 km;
# aceitação >= PISO_ABS votos perdidos; teto aritmético implícito (a queda
# nunca supera a fatia de 2022). SEM teto de quantidade: catálogo inteiro
# ranqueado por votos absolutos; listas top-50/25/10 derivam no front.
# Cortes (13/10): menos 8 pp/3000 · padrão 6 pp/2000 · mais 5 pp/2000.
# Saídas: embed_eleitores/dados/regioes_swing{suf}.json + .geojson
#         relatorios/LULA_regioes_diagnostico_swing{suf}.txt
import json
import sys
from pathlib import Path

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import STRtree
from shapely.geometry import mapping
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DADOS, DIR_PROC, DIR_RELATORIOS, DIR_SITES

PQ_SW = DIR_PROC / "eleitores/setor_swing_lula.parquet"
PQ_DASH = DIR_PROC / "dashboard/setores_eleicao_renda.parquet"
PQ_APOND = DIR_PROC / "dashboard/apond_completo.parquet"
PQ_DIST = DIR_PROC / "resultados_por_distrito/distritos_eleicao.parquet"
PQ_SUB = DADOS / "brutos/censo/malha/subdistritos_2022.parquet"
DIR_SITE = DIR_SITES / "embed_eleitores/dados"

# três cortes pré-computados p/ o controle do site:
#   menos (8 pp / 3000 votos) · padrão (6/2000) · mais (5/2000)
import sys as _sys
LIMIAR_PP = float(_sys.argv[1]) if len(_sys.argv) > 1 else 6.0
PISO_ABS = int(_sys.argv[2]) if len(_sys.argv) > 2 else 2_000
SUFIXO = "_swing" + (_sys.argv[3] if len(_sys.argv) > 3 else "")
RAZAO_MIN, RAZAO_MAX, MIN_VOTOS = 2 / 3, 1.5, 100
DIAG_KM = 60
SEED_KM = 35
SIMPLIFICA = 0.003


class UF_:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def wmean(v, w):
    m = v.notna() & w.notna() & (w > 0)
    return float(np.average(v[m], weights=w[m])) if m.any() else None


def rnd(x, nd=1):
    return round(x, nd) if x is not None else None


def arredonda(obj, nd=4):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], float):
            return [round(v, nd) for v in obj]
        return [arredonda(o, nd) for o in obj]
    return obj


def main():
    DIR_SITE.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    # blocos por subdistrito: fatias de 2022 e 2026 pela SOMA de votos ->
    # queda do bloco -> votos perdidos no eleitorado de 2026 (corte em 0)
    bl = con.sql(f"""
      SELECT substr(CD_SETOR, 1, 11) AS CD_SUB,
             sum(lula22t1 * validos22) / sum(validos22) AS l22,
             sum(lula26t1 * validos) / sum(validos) AS pl,
             sum(validos22) AS validos22,
             sum(validos) AS validos
      FROM '{PQ_SW}'
      WHERE validos > 0 AND validos22 > 0
        AND lula22t1 IS NOT NULL AND lula26t1 IS NOT NULL
      GROUP BY 1
    """).df()
    bl["deficit_pp"] = bl.l22 - bl.pl
    bl["conv"] = (bl.deficit_pp.clip(lower=0) / 100 * bl.validos)
    razao = bl.validos / bl.validos22
    bl["estavel"] = ((razao >= RAZAO_MIN) & (razao <= RAZAO_MAX) &
                     (bl.validos >= MIN_VOTOS) & (bl.validos22 >= MIN_VOTOS))
    print(f"blocos instáveis excluídos: {(~bl.estavel).sum()} "
          f"({bl.validos[~bl.estavel].sum() / bl.validos.sum():.2%} "
          f"dos válidos)", flush=True)
    bl = bl[bl.estavel].copy()
    nomes = con.sql(f"""
      SELECT t.CD_DIST, any_value(t.NM_DIST) AS NM_DIST,
             any_value(m.nm_mun) AS NM_MUN
      FROM '{PQ_DIST}' t
      LEFT JOIN (SELECT DISTINCT cd_mun, nm_mun FROM '{PQ_DASH}') m
        ON m.cd_mun = t.CD_MUN GROUP BY 1
    """).df().set_index("CD_DIST")
    muni_nm = con.sql(f"""
      SELECT DISTINCT cd_mun, nm_mun, uf FROM '{PQ_DASH}'
      WHERE cd_mun IS NOT NULL
    """).df().set_index("cd_mun")
    base = con.sql(f"""
      SELECT d.cd_setor AS CD_SETOR, substr(d.cd_setor, 1, 11) AS CD_SUB,
             d.pop, d.renda_resp_media_sm AS renda_sm, d.situacao,
             d.pct_60mais, d.idade_media_15mais, d.pct_alfabetizados_15mais,
             p.pct_catolica, p.pct_evangelica, p.pct_sem_religiao,
             p.pct_superior_25mais_2022
      FROM '{PQ_DASH}' d
      LEFT JOIN '{PQ_APOND}' p ON p.apond = d.apond
    """).df()
    rd = base[["renda_sm", "pop"]].dropna().sort_values("renda_sm")
    cw = rd["pop"].cumsum() / rd["pop"].sum()

    def pct_renda(x):
        if x is None:
            return None
        i = rd.renda_sm.searchsorted(x)
        return int(round(100 * cw.iloc[min(i, len(cw) - 1)]))

    malha = gpd.read_parquet(PQ_SUB).set_index("CD_SUB")
    cent = malha.geometry.representative_point()
    total = bl.conv.sum()
    print(f"{len(bl)} blocos; votos perdidos em relação a 2022 (soma das quedas) "
          f"{total/1e6:.2f} mi", flush=True)
    piso = PISO_ABS

    d = bl[bl.validos.notna() & (bl.validos > 0)].copy()
    d["taxa"] = d.deficit_pp

    def componentes(blocks):
        geoms = malha.reindex(blocks.CD_SUB).geometry
        ok = geoms.notna().values
        blocks = blocks[ok].reset_index(drop=True)
        geoms = geoms[ok]
        if not len(blocks):
            return []
        tree = STRtree(geoms.values)
        pares = tree.query(geoms.values, predicate="intersects")
        uf = UF_(len(blocks))
        for a, b in pares.T:
            if a != b:
                uf.union(int(a), int(b))
        comps = blocks.assign(_c=[uf.find(i) for i in range(len(blocks))])
        return [g.drop(columns="_c") for _, g in comps.groupby("_c")]

    def km2(ix, iy, jx, jy):
        kx = 111.32 * np.cos(np.radians((iy + jy) / 2))
        return ((ix - jx) * kx) ** 2 + ((iy - jy) * 111.32) ** 2

    def particiona_geo(g):
        cx = cent.reindex(g.CD_SUB).x.values
        cy = cent.reindex(g.CD_SUB).y.values
        dx = (cx.max() - cx.min()) * 111.32 * np.cos(np.radians(cy.mean()))
        dy = (cy.max() - cy.min()) * 111.32
        if (dx ** 2 + dy ** 2) ** 0.5 <= DIAG_KM or len(g) < 2:
            return [g]
        ordem = np.argsort(-g.conv.values)
        seeds = []
        for i in ordem:
            if all(km2(cx[i], cy[i], cx[j], cy[j]) >= SEED_KM ** 2
                   for j in seeds):
                seeds.append(i)
        if len(seeds) <= 1:
            return [g]
        d2 = np.array([[km2(cx[i], cy[i], cx[j], cy[j]) for j in seeds]
                       for i in range(len(g))])
        rot = d2.argmin(axis=1)
        return [g.iloc[rot == k] for k in range(len(seeds))
                if (rot == k).any()]

    regioes = []
    for g in componentes(d[d.taxa >= LIMIAR_PP]):
        if g.conv.sum() < piso:
            continue
        for pt in particiona_geo(g):
            if pt.conv.sum() >= piso:
                regioes.append(pt)
    regioes.sort(key=lambda g: -g.conv.sum())
    print(f"{len(regioes)} regiões aceitas (>= {PISO_ABS} votos, "
          f">= {LIMIAR_PP} pp)", flush=True)

    feats, lista = [], []
    for n, g in enumerate(regioes, start=1):
        conv = g.conv.sum()
        g = g.assign(cd_mun=g.CD_SUB.str[:7], cd_dist=g.CD_SUB.str[:9])
        por_mun = (g.groupby("cd_mun").conv.sum()
                   .sort_values(ascending=False))
        nm_de = lambda cd: (muni_nm.nm_mun.get(cd) or cd)
        cidade = nm_de(por_mun.index[0])
        uf_dom = muni_nm.uf.get(por_mun.index[0]) or "?"
        share1 = por_mun.iloc[0] / conv
        por_dist = (g.groupby("cd_dist").conv.sum()
                    .sort_values(ascending=False))
        tops = [nomes.NM_DIST.get(cd) for cd in por_dist.index[:2]]
        tops = [t for t in tops if t]
        dentro = [t for t in tops if t != cidade and
                  t not in set(muni_nm.nm_mun.dropna())]
        if tops and tops[0] == cidade:
            nome = cidade
        elif dentro:
            nome = f"{' / '.join(dentro[:2])}, em {cidade}"
        else:
            nome = cidade
        if len(por_mun) > 1 and share1 < 0.55:
            seg = nm_de(por_mun.index[1])
            if seg not in nome:
                nome += (f", {seg} e região" if len(por_mun) > 3
                         else f" e {seg}")
            elif len(por_mun) > 3:
                nome += " e região"
        s = base[base.CD_SUB.isin(g.CD_SUB)]
        w = s["pop"]
        renda = wmean(s.renda_sm, w)
        soma_v = g.validos.sum()
        perfil = {
            "renda_sm": rnd(renda, 2),
            "renda_percentil_br": pct_renda(renda),
            "idade_media": rnd(wmean(s.idade_media_15mais, w)),
            "pct_60mais": rnd(wmean(s.pct_60mais, w)),
            "pct_alfabetizados": rnd(wmean(s.pct_alfabetizados_15mais, w)),
            "pct_urbano": rnd(100 * s.loc[s.situacao == "urbana",
                                          "pop"].sum() /
                              max(w.sum(), 1), 0),
            "ap_pct_catolica": rnd(wmean(s.pct_catolica, w)),
            "ap_pct_evangelica": rnd(wmean(s.pct_evangelica, w)),
            "ap_pct_sem_religiao": rnd(wmean(s.pct_sem_religiao, w)),
            "ap_pct_superior": rnd(wmean(s.pct_superior_25mais_2022, w)),
        }
        geom = unary_union(malha.reindex(g.CD_SUB)
                           .geometry.dropna().values)
        geom = geom.simplify(SIMPLIFICA, preserve_topology=True)
        c = cent.get(g.sort_values("conv", ascending=False)
                     .CD_SUB.iloc[0], geom.representative_point())
        lista.append({
            "n": n, "nome": nome, "uf": uf_dom,
            "mun_cd": por_mun.index[0], "mun_nm": cidade,
            "conv": int(round(conv)), "pop": int(w.sum()),
            "ll": [round(c.x, 4), round(c.y, 4)],
            "pl": rnd(float(np.average(g.pl, weights=g.validos))),
            "l22": rnd(float(np.average(g.l22, weights=g.validos22))),
            "validos": int(soma_v),
            "validos22": int(g.validos22.sum()),
            "muns": [{"cd": cd, "nm": nm_de(cd), "conv": int(round(v))}
                     for cd, v in por_mun.items()],
            "perfil": perfil,
        })
        gm = mapping(geom)
        feats.append({"type": "Feature",
                      "properties": {"n": n, "conv": int(round(conv))},
                      "geometry": {"type": gm["type"],
                                   "coordinates":
                                   arredonda(gm["coordinates"])}})
    # pertinência bloco -> região (p/ CSV público por setor)
    membros = pd.concat([regs_g.assign(n=i + 1)[["CD_SUB", "n"]]
                         for i, regs_g in enumerate(regioes[:len(lista)])])
    membros.to_parquet(DIR_PROC / "eleitores" /
                       f"membros{SUFIXO}.parquet", index=False)
    cobertura = sum(x["conv"] for x in lista) / total if total else 0
    o = d.sort_values("deficit_pp")
    cwv = o.validos.cumsum() / o.validos.sum()
    stops = [round(float(o.deficit_pp[(cwv >= q).idxmax()]), 1)
             for q in (0.02, 0.25, 0.5, 0.75, 0.98)]
    meta = {"stops_def": stops,
            "gerado": pd.Timestamp.now().strftime("%Y-%m-%d"),
            "total_deficit": int(round(total)),
            "cobertura_regioes": round(cobertura, 3),
            "n_regioes": len(lista),
            "limiar_pp": LIMIAR_PP, "piso_votos": PISO_ABS}
    with open(DIR_SITE / f"regioes{SUFIXO}.json", "w") as f:
        json.dump({"meta": meta, "regioes": lista}, f,
                  ensure_ascii=False, separators=(",", ":"),
                  allow_nan=False)
    with open(DIR_SITE / f"regioes{SUFIXO}.geojson", "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f,
                  separators=(",", ":"))
    kb = (DIR_SITE / f"regioes{SUFIXO}.geojson").stat().st_size / 1024
    print(f"regioes.json ({len(lista)}) + geojson ({kb:.0f} KB); "
          f"cobertura {cobertura:.0%}")
    (DIR_RELATORIOS / f"LULA_regioes_diagnostico{SUFIXO}.txt").write_text(
        json.dumps(meta, indent=1) + "\n" + "\n".join(
            f"#{x['n']:>3} {x['nome'][:52]:<52} {x['uf']} "
            f"conv {x['conv']:>7,} pop {x['pop']:>9,}"
            for x in lista[:60]) + "\n")


if __name__ == "__main__":
    main()
