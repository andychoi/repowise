"""Deployment-descriptor entry points for Java EE, JAAS, SAP NetWeaver and JSP.

A Java EE container, a JAAS login configuration or the SAP portal runtime
enters application code through classes named in XML (or, for JAAS, a small
text config), never through an ``import``. Without reading those descriptors
the classes have no in-source caller: dead-code candidates, and never entry
points, in exactly the legacy estates where knowing the entry points matters.

Descriptors are found on disk, not in ``parsed_files``: the traverser skips
``.xml`` as an unknown language, and SAP portal projects keep their *source*
``portalapp.xml`` under ``dist/PORTAL-INF/``, a directory the traverser prunes
as build output. Each named class is resolved through the JVM workspace index
and stamped ``is_entry_point`` with a ``framework_role``. No edge is added,
because a descriptor is not a graph node and inventing an attribute-less node
would mislead every consumer that reads node attributes.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...fs_walk import PRUNED_DIRS, walk_repo
from ..resolvers import ResolverContext
from .base import DetectionContext, FrameworkHandler

if TYPE_CHECKING:
    import networkx as nx

#: The shared walker's prune set, plus Eclipse's ``bin/`` output folder (it
#: holds compiled copies, never the source descriptor). ``dist`` is *not*
#: pruned by the default set, which matters: SAP portal projects keep their
#: source ``portalapp.xml`` under ``dist/PORTAL-INF``.
_PRUNE = PRUNED_DIRS | frozenset({"bin", "bower_components", ".repowise"})
_MAX_DESCRIPTOR_BYTES = 1_000_000
_MAX_DESCRIPTORS = 5_000

_FQN = r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+)"
_WEB_XML_RE = re.compile(rf"<(servlet|filter|listener)-class>\s*{_FQN}\s*</\1-class>")
_WEB_XML_ROLE = {"servlet": "servlet", "filter": "servlet_filter", "listener": "servlet_listener"}
_EJB_CLASS_RE = re.compile(rf"<ejb-class>\s*{_FQN}\s*</ejb-class>")
_LOGIN_MODULE_RE = re.compile(rf"<class-name>\s*{_FQN}\s*</class-name>")
_JAAS_LINE_RE = re.compile(
    rf"^\s*{_FQN}\s+(?:required|requisite|sufficient|optional)\b", re.MULTILINE | re.IGNORECASE
)
# Attribute order varies between SAP tooling versions.
_PORTAL_CLASS_RE = re.compile(
    rf'<property\s+name="ClassName"\s+value="{_FQN}"'
    rf'|<property\s+value="{_FQN}"\s+name="ClassName"'
)
_ANDROID_NAME_RE = re.compile(r'android:name="([\w.$]+)"')
_ANDROID_PACKAGE_RE = re.compile(r'<manifest[^>]*\bpackage="([\w.]+)"')

# JSP directives and actions that name a concrete class. Wildcard imports
# (``java.util.*``) name a package, not a class, and are skipped.
_JSP_PAGE_IMPORT_RE = re.compile(r'<%@\s*page\b[^%]*?\bimport\s*=\s*"([^"]+)"', re.DOTALL)
_JSP_USEBEAN_RE = re.compile(rf'<jsp:useBean\b[^>]*?\b(?:class|type)\s*=\s*"{_FQN}"', re.DOTALL)
_JSP_EXTENSIONS = (".jsp", ".jspf", ".tag", ".tagx")

_JAAS_CONFIG_NAMES = frozenset({"jaas.config", "jaas.conf", "login.config", "login.conf"})
_DESCRIPTOR_NAMES = frozenset(
    {
        "web.xml",
        "ejb-jar.xml",
        "portalapp.xml",
        "loginmoduleconfiguration.xml",
        "androidmanifest.xml",
    }
    | _JAAS_CONFIG_NAMES
)


def find_descriptors(repo_path: Path | None) -> list[tuple[str, Path]]:
    """``(repo-relative posix path, absolute path)`` for every known descriptor."""
    if repo_path is None or not repo_path.is_dir():
        return []
    found: list[tuple[str, Path]] = []
    for root, _dirs, files in walk_repo(repo_path, prune_dirs=_PRUNE):
        for name in files:
            if name.lower() in _DESCRIPTOR_NAMES or name.lower().endswith(_JSP_EXTENSIONS):
                abs_path = Path(root) / name
                found.append((abs_path.relative_to(repo_path).as_posix(), abs_path))
                if len(found) >= _MAX_DESCRIPTORS:
                    return found
    return found


def _read(path: Path) -> str | None:
    try:
        if path.stat().st_size > _MAX_DESCRIPTOR_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def declared_classes(name: str, text: str) -> Iterator[tuple[str, str]]:
    """``(fqn, framework_role)`` for each class *text* (a descriptor named *name*) declares."""
    lower = name.lower()
    if lower == "web.xml":
        for kind, fqn in _WEB_XML_RE.findall(text):
            yield fqn, _WEB_XML_ROLE[kind]
    elif lower == "ejb-jar.xml":
        for fqn in _EJB_CLASS_RE.findall(text):
            yield fqn, "ejb"
    elif lower == "loginmoduleconfiguration.xml":
        for fqn in _LOGIN_MODULE_RE.findall(text):
            yield fqn, "jaas_login_module"
    elif lower in _JAAS_CONFIG_NAMES:
        for fqn in _JAAS_LINE_RE.findall(text):
            yield fqn, "jaas_login_module"
    elif lower == "portalapp.xml":
        for first, second in _PORTAL_CLASS_RE.findall(text):
            yield first or second, "sap_portal_component"
    elif lower.endswith(_JSP_EXTENSIONS):
        # A JSP compiles to a servlet the container enters, so a class it
        # imports or instantiates is reachable at runtime without an importer.
        for imports in _JSP_PAGE_IMPORT_RE.findall(text):
            for item in imports.split(","):
                fqn = item.strip()
                if "." in fqn and not fqn.endswith("*"):
                    yield fqn, "jsp_referenced"
        for fqn in _JSP_USEBEAN_RE.findall(text):
            yield fqn, "jsp_referenced"
    elif lower == "androidmanifest.xml":
        package = _ANDROID_PACKAGE_RE.search(text)
        for raw in _ANDROID_NAME_RE.findall(text):
            if raw.startswith(".") and package:
                raw = package.group(1) + raw
            elif "." not in raw and package:
                raw = f"{package.group(1)}.{raw}"
            if "." in raw:
                yield raw, "android_component"


def _stamp_declared_entry_points(
    graph: nx.DiGraph, ctx: ResolverContext, path_set: set[str]
) -> int:
    descriptors = find_descriptors(ctx.repo_path)
    if not descriptors:
        return 0
    try:
        from ..resolvers.jvm_workspace import get_or_build_jvm_index

        jvm_index = get_or_build_jvm_index(ctx)
    except Exception:
        return 0
    stamped = 0
    for rel, abs_path in descriptors:
        text = _read(abs_path)
        if text is None:
            continue
        for fqn, role in declared_classes(abs_path.name, text):
            for target in jvm_index.files_for_fqn(fqn):
                node = graph.nodes.get(target) if target in path_set else None
                if node is None:
                    continue
                if not node.get("is_entry_point"):
                    stamped += 1
                node["is_entry_point"] = True
                node.setdefault("framework_role", role)
                node.setdefault("declared_by", rel)
    return stamped


class _DeploymentDescriptorHandler:
    """Runs whenever the repository has JVM sources; discovery is cheap."""

    def detect(self, dctx: DetectionContext) -> bool:
        return any(p.endswith((".java", ".kt")) for p in dctx.path_set)

    def add_edges(
        self,
        graph: nx.DiGraph,
        parsed_files: dict[str, Any],
        ctx: ResolverContext,
        path_set: set[str],
    ) -> int:
        # Returns the number of classes newly marked as entry points; this
        # handler adds no edges (see the module docstring).
        return _stamp_declared_entry_points(graph, ctx, path_set)


HANDLERS: list[FrameworkHandler] = [_DeploymentDescriptorHandler()]
