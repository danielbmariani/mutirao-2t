# Catálogos por UNIDADE DE ÁREA do site eleitores (13/10): município e
# distrito censitário, com as três moedas (déficit vs esperado, abstenção
# excedente, queda de 2022) na mesma linha. Pedido do Daniel: poder
# escolher a unidade em vez de só ver as manchas agrupadas de setores
# (regioes_*); o padrão do site passa a ser MUNICÍPIO.
#
# Tudo pela SOMA direta de votos dos setores da área (sem reagregar
# ruído): as mesmas fórmulas dos geradores de região, aplicadas no nível
# da área:
#   v (voto):   conv = min(max(0, Σ deficit_votos), Σ (100−pl)·válidos/100)
#   a (abst):   conv = min(max(0, Σ vperd), Σ abst·aptos·pl); net = max(0, Σ vnet);
#               lidera = pl > pf (regra da visão: só vale onde Lula lidera;
#               conv zerado onde não lidera, flag na ficha)
#   s (queda):  fatias pela soma de votos dos dois anos; conv = max(0,
#               (l22−pl)/100·válidos26); estável = razão de válidos 2/3..1,5
# Centroide (ll) e caixa (bb) vêm dos centroides dos setores ponderados
# por população (sem geometria: o contorno vem do tileset no front);
# distrito sem coordenada herda as do município (Nova Ubiratã/MT).
# Chaves CURTAS para caber no celular (o front expande): nm, uf (só mun),
# m (cd_mun, só dist), p = perfil {r, rp, im, p60, alf, urb, cat, eva,
# sr, sup}; v/a/s = moedas.
# Saídas: embed_eleitores/dados/areas_mun.json, areas_dist.json
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DIR_PROC, DIR_SITES

E = DIR_PROC / "eleitores"
PQ_DEF = E / "setor_deficit_lula.parquet"
PQ_ABS = E / "setor_abst_lula.parquet"
PQ_SW = E / "setor_swing_lula.parquet"
PQ_DASH = DIR_PROC / "dashboard/setores_eleicao_renda.parquet"
PQ_APOND = DIR_PROC / "dashboard/apond_completo.parquet"
PQ_DIST = DIR_PROC / "resultados_por_distrito/distritos_eleicao.parquet"
DIR_SITE = DIR_SITES / "embed_eleitores/dados"
RAZAO_MIN, RAZAO_MAX, MIN_VOTOS = 2 / 3, 1.5, 100


def r1(x):
    return None if x is None or pd.isna(x) else round(float(x), 1)


