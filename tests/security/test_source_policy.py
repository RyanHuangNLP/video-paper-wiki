"""Import-policy accuracy without executing the supplied source snippets."""
import pytest

from tests.security._source_policy import assert_no_network_imports


@pytest.mark.parametrize("source", [
    'address_requests = []',
    'document = {"address_requests": [], "requests": "schema field"}',
    '# import requests\n"""urllib.request and http.client are forbidden clients."""',
    'requests = "literal data, not an import"',
    'def address_requests(requests):\n    return requests',
    'from urllib.parse import urlparse',
    'import urllib.parse as parsing',
    'from importlib import resources',
    'import importlib.resources as resources',
    'from requests_metadata import description',
    'from local_package import address_requests',
    'import http\nfrom http import HTTPStatus',
    'import json as j\nloads = j.loads\nloads("{}")',
    'import importlib as a\na = a.resources',
    'literal = "__import__(name) or importlib.import_module(name)"',
])
def test_legitimate_fields_comments_and_safe_imports(source):
    assert_no_network_imports(source)


@pytest.mark.parametrize("module", ["requests", "httpx", "urllib.request", "http.client", "aiohttp"])
@pytest.mark.parametrize("form", ["import {module}", "import {module} as client", "import {module}.submodule as client", "from {module} import Client as C"])
def test_forbidden_import_families_and_aliases(module, form):
    with pytest.raises(AssertionError, match="forbidden network import"):
        assert_no_network_imports(form.format(module=module), filename="agent.py")


@pytest.mark.parametrize("source", [
    'from urllib import request',
    'from urllib import request as client',
    'from http import client as transport',
    'from urllib.request import urlopen as open_url',
    'if False:\n    import requests',
    'def later():\n    from http import client',
    'import json, requests as client',
])
def test_parent_imports_and_nested_unexecuted_code_are_scanned(source):
    with pytest.raises(AssertionError, match="agent.py:"):
        assert_no_network_imports(source, filename="agent.py")


@pytest.mark.parametrize("source", [
    '__import__("json")',
    '__import__("req" + "uests")',
    '__import__(module_name)',
    'loader = __import__\nloader(name)',
    'import builtins as b\nb.__import__(name)',
    'from builtins import __import__ as loader\nloader(name)',
    'import importlib\nimportlib.import_module("json")',
    'import importlib as il\nil.import_module(name)',
    'from importlib import import_module as load\nload(name)',
    'import importlib\nloader = importlib.import_module\nloader(name)',
    'import importlib as il\nalias = il\nalias.import_module(name)',
    'import importlib as il\n(alias,) = (il,)\nalias.import_module(name)',
    'import importlib as il\n[alias, other] = [il, None]\nalias.import_module(name)',
    'import importlib as il\na = b\nb = il\na.import_module(name)',
    'import importlib as il\nalias: object = il\nalias.import_module(name)',
    'import importlib as il\n(alias := il).import_module(name)',
    'import importlib as il\ngetattr(il, "import_module")(name)',
    'import importlib as il\ngetattr(il, attribute_name)(name)',
    'import builtins\nbuiltins.__dict__[key](name)',
    'import importlib as il\ngetter = getattr\ngetter(il, key)(name)',
    'import builtins as b\nimport importlib as il\nb.getattr(il, key)(name)',
    '__builtins__.__import__(name)',
    '__builtins__["__import__"](name)',
    'b = __builtins__\nb[key](name)',
    'import builtins as b\nvars(b)["__import__"](name)',
    'import builtins as b\nnamespace = vars\nnamespace(b)[key](name)',
    'import builtins as b\nb.vars(b)[key](name)',
    'import importlib\nimportlib.__import__(name)',
    'import importlib as il\nloader = il.__import__\nloader(name)',
    'from importlib import __import__ as loader\nloader(name)',
    'from importlib import *',
    'from urllib import *',
])
def test_dynamic_import_entrypoints_fail_closed_for_any_target(source):
    with pytest.raises(AssertionError):
        assert_no_network_imports(source)


def test_invalid_python_cannot_silently_pass_policy():
    with pytest.raises(AssertionError, match="cannot be parsed"):
        assert_no_network_imports("import (", filename="broken.py")
