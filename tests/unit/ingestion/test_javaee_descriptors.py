"""Deployment descriptors name the classes a Java EE container enters (E9).

In a legacy Java EE / SAP NetWeaver estate the runtime's hand-off into source
is declared in XML, not in code: a JAAS ``LoginModuleConfiguration.xml`` names
the login module, an SAP ``portalapp.xml`` names each portal component,
``web.xml`` names servlets, filters and listeners, ``ejb-jar.xml`` names EJBs.
None of those classes has an in-source caller, so they read as dead code and
never as entry points.

The traverser skips ``.xml`` as an unknown language, so a descriptor is never in
``parsed_files`` (which is also why the Android manifest handler never fired on
a real repository: its tests hand it a synthetic parsed shell). These fixtures
deliberately do *not*: descriptors are found on disk, including under SAP's
source ``dist/PORTAL-INF/`` directory, which the traverser prunes as build
output.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import networkx as nx

from repowise.core.ingestion.framework_edges import add_framework_edges
from repowise.core.ingestion.models import FileInfo, ParsedFile
from repowise.core.ingestion.parser import ASTParser
from repowise.core.ingestion.resolvers.context import ResolverContext


def _java_only(repo: Path) -> dict[str, ParsedFile]:
    parser = ASTParser()
    out: dict[str, ParsedFile] = {}
    for src in repo.rglob("*.java"):
        rel = src.resolve().relative_to(repo.resolve()).as_posix()
        fi = FileInfo(
            path=rel,
            abs_path=str(src.resolve()),
            language="java",
            size_bytes=100,
            git_hash="",
            last_modified=datetime.now(),
            is_test=False,
            is_config=False,
            is_api_contract=False,
            is_entry_point=False,
        )
        out[rel] = parser.parse_file(fi, src.read_bytes())
    return out


def _run(repo: Path) -> nx.DiGraph:
    parsed = _java_only(repo)
    graph = nx.DiGraph()
    for p in parsed:
        graph.add_node(p, node_type="file", path=p)
    stem_map: dict[str, list[str]] = {}
    for p in parsed:
        stem_map.setdefault(Path(p).stem.lower(), []).append(p)
    ctx = ResolverContext(
        path_set=set(parsed), stem_map=stem_map, graph=nx.DiGraph(), repo_path=repo
    )
    add_framework_edges(graph, parsed, ctx)
    return graph


def _java(repo: Path, rel: str, fqn: str) -> str:
    pkg, name = fqn.rsplit(".", 1)
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"package {pkg};\npublic class {name} {{}}\n", encoding="utf-8")
    return rel


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_a_jaas_login_module_configuration_marks_its_module(tmp_path: Path) -> None:
    cls = _java(
        tmp_path, "iam.jaas/src/com/acme/jaas/IAMLoginModule.java", "com.acme.jaas.IAMLoginModule"
    )
    _write(
        tmp_path,
        "iam.jaasEAR/EarContent/META-INF/LoginModuleConfiguration.xml",
        '<?xml version="1.0"?>\n<login-modules>\n\t<login-module>\n'
        "\t\t<display-name>IAM_LoginModule</display-name>\n"
        "\t\t<class-name>com.acme.jaas.IAMLoginModule</class-name>\n"
        "\t</login-module>\n</login-modules>\n",
    )

    node = _run(tmp_path).nodes[cls]

    assert node["is_entry_point"] is True
    assert node["framework_role"] == "jaas_login_module"


def test_a_plain_jaas_config_file_marks_its_modules(tmp_path: Path) -> None:
    cls = _java(tmp_path, "src/com/acme/Ldap.java", "com.acme.Ldap")
    _write(tmp_path, "conf/jaas.config", "Portal {\n  com.acme.Ldap required debug=true;\n};\n")

    assert _run(tmp_path).nodes[cls]["framework_role"] == "jaas_login_module"


def test_an_sap_portal_component_under_dist_portal_inf_is_found(tmp_path: Path) -> None:
    cls = _java(
        tmp_path, "lang.common/src.core/com/acme/lang/CommonLang.java", "com.acme.lang.CommonLang"
    )
    _write(
        tmp_path,
        "lang.common/dist/PORTAL-INF/portalapp.xml",
        '<application>\n  <components>\n    <component name="default">\n'
        "      <component-config>\n"
        '        <property name="ClassName" value="com.acme.lang.CommonLang"/>\n'
        "      </component-config>\n    </component>\n  </components>\n</application>\n",
    )

    node = _run(tmp_path).nodes[cls]

    assert node["is_entry_point"] is True
    assert node["framework_role"] == "sap_portal_component"


def test_web_xml_servlets_filters_and_listeners(tmp_path: Path) -> None:
    servlet = _java(tmp_path, "src/com/acme/LoginServlet.java", "com.acme.LoginServlet")
    filt = _java(tmp_path, "src/com/acme/AuthFilter.java", "com.acme.AuthFilter")
    listener = _java(tmp_path, "src/com/acme/Boot.java", "com.acme.Boot")
    _write(
        tmp_path,
        "WebContent/WEB-INF/web.xml",
        '<web-app xmlns="http://java.sun.com/xml/ns/j2ee" version="2.4">\n'
        "<servlet><servlet-name>login</servlet-name>"
        "<servlet-class> com.acme.LoginServlet </servlet-class></servlet>\n"
        "<servlet><servlet-name>page</servlet-name><jsp-file>/logonPage.jsp</jsp-file></servlet>\n"
        "<filter><filter-name>auth</filter-name><filter-class>com.acme.AuthFilter</filter-class></filter>\n"
        "<listener><listener-class>com.acme.Boot</listener-class></listener>\n"
        "</web-app>\n",
    )

    graph = _run(tmp_path)

    assert graph.nodes[servlet]["framework_role"] == "servlet"
    assert graph.nodes[filt]["framework_role"] == "servlet_filter"
    assert graph.nodes[listener]["framework_role"] == "servlet_listener"
    assert all(graph.nodes[p]["is_entry_point"] for p in (servlet, filt, listener))


def test_ejb_jar_names_its_beans(tmp_path: Path) -> None:
    bean = _java(tmp_path, "ejbModule/com/acme/AccountBean.java", "com.acme.AccountBean")
    _write(
        tmp_path,
        "ejbModule/META-INF/ejb-jar.xml",
        "<ejb-jar><enterprise-beans><session><ejb-name>Account</ejb-name>"
        "<ejb-class>com.acme.AccountBean</ejb-class></session></enterprise-beans></ejb-jar>\n",
    )

    assert _run(tmp_path).nodes[bean]["framework_role"] == "ejb"


def test_an_android_manifest_on_disk_marks_its_activity(tmp_path: Path) -> None:
    """The manifest is not in parsed_files on a real repository; it must still work."""
    activity = _java(tmp_path, "app/src/main/java/com/x/MainActivity.java", "com.x.MainActivity")
    _write(
        tmp_path,
        "app/src/main/AndroidManifest.xml",
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '  <application><activity android:name="com.x.MainActivity" /></application>\n'
        "</manifest>\n",
    )

    assert _run(tmp_path).nodes[activity]["is_entry_point"] is True


def test_an_unresolvable_class_and_vendored_descriptors_change_nothing(tmp_path: Path) -> None:
    cls = _java(tmp_path, "src/com/acme/Real.java", "com.acme.Real")
    _write(
        tmp_path,
        "WebContent/WEB-INF/web.xml",
        "<web-app><servlet><servlet-class>com.missing.Nowhere</servlet-class></servlet></web-app>\n",
    )
    _write(
        tmp_path,
        "node_modules/pkg/web.xml",
        "<web-app><servlet><servlet-class>com.acme.Real</servlet-class></servlet></web-app>\n",
    )

    node = _run(tmp_path).nodes[cls]

    assert not node.get("is_entry_point")
    assert "framework_role" not in node
