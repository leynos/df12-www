"""Read Cuprum's public API from its source, without importing it.

The Cuprum sub-site documents the names the package exports from
``cuprum/__init__.py`` (its ``__all__``). This module resolves each name to
the statement that defines it, following re-exports through the package, and
parses the definition's signature and NumPy-style docstring. It reads the
source with :mod:`ast` only, so a checkout of Cuprum at the documented release
is all it needs: no install, no native extension, and no import side effects.
"""

from __future__ import annotations

import ast
import dataclasses as dc
import re
import typing as typ

if typ.TYPE_CHECKING:
    from pathlib import Path

#: NumPy docstring section headings the site renders, in display order.
SECTION_NAMES = (
    "Parameters",
    "Attributes",
    "Returns",
    "Yields",
    "Raises",
    "Warns",
    "See Also",
    "Notes",
    "Examples",
)
_FIELD_SECTIONS = frozenset(
    {"Parameters", "Attributes", "Returns", "Yields", "Raises", "Warns"}
)
#: Headings some docstrings spell differently, mapped to the canonical name.
_SECTION_ALIASES = {"Example": "Examples"}
_UNDERLINE = re.compile(r"^-{3,}\s*$")
_FIELD_LINE = re.compile(r"^(?P<name>[^\s:][^:]*?)\s*(?::\s*(?P<type>.*))?$")
#: A field header names one or more identifiers, perhaps starred.
_FIELD_NAME = re.compile(r"^\*{0,2}[A-Za-z_][\w.]*(?:\s*,\s*\*{0,2}[A-Za-z_][\w.]*)*$")


class ApiSourceError(Exception):
    """Raised when a public name cannot be traced to its definition."""


@dc.dataclass(frozen=True, slots=True)
class Field:
    """One entry of a Parameters, Returns, Raises, or Attributes section."""

    name: str
    type: str
    description: str


@dc.dataclass(frozen=True, slots=True)
class Docstring:
    """A NumPy-style docstring split into its summary, body, and sections."""

    summary: str
    body: tuple[str, ...]
    fields: dict[str, tuple[Field, ...]]
    texts: dict[str, tuple[str, ...]]
    examples: str


@dc.dataclass(frozen=True, slots=True)
class Member:
    """A public method, property, field, or enumeration member of a class."""

    name: str
    kind: str
    signature: str
    doc: Docstring


@dc.dataclass(frozen=True, slots=True)
class ApiEntry:
    """One exported name: what it is, where it lives, and what it documents."""

    name: str
    kind: str
    module: str
    path: str
    line: int
    signature: str
    bases: tuple[str, ...]
    doc: Docstring
    members: tuple[Member, ...]


_EMPTY_DOC = Docstring("", (), {}, {}, "")


def parse_docstring(text: str | None) -> Docstring:
    """Split a NumPy-style docstring into summary, paragraphs, and sections.

    Parameters
    ----------
    text : str | None
        The cleaned docstring, as :func:`ast.get_docstring` returns it.

    Returns
    -------
    Docstring
        The first paragraph as the summary, the remaining free text as body
        paragraphs, field sections as :class:`Field` tuples, prose sections
        as paragraph tuples, and any ``Examples`` section as literal text.

    Examples
    --------
    >>> lines = ["Run it.", "", "Returns", "-------", "int", "    The code."]
    >>> doc = parse_docstring(chr(10).join(lines))
    >>> doc.summary, doc.fields["Returns"][0].type
    ('Run it.', 'int')
    """
    if not text:
        return _EMPTY_DOC
    lines = text.expandtabs().splitlines()
    heads = [
        i
        for i in range(len(lines) - 1)
        if _section(lines[i]) in SECTION_NAMES
        and _UNDERLINE.match(lines[i + 1].strip())
    ]
    intro = lines[: heads[0]] if heads else lines
    paragraphs = _paragraphs(intro)
    fields: dict[str, tuple[Field, ...]] = {}
    texts: dict[str, tuple[str, ...]] = {}
    examples = ""
    for index, start in enumerate(heads):
        name = _section(lines[start])
        end = heads[index + 1] if index + 1 < len(heads) else len(lines)
        content = lines[start + 2 : end]
        if name in _FIELD_SECTIONS:
            fields[name], prose = _fields(
                content, returns=name in {"Returns", "Yields"}
            )
            if prose:
                texts[name] = prose
        elif name == "Examples":
            examples = _literal(content)
        else:
            texts[name] = _paragraphs(content)
    summary = paragraphs[0] if paragraphs else ""
    return Docstring(summary, paragraphs[1:], fields, texts, examples)


