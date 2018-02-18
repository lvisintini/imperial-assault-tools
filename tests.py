from normalize.contants import SOURCES

import json
for s in SOURCES.with_ids:
    with open(f'./data/{s}.json') as f:
        data = json.load(f)
    ids = [m['id'] for m in data]
    for i in range(max(ids) + 1):
        if i not in ids:
            print (f'{i} not in {s}')




with open(f'./data/source-contents.json') as f:
    data = json.load(f)
    data = sorted(data, key=lambda m: (m['source_id'], m['content_type']))

all_data = {}
for s in SOURCES.as_list:
    with open(f'./data/{s}.json') as f:
        all_data[s] = json.load(f)

for s, g in groupby(data, lambda x: x['source_id']):
    s_name = next(iter([m for m in all_data[SOURCES.SOURCE] if m["id"] == s]))['name']
    print(s_name)
    for ct, g1 in groupby(g, lambda x: x['content_type']):
        print(f'\t{ct}')
        for i in g1:
            m = next(iter([m for m in all_data[ct] if m["id"] == i['content_id']]), None)

            if not m:
                print(f'\t\tPROBLEM {i}')
            else:
                print(f'\t\t{m["name"]}')
