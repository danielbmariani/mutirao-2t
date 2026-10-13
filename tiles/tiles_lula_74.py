# Tileset do site eleitores — déficit NACIONAL de Lula (modelo_lula_72):
# um único atributo d (pp x10, com sinal) por setor/distrito/município +
# identificação. Bandas idênticas aos tilesets aliados.
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import duckdb
import geopandas as gpd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DADOS, PQ_MALHA_2022

TIPPECANOE = Path.home() / ".local/share/tippecanoe/tippecanoe"
TILE_JOIN = Path.home() / ".local/share/tippecanoe/tile-join"
DIR_TILES = DADOS / "processados/tiles"
PQ_DEF = DADOS / "processados/eleitores/setor_deficit_lula.parquet"
PQ_ABS = DADOS / "processados/eleitores/setor_abst_lula.parquet"
GJ_MUN = DIR_TILES / "municipios_v8r.geojsonl"
GJ_DIST = DIR_TILES / "distritos_v8r.geojsonl"
SAIDA = DIR_TILES / "mapa_lula_v4.mbtiles"  # v4 12/10 noite = distribuição conservativa; v3 = abstenção com biometria


def tp(args):
    subprocess.run([str(TIPPECANOE), "-P", "--force", "-q"] + args,
                   check=True)


def main():
    con = duckdb.connect()
    con.sql("SET threads TO 14")

    def agg(chave_sql, chave):
        v = con.sql(f"""
          SELECT {chave_sql} AS {chave},
                 CAST(round(10 * sum(deficit_pp * validos) /
                      sum(validos)) AS INT) AS d
          FROM '{PQ_DEF}' GROUP BY 1
        """).df().set_index(chave)
        a = con.sql(f"""
          SELECT {chave_sql} AS {chave},
                 CAST(round(10 * sum(excesso_pp * aptos) /
                      sum(aptos)) AS INT) AS a
          FROM '{PQ_ABS}' GROUP BY 1
        """).df().set_index(chave)
        return v.join(a, how="outer")

    set_at = agg("CD_SETOR", "CD_SETOR")
    dist_at = agg("substr(CD_SETOR, 1, 9)", "CD_DIST")
    mun_at = agg("cd_mun", "CD_MUN")

    mun = gpd.read_file(GJ_MUN, columns=["CD_MUN", "NM_MUN", "SIGLA_UF",
                                         "geometry"])
    mun = mun.merge(mun_at, left_on="CD_MUN", right_index=True, how="left")
    gj_m = DIR_TILES / "municipios_lula.geojsonl"
    mun.to_file(gj_m, driver="GeoJSONSeq")
    dist = gpd.read_file(GJ_DIST, columns=["CD_DIST", "NM_DIST", "CD_MUN",
                                           "NM_MUN", "geometry"])
    dist = dist.merge(dist_at, left_on="CD_DIST", right_index=True,
                      how="left")
    gj_d = DIR_TILES / "distritos_lula.geojsonl"
    dist.to_file(gj_d, driver="GeoJSONSeq")
    malha = gpd.read_parquet(PQ_MALHA_2022, columns=["CD_SETOR",
                                                     "geometry"])
    malha = malha.merge(set_at, left_on="CD_SETOR", right_index=True,
                        how="left")
    gj_s = DIR_TILES / "setores_lula.geojsonl"
    malha.to_file(gj_s, driver="GeoJSONSeq")
    print("geojsonl exportados", flush=True)

    mb_m = DIR_TILES / "municipios_lula.mbtiles"
    tp(["-o", str(mb_m), "--minimum-zoom=0", "--maximum-zoom=10",
        "--coalesce-smallest-as-needed", "--detect-shared-borders",
        "-M", "150000", "-S", "10", "-l", "municipios", str(gj_m)])
    mb_d = DIR_TILES / "distritos_lula.mbtiles"
    tp(["-o", str(mb_d), "--minimum-zoom=7", "--maximum-zoom=12",
        "--coalesce-smallest-as-needed", "--detect-shared-borders",
        "-M", "150000", "-S", "10", "-l", "distritos", str(gj_d)])
    mb_s = DIR_TILES / "setores_lula.mbtiles"
    tp(["-o", str(mb_s), "--minimum-zoom=11", "--maximum-zoom=14",
        "--coalesce-smallest-as-needed", "--detect-shared-borders",
        "--no-tiny-polygon-reduction", "-M", "450000", "-S", "10",
        "-l", "setores", str(gj_s)])
    print("bandas prontas; tile-join", flush=True)
    subprocess.run([str(TILE_JOIN), "--force", "-o", str(SAIDA),
                    str(mb_m), str(mb_d), str(mb_s)], check=True)

    db = sqlite3.connect(SAIDA)
    meta = dict(db.execute("SELECT name, value FROM metadata").fetchall())
    vl = {l["id"]: set(l["fields"]) for l in
          json.loads(meta["json"])["vector_layers"]}
    for cam, extra in [("municipios", {"d", "a", "CD_MUN", "NM_MUN"}),
                       ("distritos", {"d", "a", "CD_DIST", "NM_DIST"}),
                       ("setores", {"d", "a", "CD_SETOR"})]:
        falta = extra - vl.get(cam, set())
        assert not falta, f"GATE metadata: faltam em {cam}: {falta}"
    pior = db.execute("SELECT max(length(tile_data)) FROM tiles"
                      ).fetchone()[0]
    assert pior <= 500_000, f"GATE: tile de {pior/1000:.0f} KB"
    zooms = dict(db.execute(
        "SELECT zoom_level, count(*) FROM tiles GROUP BY 1").fetchall())
    assert all(zooms.get(z) for z in range(0, 15)), f"GATE: {zooms}"
    db.close()
    print(f"GATES ok — pior tile {pior/1000:.0f} KB")
    print(f"PRONTO: {SAIDA} ({SAIDA.stat().st_size/1e9:.2f} GB)")


if __name__ == "__main__":
    main()
