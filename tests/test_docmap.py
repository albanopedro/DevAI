from pathlib import PurePosixPath

import pytest
from conftest import write

from devai.analyzer import analyze_project
from devai.docmap import MODULE, build_docs_map, doc_sources
from devai.docmap.js_docs import DEFAULT, js_names
from devai.docmap.python_docs import NotPython, python_names
from devai.docmap.readme import check_readme, find_readme


def paths(*names):
    return [PurePosixPath(name) for name in names]


def missing(names):
    return [name for name, documented in names if not documented]


# --- Python ---------------------------------------------------------------------------


def test_python_public_names_and_their_docstrings():
    code = (
        '"""The module."""\n'
        "def run():\n"
        '    """Run it."""\n'
        "async def fetch(): pass\n"
        "class Cart:\n"
        "    def add(self): pass\n"
        "    def remove(self):\n"
        '        """Remove."""\n'
        "    async def load(self): pass\n"
        "    def __init__(self): pass\n"  # special method: not public API
        "    def _check(self): pass\n"
        "    class Meta: pass\n"  # nested class: not a method
        "class _Internal:\n"
        "    def visible(self): pass\n"  # a method of a private class
        "def _helper(): pass\n"
        "VALUE = 1\n"
    )

    assert python_names(code) == [
        (MODULE, True),
        ("run", True),
        ("fetch", False),
        ("Cart", False),
        ("Cart.add", False),
        ("Cart.remove", True),
        ("Cart.load", False),
    ]


def test_a_module_without_a_docstring():
    assert python_names("import os\n") == [(MODULE, False)]


def test_an_empty_module_has_nothing_to_document():
    assert python_names("") == []
    assert python_names("# only a comment\n") == []


def test_repeated_python_names_count_once():
    code = (
        '"""Doc."""\n'
        "class Box:\n"
        '    """A box."""\n'
        "    @property\n"
        "    def size(self):\n"
        '        """The size."""\n'
        "    @size.setter\n"
        "    def size(self, value): pass\n"
    )

    assert python_names(code) == [(MODULE, True), ("Box", True), ("Box.size", True)]


def test_invalid_python_raises():
    with pytest.raises(NotPython):
        python_names("def broken(:\n")


# --- JavaScript and TypeScript --------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "name"),
    [
        ("export function search(index, query) {", "search"),
        ("export async function api(path) {", "api"),
        ("export function* ids() {", "ids"),
        ("export default function App() {", "App"),
        ("export default function () {", DEFAULT),
        ("export default async function handler(req) {", "handler"),
        ("export class Store {", "Store"),
        ("export default class {", DEFAULT),
        ("export abstract class Base {", "Base"),
        ("export const toKey = (name) => name.trim();", "toKey"),
        ("export const toKey = name => name.trim();", "toKey"),
        ("export const load = async () => {", "load"),
        ("export const load = async id => {", "load"),
        ("export let parse = function (text) {", "parse"),
        ("export const handler: Handler = (event) => {", "handler"),
        ("  export function indented() {", "indented"),
        ("module.exports = function render(view) {", DEFAULT),
        ("module.exports = (app) => {", DEFAULT),
        ("module.exports = class Router {", DEFAULT),
        ("module.exports.render = function (view) {", "render"),
        ("exports.render = (view) => {", "render"),
    ],
)
def test_exports_that_are_found(line, name):
    assert js_names(line) == [(name, False)]


@pytest.mark.parametrize(
    "line",
    [
        "function local() {",  # not exported
        "export { search, toKey };",
        "export * from './utils';",
        "module.exports = { search, toKey };",
        "export const Button = memo(function Button() {",  # wrapped in a call
        "export const LIMIT = 30;",
        "export const NAMES = ['a', 'b'];",
        "export interface Props {",
        "export type Id = string;",
        " * export function inAComment() {",
        "// export function commentedOut() {",
    ],
)
def test_lines_that_are_not_exports(line):
    assert js_names(line) == []


@pytest.mark.parametrize(
    "above",
    [
        "/**\n * Search the index.\n * @param {string} query\n */\n",
        "/** Search the index. */\n",
        "/**\n * Search the index.\n */\n@memoize\n@trace()\n",  # decorators aside
    ],
)
def test_jsdoc_right_above_documents_an_export(above):
    assert js_names(above + "export function search() {}\n") == [("search", True)]


