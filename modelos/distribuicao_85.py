# Distribuição CONSERVATIVA dos votos de cada local de votação (LV) entre os
# setores censitários — modelo gravitacional duplamente restrito, resolvido
# por ajuste iterativo proporcional (IPF / Sinkhorn), município a município.
#
# Por que (pedido do Daniel, 12/10/2026): no método original (relacao_04 +
# agregacao_05) cada SETOR puxa a votação dos LVs da sua banda de 100 m mais
# próxima, com peso 1/distância. O percentual do setor é um bom "perfil", mas
# um mesmo LV informa vários setores — somar contagens de setores conta a
# mesma urna várias vezes (DF: 11,8x o oficial) — e LVs que não são a banda
# mais próxima de nenhum setor somem (0,1% dos votos em 2026, 1,1% em 2022).
#
# Aqui cada LV REPARTE os seus eleitores entre os setores vizinhos:
#   T[s,l] = fluxo de eleitores do setor s para o LV l
#   T = diag(u) · K · diag(v)      (forma do modelo gravitacional)
#   K[s,l] = (d_ef + D0)^-GAMA     (atração decai com a distância)
#   Σ_s T[s,l] = aptos do LV l     (EXATO: cada eleitor da urna sai 1 vez)
#   Σ_l T[s,l] ≈ população 15+ do setor (Censo 2022), escalada para somar o
#                total de aptos do município — restrição FLEXÍVEL (ALFA)
#   share[s,l] = T[s,l] / aptos_l  →  Σ_s share = 1 para todo LV
# Qualquer contagem do LV (votos por candidato, comparecimento, aptos) vira
# contagem do setor por Σ_l share·X_l — a soma dos setores reproduz o total
# do município (e do Brasil) exatamente.
#
# Escolhas (documentadas no relatório):
#   - d_ef = distância do LV ao POLÍGONO do setor + (2/3)·raio equivalente
#     do setor (raio do círculo de mesma área): aproxima a distância típica
#     de um morador ao LV; LV dentro de setor grande não vira distância 0.
#   - GAMA = 3, D0 = 100 m, K_SETOR = 8, ALFA = 0,9. CALIBRAÇÃO (12/10, 15
#     maiores municípios, 2026 t1): critério = R² intra-município do % Lula
#     do setor explicado pelo perfil dos MORADORES (log renda, idade, 60+,
#     alfabetização, cor, urbano) — atribuição melhor = voto mais alinhado a
#     quem mora ali. Método antigo 0,298. Novo: GAMA 2/3/4 → 0,337/0,336/
#     0,333; K 4/8/16 → 0,331/0,336/0,336; ALFA 0,001/0,5/0,9 → 0,334/0,335/
#     0,336 e restrição DURA (0,999/1) → 0,316/0,323 (população do Censo ≠
#     eleitorado: forçar a igualdade piora). Escolhidos os valores do meio
#     (resultado robusto; GAMA 3 suaviza menos que 2). Correlação com o %
#     antigo: 0,96. Detalhes em relatorios/RELATORIO_DISTRIBUICAO.md.
#   - suporte esparso: cada setor liga aos K_SETOR LVs mais próximos (por
#     distância ao polígono, pré-selecionados por centroide) + LVs dentro do
#     polígono + o LV mais próximo do polígono; cada LV liga aos K_LV setores
#     povoados mais próximos + o polígono povoado mais próximo. Garante que
#     todo LV com coordenada distribui (no original, LV "sombreado" sumia).
#   - setores sem população 15+ (parques, áreas industriais, setores sem
#     dado no Censo) ficam FORA: não recebem votos (NaN no resultado).
#   - LV sem coordenada: os eleitores vão para os setores povoados do
#     município proporcionalmente à população 15+ (tipo 'sem_coord').
#   - poda: shares < PODA são descartados e o LV é renormalizado (conserva).
#   - municípios: LV usa o cod_ibge do cadastro geolocalizado; sem cadastro,
#     o de-para TSE→IBGE. Setores = CD_MUN da malha 2022 (como relacao_04).
#
# Saídas (uma por eleição):
#   dados/interim/distribuicao_lv_setor/shares_malha2022_{ano}_t{turno}.parquet
#     CD_SETOR, lv_uid, share (float64), tipo ('geo' | 'sem_coord')
#   dados/interim/distribuicao_lv_setor/diag_malha2022_{ano}_t{turno}.parquet
#     por município: n_setores, n_lv, iteracoes, erro_linhas, massa_podada
#
# Uso: python distribuicao_85.py            (todas as ELEICOES)
#      python distribuicao_85.py 2026 1     (uma eleição)
#      python distribuicao_85.py teste 3550308,2304400,...  (sem gravar)
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from scipy import sparse
from scipy.spatial import cKDTree
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (DADOS, DIR_ELEITORADO, DIR_RESULTADO, ELEICOES,
                    PATH_TSE_IBGE, PQ_MALHA_2022, path_locais)

