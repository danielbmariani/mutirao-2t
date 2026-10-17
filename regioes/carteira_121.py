# Carteira do mutirão (16/10/2026, pedido do grupo: "precisamos de V votos;
# cada lugar tem indicadores com força, potencial e incerteza; achar os N
# lugares mais promissores p/ chegar a V"). Catálogo por UNIDADE (município
# e distrito) com as DUAS medidas do mutirão na mesma linha, cada uma em
# DUAS réguas que viram os extremos da faixa de potencial:
#   voto      vm  = déficit vs modelo (teto aritmético; areas_95 v.conv)
#             v22 = queda desde 1T 2022 × válidos 2026, só setores
#                   estáveis (areas_95 s.conv)
#   abstenção am  = excesso vs modelo × aptos × fatia Lula, só onde Lula
#                   lidera, teto (areas_95 a.conv)
#             a22 = (abst 2026 − abst 2T 2022) × aptos × fatia Lula 2026,
#                   só onde Lula lidera (régua da tabela /municipios)
#   potencial conservador = vm + am ; potencial 2022 = v22 + a22
#   (voto e abstenção não se sobrepõem: quem faltou não está nos válidos;
#    as duas réguas NÃO se somam — são o piso e o teto da faixa)
# Confiança (cf): 2 = alta (as duas réguas apontam na mesma medida, cobertura
# estável >= 90% dos válidos e >= 5 mil aptos); 0 = baixa (só uma régua
# aponta, ou < 5 mil aptos, ou cobertura < 70%); 1 = média (resto).
# Gates: totais municipais = areas_mun.json (v, a, s) ± 0,1%; a22 = soma
# da tabela /municipios só onde lidera.
# Saídas: embed_eleitores/dados/carteira_mun.json, carteira_dist.json
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
PQ_DIST = DIR_PROC / "resultados_por_distrito/distritos_eleicao.parquet"
DIR_SITE = DIR_SITES / "embed_eleitores/dados"
MIN_APTOS, COB_ALTA, COB_BAIXA = 5_000, 0.90, 0.70


def r1(x):
    return None if x is None or pd.isna(x) else round(float(x), 1)


