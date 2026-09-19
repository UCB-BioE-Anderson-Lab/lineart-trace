"""Every capability record in `sharables/` is true.

A record is this repository's public claim that a capability exists, can be reached by a
named command, and behaves a stated way. Nothing about writing one makes any of that so, and
a record that has drifted is worse than none: it is the first thing a reader tries, and it
fails in a way that looks like their mistake.

So this runs them. Deliberately self-contained -- it resolves the entry through
`c11-connector.json` and invokes it directly, rather than through whichever C11 installation
happens to be mounting this repository. A test that needs somebody else's checkout to pass is
a test that stops running the moment this repository is read from anywhere else.

Compared on stripped text: trailing whitespace is not behaviour.
"""
import json
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONNECTOR = json.load(open(os.path.join(ROOT, "c11-connector.json")))
STORE = os.path.join(ROOT, CONNECTOR.get("sharables", "sharables"))
BIN = os.path.join(ROOT, CONNECTOR.get("bin", "bin"))

# WHAT A RECORD MUST CARRY IS A FUNCTION OF ITS TYPE, not a constant. It was a constant here
# while every record in the store was a function, and the first schema record written broke
# four tests by being exactly what a schema is: something that HOLDS a definition and does not
# run. `entry` is not merely absent on a schema, it is forbidden -- a record that both holds
# and runs is the ambiguity `type` exists to remove.
REQUIRED = ("schema", "id", "type", "description", "phrases", "noun", "verb")
BY_TYPE = {"function": ("entry",), "schema": ("definition",), "datum": (), "view": ("binds",)}
RUNS = ("function",)


def records():
    """Every record in the store, as (id, dict). Walked, never listed by hand.

    A hand-maintained list of what to check goes stale the first time somebody adds a file,
    silently, because nothing compares it to the tree.
    """
    out = []
    for dirpath, _dirs, files in os.walk(STORE):
        for f in sorted(files):
            if f.endswith(".json"):
                path = os.path.join(dirpath, f)
                out.append((os.path.relpath(path, STORE)[:-5], json.load(open(path))))
    return sorted(out)


ALL = records()


def test_the_store_is_not_empty():
    """absence-ok: an empty store and a store nobody checked look identical otherwise."""
    assert ALL, f"no records found under {STORE} -- a world with no records cannot be mounted"


@pytest.mark.parametrize("rid,rec", ALL, ids=[r[0] for r in ALL])
def test_record_is_well_formed(rid, rec):
    kind = rec.get("type", "function")
    assert kind in BY_TYPE, f"{rid}: {kind!r} is not one of {sorted(BY_TYPE)}"
    missing = [f for f in REQUIRED + BY_TYPE[kind] if not rec.get(f)]
    assert not missing, f"{rid} is a {kind} and is missing {missing}"
    assert rec["id"] == rid, f"{rid}: the id must be its path in the store, not {rec['id']!r}"
    if kind not in RUNS:
        assert not rec.get("entry"), \
            f"{rid}: a {kind} does not run, so it may not name an entry"


@pytest.mark.parametrize("rid,rec", ALL, ids=[r[0] for r in ALL])
def test_entry_exists_and_requires_resolve(rid, rec):
    """A record naming an entry that cannot be invoked describes something that is not there."""
    if rec.get("type", "function") not in RUNS:
        for req in rec.get("requires", []):
            assert os.path.exists(os.path.join(ROOT, req["path"])), \
                f"{rid}: requires {req['path']} which is not here"
        return
    cmd = rec["entry"].split()[0]
    assert os.access(os.path.join(BIN, cmd), os.X_OK), \
        f"{rid}: entry {cmd!r} is not an executable in {CONNECTOR.get('bin', 'bin')}/"
    for req in rec.get("requires", []):
        assert os.path.exists(os.path.join(ROOT, req["path"])), \
            f"{rid}: requires {req['path']} which is not here"


EXAMPLES = [(rid, n, e) for rid, rec in ALL for n, e in enumerate(rec.get("examples", []))]


@pytest.mark.parametrize("rid,n,ex", EXAMPLES, ids=[f"{r}[{n}]" for r, n, _ in EXAMPLES])
def test_example_reproduces(rid, n, ex):
    rec = dict(ALL)[rid]
    argv = rec["entry"].split() + list(ex["input"])
    argv[0] = os.path.join(BIN, argv[0])
    r = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=600)
    # stdout when there is any, else stderr -- a tool whose result is a document on stdout
    # reports on stderr, and both are the answer the reader sees.
    got = (r.stdout or "").strip() or (r.stderr or "").strip()
    assert got == ex["output"].strip(), \
        f"{rid} example {n} no longer reproduces:\n  want {ex['output']!r}\n  got  {got!r}"
    assert r.returncode == ex.get("exit", 0), \
        f"{rid} example {n} exited {r.returncode}, record says {ex.get('exit', 0)}"


REFERENCES = [(rid, f, rec[f]) for rid, rec in ALL
              for f in ("accepts", "produces", "code_verification", "conforms", "superclass")
              if rec.get(f)]


@pytest.mark.parametrize("rid,field,ref", REFERENCES,
                         ids=[f"{r}.{f}" for r, f, _ in REFERENCES])
def test_declared_reference_resolves(rid, field, ref):
    """A declaration naming a record that is not here is a claim nobody can check.

    The kernel refuses one at write time. This repository is also a store somebody can read
    without any kernel at all -- an unmounted clone is a supported state -- so the same rule
    is checked here, against these files, with nothing installed.
    """
    want = "function" if field == "code_verification" else "schema"
    store = dict(ALL)
    assert ref in store, f"{rid}: {field} names {ref!r}, which is not a record in this store"
    got = store[ref].get("type", "function")
    assert got == want, f"{rid}: {field} names {ref!r}, which is a {got}, not a {want}"


@pytest.mark.parametrize("rid,rec", [(r, c) for r, c in ALL
                                     if c.get("type") == "schema"],
                         ids=[r for r, c in ALL if c.get("type") == "schema"])
def test_schema_definition_is_usable(rid, rec):
    """A schema carrying a definition nothing can compile is the third way of not knowing."""
    jsonschema = pytest.importorskip("jsonschema")
    d = rec.get("definition")
    assert isinstance(d, dict) and d, f"{rid}: carries no usable definition"
    jsonschema.Draft202012Validator.check_schema(d)
