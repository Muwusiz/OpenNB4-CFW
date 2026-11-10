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


def module_values(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except Exception:
                    pass
    return values, tree


def check_policy():
    errors = []
    features_dir = os.path.join(ROOT, "firmware", "features")
    profiles_dir = os.path.join(ROOT, "firmware", "profiles")
    channels = {}

    if os.path.isdir(features_dir):
        for name in sorted(os.listdir(features_dir)):
            if not name.endswith(".py") or name == "__init__.py":
                continue
            path = os.path.join(features_dir, name)
            values, tree = module_values(path)
            channel = values.get("CHANNEL")
            if channel not in CHANNELS:
                errors.append("%s: CHANNEL must be one of %s" % (name, ", ".join(CHANNELS)))
            channels[name[:-3]] = channel
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Name) or node.func.id != "BLOCK_REQUEST":
                    continue
                first = node.args[0] if node.args else None
                if not isinstance(first, ast.Constant) or first.value != 0:
                    errors.append("%s: BLOCK_REQUEST must be called with channel 0" % name)

    if os.path.isdir(profiles_dir):
        for name in sorted(os.listdir(profiles_dir)):
            if not name.endswith(".py") or name == "__init__.py":
                continue
            path = os.path.join(profiles_dir, name)
            values, _ = module_values(path)
            channel = values.get("CHANNEL")
            if channel not in CHANNELS:
                errors.append("%s: CHANNEL must be one of %s" % (name, ", ".join(CHANNELS)))
            if channel == "stable":
                for feature in values.get("FEATURES", []):
                    if channels.get(feature) == "dev":
                        errors.append("%s: stable profile includes dev feature %s"
                                      % (name, feature))

    return errors


def main():
    errors = []
    for path in walk(ROOT, ".py"):
        errors += check_python(path)
    for path in [os.path.join(ROOT, "README.md")] + list(walk(os.path.join(ROOT, "docs"), ".md")):
        if os.path.exists(path):
            errors += check_text(path)
    errors += check_policy()

    if errors:
        for e in errors:
            print(e)
        print("%d problem(s)" % len(errors))
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