DIR_OUT = DADOS / "interim/distribuicao_lv_setor"
PQ_CONTAGENS = DADOS / "processados/perfil/setor_contagens_2022.parquet"
PQ_DASH = DADOS / "processados/dashboard/setores_eleicao_renda.parquet"

GAMA = 3.0
D0 = 100.0          # metros
K_SETOR = 8
K_SETOR_PRE = 16    # pré-seleção por centroide antes da distância ao polígono
K_LV = 4
PODA = 1e-4
ALFA = 0.9          # amortecimento da restrição de linha (ver sinkhorn)
MAX_ITER = 5000


def utm_epsg(lon: float) -> int:
    zona = int(np.floor((lon + 180) / 6) + 1)
    return 31960 + zona


def eleitorado_paths(ano):
    """Mesma regra de tiles_multi_32/escalas_43 (glob ingênuo duplicava)."""
    br = DIR_ELEITORADO / f"eleitorado_local_votacao_{ano}_BRASIL.csv"
    if br.exists():
        return [str(br)]
    unico = DIR_ELEITORADO / f"eleitorado_local_votacao_{ano}.csv"
    if unico.exists():
        return [str(unico)]
    ps = sorted(DIR_ELEITORADO.glob(f"eleitorado_local_votacao_{ano}_??.csv"))
    ps = [str(p) for p in ps if "_ZZ" not in p.name]
    assert ps, f"sem eleitorado_local_votacao de {ano}"
    return ps


def uid_sql(ano):
    return (f"'{ano}_' || CAST(CAST(CD_MUNICIPIO AS INT) AS VARCHAR) || '_' "
            f"|| CAST(CAST(NR_ZONA AS INT) AS VARCHAR) || '_' || "
            f"CAST(CAST(NR_LOCAL_VOTACAO AS INT) AS VARCHAR)")


