# ─────────────────────────────────────────────────────────────────────
# Code Knowledge Graph — AST-based structural context for PRISM
# ─────────────────────────────────────────────────────────────────────
#
# WHY AST-BASED CODE KNOWLEDGE GRAPH > MICROSOFT GRAPHRAG FOR CODE REVIEW
# ========================================================================
#
# Microsoft GraphRAG builds a general-purpose entity-relationship graph
# from unstructured text using LLM extraction, community detection, and
# multi-hop summarisation.  While powerful for open-domain knowledge
# corpora, it is a poor fit for *code review* for several reasons:
#
# 1. REDUNDANT LLM CALLS: GraphRAG extracts entities via LLM prompts,
#    but source code already *has* a precise, deterministic structure
#    (the AST).  Paying for LLM extraction of what `ast.parse()` gives
#    us for free is wasteful and introduces hallucination risk.
#
# 2. LOSSY ABSTRACTION: GraphRAG summarises communities of entities into
#    natural-language descriptions, discarding the exact call chains,
#    parameter types, and line numbers a reviewer needs.
#
# 3. LATENCY: Building the full GraphRAG pipeline (extract → cluster →
#    summarise → embed) takes minutes per repo.  AST parsing of a
#    10 000-file repo completes in seconds.
#
# 4. MISSING CODE SEMANTICS: GraphRAG has no concept of call graphs,
#    class hierarchies, or import chains.  An AST-based graph captures
#    these first-class, enabling queries like "who calls this function?"
#    and "what classes inherit from this base?" that are impossible with
#    a text-entity graph.
#
# 5. DETERMINISM: AST parsing is deterministic — the same code always
#    produces the same graph.  GraphRAG extraction varies across runs,
#    making CI/CD integration unreliable.
#
# Our approach: parse every supported source file into an AST, extract
# function definitions, class definitions, call expressions, and import
# statements, and assemble them into a lightweight in-memory graph that
# the HybridCodeRetriever can query in O(1) for structural context.
# ─────────────────────────────────────────────────────────────────────

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config import MAX_CONTEXT_TOKENS, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

# ── Tiktoken lazy import ─────────────────────────────────────────────
# tiktoken is listed in requirements.txt; import at module level but
# defer the encoder creation so import-time cost is near zero.

try:
    import tiktoken

    _ENCODER = tiktoken.encoding_for_model("gpt-4")
except Exception:  # pragma: no cover — CI may lack tiktoken data files
    tiktoken = None  # type: ignore[assignment]
    _ENCODER = None
    logger.warning(
        "tiktoken unavailable — token counting will use "
        "character-based approximation (4 chars ≈ 1 token)"
    )

# ── Tree-sitter lazy import ──────────────────────────────────────────
# Tree-sitter and its language packs are optional dependencies.  If any
# are missing we fall back to regex-only extraction for non-Python files.

_TS_AVAILABLE = False
_TS_LANGUAGES: dict[str, object] = {}

try:
    import tree_sitter  # type: ignore[import-untyped]

    _LANG_MODULES: dict[str, str] = {
        ".js": "tree_sitter_javascript",
        ".jsx": "tree_sitter_javascript",
        ".ts": "tree_sitter_typescript",
        ".tsx": "tree_sitter_typescript",
        ".go": "tree_sitter_go",
        ".rs": "tree_sitter_rust",
    }

    for ext, mod_name in _LANG_MODULES.items():
        try:
            mod = __import__(mod_name)
            # tree-sitter ≥ 0.22 exposes a language() callable
            lang_fn = getattr(mod, "language", None)
            if lang_fn is None:
                continue
            # For TypeScript we may need tsx vs ts sub-languages
            if ext in (".tsx",) and hasattr(mod, "language_tsx"):
                _TS_LANGUAGES[ext] = tree_sitter.Language(
                    mod.language_tsx()
                )
            elif ext in (".ts",) and hasattr(mod, "language_typescript"):
                _TS_LANGUAGES[ext] = tree_sitter.Language(
                    mod.language_typescript()
                )
            else:
                _TS_LANGUAGES[ext] = tree_sitter.Language(lang_fn())
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "tree-sitter language pack for %s unavailable: %s",
                ext,
                exc,
            )

    _TS_AVAILABLE = bool(_TS_LANGUAGES)
    if _TS_AVAILABLE:
        logger.debug(
            "tree-sitter enabled for extensions: %s",
            ", ".join(sorted(_TS_LANGUAGES)),
        )
