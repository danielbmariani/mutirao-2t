# Ponto ÚNICO de atribuição urna→setor em forma de SHARE (fração dos
# eleitores do LV que vai para cada setor; Σ por LV = 1), usado pelos
# modelos dos sites (modelo_lula_72, modelo_abst_75, modelo_deficit_70),
# pela tipologia (78), pelo site aliados (67), pelos distritos (48), pelas
# escalas (43), pelos blocos da Câmara (50) e pela abstenção dos tiles (32).
#
# Antes de 12/10/2026 cada script repetia a mesma CTE "shares" (peso
# 1/distância normalizado por LV sobre relacao_malha2022_*). Agora:
#   METODO_VOTOS=original → exatamente essa CTE (resultado idêntico)
#   METODO_VOTOS=cons     → shares de distribuicao_85.py (gravitacional
#                           com restrição populacional)
# Em ambos a soma por LV é 1, logo Σ share·X_l conserva os totais do LV.
# A diferença do método original "não-normalizado" (votos_ponderados =
# Σ X_l/d, usado nos PERCENTUAIS por setor) está em agregacao_05 × 86.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DADOS, DIR_RELACAO, METODO_VOTOS

DIR_SHARES = DADOS / "interim/distribuicao_lv_setor"


def shares_sql(ano: int, turno: int = 1) -> str:
    """Subconsulta (lv_uid, CD_SETOR, share) para usar como
    `( ... ) AS s` em SQL do DuckDB."""
    if METODO_VOTOS == "cons":
        p = DIR_SHARES / f"shares_malha2022_{ano}_t{turno}.parquet"
        assert p.exists(), f"rode distribuicao_85.py {ano} {turno}: {p}"
        return f"(SELECT lv_uid, CD_SETOR, share FROM '{p}')"
    p = DIR_RELACAO / f"relacao_malha2022_{ano}_t{turno}_lv.parquet"
    assert p.exists(), f"faltando {p}"
    return f"""(SELECT lv_uid, CD_SETOR,
             (1.0 / greatest(distancia_centroide, 1.0)) /
             SUM(1.0 / greatest(distancia_centroide, 1.0))
               OVER (PARTITION BY lv_uid) AS share
           FROM '{p}')"""


def pesos_sql(ano: int, turno: int = 1) -> str:
    """Subconsulta (lv_uid, CD_SETOR, w) com o peso NÃO normalizado usado
    nos percentuais do método original (1/distância). No método
    conservativo o peso É o share (percentual = Σ share·X / Σ share·V)."""
    if METODO_VOTOS == "cons":
        return shares_sql(ano, turno).replace("share FROM", "share AS w FROM")
    p = DIR_RELACAO / f"relacao_malha2022_{ano}_t{turno}_lv.parquet"
    return (f"(SELECT lv_uid, CD_SETOR, "
            f"1.0 / greatest(distancia_centroide, 1.0) AS w FROM '{p}')")
