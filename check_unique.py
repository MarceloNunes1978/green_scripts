# -*- coding: utf-8 -*-
import pandas as pd, os, sys

script_dir = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(script_dir, 'logs', 'unified_logs.csv')

print(f'Reading: {path}')
df = pd.read_csv(path)
total = len(df)
df.columns = ['timestamp', 'host', 'uri']
unique = df.drop_duplicates(subset=['host', 'uri']).shape[0]
print(f'Total linhas: {total:,}')
print(f'URIs unicas (host+uri): {unique:,}')
print(f'Reducao: {100*(1 - unique/total):.1f}%')
print(f'Tempo estimado (0.2s/req): {unique*0.2/3600:.1f}h')
print(f'Tempo estimado (0.5s/req): {unique*0.5/3600:.1f}h')
print()
print('Top 5 hosts:')
print(df['host'].value_counts().head())
