"""Java sources: external imports and their usages (spec 026.7, FR-7, AC-5).

Four things the profile has to get right, and the tests follow them:

1. **Every import form** becomes a fact keyed by FQCN — single, nested, static,
   wildcard and static-wildcard (AC-5).
2. **Every usage site** is recorded where it happens: a type, an annotation and
   its attributes, and ``C.m(…)`` / ``C.FIELD`` (AC-5).
3. **Own packages are not facts**, and a wildcard import lists exactly the
   simple names it could have supplied (AC-5.2).
4. **A file that does not parse loses nothing that did** (AC-5.4).

The last part of the file is the end-to-end fixture and the failure modes a real
repo has.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from migration_planner.scanner import builtin, contract
from migration_planner.scanner.contract import FileFacts, ModuleEnv, SourceContext
from migration_planner.scanner.java import extract_java, filter_own_packages
from migration_planner.scanner.scan import scan

from .conftest import FIXTURES, read_profile


@pytest.fixture(autouse=True)
def installed_registry():
    """``scan()`` installs nothing; a scan test asks for the shipped extractors."""
    contract.reset_registry()
    builtin.install()
    yield
    contract.reset_registry()


@pytest.fixture()
def spring_java(tmp_path: Path) -> Path:
    """The Java fixture: main + test sources, own packages, both wildcard forms."""
    target = tmp_path / "spring-java"
    shutil.copytree(FIXTURES / "spring-java", target)
    return target


def _facts(
    source: str,
    *,
    package: str = "com.acme.app",
    test: bool = False,
    relative: str = "App.java",
    group_ids: tuple[str, ...] = (
        "org.springframework",
        "org.junit",
        "org.mockito",
        "org.assertj",
    ),
    own_group_ids: tuple[str, ...] = (),
) -> FileFacts:
    """Extract one in-memory file, the way ``scan()`` would call the extractor."""
    body = f"package {package};\n\n{source}" if package else source
    return extract_java(
        SourceContext(
            path=Path(relative),
            relative=relative,
            module=".",
            language="java",
            test=test,
            data=body.encode("utf-8"),
            env=ModuleEnv(
                module=".", group_ids=group_ids, own_group_ids=own_group_ids
            ),
        )
    )


def _keys(usages) -> list[str]:
    return sorted(usage.key for usage in usages)


def _sites(usages) -> list[tuple[str, int]]:
    return [(usage.key, usage.line) for usage in usages]


def _scan(repo: Path):
    result = scan(repo, out=repo / "profile.json")
    profile = read_profile(repo / "profile.json")
    symbols = {entry["key"]: entry for entry in profile["symbols"]}
    members = {entry["key"]: entry for entry in profile["members"]}
    wildcards = {entry["key"]: entry for entry in profile["wildcard_imports"]}
    return result, profile, symbols, members, wildcards


# --- AC-5: every import form ---------------------------------------------


def test_a_single_import_is_a_symbol_at_its_own_line() -> None:
    facts = _facts(
        "import org.springframework.boot.SpringApplication;\n"
        "class App {}\n"
    )

    assert _sites(facts.symbols) == [
        ("maven:org.springframework.boot.SpringApplication", 3)
    ]


def test_a_nested_type_import_keeps_its_dots() -> None:
    facts = _facts(
        "import org.springframework.util.Assert.State;\n"
        "class App { Object o = null; }\n"
    )

    assert "maven:org.springframework.util.Assert.State" in _keys(facts.symbols)


def test_a_static_import_is_a_member_of_its_class() -> None:
    facts = _facts(
        "import static org.junit.jupiter.api.Assertions.assertEquals;\n"
        "class App {}\n"
    )

    assert _keys(facts.members) == ["maven:org.junit.jupiter.api.Assertions.assertEquals"]
    assert _keys(facts.symbols) == []


def test_a_wildcard_import_is_its_own_section() -> None:
    facts = _facts(
        "import org.springframework.web.bind.annotation.*;\n"
        "@RestController\nclass App {}\n"
    )

    assert _keys(facts.wildcard_imports) == [
        "maven:org.springframework.web.bind.annotation.*"
    ]
    # The annotation the wildcard supplies is a name under that entry, not a
    # symbol of its own: no FQCN is written anywhere.
    assert _keys(facts.symbols) == []
    assert facts.wildcard_imports[0].names == ("RestController",)


def test_a_static_wildcard_import_is_its_own_section() -> None:
    facts = _facts(
        "import static org.mockito.Mockito.*;\n"
        "class App { void f() { mock(Object.class); verify(1); } }\n"
    )

    assert _keys(facts.wildcard_imports) == ["maven:org.mockito.Mockito.*"]
    assert facts.wildcard_imports[0].names == ("mock", "verify")


# --- AC-5: usage sites ---------------------------------------------------


def test_a_type_use_is_a_symbol_at_the_use_site() -> None:
    """A field, a parameter, a generic argument, ``new``, a cast, ``extends``."""
    facts = _facts(
        "import org.springframework.http.ResponseEntity;\n"
        "import java.util.List;\n"
        "class App extends Base {\n"
        "  private ResponseEntity<String> one;\n"
        "  List<ResponseEntity> many;\n"
        "  void f(ResponseEntity p) {\n"
        "    Object o = new ResponseEntity<>();\n"
        "    Object c = (ResponseEntity) o;\n"
        "  }\n"
        "}\n"
    )

    assert [key for key, _ in _sites(facts.symbols)] == [
        # the two imports
        "maven:org.springframework.http.ResponseEntity",
        "maven:java.util.List",
        # the field, its generic argument, and the generic argument of ``List``
        "maven:org.springframework.http.ResponseEntity",
        "maven:java.util.List",
        "maven:org.springframework.http.ResponseEntity",
        # the parameter, ``new``, and the cast
        "maven:org.springframework.http.ResponseEntity",
        "maven:org.springframework.http.ResponseEntity",
        "maven:org.springframework.http.ResponseEntity",
    ]


def test_an_annotation_and_its_attributes_are_facts() -> None:
    """``@C(attr = …)`` → the annotation plus one member per attribute."""
    facts = _facts(
        "import org.springframework.web.bind.annotation.RequestMapping;\n"
        "import org.springframework.web.bind.annotation.RequestMethod;\n"
        "@RequestMapping(value = \"/x\", method = RequestMethod.GET)\n"
        "class App {}\n"
    )

    assert ("maven:org.springframework.web.bind.annotation.RequestMapping", 5) in _sites(
        facts.symbols
    )
    assert _keys(facts.members) == [
        "maven:org.springframework.web.bind.annotation.RequestMapping.method",
        "maven:org.springframework.web.bind.annotation.RequestMapping.value",
        "maven:org.springframework.web.bind.annotation.RequestMethod.GET",
    ]


def test_the_single_value_annotation_shorthand_is_the_value_attribute() -> None:
    """``@C("x")`` sets ``value``, which AC-5 names explicitly."""
    facts = _facts(
        "import org.springframework.context.annotation.Profile;\n"
        '@Profile("prod")\n'
        "class App {}\n"
    )

    assert _keys(facts.members) == [
        "maven:org.springframework.context.annotation.Profile.value"
    ]


def test_a_marker_annotation_has_no_member() -> None:
    facts = _facts(
        "import org.springframework.stereotype.Component;\n"
        "@Component\n"
        "class App {}\n"
    )

    assert facts.members == []
    # The import site and the annotation are both symbols.
    assert _keys(facts.symbols) == [
        "maven:org.springframework.stereotype.Component",
        "maven:org.springframework.stereotype.Component",
    ]


def test_a_qualified_call_and_a_field_read_are_members() -> None:
    """AC-5: ``C.m(…)`` and ``C.FIELD``."""
    facts = _facts(
        "import org.springframework.boot.SpringApplication;\n"
        "import org.springframework.http.HttpStatus;\n"
        "class App {\n"
        "  void f() {\n"
        "    SpringApplication.run(App.class);\n"
        "    HttpStatus status = HttpStatus.OK;\n"
        "  }\n"
        "}\n"
    )

    assert "maven:org.springframework.boot.SpringApplication.run" in _keys(facts.members)
    assert "maven:org.springframework.http.HttpStatus.OK" in _keys(facts.members)


def test_a_chain_records_the_first_segment_after_the_class() -> None:
    """``RequestMethod.GET.name()`` is ``RequestMethod.GET``, not a member of ``GET``."""
    facts = _facts(
        "import org.springframework.web.bind.annotation.RequestMethod;\n"
        "class App { String f() { return RequestMethod.GET.name(); } }\n"
    )

    assert _keys(facts.members) == [
        "maven:org.springframework.web.bind.annotation.RequestMethod.GET"
    ]


def test_a_static_import_used_bare_is_a_member_at_the_use_site() -> None:
    facts = _facts(
        "import static org.junit.jupiter.api.Assertions.assertEquals;\n"
        "class App {\n"
        "  void f() {\n"
        "    assertEquals(1, 2);\n"
        "  }\n"
        "}\n"
    )

    assert _sites(facts.members) == [
        ("maven:org.junit.jupiter.api.Assertions.assertEquals", 3),
        ("maven:org.junit.jupiter.api.Assertions.assertEquals", 6),
    ]


def test_a_call_on_a_variable_is_not_resolved() -> None:
    """spec1 Non-Goals: instance calls on variables are not attributed."""
    facts = _facts(
        "import org.springframework.http.ResponseEntity;\n"
        "class App {\n"
        "  void f(ResponseEntity entity) {\n"
        "    entity.getStatusCode();\n"
        "  }\n"
        "}\n"
    )

    assert facts.members == []


def test_a_static_import_on_a_nested_type_is_a_symbol() -> None:
    """``import static a.b.Outer.Inner`` binds a type, so a use is a symbol."""
    facts = _facts(
        "import static org.springframework.util.Assert.State;\n"
        "class App { State state; }\n",
        group_ids=("org.springframework",),
    )
    # A symbol at the import line too, never a member (spec7 review fix 4).
    assert _sites(facts.symbols) == [
        ("maven:org.springframework.util.Assert.State", 3),
        ("maven:org.springframework.util.Assert.State", 4),
    ]
    assert facts.members == []


def test_a_static_import_of_a_constant_or_method_stays_a_member() -> None:
    """``APPLICATION_JSON`` and ``assertEquals`` are not types: no capital + lower case."""
    facts = _facts(
        "import static org.springframework.http.MediaType.APPLICATION_JSON;\n"
        "import static org.junit.jupiter.api.Assertions.assertEquals;\n"
        "class App {}\n"
    )

    assert facts.symbols == []
    assert _keys(facts.members) == [
        "maven:org.junit.jupiter.api.Assertions.assertEquals",
        "maven:org.springframework.http.MediaType.APPLICATION_JSON",
    ]


def test_an_import_whose_package_starts_with_static_is_not_static() -> None:
    """``import statics.Foo`` is a class import, keyed by its whole name."""
    facts = _facts("import statics.Foo;\nclass App {}\n")

    assert _keys(facts.symbols) == ["maven:statics.Foo"]
    assert facts.members == []


def test_a_comment_inside_an_import_is_not_part_of_the_key() -> None:
    facts = _facts(
        "import org.springframework /* web */ .http.HttpStatus;\n"
        "import static org.springframework.http.HttpStatus // the enum\n"
        "    .OK;\n"
        "class App {}\n"
    )

    assert _keys(facts.symbols) == ["maven:org.springframework.http.HttpStatus"]
    assert _keys(facts.members) == ["maven:org.springframework.http.HttpStatus.OK"]


# --- FR-7: own packages --------------------------------------------------


def test_an_import_of_an_own_package_is_skipped(make_repo) -> None:
    """A sibling module's class is the repo's own code, not an external library."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>svc</artifactId>"
                "<version>1</version><dependencies><dependency>"
                "<groupId>org.springframework</groupId><artifactId>spring-web</artifactId>"
                "<version>6.1.0</version></dependency></dependencies></project>"
            ),
            "src/main/java/com/acme/app/App.java": (
                "package com.acme.app;\n"
                "import com.acme.service.Order;\n"
                "import org.springframework.stereotype.Component;\n"
                "@Component\n"
                "class App { Order order; }\n"
            ),
            "src/main/java/com/acme/service/Order.java": (
                "package com.acme.service;\npublic class Order {}\n"
            ),
        }
    )

    _, profile, symbols, _, _ = _scan(repo)

    assert "maven:com.acme.service.Order" not in symbols
    assert "maven:org.springframework.stereotype.Component" in symbols
    assert profile["diagnostics"] == []