def _section(line: str) -> str:
    """Return the canonical section name a heading line spells."""
    heading = line.strip()
    return _SECTION_ALIASES.get(heading, heading)


def _paragraphs(lines: list[str]) -> tuple[str, ...]:
    """Join blank-line-separated lines into single-spaced paragraphs."""
    out: list[str] = []
    current: list[str] = []
    for line in [*lines, ""]:
        if line.strip():
            current.append(line.strip())
        elif current:
            out.append(" ".join(current))
            current = []
    return tuple(out)


def _literal(lines: list[str]) -> str:
    """Return a section's lines as literal text, trimmed of blank edges."""
    return "\n".join(lines).strip("\n")


def _fields(
    lines: list[str], *, returns: bool
) -> tuple[tuple[Field, ...], tuple[str, ...]]:
    """Parse ``name : type`` headed entries with indented descriptions.

    A header may also be ``name:`` with no type. A Returns entry may be a bare
    type (``int``) rather than ``name : type``, so there a line without a
    colon is read as the type. Any other unindented line is prose about the
    section rather than a field, and is returned separately as paragraphs.
    """
    entries: list[tuple[str, str, list[str]]] = []
    prose: list[str] = []
    in_prose = False
    for line in lines:
        if not line.strip():
            if in_prose:
                prose.append("")
            elif entries:
                entries[-1][2].append("")
            continue
        if not line.startswith((" ", "\t")):
            match = _FIELD_LINE.match(line.strip())
            name = match["name"].strip() if match else ""
            kind = (match["type"] or "").strip() if match else ""
            if returns and match and not kind and match["type"] is None:
                entries.append(("", name, []))
                in_prose = False
            elif match and _FIELD_NAME.match(name):
                entries.append((name, kind, []))
                in_prose = False
            else:
                prose.append(line)
                in_prose = True
        elif in_prose:
            prose.append(line)
        elif entries:
            entries[-1][2].append(line)
    fields = tuple(
        Field(name, kind, " ".join(_paragraphs(body))) for name, kind, body in entries
    )
    return fields, _paragraphs(prose)


