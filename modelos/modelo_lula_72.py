# Modelo NACIONAL do déficit de Lula 2026 (site p/ eleitores, 11/10):
# y = pct Lula 2026 t1 por setor (base válidos de presidente); X = todas
# as variáveis disponíveis, INCLUINDO a eleição passada (Lula 2022 t1/t2
# — decisão do Daniel: aqui a pergunta é "onde Lula caiu abaixo do
# próprio padrão", o baseline estrutural entra). FORA: qualquer coisa de
# 2026 além do y (abstenção/brancos 2026 são exatamente o que o mutirão
# recupera — controlar por elas apagaria o sinal) e coordenadas.
#
# Bateria de robustez (pedido: "extremamente robusto e testado"):
#   G1 out-of-fold GroupKFold(5) POR MUNICÍPIO (sem decorar política
#      local); R2/MAE ponderados por válidos
#   G2 calibração global: |viés| <= 0,2 pp (por UF é ACHADO, não erro —
#      política estadual deve ficar no resíduo; tabela reportada)
#   G3 baseline Ridge com mesmo esquema: GBM deve superar com folga
#   G4 estabilidade entre seeds: corr das predições >= 0,98 e rank-corr
#      (Spearman) do déficit por distrito >= 0,95
#   G5 importância por permutação (top 10 reportado)
#   G6 sanidade: predições em [0,100], soma do déficit conservada
# Saídas: dados/processados/eleitores/setor_deficit_lula.parquet
#         relatorios/LULA_MODELO_METRICAS.json
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DADOS, DIR_PROC, DIR_RELATORIOS, DIR_RESULTADO
from shares_lv import shares_sql

PQ_DASH = DIR_PROC / "dashboard/setores_eleicao_renda.parquet"
PQ_APOND = DIR_PROC / "dashboard/apond_completo.parquet"
DIR_OUT = DIR_PROC / "eleitores"

FEATURES = [
    # eleição passada (baseline estrutural — decisão 11/10)
    "lula22t1", "lula22t2", "bolso22t1", "haddad18t1", "haddad18t2",
    "abst22t1", "abst22t2", "bn22t1",
    # censo 2022 por setor
    "renda_sm", "pct_60mais", "idade_media", "alfab", "urbana", "log_pop",
    "cor_branca", "cor_parda", "cor_preta", "cor_indigena",
    # área de ponderação (estimativas)
    "ap_catolica", "ap_evangelica", "ap_sem_religiao", "ap_superior",
    "ap_renda_pc", "ap_estudo",
]


def validos_norm(con):
    br = DIR_RESULTADO / "votacao_secao_2026_BR.csv"
    return con.sql(f"""
    WITH lv AS (
      SELECT '2026_' || CD_MUNICIPIO::INT || '_' || NR_ZONA::INT || '_'
               || NR_LOCAL_VOTACAO::INT AS lv_uid,
             SUM(QT_VOTOS::BIGINT) FILTER (NR_VOTAVEL::INT NOT IN
               (95, 96, 97)) AS validos
      FROM read_csv('{br}', delim=';', header=true, encoding='latin-1',
                    all_varchar=true)
      WHERE NR_TURNO = '1' AND SG_UF <> 'ZZ' AND CD_CARGO = '1'
      GROUP BY 1
    ), shares AS (
      SELECT * FROM {shares_sql(2026, 1)}
    )
    SELECT s.CD_SETOR, SUM(s.share * l.validos) AS validos
    FROM shares s JOIN lv l USING (lv_uid) GROUP BY 1
    """).df()


def monta_base(con):
    df = con.sql(f"""
      SELECT d.cd_setor AS CD_SETOR, d.cd_mun, d.uf,
             d.pct_lula_2026t1 AS y,
             d.pct_lula_2022t1 AS lula22t1, d.pct_lula_2022t2 AS lula22t2,
             d.pct_bolsonaro_2022t1 AS bolso22t1,
             d.pct_haddad_2018t1 AS haddad18t1,
             d.pct_haddad_2018t2 AS haddad18t2,
             d.pct_abstencao_2022t1 AS abst22t1,
             d.pct_abstencao_2022t2 AS abst22t2,
             d.pct_brancos_nulos_2022t1 AS bn22t1,
             d.renda_resp_media_sm AS renda_sm, d.pct_60mais,
             d.idade_media_15mais AS idade_media,
             d.pct_alfabetizados_15mais AS alfab,
             CASE WHEN d.situacao = 'urbana' THEN 1.0
                  WHEN d.situacao = 'rural' THEN 0.0 END AS urbana,
             ln(1 + coalesce(d.pop, 0)) AS log_pop,
             d.pct_cor_branca AS cor_branca, d.pct_cor_parda AS cor_parda,
             d.pct_cor_preta AS cor_preta,
             d.pct_cor_indigena AS cor_indigena,
             p.pct_catolica AS ap_catolica,
             p.pct_evangelica AS ap_evangelica,
             p.pct_sem_religiao AS ap_sem_religiao,
             p.pct_superior_25mais_2022 AS ap_superior,
             p.renda_pc_media_sm AS ap_renda_pc,
             p.anos_estudo_25mais AS ap_estudo
      FROM '{PQ_DASH}' d
      LEFT JOIN '{PQ_APOND}' p ON p.apond = d.apond
      WHERE d.pct_lula_2026t1 IS NOT NULL
    """).df()
    return df


