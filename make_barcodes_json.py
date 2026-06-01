import json
import pickle

import ijson
import jsonpath_ng

class jsonpath_expr_thingy(dict):
    def __missing__(self, key):
        '''
        only triggered if accessed via square brackets. get() method still returns None
        :param key:
        :return:
        '''
        value = jsonpath_ng.parse(key)
        self[key] = value
        return value

    def find(self, expr_text, o):
        expr = self[expr_text]
        rv = list(expr.get(o))
        return rv

    def find1(self, expr_text, o):
        rv = self.find(expr_text, o)
        if len(rv) == 0:
            return None
        if len(rv) > 1:
            raise ValueError(f"{expr_text} return too many objects")
        return rv[0]


with open('/home/wegscd/mnt/xxx/release', 'rb') as f_input:
    with open('barcodes.json', 'w') as f_output:
        jsonpath_exprs = jsonpath_expr_thingy()
        # "" prefix refers to the root level objects
        for i, obj in enumerate(ijson.items(f_input, "", multiple_values=True)):
            if i % 1000 == 0:
                print(i)
            barcode = jsonpath_exprs.find1("barcode", obj)
            if barcode is not None and barcode.value is not None and barcode.value != "":
                save_data = {}
                for p in ('id', 'title', 'asin', 'barcode'):
                    item = jsonpath_exprs.find1(p, obj)
                    if item is not None and item.value is not None:
                        save_data[p] = item.value
                    pass

                artists = []
                for item in jsonpath_exprs.find("release-group.artist-credit[*].name", obj):
                    v = item.value
                    artists.append(v)
                save_data['artists'] = artists

                # print(json.dumps(save_data, indent=1, default=str))
                print(json.dumps(save_data), file=f_output)
