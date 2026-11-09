import ast
import os
import sys
import tokenize

ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_LINE = 100
MAX_MODULE = 500
MAX_README = 80
GENERATED = ("map/",)
BAD_DASHES = ("\u2014", "\u2013")
CHANNELS = ("stable", "dev")


def walk(root, suffix):
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("dist", "__pycache__")]
        for n in names:
            if n.endswith(suffix):
                yield os.path.join(base, n)


def rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


def check_python(path):
    errors = []
    name = rel(path)
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines()

    with open(path, "rb") as f:
        for tok in tokenize.tokenize(f.readline):
            if tok.type == tokenize.COMMENT:
                errors.append("%s:%d: comment" % (name, tok.start[0]))

    for i, line in enumerate(lines, 1):
        if len(line) > MAX_LINE:
            errors.append("%s:%d: line is %d characters" % (name, i, len(line)))
        if line != line.rstrip():
            errors.append("%s:%d: trailing whitespace" % (name, i))
        for dash in BAD_DASHES:
            if dash in line:
                errors.append("%s:%d: typographic dash" % (name, i))

    if not name.startswith(GENERATED) and len(lines) > MAX_MODULE:
        errors.append("%s: %d lines, limit is %d" % (name, len(lines), MAX_MODULE))

    return errors


def check_text(path):
    errors = []
    name = rel(path)
    lines = open(path, encoding="utf-8").read().splitlines()
    for i, line in enumerate(lines, 1):
        for dash in BAD_DASHES:
            if dash in line:
                errors.append("%s:%d: typographic dash" % (name, i))
        if line != line.rstrip():
            errors.append("%s:%d: trailing whitespace" % (name, i))
    if name == "README.md" and len(lines) > MAX_README:
        errors.append("%s: %d lines, limit is %d" % (name, len(lines), MAX_README))
    return errors


def check_nor_policy():
    errors = []
    specs = os.path.join(ROOT, "firmware", "specs")
    if not os.path.isdir(specs):
        return errors
    for name in sorted(os.listdir(specs)):
        if not name.endswith(".py") or name == "__init__.py":
            continue
        path = os.path.join(specs, name)
        tree = ast.parse(open(path, encoding="utf-8").read())
        channel = None
        arbitrary = False
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "CHANNEL":
                    channel = getattr(node.value, "value", None)
                elif target.id == "ARBITRARY_CALL":
                    arbitrary = bool(getattr(node.value, "value", False))
        if channel not in CHANNELS:
            errors.append("%s: CHANNEL must be one of %s" % (name, ", ".join(CHANNELS)))
        if arbitrary and channel == "stable":
            errors.append("%s: a stable spec may not allow arbitrary calls" % name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "BLOCK_REQUEST":
                continue
            first = node.args[0] if node.args else None
            if not isinstance(first, ast.Constant) or first.value != 0:
                errors.append("%s: BLOCK_REQUEST must be called with channel 0" % name)
    return errors


def main():
    errors = []
    for path in walk(ROOT, ".py"):
        errors += check_python(path)
    for path in [os.path.join(ROOT, "README.md")] + list(walk(os.path.join(ROOT, "docs"), ".md")):
        if os.path.exists(path):
            errors += check_text(path)
    errors += check_nor_policy()

    if errors:
        for e in errors:
            print(e)
        print("%d problem(s)" % len(errors))
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