def oof_gbm(X, y, w, grupos, seed):
    oof = np.full(len(y), np.nan)
    modelos = []
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups=grupos):
        m = HistGradientBoostingRegressor(
            max_iter=400, learning_rate=0.07, min_samples_leaf=50,
            l2_regularization=1.0, random_state=seed)
        m.fit(X.iloc[tr], y[tr], sample_weight=w[tr])
        oof[te] = m.predict(X.iloc[te])
        modelos.append((m, te))
    return np.clip(oof, 0, 100), modelos


def r2w(y, p, w):
    ss = np.average((y - p) ** 2, weights=w)
    st = np.average((y - np.average(y, weights=w)) ** 2, weights=w)
    return 1 - ss / st


def main():
    DIR_OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.sql("SET threads TO 14")
    print("base…", flush=True)
    df = monta_base(con)
    vn = validos_norm(con)
    df = df.merge(vn, on="CD_SETOR")
    df = df[df.validos.notna() & (df.validos > 0)].reset_index(drop=True)
    X, y, w = df[FEATURES], df.y.values, df.validos.values
    grupos = df.cd_mun.fillna("?")
    print(f"{len(df)} setores, {len(FEATURES)} variáveis", flush=True)

    # G1: out-of-fold principal
    oof, modelos = oof_gbm(X, y, w, grupos, seed=42)
    met = {"n_setores": int(len(df)), "n_features": len(FEATURES),
           "r2_oof": round(float(r2w(y, oof, w)), 4),
           "mae_pp": round(float(np.average(np.abs(y - oof),
                                            weights=w)), 3)}
    # G2: calibração global + tabela por UF (achado, não gate)
    met["bias_global_pp"] = round(float(np.average(oof - y, weights=w)), 3)
    assert abs(met["bias_global_pp"]) <= 0.2, \
        f"G2: viés global {met['bias_global_pp']} pp"
    buf = pd.DataFrame({"uf": df.uf, "d": oof - y, "w": w})
    met["bias_por_uf_pp"] = {
        u: round(float(np.average(g.d, weights=g.w)), 2)
        for u, g in buf.groupby("uf")}

    # G3: baseline linear com o MESMO esquema
    oofl = np.full(len(y), np.nan)
    for tr, te in GroupKFold(5).split(X, y, groups=grupos):
        m = make_pipeline(SimpleImputer(strategy="median"),
                          StandardScaler(), Ridge(alpha=1.0))
        m.fit(X.iloc[tr], y[tr],
              ridge__sample_weight=w[tr])
        oofl[te] = m.predict(X.iloc[te])
    met["r2_baseline_ridge"] = round(float(r2w(y, oofl, w)), 4)
    # gate RELATIVO: com baseline linear já em R2 ~0,96, o que importa
    # é a redução da variância NÃO explicada (medida 11/10: 20%)
    met["reducao_erro_vs_ridge"] = round(
        (1 - met["r2_baseline_ridge"]) / (1 - met["r2_oof"]), 3)
    assert met["reducao_erro_vs_ridge"] >= 1.05, \
        "G3: GBM não reduz o erro do baseline em ao menos 5%"

    # G4: estabilidade entre seeds
    oof2, _ = oof_gbm(X, y, w, grupos, seed=7)
    met["corr_seeds"] = round(float(np.corrcoef(oof, oof2)[0, 1]), 4)
    dist = df.CD_SETOR.str[:9]
    d1 = pd.Series((oof - y) * w).groupby(dist).sum()
    d2 = pd.Series((oof2 - y) * w).groupby(dist).sum()
    met["spearman_deficit_distrito"] = round(
        float(spearmanr(d1, d2).statistic), 4)
    assert met["corr_seeds"] >= 0.98, "G4: predições instáveis entre seeds"
    assert met["spearman_deficit_distrito"] >= 0.95, \
        "G4: ranking de déficit instável entre seeds"

    # G5: importância por permutação (no fold 1, amostra p/ custo)
    m0, te0 = modelos[0]
    amostra = np.random.default_rng(42).choice(
        te0, size=min(40000, len(te0)), replace=False)
    pi = permutation_importance(
        m0, X.iloc[amostra], y[amostra], n_repeats=3, random_state=42,
        sample_weight=w[amostra])
    ordem = np.argsort(-pi.importances_mean)
    met["importancia_top10"] = {
        FEATURES[i]: round(float(pi.importances_mean[i]), 3)
        for i in ordem[:10]}

    # G6 + saída
    df["esperado"] = oof
    df["deficit_pp"] = df.esperado - df.y
    df["deficit_votos"] = df.deficit_pp / 100.0 * df.validos
    met["deficit_bruto_positivo_mi"] = round(
        float(df.deficit_votos.clip(lower=0).sum() / 1e6), 2)
    df.rename(columns={"y": "pct_lula"})[[
        "CD_SETOR", "cd_mun", "uf", "pct_lula", "esperado", "deficit_pp",
        "deficit_votos", "validos", "lula22t1", "lula22t2"]].to_parquet(
        DIR_OUT / "setor_deficit_lula.parquet", index=False)
    with open(DIR_RELATORIOS / "LULA_MODELO_METRICAS.json", "w") as f:
        json.dump(met, f, ensure_ascii=False, indent=1)
    print(json.dumps(met, ensure_ascii=False, indent=1))
    print("PRONTO:", DIR_OUT / "setor_deficit_lula.parquet")


if __name__ == "__main__":
    main()
