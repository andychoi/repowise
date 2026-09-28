"""An Eclipse workspace is a set of packages, one per ``.project`` (E10).

Legacy Java EE and SAP NetWeaver estates are Eclipse workspaces: every module
is a directory with a ``.project`` (and usually ``.classpath``), with no
``pom.xml`` or ``build.gradle`` anywhere. The only JVM package manifests were
Maven and Gradle files, so a 25-project workspace was reported as a single
package-less tree ("a java codebase of 411 files") and every module rollup fell
back to top-level directories by accident rather than by design.
"""

from __future__ import annotations

from pathlib import Path

from repowise.core.ingestion.package_roots import package_manifest_names
from repowise.core.ingestion.traverser import FileTraverser

_PROJECT = """<?xml version="1.0" encoding="UTF-8"?>
<projectDescription>
\t<name>{name}</name>
\t<natures><nature>org.eclipse.jdt.core.javanature</nature></natures>
</projectDescription>
"""


def _eclipse_project(root: Path, name: str, source_dir: str, cls: str) -> None:
    proj = root / name
    (proj / source_dir / "com" / "acme").mkdir(parents=True)
    (proj / ".project").write_text(_PROJECT.format(name=name), encoding="utf-8")
    (proj / ".classpath").write_text(
        f'<classpath><classpathentry kind="src" path="{source_dir}"/></classpath>\n',
        encoding="utf-8",
    )
    (proj / source_dir / "com" / "acme" / f"{cls}.java").write_text(
        f"package com.acme;\npublic class {cls} {{}}\n", encoding="utf-8"
    )


def test_dot_project_is_a_package_manifest() -> None:
    assert ".project" in package_manifest_names()


def test_each_eclipse_project_is_reported_as_a_package(tmp_path: Path) -> None:
    _eclipse_project(tmp_path, "com.acme.portal.iam.jaas", "src", "IamLoginModule")
    _eclipse_project(tmp_path, "com.acme.webdcs.common", "src.api", "CommonUtil")
    _eclipse_project(tmp_path, "com.acme.portal.iam.ws.sso", "ejbModule", "SsoBean")

    traverser = FileTraverser(tmp_path)
    files = list(traverser.traverse())
    structure = traverser.get_repo_structure(files)

    assert structure.is_monorepo
    names = {p.name: p for p in structure.packages}
    assert set(names) == {
        "com.acme.portal.iam.jaas",
        "com.acme.webdcs.common",
        "com.acme.portal.iam.ws.sso",
    }
    assert all(p.manifest_file == ".project" for p in structure.packages)
    assert names["com.acme.webdcs.common"].language == "java"
