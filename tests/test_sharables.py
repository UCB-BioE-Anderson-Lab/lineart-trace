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

REQUIRED = ("schema", "id", "type", "description", "phrases", "noun", "verb", "entry")


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
    missing = [f for f in REQUIRED if not rec.get(f)]
    assert not missing, f"{rid} is missing {missing}"
    assert rec["id"] == rid, f"{rid}: the id must be its path in the store, not {rec['id']!r}"


@pytest.mark.parametrize("rid,rec", ALL, ids=[r[0] for r in ALL])
def test_entry_exists_and_requires_resolve(rid, rec):
    """A record naming an entry that cannot be invoked describes something that is not there."""
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
