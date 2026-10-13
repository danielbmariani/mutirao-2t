# Agrega os resultados por setor com a distribuição CONSERVATIVA de
# distribuicao_85.py (cada voto da urna vai para os setores uma única vez).
#
# Saídas em dados/processados/resultados_por_setor_cons/ com o MESMO esquema
# de agregacao_05.py (drop-in para os consumidores), SÓ cargo PRESIDENTE —
# único lido desses arquivos por todos os scripts (grep 12/10); com todos os
# cargos o arquivo ia a 14 GB/eleição (deputado espalha por muitos setores).
# Outros cargos: Σ share·votos a partir de shares_malha2022_*.parquet.
#   malha2022_{ano}_t{turno}_candidato.parquet / _partido.parquet
#     votos            = Σ_l share[s,l] · votos_l   (estimativa, DOUBLE)
#     votos_ponderados = votos  (mesma coluna; mantém pct_votos_ponderados_*
#                        funcionando nos scripts que leem o nome antigo)
#     pct_* com as mesmas fórmulas de agregacao_05
#   malha2022_{ano}_t{turno}_participacao.parquet (presidente)
#     CD_SETOR, aptos, comparecimento, validos, brancos_nulos (estimativas),
#     pct_abstencao, pct_brancos_nulos
# A soma dos setores reproduz o total das urnas distribuídas EXATAMENTE
# (gate abaixo); a diferença para o total do Brasil (fora o exterior) são só
# LVs de municípios sem nenhum setor povoado na malha (reportados).
#
# Uso: python agregacao_cons_86.py          (todas as ELEICOES)
#      python agregacao_cons_86.py 2026 1
import sys
import time
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agregacao_05 import garante_consulta_cand
from config import DADOS, DIR_RESULTADO, ELEICOES
from distribuicao_85 import DIR_OUT as DIR_SHARES
from distribuicao_85 import eleitorado_paths, uid_sql

DIR_CONS = DADOS / "processados/resultados_por_setor_cons"


