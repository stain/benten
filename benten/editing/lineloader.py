"""A little shim on top of PyYaml that retrieves line and column numbers for objects in the YAML.
And we get to subclass int!!!

Some profiling information

For "wgs.cwl"

In [2]: %timeit data = parse_yaml_with_line_info(cwl)
127 ms ± 1.07 ms per loop (mean ± std. dev. of 7 runs, 10 loops each)

In [2]: %timeit data = parse_yaml_with_line_info(cwl, convert_to_lam=True)
126 ms ± 1.23 ms per loop (mean ± std. dev. of 7 runs, 10 loops each)

In [3]: %timeit data = yaml.load(cwl, CSafeLoader)
95.5 ms ± 374 µs per loop (mean ± std. dev. of 7 runs, 10 loops each)

In [4]: %timeit ruamel.yaml.load(cwl, Loader=ruamel.yaml.RoundTripLoader)
2.43 s ± 165 ms per loop (mean ± std. dev. of 7 runs, 1 loop each)


For "salmon.cwl"

In [7]: %timeit ruamel.yaml.load(cwl, Loader=ruamel.yaml.RoundTripLoader)
695 ms ± 6.26 ms per loop (mean ± std. dev. of 7 runs, 1 loop each)

In [8]: %timeit data = parse_yaml_with_line_info(cwl)
36.8 ms ± 363 µs per loop (mean ± std. dev. of 7 runs, 10 loops each)

In [9]: %timeit data = yaml.load(cwl, CSafeLoader)
28.2 ms ± 250 µs per loop (mean ± std. dev. of 7 runs, 10 loops each)


(ruamel.yaml         0.15.88)

**NOTE**
For now, this code only puts in meta information in lists, seq and strings. This is sufficient
for the editing we need to do in CWL docs. We can extend as needed
"""
from typing import Union, List

import yaml
try:
    from yaml import CSafeLoader as Loader
except ImportError:
    import warnings
    warnings.warn("You don't have yaml.CSafeLoader installed, "
                  "falling back to slower yaml.SafeLoader",
                  ImportWarning)
    from yaml import SafeLoader as Loader


def load_yaml(raw_cwl: str):
    return yaml.load(raw_cwl, Loader)


class Yint(int):  # pragma: no cover
    def __new__(cls, value, node):
        x = int.__new__(cls, value)
        x.start = node.start_mark
        x.end = node.end_mark
        x.style = node.style
        return x


class Ystr(str):
    def __new__(cls, value, node):
        x = str.__new__(cls, value)
        x.start = node.start_mark
        x.end = node.end_mark
        x.style = node.style
        return x


class Yfloat(float):  # pragma: no cover
    def __new__(cls, value, node):
        x = float.__new__(cls, value)
        x.start = node.start_mark
        x.end = node.end_mark
        x.style = node.style
        return x


class Ybool(int):  # pragma: no cover
    def __new__(cls, value, node):
        x = int.__new__(cls, bool(value))
        x.start = node.start_mark
        x.end = node.end_mark
        x.style = node.style
        return x


class Ydict(dict):
    def __init__(self, value, node):
        dict.__init__(self, value)
        self.start = node.start_mark
        self.end = node.end_mark
        self.flow_style = node.flow_style


class Ylist(list):
    def __init__(self, value, node):
        list.__init__(self, value)
        self.start = node.start_mark
        self.end = node.end_mark
        self.flow_style = node.flow_style


# We've flattened them all together. The names don't clash (due to inheritance), so we are ok
# if we run into trouble, we'll have to add context information (CWL type, parent type etc.)
allowed_loms = {
    "inputs": "id",
    "outputs": "id",
    "requirements": "class",
    "hints": "class",
    "fields": "name",
    "steps": "id",
    "in": "id"
}


class LAM(dict):
    def __init__(self, value, node, key_field: str="id"):
        secret_missing_key = "there is no CWL field that looks like this, and it can safely be used"
        self.errors = []

        def _add_error_line(ln):
            self.errors += [ln]
            return secret_missing_key

        dict.__init__(self, {
            (v.get(key_field) or _add_error_line(v)): v
            for v in value
        })

        if secret_missing_key in self:
            self.pop(secret_missing_key)

        self.start = node.start_mark
        self.end = node.end_mark
        self.flow_style = node.flow_style


def y_construct(v, node):  # pragma: no cover
    if isinstance(v, str):
        return Ystr(v, node)
    elif isinstance(v, int):
        return Yint(v, node)
    elif isinstance(v, float):
        return Yfloat(v, node)
    elif isinstance(v, bool):
        return Ybool(v, node)
    elif isinstance(v, dict):
        return Ydict(v, node)
    elif isinstance(v, list):
        return Ylist(v, node)
    else:
        return v


meta_node_key = "_lineloader_secret_key_"


class YSafeLineLoader(Loader):

    # The SafeLoader always passes str to this
    def construct_scalar(self, node):
        # return y_construct(super(YSafeLineLoader, self).construct_scalar(node), node)
        return Ystr(super(YSafeLineLoader, self).construct_scalar(node), node)

    def construct_mapping(self, node, deep=False):
        mapping = super().construct_mapping(node, deep=deep)
        mapping[meta_node_key] = node
        return mapping

    def construct_sequence(self, node, deep=False):
        seq = super().construct_sequence(node, deep=deep)
        seq.append(node)
        return seq


def _recurse_extract_meta(x, key=None, convert_to_lam=False):
    if isinstance(x, dict):
        node = x.pop(meta_node_key)
        return Ydict({k: _recurse_extract_meta(v, k, convert_to_lam) for k, v in x.items()}, node)
    elif isinstance(x, list):
        node = x.pop(-1)
        _data = [_recurse_extract_meta(v, None, convert_to_lam) for v in x]
        if convert_to_lam and key in allowed_loms:
            if isinstance(x, list):
                return LAM(_data, node, key_field=allowed_loms[key])
        return Ylist(_data, node)
    else:
        return x


def parse_yaml_with_line_info(raw_cwl: str, convert_to_lam=False):
    return _recurse_extract_meta(yaml.load(raw_cwl, YSafeLineLoader), convert_to_lam=convert_to_lam)


def lookup(doc: Union[Ydict, Ylist], path: List[Union[str, int]]):
    if len(path) > 1:
        return lookup(doc[path[0]], path[1:])
    else:
        return doc[path[0]]


def reverse_lookup(line, col, doc: Union[Ydict, Ylist], path: List[Union[str, int]]=[]):
    """Not as expensive as you'd think ... """
    values = doc.items() if isinstance(doc, dict) else enumerate(doc)
    for k, v in values:
        if v.start.line <= line <= v.end.line:
            if v.start.line != v.end.line or v.start.column <= col <= v.end.column:
                if not isinstance(v, Ydict) and not isinstance(v, Ylist):
                    return path + [k], v
                else:
                    return reverse_lookup(line, col, v, path + [k])


def coordinates(v):
    return (v.start.line, v.start.column), (v.end.line, v.end.column)