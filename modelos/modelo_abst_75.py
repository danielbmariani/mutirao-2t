# Modelo NACIONAL de abstenção excedente (2ª visão do site eleitores,
# 11/10): y = abstenção 2026 t1 por setor; esperada a partir do
# HISTÓRICO de abstenção (2018/2022, brancos+nulos 2022) + demografia
# (idade/60+ e alfabetização carregam as isenções do voto obrigatório;
# renda, cor, urbanização, porte, AP). SEM variáveis políticas: a
# desmobilização política de 2026 é exatamente o sinal que o mutirão
# procura — condicionar nela apagaria o alvo.
#
#   excesso_pp = real − esperada  (positivo = abstenção acima do padrão)
#   votos de Lula perdidos (bruto) = excesso × aptos × pctLula/100
#   ganho líquido = excesso × aptos × (pctLula − pctFlavio)/100
#     (a ficha mostra os dois; regiões só aceitam blocos onde Lula
#      lidera — reverter abstenção onde ele perde devolve mais voto ao
#      adversário)
#
# Mesma bateria G1-G6 do modelo_lula_72 (oof por município, viés global,
# baseline Ridge relativo, estabilidade de seeds, permutação, sanidade).
# Saídas: dados/processados/eleitores/setor_abst_lula.parquet
#         relatorios/ABST_MODELO_METRICAS.json
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
from config import DADOS, DIR_PROC, DIR_RELATORIOS
from shares_lv import shares_sql

PQ_DASH = DIR_PROC / "dashboard/setores_eleicao_renda.parquet"
PQ_APOND = DIR_PROC / "dashboard/apond_completo.parquet"
DIR_OUT = DIR_PROC / "eleitores"
# biometria é INSUMO (abstencao_cadastro_63), não depende do método
PQ_BIOM = DADOS / "processados/eleitores/biometria_municipio.parquet"
DETALHE = DADOS / "brutos/tse/detalhe/detalhe_votacao_secao_2026_BR.csv"

FEATURES = [
    # recadastramento biométrico (pedido Daniel 11/10): cadastro limpo
    # derruba a abstenção estrutural; sem isso o "excesso" confundiria
    # desmobilização com eleitor fantasma de cadastro antigo
    "biometria26", "delta_biometria",
    "abst22t1", "abst22t2", "abst18t1", "abst18t2", "bn22t1",
    "renda_sm", "pct_60mais", "idade_media", "alfab", "urbana",
    "log_pop", "cor_branca", "cor_parda", "cor_preta", "cor_indigena",
    "ap_superior", "ap_estudo", "ap_renda_pc",
]


def aptos_norm(con):
    """Aptos de presidente por setor via shares de LV normalizados."""
    return con.sql(f"""
    WITH lv AS (
      SELECT '2026_' || CD_MUNICIPIO::INT || '_' || NR_ZONA::INT || '_'
               || NR_LOCAL_VOTACAO::INT AS lv_uid,
             SUM(QT_APTOS::BIGINT) AS aptos
      FROM read_csv('{DETALHE}', delim=';', header=true,
                    encoding='latin-1', all_varchar=true)
      WHERE NR_TURNO = '1' AND SG_UF <> 'ZZ' AND CD_CARGO = '1'
      GROUP BY 1
    ), shares AS (
      SELECT * FROM {shares_sql(2026, 1)}
    )
    SELECT s.CD_SETOR, SUM(s.share * l.aptos) AS aptos
    FROM shares s JOIN lv l USING (lv_uid) GROUP BY 1
    """).df()


def r2w(y, p, w):
    ss = np.average((y - p) ** 2, weights=w)
    st = np.average((y - np.average(y, weights=w)) ** 2, weights=w)
    return 1 - ss / st


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