def main(ano: int, turno: int):
    t0 = time.time()
    DIR_CONS.mkdir(parents=True, exist_ok=True)
    sh = DIR_SHARES / f"shares_malha2022_{ano}_t{turno}.parquet"
    assert sh.exists(), f"rode distribuicao_85.py {ano} {turno} antes"
    base = DIR_CONS / f"malha2022_{ano}_t{turno}"
    out_cand = Path(f"{base}_candidato.parquet")
    out_part = Path(f"{base}_partido.parquet")
    out_parti = Path(f"{base}_participacao.parquet")
    cand_csv = garante_consulta_cand(ano)
    vs = [str(p) for p in DIR_RESULTADO.glob(f"votacao_secao_{ano}_*.csv")]
    ele = eleitorado_paths(ano)

    con = duckdb.connect()
    con.sql("SET threads TO 14; SET preserve_insertion_order=false;")
    con.sql(f"""
    CREATE TEMP TABLE votos_lv AS
    SELECT {uid_sql(ano)} AS lv_uid, upper(DS_CARGO) AS cargo,
           CAST(NR_VOTAVEL AS INT) AS nr_votavel,
           SUM(CAST(QT_VOTOS AS BIGINT)) AS qt
    FROM read_csv({vs}, delim=';', header=true, encoding='latin-1',
                  all_varchar=true, union_by_name=true)
    WHERE NR_TURNO = '{turno}' AND SG_UF <> 'ZZ'
          AND upper(DS_CARGO) = 'PRESIDENTE'
    GROUP BY 1, 2, 3""")
    con.sql(f"CREATE TEMP TABLE sh AS SELECT CD_SETOR, lv_uid, share "
            f"FROM '{sh}'")
    con.sql(f"""
    CREATE TEMP TABLE partidos AS
    SELECT nr_partido, arg_max(SG_PARTIDO, n) AS partido
    FROM (
      SELECT substr(CAST(CAST(NR_CANDIDATO AS BIGINT) AS VARCHAR), 1, 2)
               AS nr_partido, SG_PARTIDO, count(*) AS n
      FROM read_csv('{cand_csv}', delim=';', header=true, encoding='latin-1',
                    all_varchar=true)
      GROUP BY 1, 2
    ) GROUP BY 1""")

    # GATE 1: por LV, Σ share = 1
    g1 = con.sql("SELECT max(abs(s - 1)) FROM (SELECT lv_uid, sum(share) s "
                 "FROM sh GROUP BY 1)").fetchone()[0]
    assert g1 < 1e-9, f"G1 Σ share por LV desvia {g1}"

    con.sql("""
    CREATE TEMP TABLE por_setor AS
    SELECT s.CD_SETOR, v.cargo, v.nr_votavel, p.partido,
           SUM(s.share * v.qt) AS votos
    FROM votos_lv v
    JOIN sh s USING (lv_uid)
    LEFT JOIN partidos p
      ON p.nr_partido = substr(CAST(v.nr_votavel AS VARCHAR), 1, 2)
    GROUP BY 1, 2, 3, 4""")

    # GATE 2: conservação por cargo × candidato — soma dos setores = soma
    # das urnas distribuídas (exato a 1e-6 relativo)
    g2 = con.sql("""
      WITH a AS (SELECT cargo, nr_votavel, SUM(votos) s FROM por_setor
                 GROUP BY 1, 2),
           b AS (SELECT cargo, nr_votavel, SUM(qt) s FROM votos_lv
                 WHERE lv_uid IN (SELECT DISTINCT lv_uid FROM sh)
                 GROUP BY 1, 2)
      SELECT max(abs(a.s - b.s) / greatest(b.s, 1)), count(*)
      FROM a JOIN b USING (cargo, nr_votavel)""").fetchone()
    assert g2[0] < 1e-6, f"G2 conservação desvia {g2[0]}"
    fora = con.sql("""
      SELECT count(DISTINCT lv_uid), coalesce(SUM(qt), 0) FROM votos_lv
      WHERE cargo = 'PRESIDENTE'
        AND lv_uid NOT IN (SELECT DISTINCT lv_uid FROM sh)""").fetchone()
    tot = con.sql("SELECT SUM(qt) FROM votos_lv WHERE cargo = 'PRESIDENTE'"
                  ).fetchone()[0]
    print(f"{ano} t{turno}: G1 ok, G2 ok ({g2[1]} cargo×nr, desvio máx "
          f"{g2[0]:.1e}) | LVs fora da distribuição (voto em trânsito ou município sem setor povoado): "
          f"{fora[0]} = {fora[1]:,} de {tot:,} votos de presidente "
          f"({100 * fora[1] / tot:.4f}%)", flush=True)

    con.sql(f"""
    COPY (
      SELECT *, votos AS votos_ponderados,
        100.0 * votos / SUM(votos) OVER w AS pct_voto,
        100.0 * votos / SUM(votos) OVER w AS pct_votos_ponderados,
        100.0 * votos / nullif(SUM(CASE WHEN nr_votavel < 95 THEN votos END)
          OVER w, 0) AS pct_votos_validos,
        100.0 * votos / nullif(SUM(CASE WHEN nr_votavel < 95 THEN votos END)
          OVER w, 0) AS pct_votos_ponderados_validos
      FROM por_setor
      WINDOW w AS (PARTITION BY cargo, CD_SETOR)
    ) TO '{out_cand}.tmp' (FORMAT PARQUET)""")
    Path(f"{out_cand}.tmp").replace(out_cand)
    con.sql(f"""
    COPY (
      WITH part AS (
        SELECT CD_SETOR, cargo, partido, SUM(votos) AS votos
        FROM por_setor GROUP BY 1, 2, 3)
      SELECT *, votos AS votos_ponderados,
        100.0 * votos / SUM(votos) OVER w AS pct_voto,
        100.0 * votos / SUM(votos) OVER w AS pct_votos_ponderados,
        100.0 * votos / nullif(SUM(CASE WHEN partido IS NOT NULL THEN votos
          END) OVER w, 0) AS pct_votos_validos,
        100.0 * votos / nullif(SUM(CASE WHEN partido IS NOT NULL THEN votos
          END) OVER w, 0) AS pct_votos_ponderados_validos
      FROM part
      WINDOW w AS (PARTITION BY cargo, CD_SETOR)
    ) TO '{out_part}.tmp' (FORMAT PARQUET)""")
    Path(f"{out_part}.tmp").replace(out_part)

    # participação (presidente): aptos do cadastro de locais por LV
    con.sql(f"""
    CREATE TEMP TABLE aptos_lv AS
    SELECT {uid_sql(ano)} AS lv_uid,
           SUM(CAST(QT_ELEITOR_SECAO AS BIGINT)) AS aptos
    FROM read_csv({ele}, delim=';', header=true, encoding='latin-1',
                  all_varchar=true, union_by_name=true)
    WHERE NR_TURNO = '{turno}' AND SG_UF <> 'ZZ'
    GROUP BY 1""")
    con.sql(f"""
    COPY (
      WITH lv AS (
        SELECT v.lv_uid,
               SUM(v.qt) AS comp,
               SUM(v.qt) FILTER (WHERE v.nr_votavel < 95) AS validos,
               SUM(v.qt) FILTER (WHERE v.nr_votavel >= 95) AS bn
        FROM votos_lv v WHERE v.cargo = 'PRESIDENTE' GROUP BY 1),
      s AS (
        SELECT s.CD_SETOR,
               SUM(s.share * coalesce(a.aptos, 0)) AS aptos,
               SUM(s.share * l.comp) AS comparecimento,
               SUM(s.share * coalesce(l.validos, 0)) AS validos,
               SUM(s.share * coalesce(l.bn, 0)) AS brancos_nulos,
               -- abstenção só com LVs que têm aptos no cadastro
               SUM(s.share * l.comp) FILTER (WHERE a.aptos > 0) AS comp_c_aptos
        FROM sh s JOIN lv l USING (lv_uid)
        LEFT JOIN aptos_lv a USING (lv_uid)
        GROUP BY 1)
      SELECT CD_SETOR, aptos, comparecimento, validos, brancos_nulos,
             100.0 * (1 - comp_c_aptos / nullif(aptos, 0)) AS pct_abstencao,
             100.0 * brancos_nulos / nullif(comparecimento, 0)
               AS pct_brancos_nulos
      FROM s
    ) TO '{out_parti}.tmp' (FORMAT PARQUET)""")
    Path(f"{out_parti}.tmp").replace(out_parti)
    n = con.sql(f"SELECT count(*), count(DISTINCT CD_SETOR) "
                f"FROM '{out_cand}'").fetchone()
    print(f"  {out_cand.name}: {n[0]:,} linhas, {n[1]:,} setores | "
          f"{time.time() - t0:.0f}s", flush=True)