def lvs_eleicao(con, ano, turno) -> pd.DataFrame:
    """Todos os LVs com voto no turno (fora o exterior), com município IBGE,
    coordenada (quando houver), aptos e comparecimento de presidente."""
    vs = [str(p) for p in DIR_RESULTADO.glob(f"votacao_secao_{ano}_*.csv")]
    ele = eleitorado_paths(ano)
    df = con.sql(f"""
      WITH comp AS (
        SELECT {uid_sql(ano)} AS lv_uid,
               any_value(CAST(CD_MUNICIPIO AS INT)) AS cd_tse,
               SUM(CAST(QT_VOTOS AS BIGINT)) AS comp
        FROM read_csv({vs}, delim=';', header=true, encoding='latin-1',
                      all_varchar=true, union_by_name=true)
        WHERE NR_TURNO = '{turno}' AND SG_UF <> 'ZZ'
              AND upper(DS_CARGO) = 'PRESIDENTE'
        GROUP BY 1),
      aptos AS (
        SELECT {uid_sql(ano)} AS lv_uid,
               SUM(CAST(QT_ELEITOR_SECAO AS BIGINT)) AS aptos
        FROM read_csv({ele}, delim=';', header=true, encoding='latin-1',
                      all_varchar=true, union_by_name=true)
        WHERE NR_TURNO = '{turno}' AND SG_UF <> 'ZZ'
        GROUP BY 1)
      SELECT c.lv_uid, c.cd_tse, c.comp, coalesce(a.aptos, 0) AS aptos
      FROM comp c LEFT JOIN aptos a USING (lv_uid)""").df()
    loc = pd.read_parquet(path_locais(ano),
                          columns=["lv_uid", "cod_ibge", "lat_final",
                                   "lon_final"])
    loc = loc.drop_duplicates("lv_uid")
    df = df.merge(loc, on="lv_uid", how="left")
    de_para = pd.read_csv(PATH_TSE_IBGE, usecols=["codigo_tse",
                                                  "codigo_ibge"])
    mapa = dict(zip(de_para.codigo_tse.astype(int),
                    de_para.codigo_ibge.astype(int).astype(str)))
    sem_mun = df.cod_ibge.isna()
    df.loc[sem_mun, "cod_ibge"] = df.loc[sem_mun, "cd_tse"].map(mapa)
    # voto em TRÂNSITO (códigos TSE 999xx, desde 2010): eleitor fora do
    # município de residência — não pertence a setor nenhum; fica FORA da
    # distribuição (o método original também o descartava, sem coordenada)
    transito = df.cod_ibge.isna() & (df.cd_tse >= 99900)
    if transito.any():
        print(f"  voto em trânsito excluído: {transito.sum()} LVs, "
              f"{int(df.comp[transito].sum()):,} votos", flush=True)
    df = df[~transito].copy()
    assert df.cod_ibge.notna().all(), \
        f"LV sem município IBGE: {df[df.cod_ibge.isna()].head()}"
    df["cod_ibge"] = df["cod_ibge"].astype(str).str.replace(r"\.0$", "",
                                                            regex=True)
    # massa do LV para o balanceamento: aptos; sem aptos (cadastro sem a
    # seção), o comparecimento — só define a forma do fluxo, não a contagem
    df["massa"] = np.where(df.aptos > 0, df.aptos, df.comp).astype(float)
    df["geo"] = df.lat_final.notna() & df.lon_final.notna()
    # ORDEM DETERMINÍSTICA (12/10): o DuckDB paralelo devolve as urnas em
    # ordem variável; com urnas no mesmo endereço (distância empatada) o
    # suporte escolhido mudava entre execuções (1,8 mil setores, até 19 pp)
    return df.sort_values("lv_uid").reset_index(drop=True)


def massa_setores() -> pd.DataFrame:
    """População 15+ por setor (Censo 2022). Setor com p15 = 0 mas
    população total > 0 (supressão nas tabelas de idade) usa 0,78·pop
    (razão nacional 15+/total) — são ~10 mil pessoas no Brasil."""
    p = pd.read_parquet(PQ_CONTAGENS, columns=["CD_SETOR", "pop15"])
    d = pd.read_parquet(PQ_DASH, columns=["cd_setor", "pop"]).rename(
        columns={"cd_setor": "CD_SETOR"})
    m = d.merge(p, on="CD_SETOR", how="outer")
    # Boa Esperança do Norte (MT, 5106241): malhas_02 RENOMEOU os 15 setores
    # (prefixo do município trocado), mas as tabelas do Censo guardam o
    # código original → casa pelo sufixo (distrito+setor, 8 dígitos) entre
    # os códigos de MT que sumiram da malha. Sem isso o município fica
    # "sem setor povoado" e seus LVs não distribuem.
    malha = pd.read_parquet(PQ_MALHA_2022, columns=["CD_SETOR", "CD_MUN"])
    ben = malha.CD_SETOR[malha.CD_MUN == "5106241"]
    if len(ben):
        sumiram = m[~m.CD_SETOR.isin(malha.CD_SETOR)
                    & m.CD_SETOR.str.startswith("51")]
        por_suf = sumiram.assign(suf=sumiram.CD_SETOR.str[7:])
        assert por_suf.suf.is_unique, "sufixo ambíguo p/ BEN"
        de_para = dict(zip(por_suf.suf, por_suf.CD_SETOR))
        novo = {s: de_para.get(s[7:]) for s in ben}
        assert all(novo.values()), f"setor de BEN sem original: {novo}"
        extra = m[m.CD_SETOR.isin(novo.values())].copy()
        inv = {v: k for k, v in novo.items()}
        extra["CD_SETOR"] = extra.CD_SETOR.map(inv)
        m = pd.concat([m, extra], ignore_index=True)
    m["pop15"] = m["pop15"].fillna(0.0)
    m["pop"] = m["pop"].fillna(0.0)
    m["r"] = np.where(m.pop15 > 0, m.pop15, 0.78 * m["pop"])
    return m[["CD_SETOR", "r"]]


