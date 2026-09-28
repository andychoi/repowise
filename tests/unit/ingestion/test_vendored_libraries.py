"""Vendored third-party JavaScript is not the repository's code (E5, E4).

Classic web applications (Java EE ``WebContent/``, PHP, server-rendered apps)
check library builds straight into the tree: ``bootstrap.js``, jQuery plugins,
``js.cookie.js``. None sit under ``node_modules`` or ``vendor/`` and only the
minified ones end in ``.min.js``, so they were indexed as application code:
health-scored, dead-code candidates, and, because ``bootstrap`` is a generic
entry stem, named as a Java application's execution entry point.

A distributed library build announces itself with a preserved ``/*!`` banner
carrying a version and a licence or URL. That is the signal used here, plus
the conventional third-party directory names. Hand-written code and project
banners without a version stay indexed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repowise.core.ingestion.traverser import FileTraverser, is_vendored_library

BOOTSTRAP = """/*!
 * Bootstrap v3.3.2 (http://getbootstrap.com)
 * Copyright 2011-2015 Twitter, Inc.
 * Licensed under MIT (https://github.com/twbs/bootstrap/blob/master/LICENSE)
 */

if (typeof jQuery === 'undefined') { throw new Error('Bootstrap requires jQuery') }
"""

BLOCKUI = """/*!
 * jQuery blockUI plugin
 * Version 2.70.0-2014.11.23
 * Requires jQuery v1.7 or later
 *
 * Examples at: http://malsup.com/jquery/block/
 * Copyright (c) 2007-2013 M. Alsup
 * Dual licensed under the MIT and GPL licenses:
 */
;(function() { function setup($) { $.blockUI = function() {}; } })();
"""

COOKIE = """/*!
 * JavaScript Cookie v2.1.3
 * https://github.com/js-cookie/js-cookie
 *
 * Copyright 2006, 2015 Klaus Hartl & Fagner Brack
 * Released under the MIT license
 */
;(function (factory) { factory(); }(function () {}));
"""

APP_CODE = """(function(){
    var ERROR_CLASS = "state-error";
    function submit(form) { return form.valid(); }
})();
"""

# A purchased template copied into the project: a banner, but not a /*! build.
TEMPLATE_BANNER = """/*  SmartAdmin WebApp
    Copyright 2016 MyOrange
*/
var app = {};
"""

# A project's own preserved banner with no version is still the project's code.
PROJECT_BANNER = """/*!
 * Dealer portal account screens.
 * Owned by the portal team.
 */
function init() {}
"""

# A version without any licence, copyright or URL is not enough on its own.
VERSION_ONLY_BANNER = """/*!
 * Portal screens v2.3
 */
function init() {}
"""


@pytest.mark.parametrize("source", [BOOTSTRAP, BLOCKUI, COOKIE])
def test_a_library_build_banner_is_vendored(tmp_path: Path, source: str) -> None:
    f = tmp_path / "lib.js"
    f.write_text(source, encoding="utf-8")

    assert is_vendored_library(f)


@pytest.mark.parametrize("source", [APP_CODE, TEMPLATE_BANNER, PROJECT_BANNER, VERSION_ONLY_BANNER])
def test_application_code_is_not_vendored(tmp_path: Path, source: str) -> None:
    f = tmp_path / "app.js"
    f.write_text(source, encoding="utf-8")

    assert not is_vendored_library(f)


def _java_ee_webapp(root: Path) -> None:
    web = root / "portal" / "WebContent"
    (web / "iam" / "js").mkdir(parents=True)
    (web / "js" / "libs" / "blockui").mkdir(parents=True)
    (web / "iam" / "js" / "bootstrap.js").write_text(BOOTSTRAP, encoding="utf-8")
    (web / "js" / "libs" / "blockui" / "jquery.blockUI.js").write_text(BLOCKUI, encoding="utf-8")
    (web / "js" / "iam_account.js").write_text(APP_CODE, encoding="utf-8")
    src = root / "portal" / "src" / "com" / "acme"
    src.mkdir(parents=True)
    (src / "LoginServlet.java").write_text(
        "package com.acme;\npublic class LoginServlet {}\n", encoding="utf-8"
    )
    for d in ("bower_components/jquery", "third_party/zlib"):
        (root / d).mkdir(parents=True)
    (root / "bower_components" / "jquery" / "jquery.js").write_text(APP_CODE, encoding="utf-8")
    (root / "third_party" / "zlib" / "zlib.c").write_text(
        "int z(void){return 0;}\n", encoding="utf-8"
    )


def test_the_traverser_skips_vendored_files_and_counts_them(tmp_path: Path) -> None:
    _java_ee_webapp(tmp_path)

    traverser = FileTraverser(tmp_path)
    paths = {f.path for f in traverser.traverse()}

    assert "portal/WebContent/js/iam_account.js" in paths
    assert "portal/src/com/acme/LoginServlet.java" in paths
    assert "portal/WebContent/iam/js/bootstrap.js" not in paths
    assert "portal/WebContent/js/libs/blockui/jquery.blockUI.js" not in paths
    assert not any(p.startswith(("bower_components/", "third_party/")) for p in paths)
    assert traverser.stats.skipped_vendored == 2


def test_a_vendored_bootstrap_is_never_an_entry_point(tmp_path: Path) -> None:
    """E4: the generic ``bootstrap`` stem flagged a library build as the entry."""
    _java_ee_webapp(tmp_path)

    entries = {f.path for f in FileTraverser(tmp_path).traverse() if f.is_entry_point}

    assert "portal/WebContent/iam/js/bootstrap.js" not in entries