except ImportError:
    logger.info(
        "tree-sitter not installed — non-Python files will use "
        "regex-based symbol extraction only"
    )


# ── Parseable extensions ─────────────────────────────────────────────
# We only attempt AST parsing on extensions we have parsers for.
_PYTHON_EXTS: frozenset[str] = frozenset({".py"})
_TS_EXTS: frozenset[str] = frozenset(_TS_LANGUAGES.keys())
_PARSEABLE_EXTS: frozenset[str] = _PYTHON_EXTS | _TS_EXTS

# ── Directories to always skip ───────────────────────────────────────
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        "node_modules",
        "venv",
        ".venv",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "vendor",
        "target",
    }
)


# =====================================================================
# Data classes
# =====================================================================


@dataclass(slots=True)
class FunctionNode:
    """A single function (or method) definition in the codebase."""

    name: str
    filepath: str
    line_start: int
    line_end: int
    docstring: Optional[str] = None
    params: list[str] = field(default_factory=list)
    return_type: Optional[str] = None


@dataclass(slots=True)
class ClassNode:
    """A class definition and its immediate members."""

    name: str
    filepath: str
    bases: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    line_start: int = 0
    line_end: int = 0


# =====================================================================
# Token counting helper
# =====================================================================


def _count_tokens(text: str) -> int:
    """Count tokens using tiktoken, or approximate from char length."""
    if _ENCODER is not None:
        return len(_ENCODER.encode(text, disallowed_special=()))
    # Rough approximation: 1 token ≈ 4 characters
    return len(text) // 4


# =====================================================================
# CodeGraph
# =====================================================================