def test_an_own_package_prefix_is_matched_segment_by_segment(make_repo) -> None:
    """``com.acme.shop`` owns ``com.acme.shop.web.X``, not ``com.acme.shopping.Y``."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>svc</artifactId>"
                "<version>1</version><dependencies><dependency>"
                "<groupId>com.acme.shopping</groupId><artifactId>cart</artifactId>"
                "<version>1</version></dependency></dependencies></project>"
            ),
            "src/main/java/com/acme/shop/App.java": (
                "package com.acme.shop;\n"
                "import com.acme.shopping.Cart;\n"
                "import com.acme.shop.web.Controller;\n"
                "class App { Cart cart; Controller c; }\n"
            ),
            "src/main/java/com/acme/shop/web/Controller.java": (
                "package com.acme.shop.web;\npublic class Controller {}\n"
            ),
        }
    )

    _, _, symbols, _, _ = _scan(repo)

    assert "maven:com.acme.shopping.Cart" in symbols
    assert "maven:com.acme.shop.web.Controller" not in symbols


def test_a_file_with_no_package_declaration_is_handled(make_repo) -> None:
    """The default package is not an own package, so nothing is filtered."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>svc</artifactId>"
                "<version>1</version><dependencies><dependency>"
                "<groupId>org.springframework</groupId><artifactId>spring-web</artifactId>"
                "<version>6.1.0</version></dependency></dependencies></project>"
            ),
            "src/main/java/DefaultPackage.java": (
                "import org.springframework.stereotype.Component;\n"
                "@Component\nclass DefaultPackage {}\n"
            ),
        }
    )

    _, profile, symbols, _, _ = _scan(repo)

    assert symbols["maven:org.springframework.stereotype.Component"]["count"] == 2
    assert profile["diagnostics"] == []