def sinkhorn(K: sparse.csr_matrix, r: np.ndarray, c: np.ndarray,
             alfa: float = None):
    """Escala K para T = diag(u) K diag(v) com colunas = c (EXATO, último
    passo) e linhas ≈ r. Atualização das linhas amortecida (u ← (r/Kv)^alfa,
    Sinkhorn "não balanceado" com penalidade KL nas linhas): com suporte
    esparso o problema estritamente duplamente restrito pode ser inviável e
    as escalas divergem (u→∞, v→0 — visto em Salvador no teste); com alfa<1
    a iteração é uma contração e sempre converge. alfa→1 = restrição dura
    da população; alfa→0 = só o núcleo de distância.
    Devolve (T, iterações, erro relativo L1 das linhas)."""
    alfa = ALFA if alfa is None else alfa
    Kt = K.T.tocsr()
    v = np.ones(K.shape[1])
    lu_ant = None
    tot = r.sum()
    it = 0
    for it in range(1, MAX_ITER + 1):
        with np.errstate(over="raise", divide="raise", invalid="raise"):
            u = (r / (K @ v)) ** alfa
            v = c / (Kt @ u)
        lu = np.log(u)
        if lu_ant is not None and np.abs(lu - lu_ant).max() < 1e-7:
            break
        lu_ant = lu
    assert np.isfinite(u).all() and np.isfinite(v).all(), "escala infinita"
    T = sparse.diags(u) @ K @ sparse.diags(v)
    err = np.abs(np.asarray(T.sum(axis=1)).ravel() - r).sum() / tot
    return T.tocsr(), it, err


def pares_candidatos(polys, cents, req, pts):
    """Suporte esparso (índices setor, LV) e distância efetiva d_ef."""
    n_s, n_l = len(polys), len(pts)
    pts_xy = np.column_stack([shapely.get_x(pts), shapely.get_y(pts)])
    cen_xy = np.column_stack([shapely.get_x(cents), shapely.get_y(cents)])
    pares = []
    # (a) setor → K_SETOR LVs mais próximos do polígono
    k_pre = min(K_SETOR_PRE, n_l)
    _, jj = cKDTree(pts_xy).query(cen_xy, k=k_pre)
    jj = jj.reshape(n_s, k_pre)
    ii = np.repeat(np.arange(n_s), k_pre)
    dd = shapely.distance(polys[ii], pts[jj.ravel()]).reshape(n_s, k_pre)
    k = min(K_SETOR, n_l)
    # k mais próximos COM EMPATES: urnas à mesma distância (mesmo endereço,
    # zonas diferentes) entram juntas — sem isso a escolha dependia da
    # ordem das linhas e o resultado não era reproduzível
    thr = np.sort(dd, axis=1)[:, k - 1]
    mask = dd <= thr[:, None] + 1e-6
    si, sj = np.nonzero(mask)
    pares.append(np.column_stack([si, jj[si, sj]]))
    # (b) LVs dentro do polígono e o LV mais próximo de cada polígono
    arv_pts = STRtree(pts)
    dentro = arv_pts.query(polys, predicate="intersects")
    pares.append(dentro.T)
    viz = arv_pts.query_nearest(polys, all_matches=False)
    pares.append(viz.T)
    # (c) LV → K_LV setores mais próximos (centroide) + polígono mais próximo
    k2 = min(K_LV, n_s)
    _, ss = cKDTree(cen_xy).query(pts_xy, k=k2)
    ss = ss.reshape(n_l, k2)
    pares.append(np.column_stack([ss.ravel(),
                                  np.repeat(np.arange(n_l), k2)]))
    viz2 = STRtree(polys).query_nearest(pts, all_matches=False)
    pares.append(np.column_stack([viz2[1], viz2[0]]))
    P = np.unique(np.vstack(pares).astype(np.int64), axis=0)
    dpol = shapely.distance(polys[P[:, 0]], pts[P[:, 1]])
    d_ef = dpol + (2.0 / 3.0) * req[P[:, 0]]
    return P, d_ef