class CodeGraph:
    """AST-based code knowledge graph for structural context retrieval.

    Parses all supported source files under a repository root, building
    in-memory maps of function definitions, call edges, class hierarchy,
    import relationships, and a flat symbol index.  These maps power fast
    structural context lookups used by the HybridCodeRetriever.
    """

    def __init__(self) -> None:
        """Initialise empty graph maps."""
        # key: "filepath::function_name" → FunctionNode
        self.function_defs: dict[str, FunctionNode] = {}

        # key: "filepath::caller" → set of "filepath::callee"
        self.call_graph: dict[str, set[str]] = {}

        # key: "filepath::ClassName" → ClassNode
        self.class_hierarchy: dict[str, ClassNode] = {}

        # key: filepath → set of filepaths it imports from
        self.import_graph: dict[str, set[str]] = {}

        # key: bare symbol name → "filepath::name" (last-write wins)
        self.symbol_index: dict[str, str] = {}

        # Keep track of repo root for source-reading later
        self._repo_path: Optional[Path] = None

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def build(self, repo_path: Path) -> None:
        """Walk all supported files, parse ASTs, and populate maps.

        For *.py* files the built-in ``ast`` module is used.  For
        *.js/.jsx/.ts/.tsx/.go/.rs* files tree-sitter is used when
        available; otherwise those files are silently skipped.

        Files that fail to parse are logged and skipped.
        """
        self._repo_path = repo_path.resolve()
        n_functions = 0
        n_classes = 0
        n_call_edges = 0

        for file_path in self._repo_path.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix not in SUPPORTED_EXTENSIONS:
                continue
            if file_path.suffix not in _PARSEABLE_EXTS:
                continue
            if any(part in _SKIP_DIRS for part in file_path.parts):
                continue

            relative = file_path.relative_to(self._repo_path).as_posix()

            try:
                source = file_path.read_text(
                    encoding="utf-8", errors="ignore"
                )
            except OSError as exc:
                logger.warning("Cannot read %s: %s", relative, exc)
                continue

            if not source.strip():
                continue

            if file_path.suffix in _PYTHON_EXTS:
                fns, cls, edges, imports = self._parse_python(
                    source, relative
                )
            elif file_path.suffix in _TS_EXTS:
                fns, cls, edges, imports = self._parse_tree_sitter(
                    source, relative, file_path.suffix
                )
            else:
                continue

            # Merge into global maps
            for key, node in fns.items():
                self.function_defs[key] = node
                self.symbol_index[node.name] = key
                n_functions += 1

            for key, node in cls.items():
                self.class_hierarchy[key] = node
                self.symbol_index[node.name] = key
                n_classes += 1

            for caller, callees in edges.items():
                existing = self.call_graph.setdefault(caller, set())
                existing.update(callees)
                n_call_edges += len(callees)

            if imports:
                self.import_graph[relative] = imports

        logger.info(
            "Built code graph: %d functions, %d classes, %d call edges",
            n_functions,
            n_classes,
            n_call_edges,
        )

    def get_structural_context(
        self,
        changed_files: list[str],
        changed_symbols: list[str],
    ) -> str:
        """Return prioritised structural context for changed code.

        Priority order (highest first):
        1. DIRECT CALLERS   — functions calling any changed symbol
        2. CLASS CONTEXT    — class info when a method was changed
        3. DIRECT CALLEES   — functions called *by* changed symbols
        4. IMPORT CHAIN     — files importing the changed files

        Output is capped at ``MAX_CONTEXT_TOKENS`` tokens.
        """
        sections: list[str] = []
        budget = MAX_CONTEXT_TOKENS
        changed_files_set = set(changed_files)

        # Resolve changed symbols to qualified keys
        qualified_symbols: list[str] = []
        for sym in changed_symbols:
            if "::" in sym:
                qualified_symbols.append(sym)
            elif sym in self.symbol_index:
                qualified_symbols.append(self.symbol_index[sym])

        # ── 1. DIRECT CALLERS (highest priority) ─────────────────
        caller_section = self._build_callers_section(qualified_symbols)
        if caller_section:
            tokens = _count_tokens(caller_section)
            if tokens <= budget:
                sections.append(caller_section)
                budget -= tokens

        # ── 2. CLASS CONTEXT ─────────────────────────────────────
        class_section = self._build_class_section(
            changed_symbols, changed_files
        )
        if class_section:
            tokens = _count_tokens(class_section)
            if tokens <= budget:
                sections.append(class_section)
                budget -= tokens

        # ── 3. DIRECT CALLEES ────────────────────────────────────
        callee_section = self._build_callees_section(qualified_symbols)
        if callee_section:
            tokens = _count_tokens(callee_section)
            if tokens <= budget:
                sections.append(callee_section)
                budget -= tokens

        # ── 4. IMPORT CHAIN (lowest priority) ────────────────────
        import_section = self._build_import_section(changed_files_set)
        if import_section:
            tokens = _count_tokens(import_section)
            if tokens <= budget:
                sections.append(import_section)
                budget -= tokens

        return "\n\n".join(sections)

    @staticmethod
    def extract_changed_symbols(diff_patch: str) -> list[str]:
        """Extract function/class names from unified diff +/- lines.

        Parses added and removed lines for symbol definition keywords
        across Python, JavaScript/TypeScript, Go, and Rust.
        """
        symbols: list[str] = []
        seen: set[str] = set()

        # Patterns that capture bare symbol names from definition lines
        patterns: list[re.Pattern[str]] = [
            # Python: def foo(...) / async def foo(...)
            re.compile(
                r"^[+-]\s*(?:async\s+)?def\s+([A-Za-z_]\w*)"
            ),
            # Python: class Foo(...):
            re.compile(r"^[+-]\s*class\s+([A-Za-z_]\w*)"),
            # JS/TS: function foo(...)
            re.compile(r"^[+-]\s*(?:export\s+)?function\s+([A-Za-z_]\w*)"),
            # JS/TS: const foo = / let foo = / var foo =
            re.compile(
                r"^[+-]\s*(?:export\s+)?(?:const|let|var)\s+"
                r"([A-Za-z_]\w*)\s*="
            ),
            # JS/TS: export default class/function
            re.compile(
                r"^[+-]\s*export\s+default\s+"
                r"(?:class|function)\s+([A-Za-z_]\w*)"
            ),
            # Go: func Foo(...) or func (r *Recv) Foo(...)
            re.compile(
                r"^[+-]\s*func\s+(?:\([^)]*\)\s+)?([A-Za-z_]\w*)"
            ),
            # Rust: fn foo(...) / pub fn foo(...)
            re.compile(
                r"^[+-]\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)"
            ),
            # Rust: struct Foo / pub struct Foo
            re.compile(
                r"^[+-]\s*(?:pub\s+)?struct\s+([A-Za-z_]\w*)"
            ),
            # Rust: impl Foo
            re.compile(r"^[+-]\s*impl\s+([A-Za-z_]\w*)"),
        ]

        for line in diff_patch.splitlines():
            if not line.startswith(("+", "-")):
                continue
            # Skip diff headers
            if line.startswith(("+++", "---")):
                continue
            for pattern in patterns:
                match = pattern.match(line)
                if match:
                    name = match.group(1)
                    if name not in seen:
                        seen.add(name)
                        symbols.append(name)
                    break  # One match per line is enough

        return symbols

    # -----------------------------------------------------------------
    # Section builders (private)
    # -----------------------------------------------------------------

    def _build_callers_section(
        self, qualified_symbols: list[str]
    ) -> str:
        """Build the CALLERS section — full source of callers."""
        blocks: list[str] = []

        for qsym in qualified_symbols:
            callers = self._reverse_call_lookup(qsym)
            if not callers:
                continue

            sym_label = qsym.split("::")[-1] if "::" in qsym else qsym
            parts: list[str] = [f"=== CALLERS OF {sym_label} ==="]

            for caller_key in sorted(callers):
                fn_node = self.function_defs.get(caller_key)
                if fn_node is None:
                    continue
                source = self._read_source_lines(
                    fn_node.filepath, fn_node.line_start, fn_node.line_end
                )
                parts.append(
                    f"[{fn_node.filepath}:{fn_node.line_start}"
                    f"-{fn_node.line_end}]"
                )
                parts.append(source)

            if len(parts) > 1:
                blocks.append("\n".join(parts))

        return "\n\n".join(blocks)

    def _build_callees_section(
        self, qualified_symbols: list[str]
    ) -> str:
        """Build the CALLEES section — signature + docstring only."""
        blocks: list[str] = []

        for qsym in qualified_symbols:
            callees = self.call_graph.get(qsym, set())
            if not callees:
                continue

            sym_label = qsym.split("::")[-1] if "::" in qsym else qsym
            parts: list[str] = [f"=== CALLEES OF {sym_label} ==="]

            for callee_key in sorted(callees):
                fn_node = self.function_defs.get(callee_key)
                if fn_node is None:
                    continue
                sig = self._format_signature(fn_node)
                parts.append(
                    f"[{fn_node.filepath}:{fn_node.line_start}"
                    f"-{fn_node.line_end}]"
                )
                parts.append(sig)

            if len(parts) > 1:
                blocks.append("\n".join(parts))

        return "\n\n".join(blocks)

    def _build_class_section(
        self,
        changed_symbols: list[str],
        changed_files: list[str],
    ) -> str:
        """Build CLASS CONTEXT section for symbols that are methods."""
        blocks: list[str] = []
        seen_classes: set[str] = set()

        for cls_key, cls_node in self.class_hierarchy.items():
            if cls_key in seen_classes:
                continue

            # Include if the class itself was changed
            is_relevant = cls_node.name in changed_symbols
            # Include if any of its methods were changed
            if not is_relevant:
                is_relevant = any(
                    m in changed_symbols for m in cls_node.methods
                )
            # Include if the class is in a changed file
            if not is_relevant:
                is_relevant = cls_node.filepath in changed_files

            if not is_relevant:
                continue

            seen_classes.add(cls_key)
            source = self._read_source_lines(
                cls_node.filepath,
                cls_node.line_start,
                cls_node.line_end,
            )
            parts: list[str] = [
                "=== CLASS CONTEXT ===",
                f"[{cls_node.filepath}:{cls_node.line_start}"
                f"-{cls_node.line_end}]",
                f"class {cls_node.name}"
                + (
                    f"({', '.join(cls_node.bases)})"
                    if cls_node.bases
                    else ""
                ),
                f"  methods: {cls_node.methods}",
                source,
            ]
            blocks.append("\n".join(parts))

        return "\n\n".join(blocks)

    def _build_import_section(
        self, changed_files: set[str]
    ) -> str:
        """Build IMPORT CHAIN section — files importing changed files."""
        blocks: list[str] = []

        for changed_file in sorted(changed_files):
            importers: list[str] = []
            for filepath, imports in self.import_graph.items():
                if changed_file in imports:
                    importers.append(filepath)

            if importers:
                parts = [f"=== FILES IMPORTING {changed_file} ==="]
                for imp in sorted(importers):
                    parts.append(f"  - {imp}")
                blocks.append("\n".join(parts))

        return "\n\n".join(blocks)

    # -----------------------------------------------------------------
    # Reverse call-graph lookup
    # -----------------------------------------------------------------

    def _reverse_call_lookup(self, target: str) -> set[str]:
        """Find all function keys that call *target*."""
        callers: set[str] = set()
        # Also check bare name matches for cross-file calls
        target_bare = target.split("::")[-1] if "::" in target else target

        for caller_key, callees in self.call_graph.items():
            if target in callees:
                callers.add(caller_key)
                continue
            # Check if any callee ends with the bare target name
            for callee in callees:
                callee_bare = (
                    callee.split("::")[-1] if "::" in callee else callee
                )
                if callee_bare == target_bare:
                    callers.add(caller_key)
                    break

        return callers

    # -----------------------------------------------------------------
    # Source reading helpers
    # -----------------------------------------------------------------

    def _read_source_lines(
        self, filepath: str, line_start: int, line_end: int
    ) -> str:
        """Read specific line range from a file under the repo root."""
        if self._repo_path is None:
            return ""
        full_path = self._repo_path / filepath
        try:
            lines = full_path.read_text(
                encoding="utf-8", errors="ignore"
            ).splitlines()
            # line numbers are 1-indexed
            selected = lines[max(0, line_start - 1) : line_end]
            return "\n".join(selected)
        except OSError as exc:
            logger.debug("Cannot read %s: %s", filepath, exc)
            return ""

    @staticmethod
    def _format_signature(fn: FunctionNode) -> str:
        """Format a function node as signature + docstring."""
        params_str = ", ".join(fn.params)
        ret = f" -> {fn.return_type}" if fn.return_type else ""
        sig = f"def {fn.name}({params_str}){ret}"
        if fn.docstring:
            sig += f'\n    """{fn.docstring}"""'
        return sig

    # =================================================================
    # Python AST parser (built-in ast module)
    # =================================================================

    def _parse_python(
        self, source: str, filepath: str
    ) -> tuple[
        dict[str, FunctionNode],
        dict[str, ClassNode],
        dict[str, set[str]],
        set[str],
    ]:
        """Parse a Python source file and extract graph data."""
        functions: dict[str, FunctionNode] = {}
        classes: dict[str, ClassNode] = {}
        edges: dict[str, set[str]] = {}
        imports: set[str] = set()

        try:
            tree = ast.parse(source, filename=filepath)
        except SyntaxError as exc:
            logger.warning("Syntax error in %s: %s", filepath, exc)
            return functions, classes, edges, imports

        self._walk_python_ast(tree, filepath, functions, classes, edges)
        imports = self._extract_python_imports(tree, filepath)

        return functions, classes, edges, imports

    def _walk_python_ast(
        self,
        tree: ast.AST,
        filepath: str,
        functions: dict[str, FunctionNode],
        classes: dict[str, ClassNode],
        edges: dict[str, set[str]],
    ) -> None:
        """Recursively walk a Python AST and populate maps."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                key = f"{filepath}::{node.name}"
                fn_node = FunctionNode(
                    name=node.name,
                    filepath=filepath,
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    docstring=ast.get_docstring(node),
                    params=self._extract_python_params(node),
                    return_type=self._extract_python_return(node),
                )
                functions[key] = fn_node

                # Extract call edges from this function body
                call_targets = self._extract_python_calls(node, filepath)
                if call_targets:
                    edges[key] = call_targets

            elif isinstance(node, ast.ClassDef):
                key = f"{filepath}::{node.name}"
                methods = [
                    n.name
                    for n in ast.walk(node)
                    if isinstance(
                        n, ast.FunctionDef | ast.AsyncFunctionDef
                    )
                ]
                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        bases.append(ast.unparse(base))

                classes[key] = ClassNode(
                    name=node.name,
                    filepath=filepath,
                    bases=bases,
                    methods=methods,
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                )

    @staticmethod
    def _extract_python_params(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> list[str]:
        """Extract parameter names from a Python function def."""
        params: list[str] = []
        for arg in node.args.args:
            annotation = ""
            if arg.annotation:
                try:
                    annotation = f": {ast.unparse(arg.annotation)}"
                except Exception:  # noqa: BLE001
                    pass
            params.append(f"{arg.arg}{annotation}")
        return params

    @staticmethod
    def _extract_python_return(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> Optional[str]:
        """Extract return type annotation as a string."""
        if node.returns:
            try:
                return ast.unparse(node.returns)
            except Exception:  # noqa: BLE001
                return None
        return None

    def _extract_python_calls(
        self, node: ast.AST, filepath: str
    ) -> set[str]:
        """Extract function/method call targets from an AST node."""
        targets: set[str] = set()
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if isinstance(func, ast.Name):
                # Simple call: foo()
                targets.add(f"{filepath}::{func.id}")
            elif isinstance(func, ast.Attribute):
                # Method call: obj.method() — record bare method name
                targets.add(f"{filepath}::{func.attr}")
        return targets

    def _extract_python_imports(
        self, tree: ast.AST, filepath: str
    ) -> set[str]:
        """Map import statements to probable file paths."""
        imports: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    resolved = self._resolve_module_path(alias.name)
                    if resolved:
                        imports.add(resolved)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    resolved = self._resolve_module_path(node.module)
                    if resolved:
                        imports.add(resolved)

        return imports

    def _resolve_module_path(self, module: str) -> Optional[str]:
        """Best-effort conversion of a Python module name to a filepath.

        Checks if a corresponding .py file or package __init__.py exists
        under the repo root.  Returns the POSIX relative path or None.
        """
        if self._repo_path is None:
            return None

        parts = module.split(".")
        # Try as a direct .py file
        candidate = self._repo_path / Path(*parts).with_suffix(".py")
        if candidate.is_file():
            return candidate.relative_to(self._repo_path).as_posix()

        # Try as a package (directory with __init__.py)
        candidate_pkg = self._repo_path / Path(*parts) / "__init__.py"
        if candidate_pkg.is_file():
            pkg_dir = candidate_pkg.parent
            return pkg_dir.relative_to(self._repo_path).as_posix()

        return None

    # =================================================================
    # Tree-sitter parser (JS/TS/Go/Rust)
    # =================================================================

    def _parse_tree_sitter(
        self, source: str, filepath: str, extension: str
    ) -> tuple[
        dict[str, FunctionNode],
        dict[str, ClassNode],
        dict[str, set[str]],
        set[str],
    ]:
        """Parse a source file via tree-sitter and extract graph data."""
        functions: dict[str, FunctionNode] = {}
        classes: dict[str, ClassNode] = {}
        edges: dict[str, set[str]] = {}
        imports: set[str] = set()

        if not _TS_AVAILABLE or extension not in _TS_LANGUAGES:
            return functions, classes, edges, imports

        lang = _TS_LANGUAGES[extension]

        try:
            parser = tree_sitter.Parser(lang)
            tree = parser.parse(source.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "tree-sitter parse error for %s: %s", filepath, exc
            )
            return functions, classes, edges, imports

        root = tree.root_node

        if extension in (".js", ".jsx", ".ts", ".tsx"):
            self._extract_js_ts_nodes(
                root, source, filepath, functions, classes, edges, imports
            )
        elif extension == ".go":
            self._extract_go_nodes(
                root, source, filepath, functions, edges, imports
            )
        elif extension == ".rs":
            self._extract_rust_nodes(
                root, source, filepath, functions, classes, edges, imports
            )

        return functions, classes, edges, imports

    # ── JS / TS extraction ───────────────────────────────────────────

    def _extract_js_ts_nodes(
        self,
        root: object,
        source: str,
        filepath: str,
        functions: dict[str, FunctionNode],
        classes: dict[str, ClassNode],
        edges: dict[str, set[str]],
        imports: set[str],
    ) -> None:
        """Extract functions, classes, and imports from JS/TS AST."""
        for node in self._ts_walk(root):
            ntype = node.type

            # Function declarations
            if ntype in (
                "function_declaration",
                "generator_function_declaration",
            ):
                name = self._ts_child_text(node, "name", source)
                if name:
                    key = f"{filepath}::{name}"
                    functions[key] = FunctionNode(
                        name=name,
                        filepath=filepath,
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                        params=self._ts_extract_params(node, source),
                    )
                    calls = self._ts_extract_calls(node, source, filepath)
                    if calls:
                        edges[key] = calls

            # Arrow functions / const declarations with functions
            elif ntype == "lexical_declaration":
                for child in node.children:
                    if child.type == "variable_declarator":
                        var_name = self._ts_child_text(
                            child, "name", source
                        )
                        value = child.child_by_field_name("value")
                        if var_name and value and value.type in (
                            "arrow_function",
                            "function_expression",
                        ):
                            key = f"{filepath}::{var_name}"
                            functions[key] = FunctionNode(
                                name=var_name,
                                filepath=filepath,
                                line_start=node.start_point[0] + 1,
                                line_end=node.end_point[0] + 1,
                                params=self._ts_extract_params(
                                    value, source
                                ),
                            )
                            calls = self._ts_extract_calls(
                                value, source, filepath
                            )
                            if calls:
                                edges[key] = calls

            # Class declarations
            elif ntype == "class_declaration":
                name = self._ts_child_text(node, "name", source)
                if name:
                    methods = self._ts_extract_class_methods(node, source)
                    bases = self._ts_extract_heritage(node, source)
                    key = f"{filepath}::{name}"
                    classes[key] = ClassNode(
                        name=name,
                        filepath=filepath,
                        bases=bases,
                        methods=methods,
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                    )

            # Import statements
            elif ntype == "import_statement":
                src_node = node.child_by_field_name("source")
                if src_node:
                    raw = self._ts_node_text(src_node, source).strip(
                        "\"'`"
                    )
                    if raw.startswith("."):
                        resolved = self._resolve_relative_import(
                            filepath, raw
                        )
                        if resolved:
                            imports.add(resolved)

    # ── Go extraction ────────────────────────────────────────────────

    def _extract_go_nodes(
        self,
        root: object,
        source: str,
        filepath: str,
        functions: dict[str, FunctionNode],
        edges: dict[str, set[str]],
        imports: set[str],
    ) -> None:
        """Extract functions and imports from Go AST."""
        for node in self._ts_walk(root):
            ntype = node.type

            if ntype == "function_declaration":
                name = self._ts_child_text(node, "name", source)
                if name:
                    key = f"{filepath}::{name}"
                    functions[key] = FunctionNode(
                        name=name,
                        filepath=filepath,
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                        params=self._ts_extract_params(node, source),
                    )
                    calls = self._ts_extract_calls(node, source, filepath)
                    if calls:
                        edges[key] = calls

            elif ntype == "method_declaration":
                name = self._ts_child_text(node, "name", source)
                if name:
                    key = f"{filepath}::{name}"
                    functions[key] = FunctionNode(
                        name=name,
                        filepath=filepath,
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                        params=self._ts_extract_params(node, source),
                    )
                    calls = self._ts_extract_calls(node, source, filepath)
                    if calls:
                        edges[key] = calls

            elif ntype == "import_spec":
                path_node = node.child_by_field_name("path")
                if path_node:
                    raw = self._ts_node_text(path_node, source).strip('"')
                    imports.add(raw)

    # ── Rust extraction ──────────────────────────────────────────────

    def _extract_rust_nodes(
        self,
        root: object,
        source: str,
        filepath: str,
        functions: dict[str, FunctionNode],
        classes: dict[str, ClassNode],
        edges: dict[str, set[str]],
        imports: set[str],
    ) -> None:
        """Extract functions, structs, impls, and imports from Rust AST."""
        for node in self._ts_walk(root):
            ntype = node.type

            if ntype == "function_item":
                name = self._ts_child_text(node, "name", source)
                if name:
                    key = f"{filepath}::{name}"
                    functions[key] = FunctionNode(
                        name=name,
                        filepath=filepath,
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                        params=self._ts_extract_params(node, source),
                    )
                    calls = self._ts_extract_calls(node, source, filepath)
                    if calls:
                        edges[key] = calls

            elif ntype == "struct_item":
                name = self._ts_child_text(node, "name", source)
                if name:
                    key = f"{filepath}::{name}"
                    classes[key] = ClassNode(
                        name=name,
                        filepath=filepath,
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                    )

            elif ntype == "impl_item":
                type_node = node.child_by_field_name("type")
                if type_node:
                    impl_name = self._ts_node_text(type_node, source)
                    cls_key = f"{filepath}::{impl_name}"
                    if cls_key in classes:
                        # Gather methods inside impl block
                        for child in self._ts_walk(node):
                            if child.type == "function_item":
                                mname = self._ts_child_text(
                                    child, "name", source
                                )
                                if mname:
                                    classes[cls_key].methods.append(mname)

            elif ntype == "use_declaration":
                # Simplified: just record the raw use path
                text = self._ts_node_text(node, source)
                imports.add(text)

    # ── Tree-sitter helpers ──────────────────────────────────────────

    @staticmethod
    def _ts_walk(node: object) -> list[object]:
        """Flatten a tree-sitter node tree via BFS."""
        result: list[object] = []
        stack: list[object] = [node]
        while stack:
            current = stack.pop()
            result.append(current)
            children = getattr(current, "children", [])
            stack.extend(reversed(children))
        return result

    @staticmethod
    def _ts_node_text(node: object, source: str) -> str:
        """Get the source text for a tree-sitter node."""
        start = getattr(node, "start_byte", 0)
        end = getattr(node, "end_byte", 0)
        return source[start:end]

    @staticmethod
    def _ts_child_text(
        node: object, field_name: str, source: str
    ) -> Optional[str]:
        """Get text of a named child field, or None."""
        child = getattr(node, "child_by_field_name", lambda _: None)(
            field_name
        )
        if child is None:
            return None
        start = getattr(child, "start_byte", 0)
        end = getattr(child, "end_byte", 0)
        return source[start:end]

    def _ts_extract_params(
        self, node: object, source: str
    ) -> list[str]:
        """Extract parameter names from a tree-sitter function node."""
        params: list[str] = []
        parameters = getattr(
            node, "child_by_field_name", lambda _: None
        )("parameters")
        if parameters is None:
            return params
        for child in getattr(parameters, "children", []):
            ctype = getattr(child, "type", "")
            if ctype in (
                "formal_parameters",
                "required_parameter",
                "optional_parameter",
                "identifier",
                "parameter_declaration",
                "shorthand_field_identifier",
            ):
                text = self._ts_node_text(child, source)
                if text and text not in ("(", ")", ",", " "):
                    params.append(text.strip())
            # Nested identifier inside parameter nodes
            name_child = getattr(
                child, "child_by_field_name", lambda _: None
            )("name")
            if name_child:
                name_text = self._ts_node_text(name_child, source)
                if name_text:
                    params.append(name_text.strip())
        return params

    def _ts_extract_calls(
        self, node: object, source: str, filepath: str
    ) -> set[str]:
        """Extract call expression targets from a tree-sitter node."""
        calls: set[str] = set()
        for child in self._ts_walk(node):
            ctype = getattr(child, "type", "")
            if ctype == "call_expression":
                func_node = getattr(
                    child, "child_by_field_name", lambda _: None
                )("function")
                if func_node:
                    fname = self._ts_node_text(func_node, source)
                    # Take the last segment (e.g., "obj.method" → "method")
                    bare = fname.rsplit(".", 1)[-1]
                    calls.add(f"{filepath}::{bare}")
        return calls

    @staticmethod
    def _ts_extract_class_methods(
        node: object, source: str
    ) -> list[str]:
        """Extract method names from a JS/TS class body."""
        methods: list[str] = []
        body = getattr(
            node, "child_by_field_name", lambda _: None
        )("body")
        if body is None:
            return methods
        for child in getattr(body, "children", []):
            ctype = getattr(child, "type", "")
            if ctype in ("method_definition", "public_field_definition"):
                name_node = getattr(
                    child, "child_by_field_name", lambda _: None
                )("name")
                if name_node:
                    start = getattr(name_node, "start_byte", 0)
                    end = getattr(name_node, "end_byte", 0)
                    name = source[start:end]
                    if name:
                        methods.append(name)
        return methods

    @staticmethod
    def _ts_extract_heritage(
        node: object, source: str
    ) -> list[str]:
        """Extract base class names from a JS/TS class heritage clause."""
        bases: list[str] = []
        for child in getattr(node, "children", []):
            ctype = getattr(child, "type", "")
            if ctype == "class_heritage":
                for sub in getattr(child, "children", []):
                    stype = getattr(sub, "type", "")
                    if stype == "identifier":
                        start = getattr(sub, "start_byte", 0)
                        end = getattr(sub, "end_byte", 0)
                        bases.append(source[start:end])
        return bases

    @staticmethod
    def _resolve_relative_import(
        current_file: str, import_path: str
    ) -> Optional[str]:
        """Resolve a relative JS/TS import to a filepath."""
        current_dir = str(Path(current_file).parent)
        if current_dir == ".":
            resolved = import_path.lstrip("./")
        else:
            # Simple relative path resolution
            parts = import_path.split("/")
            base_parts = current_dir.split("/")
            for part in parts:
                if part == ".":
                    continue
                elif part == "..":
                    if base_parts:
                        base_parts.pop()
                else:
                    base_parts.append(part)
            resolved = "/".join(base_parts)

        # Try common extensions
        for ext in (".ts", ".tsx", ".js", ".jsx"):
            candidate = resolved + ext
            # We can't check disk here — return best guess
            if not resolved.endswith(ext):
                continue
            return resolved

        # Return with assumed extension
        if not any(resolved.endswith(e) for e in (".ts", ".tsx", ".js", ".jsx")):
            return resolved + ".ts"
        return resolved
