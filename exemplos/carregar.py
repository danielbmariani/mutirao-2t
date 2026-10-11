# Carregar os dados e os modelos em Python
# pip install pandas pyarrow scikit-learn joblib
import joblib
import pandas as pd

# 1) Dados por setor (todos os 468 mil, com pertinência às regiões)
df = pd.read_parquet("../dados_modelo/setores_completo.parquet")
# ou: pd.read_csv("../dados_modelo/setores_completo.csv.gz")
print(df.columns.tolist())
print(df[df.regiao_voto.notna()].head())  # setores em região de interesse

# 2) Modelo do voto (objeto scikit-learn; versão em META.json)
pacote = joblib.load("../modelos/treinados/modelo_voto.joblib")
modelo, features = pacote["modelo"], pacote["features"]
# Exemplo: prever com as variáveis de um dataframe X[features]
# X deve ter as colunas listadas em `features` (NaN é aceito)
# pred = modelo.predict(X[features])

# 3) Modelo da abstenção (ensemble: use a MÉDIA dos 4)
pac = joblib.load("../modelos/treinados/modelo_abstencao.joblib")
# pred = sum(m.predict(X[pac["features"]]) for m in pac["ensemble"]) / 4