def test_an_import_of_the_files_own_package_is_not_a_fact(make_repo) -> None:
    """A class in the same package is imported without a path at all."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>svc</artifactId>"
                "<version>1</version><dependencies><dependency>"
                "<groupId>org.springframework</groupId><artifactId>spring-web</artifactId>"
                "<version>6.1.0</version></dependency></dependencies></project>"
            ),
            "src/main/java/com/acme/app/App.java": (
                "package com.acme.app;\n"
                "import com.acme.app.Helper;\n"
                "class App { Helper helper; }\n"
            ),
            "src/main/java/com/acme/app/Helper.java": (
                "package com.acme.app;\npublic class Helper {}\n"
            ),
        }
    )

    _, _, symbols, members, _ = _scan(repo)

    assert symbols == {}
    assert members == {}


def test_the_post_pass_is_the_own_package_filter() -> None:
    """The filter is a post-pass (spec1 contract), not part of the extractor."""
    assert filter_own_packages in contract.post_passes()
    assert "java" in contract.source_extractors()
    assert contract.source_extractors()["java"] is extract_java


# --- AC-5.2: wildcard names ----------------------------------------------


def test_a_wildcard_lists_every_simple_name_it_could_supply() -> None:
    facts = _facts(
        "import java.util.*;\n"
        "class App {\n"
        "  Map<String, Integer> counts;\n"
        "  int size() { return Arrays.asList(1).size(); }\n"
        "}\n"
    )

    assert facts.wildcard_imports[0].names == ("Arrays", "Map")


def test_a_name_declared_in_the_file_is_not_under_the_wildcard() -> None:
    """AC-5.2: a name the file declares itself needs no import."""
    facts = _facts(
        "import java.util.*;\n"
        "class App {\n"
        "  Report report;\n"
        "  record Report(int size) {}\n"
        "}\n"
    )

    assert facts.wildcard_imports[0].names == ()


def test_a_java_lang_type_is_not_under_a_wildcard() -> None:
    """``String`` and ``Object`` are imported implicitly; no wildcard supplies them."""
    facts = _facts(
        "import java.util.*;\n"
        "class App {\n"
        "  String name(Object value) { return List.of().toString(); }\n"
        "}\n"
    )

    assert facts.wildcard_imports[0].names == ("List",)


def test_a_variable_name_is_never_under_a_wildcard() -> None:
    """``list.add(x)`` is a call on a variable: the Java type convention rules it out."""
    facts = _facts(
        "import java.util.*;\n"
        "class App {\n"
        "  void f(List<String> list) { list.add(null); entity.save(); }\n"
        "}\n"
    )

    assert facts.wildcard_imports[0].names == ("List",)


def test_two_wildcard_packages_both_list_an_unexplained_name() -> None:
    """Without a classpath the scanner cannot tell which package declares a name.

    Listing it under each is the safe direction: a missing name would drop a rule
    that applies, while an extra one only gives a matcher something to verify.
    """
    facts = _facts(
        "import java.util.*;\n"
        "import java.time.*;\n"
        "class App { Duration span; Map<String, String> m; }\n"
    )

    by_key = {usage.key: usage.names for usage in facts.wildcard_imports}

    assert by_key == {
        "maven:java.util.*": ("Duration", "Map"),
        "maven:java.time.*": ("Duration", "Map"),
    }


def test_a_static_wildcard_does_not_claim_a_type_name() -> None:
    """A class name is not a member, so a static wildcard does not list it."""
    facts = _facts(
        "import java.util.*;\n"
        "import static java.util.Collections.*;\n"
        "class App { Map<String, String> m; void f() { sort(null); } }\n"
    )

    by_key = {usage.key: usage.names for usage in facts.wildcard_imports}

    assert by_key == {
        "maven:java.util.*": ("Map",),
        "maven:java.util.Collections.*": ("sort",),
    }


def test_annotation_attributes_under_a_wildcard_are_members() -> None:
    """``@RequestMapping(method = …)`` with ``import …annotation.*`` keeps its attributes."""
    facts = _facts(
        "import org.springframework.web.bind.annotation.*;\n"
        '@RequestMapping(path = "/a", method = RequestMethod.GET)\n'
        "class App {\n"
        '  @GetMapping("/b") void b() {}\n'
        "}\n"
    )

    prefix = "maven:org.springframework.web.bind.annotation"
    assert _sites(facts.members) == [
        (f"{prefix}.RequestMapping.path", 4),
        (f"{prefix}.RequestMapping.method", 4),
        (f"{prefix}.GetMapping.value", 6),
    ]
    assert facts.wildcard_imports[0].names == (
        "GetMapping",
        "RequestMapping",
        "RequestMethod",
    )


def test_a_declared_or_java_lang_annotation_is_not_put_under_a_wildcard() -> None:
    facts = _facts(
        "import org.springframework.web.bind.annotation.*;\n"
        "class App {\n"
        '  @Deprecated(since = "1") @Local(x = 1) void m() {}\n'
        "  @interface Local { int x(); }\n"
        "}\n"
    )

    assert facts.members == []


def test_an_own_wildcard_package_supplies_no_name_to_an_external_one(make_repo) -> None:
    """``Widget`` from an own ``com.acme.app.sub.*`` is not under Spring's wildcard."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>svc</artifactId>"
                "<version>1</version><dependencies><dependency>"
                "<groupId>org.springframework</groupId><artifactId>spring-web</artifactId>"
                "<version>6.1.0</version></dependency></dependencies></project>"
            ),
            "src/main/java/com/acme/app/App.java": (
                "package com.acme.app;\n"
                "import com.acme.app.sub.*;\n"
                "import org.springframework.web.bind.annotation.*;\n"
                '@RequestMapping(path = "/a")\n'
                "class App {\n"
                '  @Audited(level = "x") Widget widget;\n'
                "}\n"
            ),
            "src/main/java/com/acme/app/sub/Widget.java": (
                "package com.acme.app.sub;\npublic class Widget {}\n"
            ),
            "src/main/java/com/acme/app/sub/Audited.java": (
                "package com.acme.app.sub;\npublic @interface Audited { String level(); }\n"
            ),
        }
    )

    _, _, _, members, wildcards = _scan(repo)

    prefix = "maven:org.springframework.web.bind.annotation"
    assert list(wildcards) == [f"{prefix}.*"]
    assert wildcards[f"{prefix}.*"]["names"] == ["RequestMapping"]
    assert list(members) == [f"{prefix}.RequestMapping.path"]


