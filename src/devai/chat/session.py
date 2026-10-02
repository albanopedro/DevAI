"""The interactive chat (D040): you approve the files before every question.

The session takes its input and output as functions, so the CLI passes the
terminal and the tests pass scripted lines.
"""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path, PurePosixPath

from devai.ai.result import AIError, LLMClient
from devai.ai.settings import AISettings
from devai.analyzer.files import list_project_files
from devai.chat.ai import chat_question, chat_request, ground_answer
from devai.chat.context import build_chat_context
from devai.chat.retrieval import ChatError, SelectedFile, extra_file, select_files
from devai.models import CheckReport, ProjectInfo
from devai.report import SEPARATOR, format_chat_answer, format_chat_files, printable

ReadLine = Callable[[str], str | None]  # prompt → typed line, or None at the end
Write = Callable[[str], None]

HELP = """\
Commands:
  /add PATH    send this file with every next question
  /drop PATH   stop sending a file added with /add
  /files       list the files added with /add
  /clear       forget the conversation so far
  /help        show this help
  /quit        leave (Ctrl+D also works)
Anything else is a question. Nothing is sent without your OK."""

APPROVAL_CHOICES = "[y]es / [n]o / drop N / add PATH: "


class ChatSession:
    def __init__(
        self,
        info: ProjectInfo,
        checks: CheckReport,
        client: LLMClient,
        settings: AISettings,
        read_line: ReadLine,
        write: Write,
        assume_yes: bool = False,
    ):
        self.info = info
        self.checks = checks
        self.client = client
        self.settings = settings
        self.read_line = read_line
        self.write = write
        self.assume_yes = assume_yes
        self.pinned: list[PurePosixPath] = []
        self.history: list[dict[str, str]] = []

    @property
    def root(self) -> Path:
        return self.info.path

    def run(self) -> None:
        self.write(self.banner())
        while True:
            line = self.read_line("\nyou> ")
            if line is None:
                return
            line = line.strip()
            if not line:
                continue
            if line.startswith("/"):
                if not self.command(line):
                    return
            else:
                self.ask(line)

    def banner(self) -> str:
        if self.settings.leaves_machine:
            where = f"Answers come from {self.settings.destination}."
        else:
            where = f"Answers come from {self.settings.destination}; nothing leaves "
            where += "this machine."
        lines = [
            f"DEVAI CHAT · {printable(self.info.name)}",
            SEPARATOR,
            where,
            "Before each question you see which files would be sent, and why.",
            "Type a question, or /help for commands.",
        ]
        if self.settings.data_note:
            lines.append(f"Note: {self.settings.data_note}.")
        return "\n".join(lines)

    # --- commands -------------------------------------------------------------

    def command(self, line: str) -> bool:
        """Run a /command. Returns False to leave the chat."""
        name, _, argument = line.partition(" ")
        argument = argument.strip()
        if name in ("/quit", "/exit"):
            return False
        if name == "/help":
            self.write(HELP)
        elif name == "/add":
            self.pin(argument)
        elif name == "/drop":
            self.unpin(argument)
        elif name == "/files":
            names = ", ".join(str(path) for path in self.pinned) or "none"
            self.write(f"Files added with /add: {names}")
        elif name == "/clear":
            self.history.clear()
            self.write("Conversation cleared: earlier questions won't be sent.")
        else:
            self.write(f"Unknown command {printable(name)}. Type /help.")
        return True

    def pin(self, name: str) -> None:
        checked = self.check_file(name)
        if checked is None:
            return
        if checked.path not in self.pinned:
            self.pinned.append(checked.path)
        self.write(f"Added {checked.path}: it goes with every next question.")

    def unpin(self, name: str) -> None:
        path = PurePosixPath(name)
        if path in self.pinned:
            self.pinned.remove(path)
            self.write(f"Dropped {path}.")
        else:
            self.write(f"{printable(name)} wasn't added with /add.")

    def check_file(self, name: str) -> SelectedFile | None:
        """The same checks as --file; reports the problem and returns None."""
        if not name:
            self.write("Which file? For example: /add src/app.py")
            return None
        try:
            allowed = list_project_files(self.root).files
            return extra_file(self.root, name, allowed, "added by you")
        except ChatError as problem:
            self.write(f"Can't use it: {problem}")
            return None

    # --- questions ------------------------------------------------------------

    def ask(self, question: str) -> None:
        try:
            pinned = tuple(str(path) for path in self.pinned)
            selection = select_files(
                self.root, question, pinned, extra_reason="added with /add"
            )
        except ChatError as problem:
            self.write(f"Can't use a file added with /add: {problem}")
            return

        files = list(selection.files)
        while True:
            context = build_chat_context(
                question,
                self.info,
                self.checks,
                replace(selection, files=tuple(files)),
                self.history,
            )
            self.write("\n".join(format_chat_files(context)))
            if not self.settings.leaves_machine or self.assume_yes:
                break
            reply = self.read_line(
                f"{chat_question(context, self.settings)} {APPROVAL_CHOICES}"
            )
            decision = self.decide(reply, files)
            if decision == "send":
                break
            if decision == "skip":
                self.write("Not sent.")
                return

        if self.settings.leaves_machine:
            self.write(f"Asking {self.settings.model}…")
        else:
            self.write(
                f"Asking {self.settings.model} locally (nothing leaves this machine)…"
            )
        try:
            result = self.client.complete(chat_request(context))
        except AIError as problem:
            self.write(f"AI chat failed: {problem}")
            return
        answer, dropped_sources, dropped_suggestions = ground_answer(
            result.report, context, self.root
        )
        self.write(
            format_chat_answer(
                replace(result, report=answer), dropped_sources, dropped_suggestions
            )
        )
        self.history.append({"question": context["question"], "answer": answer.answer})

    def decide(self, reply: str | None, files: list[SelectedFile]) -> str:
        """Apply an approval reply. Returns "send", "skip" or "again"."""
        if reply is None:
            return "skip"
        reply = reply.strip()
        if reply.lower() in ("y", "yes"):
            return "send"
        if reply.lower() in ("", "n", "no"):
            return "skip"
        verb, _, argument = reply.partition(" ")
        if verb.lower() == "drop" and argument.strip().isdigit():
            index = int(argument) - 1
            if 0 <= index < len(files):
                dropped = files.pop(index)
                self.write(f"Dropped {dropped.path} for this question.")
            else:
                self.write(f"There is no file {argument.strip()}.")
        elif verb.lower() == "add":
            checked = self.check_file(argument.strip())
            if checked is not None and all(f.path != checked.path for f in files):
                files.append(checked)
        else:
            self.write(f"Please answer {APPROVAL_CHOICES.rstrip(': ')}.")
        return "again"