def main():
    con = duckdb.connect()
    con.sql("SET threads TO 8")
    nomes_d = con.sql(f"SELECT CD_DIST, any_value(NM_DIST) AS NM_DIST "
                      f"FROM '{PQ_DIST}' GROUP BY 1").df().set_index("CD_DIST").NM_DIST
    muni = con.sql(f"""SELECT cd_mun, any_value(nm_mun) AS nm_mun, any_value(uf) AS uf
      FROM '{PQ_DASH}' WHERE cd_mun IS NOT NULL GROUP BY 1""").df().set_index("cd_mun")
    areas = {n: json.load(open(DIR_SITE / f"areas_{n}.json")) for n in ("mun", "dist")}
    for nivel, k_sql in (("mun", "cd_mun"), ("dist", "substr(CD_SETOR, 1, 9)")):
        v = con.sql(f"""
          SELECT {k_sql} AS k,
                 greatest(0, least(greatest(0, sum(deficit_votos)),
                       sum((100 - pct_lula) * validos) / 100.0)) AS vm,
                 sum(pct_lula * validos) / sum(validos) AS pl,
                 sum(esperado * validos) / sum(validos) AS esp,
                 sum(validos) AS validos
          FROM '{PQ_DEF}' WHERE validos > 0 GROUP BY 1""").df().set_index("k")
        k_a = "s.cd_mun" if nivel == "mun" else "substr(s.CD_SETOR, 1, 9)"
        a = con.sql(f"""
          SELECT {k_a} AS k,
                 greatest(0, least(greatest(0, sum(vperd)),
                       sum(abstencao / 100.0 * aptos * pl26 / 100.0))) AS am,
                 sum(pl26 * aptos) / sum(aptos) AS pla,
                 sum(pf26 * aptos) / sum(aptos) AS pf,
                 sum(abstencao * aptos) / sum(aptos) AS abr,
                 sum(esperada * aptos) / sum(aptos) AS abe,
                 sum(d.pct_abstencao_2022t2 * aptos) FILTER (d.pct_abstencao_2022t2 IS NOT NULL)
                   / sum(aptos) FILTER (d.pct_abstencao_2022t2 IS NOT NULL) AS ab22,
                 sum(aptos) AS aptos
          FROM '{PQ_ABS}' s LEFT JOIN '{PQ_DASH}' d ON d.cd_setor = s.CD_SETOR
          WHERE aptos > 0 GROUP BY 1""").df().set_index("k")
        s = con.sql(f"""
          SELECT {k_sql} AS k,
                 sum(lula22t1 * validos22) / sum(validos22) AS l22,
                 sum(lula26t1 * validos) / sum(validos) AS pl,
                 sum(validos22) AS v22, sum(validos) AS v26,
                 sum(validos) FILTER (estavel) AS v26_est
          FROM '{PQ_SW}' WHERE validos > 0 AND validos22 > 0
            AND lula22t1 IS NOT NULL AND lula26t1 IS NOT NULL GROUP BY 1""").df().set_index("k")
        s["queda"] = s.l22 - s.pl
        raz = s.v26 / s.v22
        s["estavel"] = (raz >= 2 / 3) & (raz <= 1.5) & (s.v26 >= 100) & (s.v22 >= 100)
        s["v22c"] = np.where(s.estavel, s.queda.clip(lower=0) / 100 * s.v26, 0.0)
        a["lid"] = a.pla > a.pf
        a["ab22pp"] = a.abr - a.ab22
        a["a22"] = np.where(a.lid, (a.ab22pp.clip(lower=0) / 100 * a.aptos * a.pla / 100), 0.0)
        a.loc[~a.lid, "am"] = 0.0
        if nivel == "mun":
            # município: a régua de 2022 da abstenção é a OFICIAL (TSE por
            # município, como na tabela /municipios); a dos setores só
            # serve ao distrito, onde não há oficial. Diferença: aptos dos
            # setores do modelo ≠ oficial em municípios pequenos.
            rk = con.sql(f"""SELECT cd_mun::VARCHAR AS k, abst_2022_votos_lula, abst_2022_pp,
                             abst_2022t2_pct FROM '{E / "ranking_municipios.parquet"}'""").df().set_index("k")
            rk["cd7"] = rk.index.str.zfill(7)
            rk = rk.set_index("cd7")
            comum = a.index.intersection(rk.index)
            corr = np.corrcoef(a.loc[comum, "a22"], rk.loc[comum, "abst_2022_votos_lula"].clip(lower=0))[0, 1]
            print(f"mun: abst 2022 setores × oficial: corr {corr:.3f} em {len(comum)} municípios")
            a.loc[comum, "a22"] = np.where(a.loc[comum, "lid"],
                                           rk.loc[comum, "abst_2022_votos_lula"].clip(lower=0), 0.0)
            a.loc[comum, "ab22"] = rk.loc[comum, "abst_2022t2_pct"]
        pos = {x["cd"]: x for x in areas[nivel]["areas"]}
        lista = []
        for k in sorted(set(v.index) | set(a.index) | set(s.index)):
            if k is None or k not in pos:
                continue
            ar = pos[k]
            vv = v.loc[k] if k in v.index else None
            aa = a.loc[k] if k in a.index else None
            ss = s.loc[k] if k in s.index else None
            vm = float(vv.vm) if vv is not None else 0.0
            am = float(aa.am) if aa is not None else 0.0
            v22 = float(ss.v22c) if ss is not None else 0.0
            a22 = float(aa.a22) if aa is not None else 0.0
            aptos = float(aa.aptos) if aa is not None else 0.0
            cob = (float(0 if pd.isna(ss.v26_est) else ss.v26_est) / float(ss.v26)) if ss is not None and ss.v26 else 0.0
            conc_v = vm > 0 and v22 > 0
            conc_a = am > 0 and a22 > 0
            alguma = (vm + am + v22 + a22) > 0
            if not alguma:
                cf = 0
            elif (conc_v or conc_a) and cob >= COB_ALTA and aptos >= MIN_APTOS:
                cf = 2
            elif (not conc_v and not conc_a) or aptos < MIN_APTOS or cob < COB_BAIXA:
                cf = 0
            else:
                cf = 1
            item = {"cd": k, "nm": ar["nm"], "pop": ar["pop"], "ll": ar["ll"],
                    "ap": int(round(aptos)),
                    "va": int(round(float(vv.validos))) if vv is not None else 0,
                    "vm": int(round(vm)), "v22": int(round(v22)),
                    "am": int(round(am)), "a22": int(round(a22)),
                    "pl": r1(vv.pl) if vv is not None else None,
                    "esp": r1(vv.esp) if vv is not None else None,
                    "l22": r1(ss.l22) if ss is not None else None,
                    "pf": r1(aa.pf) if aa is not None else None,
                    "abr": r1(aa.abr) if aa is not None else None,
                    "abe": r1(aa.abe) if aa is not None else None,
                    "ab22": r1(aa.ab22) if aa is not None else None,
                    "lid": bool(aa.lid) if aa is not None else False,
                    "cob": int(round(100 * cob)), "cf": cf}
            if nivel == "mun":
                item["uf"] = ar["uf"]
            else:
                item["m"] = ar["m"]
            lista.append(item)
        tot = {c: int(round(sum(x[c] for x in lista))) for c in ("vm", "v22", "am", "a22")}
        meta = {"nivel": nivel, "n": len(lista), "total": tot,
                "gerado": pd.Timestamp.now().strftime("%Y-%m-%d"),
                "regras": {"min_aptos": MIN_APTOS, "cob_alta": COB_ALTA, "cob_baixa": COB_BAIXA}}
        out = DIR_SITE / f"carteira_{nivel}.json"
        with open(out, "w") as f:
            json.dump({"meta": meta, "areas": lista}, f, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)
        # gates
        ta = areas[nivel]["meta"]["total"]
        for ours, theirs in (("vm", "v"), ("am", "a"), ("v22", "s")):
            assert abs(tot[ours] - ta[theirs]) <= 0.001 * ta[theirs] + 50, (nivel, ours, tot[ours], ta[theirs])
        if nivel == "mun":
            rk = con.sql(f"""SELECT sum(abst_2022_votos_lula) FILTER (abst_2022_votos_lula > 0 AND lula_lidera)
                             FROM '{E / "ranking_municipios.parquet"}'""").fetchone()[0]
            assert abs(tot["a22"] - rk) <= 0.02 * rk, (tot["a22"], rk)
        cfs = pd.Series([x["cf"] for x in lista]).value_counts().to_dict()
        print(f"{nivel}: {len(lista)} unidades, {out.stat().st_size/1e6:.2f} MB; totais {tot}; "
              f"confiança {cfs}; top conservador: "
              f"{[(x['nm'], x['vm']+x['am']) for x in sorted(lista, key=lambda x: -(x['vm']+x['am']))[:3]]}")


if __name__ == "__main__":
    main()
