import json

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


with open('/home/wegscd/mnt/xxx/release', 'rb') as f:
    jsonpath_exprs = jsonpath_expr_thingy()
    # "" prefix refers to the root level objects
    for obj in ijson.items(f, "", multiple_values=True):
        barcode = jsonpath_exprs.find1("barcode", obj)
        if barcode is not None:
            for item in jsonpath_exprs.find("media[*]", obj):
                v = item.value
                if type(v) is dict:
                    print(item.full_path, type(v), v.keys())
                elif type(v) is list:
                    print(item.full_path, type(v), v[0] if len(v) > 0 else "[]")
                else:
                    print(item.full_path, type(v), v)
            for item in jsonpath_exprs.find("release-group.*", obj):
                v = item.value
                if type(v) is dict:
                    print(item.full_path, type(v), v.keys())
                elif type(v) is list:
                    print(item.full_path, type(v), v[0] if len(v) > 0 else "[]")
                else:
                    print(item.full_path, type(v), v)
            artist_credit = jsonpath_exprs.find1("release-group.artist-credit", obj)
            print(json.dumps(artist_credit.value, indent=1, default=str))

            for item in jsonpath_exprs.find("release-group.artist-credit[*].name", obj):
                v = item.value
                if type(v) is dict:
                    print(item.full_path, type(v), v.keys())
                elif type(v) is list:
                    print(item.full_path, type(v), v[0] if len(v) > 0 else "[]")
                else:
                    print(item.full_path, type(v), v)

            keep = []
            for p in ('id', 'title', 'asin', 'barcode'):
                pass
            # print(json.dumps (obj, indent=1, default=str))
            break

