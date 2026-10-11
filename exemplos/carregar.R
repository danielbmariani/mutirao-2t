# Carregar os dados e os modelos em R
# Dados: nativo. Modelos: objetos scikit-learn, via {reticulate}.
# install.packages(c("arrow", "reticulate"))

library(arrow)
df <- read_parquet("../dados_modelo/setores_completo.parquet")
# ou: df <- read.csv(gzfile("../dados_modelo/setores_completo.csv.gz"))
str(df)
# setores dentro de regiões de interesse (visão voto):
head(df[!is.na(df$regiao_voto), ])

# Modelos (precisam de Python com scikit-learn == versão do META.json)
library(reticulate)
joblib <- import("joblib")
pacote <- joblib$load("../modelos/treinados/modelo_voto.joblib")
modelo <- pacote$modelo
features <- unlist(pacote$features)
# pred <- modelo$predict(r_to_py(df_novo[, features]))

pac <- import("joblib")$load("../modelos/treinados/modelo_abstencao.joblib")
# media dos 4 modelos do ensemble:
# preds <- sapply(pac$ensemble, function(m) m$predict(X_py))
# pred  <- rowMeans(preds)