def processa_municipio(args):
    """Distribui todas as eleições de um município. Roda em subprocesso."""
    cod, lvs_por_el, massa_mun, malha_path, gama, alfa = args
    malha = gpd.read_parquet(malha_path, columns=["CD_SETOR", "geometry"],
                             filters=[("CD_MUN", "==", cod)])
    malha = malha.sort_values("CD_SETOR").reset_index(drop=True)
    out, diag = [], []
    if len(malha):
        malha = malha.merge(massa_mun, on="CD_SETOR", how="left")
        malha["r"] = malha["r"].fillna(0.0)
        malha = malha[malha.r > 0].reset_index(drop=True)
    for el, lvs in lvs_por_el.items():
        d = {"eleicao": el, "cod_ibge": cod, "n_lv": len(lvs),
             "n_lv_geo": int(lvs.geo.sum()), "massa_lv": lvs.massa.sum()}
        if len(malha) == 0:
            d["status"] = "sem_setores_povoados"
            diag.append(d)
            continue
        setores = malha.CD_SETOR.values
        r_pop = malha.r.values.astype(float)
        geo = lvs[lvs.geo].reset_index(drop=True)
        sem = lvs[~lvs.geo]
        m_geo = geo.massa.sum()
        if len(geo):
            crs = utm_epsg(float(geo.lon_final.iloc[0]))
            polys = malha.geometry.to_crs(crs).values
            cents = shapely.centroid(polys)
            area = shapely.area(polys)
            req = np.sqrt(area / np.pi)
            pts = gpd.GeoSeries(shapely.points(geo.lon_final.values,
                                               geo.lat_final.values),
                                crs=4326).to_crs(crs).values
            P, d_ef = pares_candidatos(polys, cents, req, pts)
            kern = (d_ef + D0) ** (-gama)
            K = sparse.csr_matrix((kern, (P[:, 0], P[:, 1])),
                                  shape=(len(polys), len(pts)))
            # linhas sem nenhum par (não deveria) recebem o LV mais próximo
            assert (np.diff(K.indptr) > 0).all(), "setor sem par"
            assert (np.diff(K.tocsc().indptr) > 0).all(), "LV sem par"
            r = r_pop * (m_geo / r_pop.sum())
            c = geo.massa.values.astype(float)
            # restrição dura demais pode divergir num município (suporte
            # inviável): recua o alfa e registra qual foi usado
            for a_us in [alfa] + [x for x in (0.99, 0.95, 0.9, 0.8)
                                  if x < alfa]:
                try:
                    T, it, err = sinkhorn(K, r, c, a_us)
                    break
                except (AssertionError, FloatingPointError):
                    continue
            else:
                raise RuntimeError(f"{cod} {el}: Sinkhorn não convergiu")
            d["alfa_usado"] = a_us
            T = T.tocoo()
            share = T.data / c[T.col]
            # poda + renormalização por LV (conserva exatamente)
            ok = share >= PODA
            podada = float((share[~ok] * c[T.col[~ok]]).sum())
            s_i, l_i, sh = T.row[ok], T.col[ok], share[ok]
            soma = np.bincount(l_i, weights=sh, minlength=len(pts))
            sh = sh / soma[l_i]
            out.append(pd.DataFrame({
                "CD_SETOR": setores[s_i], "lv_uid": geo.lv_uid.values[l_i],
                "share": sh, "tipo": "geo"}))
            linhas = np.bincount(s_i, weights=sh * c[l_i],
                                 minlength=len(polys))
            rel = linhas / np.where(r > 0, r, np.nan)
            d.update(n_setores=len(polys), n_pares=len(P),
                     n_pares_final=int(ok.sum()), iteracoes=it,
                     erro_linhas=err, massa_podada=podada,
                     razao_linha_p05=float(np.nanpercentile(rel, 5)),
                     razao_linha_p95=float(np.nanpercentile(rel, 95)),
                     razao_linha_max=float(np.nanmax(rel)))
        if len(sem):
            w = r_pop / r_pop.sum()
            for uid in sem.lv_uid.values:
                out.append(pd.DataFrame({"CD_SETOR": setores,
                                         "lv_uid": uid, "share": w,
                                         "tipo": "sem_coord"}))
        d["status"] = "ok"
        d["massa_sem_coord"] = float(sem.massa.sum())
        diag.append(d)
    res = pd.concat(out, ignore_index=True) if out else None
    return cod, res, diag


