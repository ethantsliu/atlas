import ast
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "pipeline"
SOURCE_ROOTS = (
    ROOT / ".github/workflows",
    ROOT / "db",
    ROOT / "data/source",
    ROOT / "data/reviewed/audits",
    ROOT / "docs",
    ROOT / "pipeline",
    ROOT / "schemas",
    ROOT / "tests",
    ROOT / "web/e2e",
    ROOT / "web/src",
)
SOURCE_SUFFIXES = {".css", ".json", ".md", ".py", ".ts", ".tsx", ".yaml", ".yml"}
SOURCE_FILES = (
    ROOT / "Makefile",
    ROOT / "README.md",
    ROOT / "dev.txt",
    ROOT / "requirements.txt",
    ROOT / "pyproject.toml",
)
NAME_SUFFIXES = (".schema", ".spec", ".test")
CAMEL_PART = re.compile(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|\d+")
MODULE_LINE_LIMIT = 600
FUNCTION_LINE_LIMIT = 180


def name_parts(name: str) -> tuple[str, ...]:
    """Split snake and camel names while preserving common compact acronyms."""
    parts: list[str] = []
    for segment in re.split(r"[_\-\s]+", name.strip("_")):
        if not segment:
            continue
        if segment.islower() or segment.isupper():
            parts.append(segment)
        else:
            parts.extend(CAMEL_PART.findall(segment))
    return tuple(part for part in parts if not part.isdigit())


def source_paths() -> tuple[Path, ...]:
    """Return authored source paths, excluding generated cache directories."""
    paths: list[Path] = list(SOURCE_FILES)
    for root in SOURCE_ROOTS:
        paths.extend(
            path
            for path in root.rglob("*")
            if "__pycache__" not in path.parts
            and (path.is_dir() or path.suffix in SOURCE_SUFFIXES)
        )
    return tuple(paths)


def name_stem(path: Path) -> str:
    """Remove only conventional test and schema markers from a source name."""
    name = path.name if path.is_dir() else path.name.removesuffix(path.suffix)
    if name.startswith("test_"):
        name = name.removeprefix("test_")
    for suffix in NAME_SUFFIXES:
        name = name.removesuffix(suffix)
    return name


def pipeline_import_graph() -> dict[str, set[str]]:
    """Return internal pipeline dependencies without importing command modules."""
    modules = {path.stem: path for path in PIPELINE.glob("*.py")}
    graph = {name: set() for name in modules}

    for name, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = {node.module.split(".")[0]}
            else:
                continue
            graph[name].update(imported & modules.keys())

    return graph


class ArchitectureTests(unittest.TestCase):
    def test_source_names(self) -> None:
        violations = {
            str(path.relative_to(ROOT)): name_parts(name_stem(path))
            for path in source_paths()
            if len(name_parts(name_stem(path))) > 1
        }
        self.assertEqual(violations, {})

    def test_function_names(self) -> None:
        violations: dict[str, tuple[str, ...]] = {}
        for path in (*PIPELINE.glob("*.py"), *ROOT.glob("tests/*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                parts = name_parts(node.name)
                if len(parts) > 3:
                    key = f"{path.relative_to(ROOT)}:{node.lineno}:{node.name}"
                    violations[key] = parts
        self.assertEqual(violations, {})

    def test_module_sizes(self) -> None:
        paths = [
            *PIPELINE.glob("*.py"),
            *(
                path
                for path in (ROOT / "web/src").rglob("*")
                if path.suffix in {".css", ".ts", ".tsx"} and ".test." not in path.name
            ),
        ]
        violations = {
            str(path.relative_to(ROOT)): len(
                path.read_text(encoding="utf-8").splitlines()
            )
            for path in paths
            if len(path.read_text(encoding="utf-8").splitlines()) > MODULE_LINE_LIMIT
        }
        self.assertEqual(violations, {})

    def test_function_sizes(self) -> None:
        violations: dict[str, int] = {}
        for path in PIPELINE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                line_count = (node.end_lineno or node.lineno) - node.lineno + 1
                if line_count > FUNCTION_LINE_LIMIT:
                    key = f"{path.relative_to(ROOT)}:{node.lineno}:{node.name}"
                    violations[key] = line_count
        self.assertEqual(violations, {})

    def test_pipeline_cycles(self) -> None:
        graph = pipeline_import_graph()

        try:
            ordered = tuple(TopologicalSorter(graph).static_order())
        except CycleError as error:
            self.fail(f"Pipeline dependency cycle: {error.args[1]}")

        self.assertEqual(set(ordered), set(graph))


if __name__ == "__main__":
    unittest.main()