def test_an_explicit_import_keeps_its_members_when_an_own_type_shares_its_name(
    make_repo,
) -> None:
    """The own-wildcard filter only drops what nothing else explains."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>svc</artifactId>"
                "<version>1</version><dependencies><dependency>"
                "<groupId>org.springframework</groupId><artifactId>spring-web</artifactId>"
                "<version>6.1.0</version></dependency></dependencies></project>"
            ),
            "src/main/java/com/acme/app/App.java": (
                "package com.acme.app;\n"
                "import org.springframework.http.*;\n"
                "import org.springframework.http.HttpStatus;\n"
                "class App { Object s = HttpStatus.OK; }\n"
            ),
            "src/main/java/com/acme/app/HttpStatus.java": (
                "package com.acme.app;\npublic enum HttpStatus { OK }\n"
            ),
        }
    )

    _, _, _, members, _ = _scan(repo)

    assert "maven:org.springframework.http.HttpStatus.OK" in members


def test_a_wildcard_entry_unions_the_names_of_the_files_that_use_it(make_repo) -> None:
    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>svc</artifactId>"
                "<version>1</version><dependencies><dependency>"
                "<groupId>java</groupId><artifactId>x</artifactId><version>1</version>"
                "</dependency></dependencies></project>"
            ),
            "src/main/java/com/acme/A.java": (
                "package com.acme;\nimport java.util.*;\nclass A { Map<String, String> m; }\n"
            ),
            "src/main/java/com/acme/B.java": (
                "package com.acme;\nimport java.util.*;\nclass B { Arrays a; }\n"
            ),
        }
    )

    _, _, _, _, wildcards = _scan(repo)

    assert set(wildcards["maven:java.util.*"]["names"]) == {"Arrays", "Map"}
    assert wildcards["maven:java.util.*"]["count"] == 2


def test_a_wildcard_name_the_files_own_package_declares_is_dropped(make_repo) -> None:
    """``A`` is declared in ``com.acme``, so ``java.util.*`` cannot be supplying it."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>svc</artifactId>"
                "<version>1</version><dependencies><dependency>"
                "<groupId>java</groupId><artifactId>x</artifactId><version>1</version>"
                "</dependency></dependencies></project>"
            ),
            "src/main/java/com/acme/A.java": "package com.acme;\npublic class A {}\n",
            "src/main/java/com/acme/B.java": (
                "package com.acme;\n"
                "import java.util.*;\n"
                "class B { A a; Map<String, String> m; }\n"
            ),
        }
    )

    _, _, _, _, wildcards = _scan(repo)

    assert wildcards["maven:java.util.*"]["names"] == ["Map"]


