import pandas as pd

# Load CSV
df = pd.read_csv("team_xxx.csv")

# Save as XLSX
df.to_excel("team_xxx.xlsx", index=False)