def main():
    con = duckdb.connect()
    con.sql("SET threads TO 8")
    nomes_d = con.sql(f"""
      SELECT CD_DIST, any_value(NM_DIST) AS NM_DIST FROM '{PQ_DIST}'
      GROUP BY 1""").df().set_index("CD_DIST").NM_DIST
    muni = con.sql(f"""
      SELECT cd_mun, any_value(nm_mun) AS nm_mun, any_value(uf) AS uf
      FROM '{PQ_DASH}' WHERE cd_mun IS NOT NULL GROUP BY 1
    """).df().set_index("cd_mun")
    base = con.sql(f"""
      SELECT d.cd_setor AS CD_SETOR, d.cd_mun, substr(d.cd_setor, 1, 9) AS cd_dist,
             d.pop, d.lon, d.lat, d.renda_resp_media_sm AS renda_sm,
             d.situacao, d.pct_60mais, d.idade_media_15mais,
             d.pct_alfabetizados_15mais, p.pct_catolica, p.pct_evangelica,
             p.pct_sem_religiao, p.pct_superior_25mais_2022
      FROM '{PQ_DASH}' d LEFT JOIN '{PQ_APOND}' p ON p.apond = d.apond
    """).df()
    rd = base[["renda_sm", "pop"]].dropna().sort_values("renda_sm")
    cw = rd["pop"].cumsum() / rd["pop"].sum()

    def pct_renda(x):
        if x is None or pd.isna(x):
            return None
        i = rd.renda_sm.searchsorted(x)
        return int(round(100 * cw.iloc[min(i, len(cw) - 1)]))

    ll_mun, bb_mun = {}, {}
    for nivel, chave_sql, chave in (("mun", "cd_mun", "cd_mun"),
                                    ("dist", "substr(CD_SETOR, 1, 9)", "cd_dist")):
        v = con.sql(f"""
          SELECT {chave_sql} AS k,
                 greatest(0, least(greatest(0, sum(deficit_votos)),
                       sum((100 - pct_lula) * validos) / 100.0)) AS conv,
                 sum(pct_lula * validos) / sum(validos) AS pl,
                 sum(esperado * validos) / sum(validos) AS esp,
                 sum(lula22t2 * validos) / sum(validos) AS l22,
                 sum(validos) AS validos
          FROM '{PQ_DEF}' WHERE validos > 0 GROUP BY 1""").df().set_index("k")
        a = con.sql(f"""
          SELECT {chave_sql} AS k,
                 -- teto com corte em 0: há setores com abstenção modelada
                 -- negativa (1.037), e o teto somado pode ficar < 0
                 greatest(0, least(greatest(0, sum(vperd)),
                       sum(abstencao / 100.0 * aptos * pl26 / 100.0))) AS conv,
                 greatest(0, sum(vnet)) AS net,
                 sum(pl26 * aptos) / sum(aptos) AS pl,
                 sum(pf26 * aptos) / sum(aptos) AS pf,
                 sum(abstencao * aptos) / sum(aptos) AS abr,
                 sum(esperada * aptos) / sum(aptos) AS abe,
                 sum(abst22t1 * aptos) / sum(aptos) AS ab22,
                 sum(aptos) AS aptos
          FROM '{PQ_ABS}' WHERE aptos > 0 GROUP BY 1""").df().set_index("k")
        s = con.sql(f"""
          SELECT {chave_sql} AS k,
                 sum(lula22t1 * validos22) / sum(validos22) AS l22,
                 sum(lula26t1 * validos) / sum(validos) AS pl,
                 sum(validos22) AS v22, sum(validos) AS v26
          FROM '{PQ_SW}'
          WHERE validos > 0 AND validos22 > 0
            AND lula22t1 IS NOT NULL AND lula26t1 IS NOT NULL
          GROUP BY 1""").df().set_index("k")
        s["queda"] = s.l22 - s.pl
        s["conv"] = s.queda.clip(lower=0) / 100 * s.v26
        raz = s.v26 / s.v22
        s["estavel"] = ((raz >= RAZAO_MIN) & (raz <= RAZAO_MAX) &
                        (s.v26 >= MIN_VOTOS) & (s.v22 >= MIN_VOTOS))
        s.loc[~s.estavel, "conv"] = 0.0
        a["lidera"] = a.pl > a.pf
        a.loc[~a.lidera, "conv"] = 0.0
        a.loc[~a.lidera, "net"] = 0.0

        g = base.groupby(chave)
        w = base["pop"].fillna(0)

        def wavg(col):
            m = base[col].notna() & (w > 0)
            num = (base[col].where(m) * w.where(m)).groupby(base[chave]).sum()
            den = w.where(m).groupby(base[chave]).sum()
            return (num / den.replace(0, np.nan))

        perf = pd.DataFrame({
            "pop": g["pop"].sum(),
            "renda_sm": wavg("renda_sm"),
            "idade_media": wavg("idade_media_15mais"),
            "pct_60mais": wavg("pct_60mais"),
            "pct_alfabetizados": wavg("pct_alfabetizados_15mais"),
            "ap_pct_catolica": wavg("pct_catolica"),
            "ap_pct_evangelica": wavg("pct_evangelica"),
            "ap_pct_sem_religiao": wavg("pct_sem_religiao"),
            "ap_pct_superior": wavg("pct_superior_25mais_2022"),
            "pop_urb": base["pop"].where(base.situacao == "urbana", 0)
                       .groupby(base[chave]).sum(),
            "lon": (base.lon * w).groupby(base[chave]).sum() /
                   w.groupby(base[chave]).sum().replace(0, np.nan),
            "lat": (base.lat * w).groupby(base[chave]).sum() /
                   w.groupby(base[chave]).sum().replace(0, np.nan),
            "x0": g["lon"].min(), "x1": g["lon"].max(),
            "y0": g["lat"].min(), "y1": g["lat"].max(),
            "mun": g["cd_mun"].first(),
        })
        # centroide de fallback: média simples quando pop = 0
        perf["lon"] = perf.lon.fillna(g["lon"].mean())
        perf["lat"] = perf.lat.fillna(g["lat"].mean())

        lista = []
        for k, row in perf.iterrows():
            if k is None:
                continue
            cd_mun = k if nivel == "mun" else row.mun
            if cd_mun not in muni.index:
                continue
            ll = [round(float(row.lon), 3), round(float(row.lat), 3)]
            bb = [round(float(row.x0), 3), round(float(row.y0), 3),
                  round(float(row.x1), 3), round(float(row.y1), 3)]
            if any(pd.isna(x) for x in ll + bb):
                if nivel == "mun" or cd_mun not in ll_mun:
                    print(f"  sem coordenada, pulado: {k}")
                    continue
                ll, bb = ll_mun[cd_mun], bb_mun[cd_mun]
            if nivel == "mun":
                ll_mun[k], bb_mun[k] = ll, bb
            nm_mun = muni.nm_mun[cd_mun]
            uf = muni.uf[cd_mun]
            if nivel == "mun":
                nome = nm_mun
            else:
                nd = nomes_d.get(k)
                nome = nd if nd and nd != nm_mun else nm_mun
                if nd and nd != nm_mun:
                    nome = f"{nd}, em {nm_mun}"
            vv = v.loc[k] if k in v.index else None
            aa = a.loc[k] if k in a.index else None
            ss = s.loc[k] if k in s.index else None
            pop = int(row["pop"]) if not pd.isna(row["pop"]) else 0
            item = {"cd": k, "nm": nome, "pop": pop, "ll": ll, "bb": bb}
            if nivel == "mun":
                item["uf"] = uf
            else:
                item["m"] = cd_mun
            item["p"] = {kk: vv_ for kk, vv_ in {
                "r": (None if pd.isna(row.renda_sm)
                      else round(float(row.renda_sm), 2)),
                "rp": pct_renda(row.renda_sm),
                "im": r1(row.idade_media),
                "p60": r1(row.pct_60mais),
                "alf": r1(row.pct_alfabetizados),
                "urb": (None if not pop else
                        int(round(100 * row.pop_urb / pop))),
                "cat": r1(row.ap_pct_catolica),
                "eva": r1(row.ap_pct_evangelica),
                "sr": r1(row.ap_pct_sem_religiao),
                "sup": r1(row.ap_pct_superior),
            }.items() if vv_ is not None}
            if vv is not None:
                item["v"] = {"conv": int(round(vv.conv)), "pl": r1(vv.pl),
                             "esp": r1(vv.esp), "l22": r1(vv.l22),
                             "validos": int(round(vv.validos))}
            if aa is not None:
                item["a"] = {"conv": int(round(aa.conv)),
                             "net": int(round(aa.net)), "pl": r1(aa.pl),
                             "pf": r1(aa.pf), "abr": r1(aa.abr),
                             "abe": r1(aa.abe), "ab22": r1(aa.ab22),
                             "aptos": int(round(aa.aptos)),
                             "lidera": bool(aa.lidera)}
            if ss is not None:
                item["s"] = {"conv": int(round(ss.conv)), "pl": r1(ss.pl),
                             "l22": r1(ss.l22), "validos": int(round(ss.v26)),
                             "estavel": bool(ss.estavel)}
            lista.append(item)
        total = {m: int(round(sum(x[m]["conv"] for x in lista if m in x)))
                 for m in ("v", "a", "s")}
        meta = {"nivel": nivel, "n": len(lista), "total": total,
                "gerado": pd.Timestamp.now().strftime("%Y-%m-%d")}
        out = DIR_SITE / f"areas_{nivel}.json"
        with open(out, "w") as f:
            json.dump({"meta": meta, "areas": lista}, f, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)
        # gates: cobertura e sanidade das moedas
        assert len(lista) >= (5500 if nivel == "mun" else 10500), meta
        for m in ("v", "a", "s"):
            assert all(x[m]["conv"] >= 0 for x in lista if m in x)
        top = sorted(lista, key=lambda x: -x.get("v", {}).get("conv", 0))[:3]
        print(f"{nivel}: {len(lista)} áreas, {out.stat().st_size/1e6:.1f} MB; "
              f"totais {total}; top voto: "
              f"{[(t['nm'], t['v']['conv']) for t in top]}")


if __name__ == "__main__":
    main()