def _parse_source(path: Path, label: str) -> ast.Module:
    """Read and parse one source file, raising :class:`ApiSourceError` on failure.

    ``label`` names the file in the message, as a module or a file name.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        msg = f"cannot read module {label} from {path}: {error}"
        raise ApiSourceError(msg) from error
    try:
        return ast.parse(source)
    except SyntaxError as error:
        msg = f"cannot parse module {label} from {path}: {error}"
        raise ApiSourceError(msg) from error


def public_names(package_init: Path) -> list[str]:
    """Return the ``__all__`` list declared in ``package_init``.

    Parameters
    ----------
    package_init : Path
        The package's ``__init__.py``.

    Returns
    -------
    list[str]
        The exported names, in declaration order.

    Raises
    ------
    ApiSourceError
        If the file cannot be read, is not valid UTF-8, or does not parse as
        Python, or if the module declares no literal ``__all__`` list or tuple.
    """
    tree = _parse_source(package_init, package_init.name)
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
            and isinstance(node.value, ast.List | ast.Tuple)
        ):
            return [
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]
    msg = f"{package_init} declares no literal __all__"
    raise ApiSourceError(msg)


class _Resolver:
    """Trace names through a package's modules to their defining statements."""

    def __init__(self, root: Path, package: str) -> None:
        self.root = root
        self.package = package
        self._trees: dict[str, ast.Module] = {}

    def _path(self, module: str) -> Path:
        """Return the source file of dotted ``module`` under the root."""
        parts = module.split(".")
        as_package = self.root.joinpath(*parts, "__init__.py")
        if as_package.is_file():
            return as_package
        as_module = self.root.joinpath(*parts[:-1], f"{parts[-1]}.py")
        if as_module.is_file():
            return as_module
        msg = f"no source for module {module!r} under {self.root}"
        raise ApiSourceError(msg)

    def has_source(self, module: str) -> bool:
        """Return whether dotted ``module`` has a source file under the root."""
        try:
            self._path(module)
        except ApiSourceError:
            return False
        return True

    def tree(self, module: str) -> ast.Module:
        """Return the parsed source of ``module``, parsing it once.

        Raises
        ------
        ApiSourceError
            If ``module``'s source file cannot be read, is not valid UTF-8,
            or does not parse as Python.
        """
        if module not in self._trees:
            self._trees[module] = _parse_source(self._path(module), repr(module))
        return self._trees[module]

    def relpath(self, module: str) -> str:
        """Return ``module``'s source path relative to the checkout root."""
        return self._path(module).relative_to(self.root).as_posix()

    def _absolute(self, module: str, node: ast.ImportFrom) -> str | None:
        """Resolve an import's target module, or ``None`` outside the package."""
        if node.level == 0:
            target = node.module or ""
            return target if target.split(".")[0] == self.package else None
        is_package = self._path(module).name == "__init__.py"
        base = module.split(".")
        drop = node.level - 1 if is_package else node.level
        if drop:
            base = base[:-drop]
        return ".".join([*base, *([node.module] if node.module else [])])

    def find(
        self, module: str, name: str, seen: frozenset[str] = frozenset()
    ) -> tuple[str, ast.stmt]:
        """Return the module and statement that define ``name``."""
        key = f"{module}:{name}"
        if key in seen:
            msg = f"import cycle while resolving {name!r} from {module}"
            raise ApiSourceError(msg)
        tree = self.tree(module)
        for node in tree.body:
            if _defines(node, name):
                return module, node
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue
            for alias in node.names:
                if (alias.asname or alias.name) != name:
                    continue
                target = self._absolute(module, node)
                if target is None:
                    msg = f"{name!r} is imported into {module} from outside the package"
                    raise ApiSourceError(msg)
                try:
                    return self.find(target, alias.name, seen | {key})
                except ApiSourceError:
                    # ``from . import sh`` names a submodule, not an attribute.
                    # When there is no such submodule either, the original
                    # error is the one that explains the failure.
                    submodule = f"{target}.{alias.name}"
                    if not self.has_source(submodule):
                        raise
                    return submodule, _module_stub(self.tree(submodule))
        msg = f"cannot find a definition of {name!r} in {module}"
        raise ApiSourceError(msg)


def _defines(node: ast.stmt, name: str) -> bool:
    """Report whether a top-level statement defines ``name``."""
    match node:
        case ast.ClassDef() | ast.FunctionDef() | ast.AsyncFunctionDef():
            return node.name == name
        case ast.Assign(targets=targets):
            return any(isinstance(t, ast.Name) and t.id == name for t in targets)
        case ast.AnnAssign(target=ast.Name(id=target)):
            return target == name
        case ast.TypeAlias(name=ast.Name(id=target)):
            return target == name
    return False


def _module_stub(tree: ast.Module) -> ast.Expr:
    """Stand in for a submodule export with its module docstring."""
    return ast.Expr(value=ast.Constant(value=ast.get_docstring(tree) or ""))


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef, *, drop_self: bool) -> str:
    """Render a function's parameters and return annotation."""
    args = node.args
    if drop_self and (args.posonlyargs or args.args):
        first = (args.posonlyargs or args.args)[0].arg
        if first in {"self", "cls"}:
            args = ast.arguments(
                posonlyargs=args.posonlyargs[1:] if args.posonlyargs else [],
                args=args.args if args.posonlyargs else args.args[1:],
                vararg=args.vararg,
                kwonlyargs=args.kwonlyargs,
                kw_defaults=args.kw_defaults,
                kwarg=args.kwarg,
                defaults=args.defaults,
            )
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"({ast.unparse(args)}){returns}"