def prepara(eleicoes):
    con = duckdb.connect()
    con.sql("SET threads TO 12")
    lvs = {}
    for ano, turno in eleicoes:
        t0 = time.time()
        df = lvs_eleicao(con, ano, turno)
        sem_mun = df.cod_ibge.isin(["nan", "None"])
        assert not sem_mun.any(), \
            f"{ano}t{turno}: {sem_mun.sum()} LVs sem município IBGE"
        lvs[(ano, turno)] = df
        print(f"{ano} t{turno}: {len(df)} LVs | sem coord "
              f"{(~df.geo).sum()} ({df.massa[~df.geo].sum():,.0f} aptos) | "
              f"aptos 0 {(df.aptos == 0).sum()} | {time.time() - t0:.0f}s",
              flush=True)
    return lvs


def roda(eleicoes, municipios=None, gama=GAMA, alfa=ALFA, workers=14):
    lvs = prepara(eleicoes)
    massa = massa_setores()
    massa["CD_MUN"] = massa.CD_SETOR.str[:7]
    cods = sorted(set().union(*[set(d.cod_ibge) for d in lvs.values()]))
    if municipios:
        cods = [c for c in cods if c in municipios]
    jobs = []
    for cod in cods:
        por_el = {el: d[d.cod_ibge == cod] for el, d in lvs.items()}
        por_el = {el: d for el, d in por_el.items() if len(d)}
        jobs.append((cod, por_el,
                     massa[massa.CD_MUN == cod][["CD_SETOR", "r"]],
                     str(PQ_MALHA_2022), gama, alfa))
    print(f"{len(jobs)} municípios", flush=True)
    res = {el: [] for el in lvs}
    diags = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(processa_municipio, j) for j in jobs]
        for n, fut in enumerate(as_completed(futs), 1):
            cod, df, dg = fut.result()
            diags.extend(dg)
            if df is not None:
                # separa por eleição pelo prefixo do lv_uid (ano) — o turno
                # vem do dicionário de LVs: um lv_uid pode existir nos 2
                for el in lvs:
                    uids = set(lvs[el].lv_uid[lvs[el].cod_ibge == cod])
                    sub = df[df.lv_uid.isin(uids)]
                    if len(sub):
                        res[el].append(sub)
            if n % 500 == 0:
                print(f"  {n}/{len(jobs)} ({time.time() - t0:.0f}s)",
                      flush=True)
    diag = pd.DataFrame(diags)
    return lvs, res, diag


