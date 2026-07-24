import ijson

with open('/home/wegscd/mnt/xxx/release', 'rb') as f:
    # "" prefix refers to the root level objects
    i = 1
    for obj in ijson.items(f, "", multiple_values=True):
        if i % 10000 == 0:
            print(i)
        i += 1
