# Upload de mbtiles ao Mapbox via Uploads API (mesmo método do v4):
#   1. credenciais S3 temporárias  2. boto3 multipart p/ o bucket staging
#   3. cria o upload apontando o tileset  4. acompanha até complete/error
# Uso: upload_mapbox_35.py <arquivo.mbtiles> <tileset_sem_usuario> ["Nome"]
#   ex.: upload_mapbox_35.py dados/processados/tiles/mapa_v5.mbtiles \
#        setores_voto_2026_v5 "Setores voto 2010-2026 v5"
# Token: embed_mapa/.mapbox_sk (sk com uploads:write/read, user danielbmariani)
import sys
import time
from pathlib import Path

import boto3
import requests

RAIZ = Path(__file__).resolve().parent.parent
USER = "danielbmariani"
TK = (RAIZ / "embed_mapa/.mapbox_sk").read_text().strip()
API = f"https://api.mapbox.com/uploads/v1/{USER}"


def main(mbtiles: str, tileset: str, nome: str | None = None):
    arq = Path(mbtiles)
    assert arq.exists(), arq
    nome = (nome or tileset)[:64]  # a API recusa name > 64 caracteres
    print(f"{arq.name} ({arq.stat().st_size/1e9:.2f} GB) -> "
          f"{USER}.{tileset}", flush=True)

    cred = requests.get(f"{API}/credentials?access_token={TK}",
                        timeout=60).json()
    assert "bucket" in cred, cred
    s3 = boto3.client(
        "s3", aws_access_key_id=cred["accessKeyId"],
        aws_secret_access_key=cred["secretAccessKey"],
        aws_session_token=cred["sessionToken"], region_name="us-east-1")
    t0 = time.time()
    s3.upload_file(str(arq), cred["bucket"], cred["key"],
                   Callback=lambda n: None)
    print(f"S3 ok em {time.time()-t0:.0f}s", flush=True)

    up = requests.post(
        f"{API}?access_token={TK}",
        json={"url": cred["url"], "tileset": f"{USER}.{tileset}",
              "name": nome}, timeout=60).json()
    assert "id" in up, up
    print("upload id:", up["id"], flush=True)
    while True:
        time.sleep(15)
        st = requests.get(f"{API}/{up['id']}?access_token={TK}",
                          timeout=60).json()
        if st.get("error"):
            raise SystemExit(f"ERRO no processamento Mapbox: {st['error']}")
        print(f"  progresso: {st.get('progress', 0):.0%} "
              f"complete={st.get('complete')}", flush=True)
        if st.get("complete"):
            break
    print(f"tileset {USER}.{tileset} PUBLICADO ✓")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