def bn_ab_setor():
    """bn_ab_setor.parquet no MESMO formato de bn_ab_setor_45 (CD_SETOR +
    bn{s}/ab{s} em p.p.), a partir das participações conservativas."""
    import pandas as pd
    from config import sufixo
    base = None
    for ano, turno in ELEICOES:
        s = sufixo(ano, turno)
        p = pd.read_parquet(DIR_CONS / f"malha2022_{ano}_t{turno}"
                            "_participacao.parquet")
        d = p[["CD_SETOR", "pct_brancos_nulos", "pct_abstencao"]].rename(
            columns={"pct_brancos_nulos": f"bn{s}",
                     "pct_abstencao": f"ab{s}"})
        base = d if base is None else base.merge(d, on="CD_SETOR",
                                                 how="outer")
    assert base.CD_SETOR.is_unique
    tmp = DIR_CONS / "bn_ab_setor.tmp.parquet"
    base.sort_values("CD_SETOR").to_parquet(tmp, index=False)
    tmp.replace(DIR_CONS / "bn_ab_setor.parquet")
    print(f"bn_ab_setor.parquet: {len(base)} setores", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["bnab"]:
        bn_ab_setor()
        sys.exit(0)
    els = [(int(a[0]), int(a[1]))] if a else ELEICOES
    for ano, turno in els:
        main(ano, turno)
    if not a:
        bn_ab_setor()
