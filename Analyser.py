import pandas as pd

df = pd.read_csv("CiderProducts.csv")
print(df[df["price per sd"]<1.5].sort_values("price per sd"))
# print(df.describe())