@pytest.mark.parametrize(
    "above",
    [
        "// Search the index.\n",
        "/* Search the index. */\n",
        "/**\n * Search the index.\n */\n\n",  # a blank line in between
        "/** Search the index. */\nconst x = 1;\n",
        "",
    ],
)
def test_other_comments_do_not_document_an_export(above):
    assert js_names(above + "export function search() {}\n") == [("search", False)]


def test_typescript_overloads_count_once():
    code = (
        "/** Parse a value. */\n"
        "export function parse(text: string): Value;\n"
        "export function parse(data: Buffer): Value;\n"
        "export function parse(input: unknown): Value {\n"
    )

    assert js_names(code) == [("parse", True)]


# --- which files are checked ----------------------------------------------------------


def test_only_relevant_source_files_are_checked():
    files = paths(
        "src/app.py",
        "src/__init__.py",
        "src/__main__.py",
        "src/_internal.py",
        "src/_vendor/lib.py",
        "src/types.pyi",
        "tests/conftest.py",
        "tests/test_app.py",
        "setup.py",
        "web/App.jsx",
        "web/App.test.jsx",
        "web/api.ts",
        "web/types.d.ts",
        "vite.config.js",
        "README.md",
        "main.go",
    )

    assert [str(p) for p in doc_sources(files)] == [
        "src/app.py",
        "src/__init__.py",
        "src/__main__.py",
        "web/App.jsx",
        "web/api.ts",
    ]


# --- README ---------------------------------------------------------------------------


def readme(tmp_path, text, *other_files):
    write(tmp_path, "README.md", text)
    for name, content in other_files:
        write(tmp_path, name, content)
    files = sorted(
        PurePosixPath(p.relative_to(tmp_path).as_posix())
        for p in tmp_path.rglob("*")
        if p.is_file()
    )
    return check_readme(tmp_path, tuple(files))


def test_sections_found_by_heading_words(tmp_path):
    result = readme(
        tmp_path,
        "# Tool\n\n## Getting Started\n\nText.\n\n## Usage\n\n## Running the tests\n",
    )

    assert result.checked is True
    assert result.sections == ("installation", "usage", "tests")
    assert result.missing_sections == ("license",)


def test_sections_in_portuguese(tmp_path):
    result = readme(
        tmp_path,
        "# Wiki\n\n## Instalação\n\n## Como ligar\n\n## Testes\n\n## Licença\n",
    )

    assert result.sections == ("installation", "usage", "tests", "license")


def test_setext_headings(tmp_path):
    result = readme(tmp_path, "Tool\n====\n\nInstallation\n------------\n")

    assert result.sections == ("installation",)


def test_words_must_start_a_heading_word(tmp_path):
    # "uso" is not in "recursos", "test" is not in "latest", "#tag" isn't a heading.
    result = readme(tmp_path, "# Recursos\n\n## The latest news\n\n#install\n")

    assert result.sections == ()


def test_comments_in_code_blocks_are_not_headings(tmp_path):
    result = readme(tmp_path, "# Tool\n\n```bash\n# install the tests\nmake\n```\n")

    assert result.sections == ()


def test_a_license_file_covers_the_license_section(tmp_path):
    result = readme(tmp_path, "# Tool\n", ("LICENSE", "MIT"))

    assert result.sections == ("license",)
    assert str(result.license_file) == "LICENSE"


PACKAGE_JSON = '{"scripts": {"dev": "vite", "test": "vitest", "test:watch": "x"}}'


def test_npm_scripts_that_do_not_exist(tmp_path):
    text = (
        "# Tool\n"
        "\n"
        "```bash\n"
        "npm install && npm run dev\n"
        "npm run deploy   # a comment\n"
        "npm run test:watch\n"
        "```\n"
        "\n"
        "Then run `npm run lint` or `npm start`. Use npm to run the server.\n"
    )

    result = readme(tmp_path, text, ("package.json", PACKAGE_JSON))

    assert result.scripts_mentioned == 5
    assert [(m.command, m.script, m.line) for m in result.missing_scripts] == [
        ("npm run deploy", "deploy", 5),
        ("npm run lint", "lint", 9),
        ("npm start", "start", 9),
    ]


@pytest.mark.parametrize(
    "command",
    [
        "npm test",
        "npm t",
        "npm run-script dev",
        "pnpm --filter web run dev",
        "npm run dev -- --port 3000",
        "npm run dev.",
    ],
)
def test_npm_commands_of_existing_scripts(tmp_path, command):
    result = readme(tmp_path, f"`{command}`\n", ("package.json", PACKAGE_JSON))

    assert result.scripts_mentioned == 1
    assert result.missing_scripts == ()


