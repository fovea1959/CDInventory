import collections
import json
import pickle
import sys




def load_barcodes():
    rv = {}
    c = collections.Counter()
    with open('barcodes.json', 'rb') as f:
        for line in f:
            x = json.loads(line)
            barcode = x.get('barcode')
            if barcode is not None:
                c[len(barcode)] += 1
                if len(barcode) == 12:
                    barcode = '0' + barcode
                rv[barcode] = x

    print(len(rv))

    print(c)

    with open('barcodes.pickle', 'wb') as f:
        pickle.dump(rv, f)


def main(argv):
    load_barcodes()


if __name__ == '__main__':
    main(sys.argv[1:])