from collections import Iterable

def product(dic):
    result = [{}]

    def add_dict(d1, d2):
        d1 = d1.copy()
        d1.update(d2)
        return d1

    for key, value in dic.items():
        if isinstance(value, str) or not isinstance(value, Iterable):
            value = [value]
        if value != []:
            result = [add_dict(x,{key:y}) for x in result for y in value]

    # print("hello!!!")
    for r in result:
        yield r
