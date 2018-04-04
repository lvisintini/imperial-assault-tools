import json
from imperial_assault_tools.data_processing.contants import SOURCES

print('INITIAL_IDS = {')
for s in sorted(SOURCES.with_ids):
    with open(f'../imperial-assault-data/data/{s}.json') as f:
        data = json.load(f)
    ids = [m['id'] for m in data]
    print(f'    "{s}": {max(ids)},')
print('}')