# --- AC-5.3: tests ------------------------------------------------------


def test_a_test_source_records_test_true(spring_java: Path) -> None:
    """AC-5.3: ``@MockBean`` in ``src/test/java`` → a location with ``test: true``."""
    _, _, symbols, _, _ = _scan(spring_java)

    entry = symbols["maven:org.springframework.boot.test.mock.mockito.MockBean"]
    assert {location["test"] for location in entry["locations"]} == {True}
    assert entry["locations"][0]["file"] == (
        "src/test/java/com/acme/shop/web/CatalogServiceTests.java"
    )


def test_a_gradle_test_source_set_records_test_true(make_repo) -> None:
    """``src/integrationTest/java`` is test code (FR-1), like ``src/test/java``."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>svc</artifactId>"
                "<version>1</version><dependencies><dependency>"
                "<groupId>org.springframework.boot</groupId>"
                "<artifactId>spring-boot-starter-test</artifactId>"
                "<version>3.3.4</version></dependency></dependencies></project>"
            ),
            "src/componentTest/java/com/acme/ACT.java": (
                "package com.acme;\n"
                "import org.springframework.boot.test.mock.mockito.MockBean;\n"
                "class ACT { @MockBean Object service; }\n"
            ),
        }
    )

    _, _, symbols, _, _ = _scan(repo)

    entry = symbols["maven:org.springframework.boot.test.mock.mockito.MockBean"]
    assert {location["test"] for location in entry["locations"]} == {True}


def test_a_main_source_records_test_false(spring_java: Path) -> None:
    _, _, symbols, _, _ = _scan(spring_java)

    entry = symbols["maven:org.springframework.boot.SpringApplication"]
    assert {location["test"] for location in entry["locations"]} == {False}


# --- AC-5.4: a syntax error ---------------------------------------------


def test_a_file_with_a_syntax_error_keeps_the_imports_that_parsed() -> None:
    facts = _facts(
        "import org.springframework.stereotype.Component;\n"
        "@Component\n"
        "class Broken {\n"
        "  void f( {\n"
        "}\n"
    )

    assert "maven:org.springframework.stereotype.Component" in _keys(facts.symbols)
    assert [diagnostic.kind for diagnostic in facts.diagnostics] == [
        "partial_parse_error"
    ]


def test_a_file_that_cannot_be_parsed_at_all_is_one_diagnostic() -> None:
    """Nothing parses, so there is one ``parse_error`` and no partial parse."""
    facts = _facts("}}} not java {{{\n", package="")

    assert facts.symbols == []
    assert facts.members == []
    assert [diagnostic.kind for diagnostic in facts.diagnostics] == ["parse_error"]


@pytest.mark.parametrize(
    "source",
    [
        "",
        "import org.springframework.boot.SpringApplication;\n",
        "class {",
        "package",
        "import",
        "import static",
        "@",
        "class A { void f() { new } }",
        "import org.springframework.a.*;\nclass A {",
    ],
)
def test_a_truncated_source_never_raises(source: str) -> None:
    facts = _facts(source)

    assert facts.package_name == "com.acme.app"


# --- FR-7: fully qualified usages without an import ---------------------


def test_a_fully_qualified_usage_with_no_import_is_a_fact() -> None:
    facts = _facts(
        "class App {\n"
        "  void f() {\n"
        "    org.springframework.util.Assert.notNull(this);\n"
        "  }\n"
        "}\n"
    )

    assert "maven:org.springframework.util.Assert.notNull" in _keys(facts.members)
    assert "maven:org.springframework.util.Assert" in _keys(facts.symbols)

def test_a_fully_qualified_annotation_with_no_import_is_a_fact() -> None:
    facts = _facts("@org.springframework.stereotype.Component\nclass App {}\n")

    assert _keys(facts.symbols) == ["maven:org.springframework.stereotype.Component"]


def test_a_fully_qualified_own_class_is_not_a_fact() -> None:
    """Without a declared groupId the name is not external, so it is not recorded."""
    facts = _facts("class App { com.acme.other.Thing t; }\n")

    assert facts.symbols == []


def test_a_parent_group_id_is_external_too() -> None:
    """Starters declare ``org.springframework.boot``; ``spring-core`` is its parent's."""
    facts = _facts(
        "class App {\n"
        "  void f() {\n"
        "    org.springframework.util.Assert.notNull(this);\n"
        "  }\n"
        "}\n",
        group_ids=("org.springframework.boot",),
    )

    assert "maven:org.springframework.util.Assert.notNull" in _keys(facts.members)


