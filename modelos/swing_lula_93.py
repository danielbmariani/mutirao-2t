# Queda de Lula 2022 -> 2026 por setor (3ª visão do site eleitores, 13/10).
# Diferente das duas visões com modelo (déficit vs esperado, abstenção
# excedente), aqui a régua é a PRÓPRIA eleição passada: quanto a fatia de
# Lula no 1º turno de 2026 caiu em relação ao 1º turno de 2022 (mesmo
# turno, mesma base: válidos de presidente). Votos perdidos = queda em
# pontos x válidos de 2026 / 100 ("quantos votos Lula teria a mais se
# mantivesse a fatia de 2022 no eleitorado de hoje") — mesma base dos
# déficits da visão voto, para as duas serem comparáveis.
#
# Comparabilidade entre anos: a passagem urna -> setor muda quando o TSE
# reatribui locais de votação; por isso o setor só recebe queda quando
# delta_estavel (>= 100 válidos nos dois anos e razão 2/3..1,5; critério
# do dashboard_40). Nos blocos (subdistritos) e níveis acima a reatribuição
# se cancela e a queda sai da soma de votos (regioes_swing_94, tiles).
#
# Gates: G1 soma dos válidos = soma do dashboard (conservativa);
#        G2 setores estáveis >= 90% dos válidos de 2026;
#        G3 queda nacional nos estáveis = oficial +- 0,3 pp
#           (TSE: Lula 48,43% em 2022 t1 -> 45,15% em 2026 t1);
#        G4 nenhuma queda fora de [-100, 100]; perda total conservada.
# Saídas: dados/processados/eleitores/setor_swing_lula.parquet
#         relatorios/SWING_LULA_METRICAS.json
import json
import sys
from pathlib import Path

import duckdb
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DIR_PROC, DIR_RELATORIOS

PQ_DASH = DIR_PROC / "dashboard/setores_eleicao_renda.parquet"
PQ_OUT = DIR_PROC / "eleitores/setor_swing_lula.parquet"
MET = DIR_RELATORIOS / "SWING_LULA_METRICAS.json"


def main():
    PQ_OUT.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.sql("SET threads TO 8")
    df = con.sql(f"""
      SELECT cd_setor AS CD_SETOR, cd_mun, uf,
             pct_lula_2022t1 AS lula22t1, pct_lula_2026t1 AS lula26t1,
             votos_validos_2022t1 AS validos22,
             votos_validos_2026t1 AS validos,
             coalesce(delta_estavel, FALSE) AS estavel,
             CASE WHEN delta_estavel
                  THEN pct_lula_2022t1 - pct_lula_2026t1 END AS queda_pp,
             CASE WHEN delta_estavel
                  THEN (pct_lula_2022t1 - pct_lula_2026t1) / 100.0
                       * votos_validos_2026t1 END AS perda_votos
      FROM '{PQ_DASH}'
      WHERE votos_validos_2026t1 > 0
    """).df()
    tot = con.sql(f"""
      SELECT sum(votos_validos_2026t1) v26, sum(votos_validos_2022t1) v22,
             sum(pct_lula_2022t1 * votos_validos_2022t1) /
               sum(votos_validos_2022t1) l22,
             sum(pct_lula_2026t1 * votos_validos_2026t1) /
               sum(votos_validos_2026t1) l26
      FROM '{PQ_DASH}'
    """).df().iloc[0]
    est = df[df.estavel]
    m = {
        "setores": int(len(df)), "setores_estaveis": int(len(est)),
        "share_validos_estaveis": round(est.validos.sum() /
                                        df.validos.sum(), 4),
        "lula_2022t1_pct": round(float(tot.l22), 2),
        "lula_2026t1_pct": round(float(tot.l26), 2),
        "queda_nacional_pp": round(float(tot.l22 - tot.l26), 2),
        "queda_estaveis_pp": round(float(np.average(
            est.queda_pp, weights=est.validos)), 2),
        "perda_bruta_votos": int(round(est.perda_votos.clip(lower=0)
                                       .sum())),
        "perda_liquida_votos": int(round(est.perda_votos.sum())),
        "validos_2026": int(round(df.validos.sum())),
    }
    # G1: a base é a mesma do déficit (conservativa: soma ao oficial)
    assert abs(df.validos.sum() - tot.v26) < 1, "G1: válidos divergem"
    # G2
    assert m["share_validos_estaveis"] >= 0.90, f"G2: {m}"
    # G3: oficial TSE (presidente, 1t): 48,43 -> 45,15 (-3,28 pp)
    assert abs(m["queda_estaveis_pp"] - m["queda_nacional_pp"]) <= 0.3, \
        f"G3: estáveis {m['queda_estaveis_pp']} x nacional " \
        f"{m['queda_nacional_pp']}"
    # G4
    assert est.queda_pp.abs().max() <= 100
    assert abs(est.perda_votos.sum() - (est.queda_pp / 100 *
                                        est.validos).sum()) < 1
    df.to_parquet(PQ_OUT, index=False)
    MET.write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(m, indent=1, ensure_ascii=False))
    print(f"OK -> {PQ_OUT}")


if __name__ == "__main__":
    main()