def _decorators(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
) -> set[str]:
    """Return the final dotted component of each decorator's name."""
    names: set[str] = set()
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        names.add(ast.unparse(target).rsplit(".", 1)[-1])
    return names


def _following_docstring(body: list[ast.stmt], index: int) -> str | None:
    """Return the string literal directly after ``body[index]``, if any."""
    if index + 1 < len(body):
        nxt = body[index + 1]
        if isinstance(nxt, ast.Expr) and isinstance(nxt.value, ast.Constant):
            value = nxt.value.value
            if isinstance(value, str):
                return value
    return None


def _class_members(node: ast.ClassDef) -> tuple[Member, ...]:
    """Collect a class's public fields, properties, and methods."""
    members: list[Member] = []
    is_enum = any(
        ast.unparse(base).rsplit(".", 1)[-1].endswith("Enum") for base in node.bases
    )
    seen: set[str] = set()
    for index, item in enumerate(node.body):
        match item:
            case ast.AnnAssign(target=ast.Name(id=name)) if not name.startswith("_"):
                if "ClassVar" in ast.unparse(item.annotation):
                    continue
                doc = parse_docstring(_clean(_following_docstring(node.body, index)))
                members.append(
                    Member(name, "field", f": {ast.unparse(item.annotation)}", doc)
                )
            case ast.Assign(targets=[ast.Name(id=name)]) if (
                is_enum and not name.startswith("_")
            ):
                doc = parse_docstring(_clean(_following_docstring(node.body, index)))
                members.append(
                    Member(name, "member", f" = {ast.unparse(item.value)}", doc)
                )
            case ast.FunctionDef() | ast.AsyncFunctionDef() if not item.name.startswith(
                "_"
            ):
                decorators = _decorators(item)
                if "overload" in decorators or item.name in seen:
                    continue
                seen.add(item.name)
                doc = parse_docstring(ast.get_docstring(item))
                if "property" in decorators or "cached_property" in decorators:
                    annotation = (
                        f": {ast.unparse(item.returns)}" if item.returns else ""
                    )
                    members.append(Member(item.name, "property", annotation, doc))
                    continue
                kind = (
                    "classmethod"
                    if "classmethod" in decorators
                    else ("staticmethod" if "staticmethod" in decorators else "method")
                )
                prefix = "async " if isinstance(item, ast.AsyncFunctionDef) else ""
                signature = _signature(item, drop_self=kind != "staticmethod")
                members.append(Member(item.name, kind, prefix + signature, doc))
    return tuple(members)


def _clean(text: str | None) -> str | None:
    """Dedent a raw string literal the way :func:`ast.get_docstring` does."""
    if text is None:
        return None
    import inspect  # noqa: PLC0415 - only the cleaning helper is needed, and rarely

    return inspect.cleandoc(text)


def _class_signature(node: ast.ClassDef) -> str:
    """Render a class's constructor from ``__init__`` or its dataclass fields."""
    for item in node.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            return _signature(item, drop_self=True)
    if "dataclass" in _decorators(node):
        params: list[str] = []
        for item in node.body:
            if (
                isinstance(item, ast.AnnAssign)
                and isinstance(item.target, ast.Name)
                and "ClassVar" not in ast.unparse(item.annotation)
            ):
                default = (
                    f" = {ast.unparse(item.value)}" if item.value is not None else ""
                )
                params.append(
                    f"{item.target.id}: {ast.unparse(item.annotation)}{default}"
                )
        return f"({', '.join(params)})"
    return ""


def _module_members(
    module: str, exported: frozenset[str], resolver: _Resolver
) -> tuple[Member, ...]:
    """Describe a submodule's own exports that the package does not re-export."""
    names = public_names(resolver.root / resolver.relpath(module))
    members: list[Member] = []
    for member in names:
        if member in exported or member.startswith("_"):
            continue
        owner, node = resolver.find(module, member)
        entry = _entry(member, owner, node, resolver, exported)
        members.append(Member(member, entry.kind, entry.signature, entry.doc))
    return tuple(members)