def main():
    DIR_OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.sql("SET threads TO 14")
    print("base…", flush=True)
    df = con.sql(f"""
      SELECT d.cd_setor AS CD_SETOR, d.cd_mun, d.uf,
             d.pct_abstencao_2026t1 AS y,
             d.pct_lula_2026t1 AS pl26, d.pct_flavio_2026t1 AS pf26,
             d.pct_abstencao_2022t1 AS abst22t1,
             d.pct_abstencao_2022t2 AS abst22t2,
             d.pct_abstencao_2018t1 AS abst18t1,
             d.pct_abstencao_2018t2 AS abst18t2,
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
             p.pct_superior_25mais_2022 AS ap_superior,
             p.anos_estudo_25mais AS ap_estudo,
             p.renda_pc_media_sm AS ap_renda_pc
      FROM '{PQ_DASH}' d
      LEFT JOIN '{PQ_APOND}' p ON p.apond = d.apond
      WHERE d.pct_abstencao_2026t1 IS NOT NULL
    """).df()
    ap = aptos_norm(con)
    df = df.merge(ap, on="CD_SETOR")
    biom = pd.read_parquet(PQ_BIOM)
    df = df.merge(biom[["cd_mun", "pct_biometria26",
                        "delta_biometria"]].rename(
        columns={"pct_biometria26": "biometria26"}),
        on="cd_mun", how="left")
    df = df[df.aptos.notna() & (df.aptos > 0)].reset_index(drop=True)
    X, y, w = df[FEATURES], df.y.values, df.aptos.values
    grupos = df.cd_mun.fillna("?")
    print(f"{len(df)} setores, {len(FEATURES)} variáveis", flush=True)

    oof, modelos = oof_gbm(X, y, w, grupos, seed=42)
    met = {"n_setores": int(len(df)), "n_features": len(FEATURES),
           "r2_oof": round(float(r2w(y, oof, w)), 4),
           "mae_pp": round(float(np.average(np.abs(y - oof),
                                            weights=w)), 3)}
    met["bias_global_pp"] = round(float(np.average(oof - y, weights=w)), 3)
    assert abs(met["bias_global_pp"]) <= 0.2, \
        f"G2: viés global {met['bias_global_pp']} pp"
    buf = pd.DataFrame({"uf": df.uf, "d": oof - y, "w": w})
    met["bias_por_uf_pp"] = {
        u: round(float(np.average(g.d, weights=g.w)), 2)
        for u, g in buf.groupby("uf")}

    oofl = np.full(len(y), np.nan)
    for tr, te in GroupKFold(5).split(X, y, groups=grupos):
        m = make_pipeline(SimpleImputer(strategy="median"),
                          StandardScaler(), Ridge(alpha=1.0))
        m.fit(X.iloc[tr], y[tr], ridge__sample_weight=w[tr])
        oofl[te] = m.predict(X.iloc[te])
    met["r2_baseline_ridge"] = round(float(r2w(y, oofl, w)), 4)
    met["reducao_erro_vs_ridge"] = round(
        (1 - met["r2_baseline_ridge"]) / (1 - met["r2_oof"]), 3)
    assert met["reducao_erro_vs_ridge"] >= 1.05, \
        "G3: GBM não reduz o erro do baseline em ao menos 5%"

    # abstenção tem muito componente idiossincrático: a predição final
    # é o ENSEMBLE de QUATRO seeds (as variáveis municipais de
    # biometria, em degrau, aumentam a variância de seed único) e o
    # gate duro é a concordância do ranking agregado por distrito entre
    # as duas METADES do ensemble — o nível em que o site decide
    oofs = [oof]
    for sd in (7, 2026, 13):
        o, _ = oof_gbm(X, y, w, grupos, seed=sd)
        oofs.append(o)
    dist = df.CD_SETOR.str[:9]
    h1 = (oofs[0] + oofs[1]) / 2
    h2 = (oofs[2] + oofs[3]) / 2
    met["corr_entre_metades"] = round(float(np.corrcoef(h1, h2)[0, 1]), 4)
    e1 = pd.Series((y - h1) * w).groupby(dist).sum()
    e2 = pd.Series((y - h2) * w).groupby(dist).sum()
    met["spearman_excesso_distrito"] = round(
        float(spearmanr(e1, e2).statistic), 4)
    assert met["corr_entre_metades"] >= 0.95, "G4: metades divergem"
    assert met["spearman_excesso_distrito"] >= 0.95, \
        "G4: ranking de excesso instável entre metades do ensemble"
    oof = np.mean(oofs, axis=0)
    met["r2_oof_ensemble"] = round(float(r2w(y, oof, w)), 4)
    # R² no nível de BLOCO (distrito): onde o ruído de setor se cancela
    yd = pd.Series(y * w).groupby(dist).sum() / \
        pd.Series(w).groupby(dist).sum()
    pdm = pd.Series(oof * w).groupby(dist).sum() / \
        pd.Series(w).groupby(dist).sum()
    wd = pd.Series(w).groupby(dist).sum()
    met["r2_oof_distrito"] = round(float(r2w(yd.values, pdm.values,
                                             wd.values)), 4)

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

    df["esperada"] = oof
    df["excesso_pp"] = df.y - df.esperada   # positivo = abst. ACIMA
    df["abstencao"] = df.y
    # votos de Lula perdidos (bruto) e ganho líquido por setor; cortes
    # e tetos entram no agregado por bloco (regioes_abst_76)
    df["vperd"] = df.excesso_pp / 100 * df.aptos * df.pl26 / 100
    df["vnet"] = df.excesso_pp / 100 * df.aptos * \
        (df.pl26 - df.pf26) / 100
    met["vperd_bruto_positivo_mi"] = round(float(
        df.vperd.clip(lower=0).sum() / 1e6), 3)
    df[["CD_SETOR", "cd_mun", "uf", "abstencao", "esperada", "excesso_pp",
        "aptos", "pl26", "pf26", "vperd", "vnet",
        "abst22t1"]].to_parquet(DIR_OUT / "setor_abst_lula.parquet",
                                index=False)
    with open(DIR_RELATORIOS / "ABST_MODELO_METRICAS.json", "w") as f:
        json.dump(met, f, ensure_ascii=False, indent=1)
    print(json.dumps(met, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