def grava_eleicao(el, lvs, res, diag, substitui_cod=None):
    """Gate de conservação + gravação; com substitui_cod, troca só as
    linhas desse município nos parquets existentes (rerun pontual)."""
    ano, turno = el
    sh = pd.concat(res[el], ignore_index=True)
    soma = sh.groupby("lv_uid").share.sum()
    assert np.allclose(soma.values, 1.0, atol=1e-9), \
        f"Σ share ≠ 1: {soma[(soma - 1).abs() > 1e-9].head()}"
    p_sh = DIR_OUT / f"shares_malha2022_{ano}_t{turno}.parquet"
    p_dg = DIR_OUT / f"diag_malha2022_{ano}_t{turno}.parquet"
    if substitui_cod:
        # SÓ as urnas do município rerodado (bug 12/10: filtrar pelo
        # conjunto inteiro apagava o resto do arquivo)
        uids = set(lvs[el].lv_uid[lvs[el].cod_ibge == substitui_cod])
        assert 0 < len(uids) < 1000, len(uids)
        antigo = pd.read_parquet(p_sh)
        sh = pd.concat([antigo[~antigo.lv_uid.isin(uids)], sh],
                       ignore_index=True)
        dg = pd.read_parquet(p_dg)
        diag = pd.concat([dg[dg.cod_ibge != substitui_cod], diag],
                         ignore_index=True)
    # gravação ATÔMICA (tmp + replace): leitores concorrentes veem o
    # arquivo antigo íntegro ou o novo, nunca um torso
    for df, p in ((sh, p_sh), (diag, p_dg)):
        tmp = p.with_suffix(".tmp.parquet")
        df.to_parquet(tmp, index=False)
        tmp.replace(p)
    return sh, diag


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--so-municipio":
        # rerun pontual de um município em todas as eleições (ex.: BEN)
        cod = a[1]
        lvs, res, diag = roda(ELEICOES, [cod])
        for el in ELEICOES:
            if not res[el]:
                print(f"{el}: {cod} sem LV", flush=True)
                continue
            sh, dg = grava_eleicao(el, lvs, res,
                                   diag[diag.eleicao == el], cod)
            print(f"{el}: {cod} regravado ({len(sh):,} pares no total)",
                  flush=True)
        sys.exit(0)
    if a and a[0] == "teste":
        muns = a[1].split(",")
        gama = float(a[2]) if len(a) > 2 else GAMA
        alfa = float(a[3]) if len(a) > 3 else ALFA
        lvs, res, diag = roda([(2026, 1)], muns, gama=gama, alfa=alfa)
        print(diag.to_string())
        sys.exit(0)
    els = [(int(a[0]), int(a[1]))] if a else ELEICOES
    DIR_OUT.mkdir(parents=True, exist_ok=True)
    for el in els:
        ano, turno = el
        if (DIR_OUT / f"shares_malha2022_{ano}_t{turno}.parquet").exists():
            print(f"=== {el}: já existe, pulando", flush=True)
            continue
        print(f"=== {el}", flush=True)
        lvs, res, diag = roda([el])
        ano, turno = el
        sh = pd.concat(res[el], ignore_index=True)
        # GATE de conservação por LV: Σ share = 1 para todo LV com massa
        soma = sh.groupby("lv_uid").share.sum()
        dl = lvs[el]
        # LV sem distribuição só pode vir de município sem setor povoado
        sem_set = set(diag.cod_ibge[diag.status == "sem_setores_povoados"])
        faltam = dl[~dl.lv_uid.isin(soma.index)]
        assert faltam.cod_ibge.isin(sem_set).all(), \
            f"LV sem share fora de município vazio: {faltam.head()}"
        assert np.allclose(soma.values, 1.0, atol=1e-9), \
            f"Σ share ≠ 1: {soma[(soma - 1).abs() > 1e-9].head()}"
        for df, p in ((sh, DIR_OUT / f"shares_malha2022_{ano}_t{turno}.parquet"),
                      (diag, DIR_OUT / f"diag_malha2022_{ano}_t{turno}.parquet")):
            tmp = p.with_suffix(".tmp.parquet")
            df.to_parquet(tmp, index=False)
            tmp.replace(p)
        perd = dl[~dl.lv_uid.isin(soma.index)]
        print(f"gravado: {len(sh):,} pares | LVs sem distribuição: "
              f"{len(perd)} ({perd.comp.sum():,} votos) | erro linhas "
              f"mediano {diag.erro_linhas.median():.2e} máx "
              f"{diag.erro_linhas.max():.2e}", flush=True)