def _entry(
    name: str,
    module: str,
    node: ast.stmt,
    resolver: _Resolver,
    exported: frozenset[str] = frozenset(),
) -> ApiEntry:
    """Describe the statement that defines exported ``name``."""
    path = resolver.relpath(module)
    line = getattr(node, "lineno", 1)
    match node:
        case ast.ClassDef():
            kind = (
                "exception"
                if any(
                    ast.unparse(base).endswith(("Error", "Exception"))
                    for base in node.bases
                )
                else "class"
            )
            return ApiEntry(
                name,
                kind,
                module,
                path,
                line,
                _class_signature(node),
                tuple(ast.unparse(base) for base in node.bases),
                parse_docstring(ast.get_docstring(node)),
                _class_members(node),
            )
        case ast.FunctionDef() | ast.AsyncFunctionDef():
            prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            return ApiEntry(
                name,
                "function",
                module,
                path,
                line,
                prefix + _signature(node, drop_self=False),
                (),
                parse_docstring(ast.get_docstring(node)),
                (),
            )
        case ast.Expr(value=ast.Constant(value=str() as text)):
            return ApiEntry(
                name,
                "module",
                module,
                path,
                1,
                "",
                (),
                parse_docstring(text),
                _module_members(module, exported, resolver),
            )
    body = resolver.tree(module).body
    index = body.index(node)
    doc = parse_docstring(_clean(_following_docstring(body, index)))
    value = getattr(node, "value", None)
    annotation = getattr(node, "annotation", None)
    rendered = ast.unparse(value) if value is not None else ""
    if rendered.startswith(("typ.NewType(", "typing.NewType(", "NewType(")):
        return ApiEntry(
            name, "new type", module, path, line, f" = {rendered}", (), doc, ()
        )
    if isinstance(value, ast.Name) and value.id in exported:
        return ApiEntry(
            name, "alias", module, path, line, f" = {rendered}", (), doc, ()
        )
    is_alias = (
        isinstance(node, ast.TypeAlias)
        or (annotation is not None and "TypeAlias" in ast.unparse(annotation))
        or rendered.startswith(
            ("typ.Callable", "cabc.Callable", "typ.Literal", "Callable[")
        )
    )
    kind = "type alias" if is_alias else "constant"
    if rendered:
        signature = f" = {rendered}"
    elif annotation is not None:
        signature = f": {ast.unparse(annotation)}"
    else:
        signature = ""
    return ApiEntry(name, kind, module, path, line, signature, (), doc, ())


def load_api(
    root: Path, package: str, extra_modules: tuple[str, ...] = ()
) -> list[ApiEntry]:
    """Describe every name ``package`` exports, in ``__all__`` order.

    Parameters
    ----------
    root : Path
        The checkout root holding the ``package`` directory.
    package : str
        The importable package name, such as ``"cuprum"``.
    extra_modules : tuple[str, ...]
        Dotted names of public submodules the package does not re-export,
        such as ``"cuprum.sinks"``. Each becomes a module entry, named by
        its dotted path, listing the names in its ``__all__`` that the
        package does not already export.

    Returns
    -------
    list[ApiEntry]
        One entry per exported name, then one per extra module.

    Raises
    ------
    ApiSourceError
        If a name cannot be traced to a definition inside the package, or if
        a source file cannot be read, is not valid UTF-8, or does not parse
        as Python.
    """
    resolver = _Resolver(root, package)
    names = public_names(root / package / "__init__.py")
    exported = frozenset(names)
    entries: list[ApiEntry] = []
    for name in names:
        module, node = resolver.find(package, name)
        entries.append(_entry(name, module, node, resolver, exported))
    for module in extra_modules:
        stub = _module_stub(resolver.tree(module))
        entries.append(_entry(module, module, stub, resolver, exported))
    return entries


__all__ = [
    "SECTION_NAMES",
    "ApiEntry",
    "ApiSourceError",
    "Docstring",
    "Field",
    "Member",
    "load_api",
    "parse_docstring",
    "public_names",
]