@pytest.mark.parametrize(
    "command",
    [
        "yarn run eslint",  # yarn and bun also run binaries and files
        "bun run index.ts",
        "pnpm t",  # `t` is npm's alias only
        "cargo run --release",
        "npx vite build",
        "npm install && cargo run build",
    ],
)
def test_commands_that_are_not_npm_scripts(tmp_path, command):
    result = readme(tmp_path, f"`{command}`\n", ("package.json", PACKAGE_JSON))

    assert result.scripts_mentioned == 0


def test_scripts_of_every_package_json_count(tmp_path):
    result = readme(
        tmp_path,
        "`cd web && npm run build`\n",
        ("package.json", "{}"),
        ("web/package.json", '{"scripts": {"build": "vite build"}}'),
    )

    assert result.missing_scripts == ()


def test_npm_start_runs_server_js_without_a_start_script(tmp_path):
    result = readme(
        tmp_path, "`npm start`\n", ("package.json", "{}"), ("server.js", "")
    )

    assert result.missing_scripts == ()


def test_without_package_json_every_script_is_missing(tmp_path):
    result = readme(tmp_path, "`npm run dev`\n")

    assert [m.script for m in result.missing_scripts] == ["dev"]
    assert result.scripts_checked is True


def test_an_unreadable_package_json_means_scripts_are_not_checked(tmp_path):
    result = readme(
        tmp_path,
        "`npm run dev`\n",
        ("package.json", "{ not json"),
        ("web/package.json", PACKAGE_JSON),
    )

    assert result.scripts_checked is False
    assert result.missing_scripts == ()


def test_a_script_mentioned_twice_is_listed_once(tmp_path):
    result = readme(tmp_path, "`npm run x`\n\n```\nnpm run x\n```\n")

    assert [(m.script, m.line) for m in result.missing_scripts] == [("x", 1)]


def test_the_markdown_readme_is_preferred():
    files = paths("README.rst", "README.pt-BR.md", "README.md", "docs/README.md")

    assert str(find_readme(files)) == "README.md"
    assert find_readme(paths("docs/README.md")) is None


def test_a_readme_that_is_not_markdown_is_not_checked(tmp_path):
    write(tmp_path, "README.rst", "Tool\n====\n")

    result = check_readme(tmp_path, (PurePosixPath("README.rst"),))

    assert result.checked is False
    assert result.sections == ()


# --- the map --------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path):
    write(tmp_path, "README.md", "# Tool\n\n## Usage\n\n`npm run dev`\n")
    write(tmp_path, "package.json", '{"scripts": {"dev": "vite"}}')
    write(tmp_path, "src/app.py", '"""App."""\ndef run():\n    pass\n')
    write(tmp_path, "src/broken.py", "def broken(:\n")
    write(
        tmp_path,
        "web/api.js",
        "/** Call the API. */\nexport function api() {}\nexport function send() {}\n",
    )
    write(tmp_path, "web/cart.js", "export function add() {}\nexport class Cart {}\n")
    write(tmp_path, "tests/test_app.py", "def test_run():\n    pass\n")
    return tmp_path


def test_docs_map(project):
    docs = build_docs_map(analyze_project(project))

    assert docs.sources_checked == 4
    assert docs.languages == ("JavaScript", "Python")
    assert docs.public_names == 6  # app: module, run; api: api, send; cart: add, Cart
    assert docs.documented == 2
    assert [(str(p), names) for p, names in docs.undocumented] == [
        ("web/cart.js", ("add", "Cart")),  # the file missing most comes first
        ("src/app.py", ("run",)),
        ("web/api.js", ("send",)),
    ]
    assert [str(p) for p in docs.not_parsed] == ["src/broken.py"]
    assert docs.readme.sections == ("usage",)
    assert docs.readme.missing_scripts == ()


def test_ignored_files_are_not_read(project):
    write(project, ".gitignore", "generated/\n")
    write(project, "generated/client.js", "export function call() {}\n")

    docs = build_docs_map(analyze_project(project))

    assert "generated/client.js" not in [str(p) for p, _ in docs.undocumented]


def test_a_project_without_a_readme(tmp_path):
    write(tmp_path, "app.py", '"""App."""\n')

    assert build_docs_map(analyze_project(tmp_path)).readme is None