def test_a_one_segment_parent_is_not_a_prefix() -> None:
    """``io.micrometer`` does not make every ``io.…`` name external."""
    facts = _facts(
        "class App { io.netty.Channel channel; }\n", group_ids=("io.micrometer",)
    )

    assert facts.symbols == []


def test_a_parent_group_id_that_reaches_own_code_is_not_a_prefix() -> None:
    """``com.acme.platform`` → ``com.acme`` would claim the repo's ``com.acme.shop``."""
    facts = _facts(
        "class App { com.acme.shop.Order order; com.acme.platform.Widget widget; }\n",
        group_ids=("com.acme.platform",),
        own_group_ids=("com.acme.shop",),
    )

    assert _keys(facts.symbols) == ["maven:com.acme.platform.Widget"]


def test_the_scan_passes_own_group_ids_for_the_parent_rule(make_repo) -> None:
    """A starter-only pom still records a fully qualified ``spring-core`` call."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><parent><groupId>org.springframework.boot</groupId>"
                "<artifactId>spring-boot-starter-parent</artifactId>"
                "<version>3.2.0</version></parent><groupId>com.acme</groupId>"
                "<artifactId>svc</artifactId><version>1</version><dependencies>"
                "<dependency><groupId>org.springframework.boot</groupId>"
                "<artifactId>spring-boot-starter-web</artifactId></dependency>"
                "</dependencies></project>"
            ),
            "src/main/java/com/acme/app/App.java": (
                "package com.acme.app;\n"
                "class App {\n"
                "  void f() { org.springframework.util.Assert.notNull(this, \"x\"); }\n"
                "}\n"
            ),
        }
    )

    _, _, symbols, members, _ = _scan(repo)

    assert "maven:org.springframework.util.Assert" in symbols
    assert "maven:org.springframework.util.Assert.notNull" in members


def test_an_own_group_id_is_removed_by_the_scan(make_repo) -> None:
    """A dependency on a sibling module never makes ``com.acme.…`` look external."""
    repo = make_repo(
        {
            "pom.xml": (
                "<project><groupId>com.acme</groupId><artifactId>root</artifactId>"
                "<version>1</version><packaging>pom</packaging>"
                "<modules><module>app</module><module>lib</module></modules></project>"
            ),
            "app/pom.xml": (
                "<project><parent><groupId>com.acme</groupId><artifactId>root</artifactId>"
                "<version>1</version></parent><artifactId>app</artifactId>"
                "<dependencies><dependency><groupId>com.acme.platform</groupId>"
                "<artifactId>lib</artifactId><version>1</version></dependency>"
                "<dependency><groupId>org.springframework</groupId>"
                "<artifactId>spring-web</artifactId><version>6.1.0</version></dependency>"
                "</dependencies></project>"
            ),
            "lib/pom.xml": (
                "<project><parent><groupId>com.acme</groupId><artifactId>root</artifactId>"
                "<version>1</version></parent><groupId>com.acme.platform</groupId>"
                "<artifactId>lib</artifactId></project>"
            ),
            "app/src/main/java/com/acme/app/App.java": (
                "package com.acme.app;\n"
                "class App {\n"
                "  void f() {\n"
                "    com.acme.platform.Widget.make();\n"
                "    org.springframework.util.Assert.notNull(this);\n"
                "  }\n"
                "}\n"
            ),
        }
    )

    _, _, symbols, members, _ = _scan(repo)

    assert not any(key.startswith("maven:com.acme") for key in symbols)
    assert not any(key.startswith("maven:com.acme") for key in members)
    assert "maven:org.springframework.util.Assert.notNull" in members


# --- the fixture end to end ---------------------------------------------


def test_the_fixture_profile(spring_java: Path) -> None:
    result, profile, symbols, members, wildcards = _scan(spring_java)

    assert result.summary.framework == "spring-boot"
    # Own packages are not facts: the fixture imports its own service classes.
    assert not any(key.startswith("maven:com.acme") for key in symbols)
    assert not any(key.startswith("maven:com.acme") for key in members)
    # The Spring imports are, with a location each.
    assert "maven:org.springframework.web.bind.annotation.RequestMapping" in symbols
    assert "maven:org.springframework.web.bind.annotation.RequestMapping.method" in members
    assert "maven:org.springframework.util.Assert.isTrue" in members
    # Both wildcard forms, with the names they supply.
    assert set(wildcards) == {"maven:java.util.*", "maven:java.util.Collections.*"}
    assert wildcards["maven:java.util.*"]["names"] == [
        "Arrays",
        "HashMap",
        "List",
        "Map",
    ]
    assert wildcards["maven:java.util.Collections.*"]["names"] == ["emptyList", "sort"]
    # AC-5.4: the broken file is one diagnostic, not a lost scan.
    assert [
        (entry["kind"], entry["file"])
        for entry in profile["diagnostics"]
        if entry["kind"].endswith("parse_error")
    ] == [
        (
            "partial_parse_error",
            "src/main/java/com/acme/shop/reports/BrokenReport.java",
        )
    ]


def test_the_fixture_counts_reach_the_summary(spring_java: Path) -> None:
    result = scan(spring_java, out=spring_java / "p.json")

    assert result.summary.symbols == len(result.profile.symbols)
    assert result.summary.members == len(result.profile.members)
    assert result.summary.symbols > 0
    assert result.summary.members > 0


def test_a_scan_of_java_sources_is_deterministic(spring_java: Path) -> None:
    first = scan(spring_java, out=spring_java / "a.json").profile
    second = scan(spring_java, out=spring_java / "b.json").profile

    assert [(entry.key, entry.count) for entry in first.symbols] == [
        (entry.key, entry.count) for entry in second.symbols
    ]
    assert first.inputs_hash == second.inputs_hash


def test_the_java_extractor_handles_only_java() -> None:
    facts = extract_java(
        SourceContext(
            path=Path("a.ts"),
            relative="a.ts",
            module=".",
            language="ts",
            data=b"const a = 1;",
        )
    )

    assert facts.symbols == [] and facts.members == []
