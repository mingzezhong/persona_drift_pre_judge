import pathlib
import re
import unittest
from collections.abc import Iterator


ROOT = pathlib.Path(__file__).parents[1]
README = ROOT / "README.md"

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
BACKTICK_RUN_RE = re.compile(r"`+")
CURRENCY_RE = re.compile(
    r"\$(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?"
)


def _mask_inline_code_spans(line: str) -> str:
    """Mask CommonMark code spans only when backtick-run lengths match."""

    runs = list(BACKTICK_RUN_RE.finditer(line))
    masked = list(line)
    cursor = 0

    while cursor < len(runs):
        opener = runs[cursor]
        closer_index = None
        for candidate_index in range(cursor + 1, len(runs)):
            if len(runs[candidate_index].group(0)) == len(opener.group(0)):
                closer_index = candidate_index
                break
        if closer_index is None:
            cursor += 1
            continue

        closer = runs[closer_index]
        for index in range(opener.start(), closer.end()):
            masked[index] = " "
        cursor = closer_index + 1

    return "".join(masked)


def _outside_code_lines(text: str) -> Iterator[str]:
    fence_char = None
    fence_length = 0

    for line in text.splitlines():
        match = FENCE_RE.match(line)
        if fence_char is not None:
            if match:
                marker = match.group(1)
                if (
                    marker[0] == fence_char
                    and len(marker) >= fence_length
                    and not match.group(2).strip()
                ):
                    fence_char = None
                    fence_length = 0
            continue

        if match:
            marker = match.group(1)
            fence_char = marker[0]
            fence_length = len(marker)
            continue

        # GitHub/CommonMark treats four-space or tab indentation as code.
        if line.startswith("    ") or line.startswith("\t"):
            continue

        yield _mask_inline_code_spans(line)

    if fence_char is not None:
        raise AssertionError("README contains an unclosed fenced code block")


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _unescaped_dollar_positions(line: str) -> list[int]:
    return [
        index
        for index, character in enumerate(line)
        if character == "$" and not _is_escaped(line, index)
    ]


def _currency_end(line: str, position: int) -> int | None:
    match = CURRENCY_RE.match(line, position)
    if match is None:
        return None

    end = match.end()
    if end < len(line):
        following = line[end]
        if following.isalnum() or following == "_":
            return None
        if (
            following in {".", ","}
            and end + 1 < len(line)
            and line[end + 1].isdigit()
        ):
            return None
    return end


def _parse_inline_math(line: str, line_number: int) -> list[str]:
    positions = _unescaped_dollar_positions(line)
    payloads: list[str] = []

    for first, second in zip(positions, positions[1:]):
        if second == first + 1:
            raise AssertionError(
                f"$$ must be alone on its line (line {line_number})"
            )

    cursor = 0
    while cursor < len(positions):
        opener = positions[cursor]
        closer = positions[cursor + 1] if cursor + 1 < len(positions) else None

        is_math_pair = (
            closer is not None
            and opener + 1 < closer
            and not line[opener + 1].isspace()
            and not line[closer - 1].isspace()
            and (closer + 1 == len(line) or not line[closer + 1].isdigit())
        )
        if is_math_pair:
            payloads.append(line[opener + 1 : closer])
            cursor += 2
            continue

        if _currency_end(line, opener) is not None:
            cursor += 1
            continue

        raise AssertionError(f"unmatched or malformed inline $ on line {line_number}")

    return payloads


def _parse_github_math(text: str) -> tuple[list[str], list[str]]:
    display_payloads: list[str] = []
    inline_payloads: list[str] = []
    current_display: list[str] | None = None

    for line_number, line in enumerate(_outside_code_lines(text), start=1):
        stripped = line.strip()

        if stripped == "$$":
            if line.startswith("    ") or line.startswith("\t"):
                raise AssertionError(
                    f"display math is indented as code on line {line_number}"
                )
            if current_display is None:
                current_display = []
            else:
                payload = "\n".join(current_display).strip()
                if not payload:
                    raise AssertionError(
                        f"empty display-math block ending at line {line_number}"
                    )
                display_payloads.append(payload)
                current_display = None
            continue

        if current_display is not None:
            positions = _unescaped_dollar_positions(line)
            for first, second in zip(positions, positions[1:]):
                if second == first + 1:
                    raise AssertionError(
                        f"nested $$ inside display math on line {line_number}"
                    )
            current_display.append(line)
            continue

        inline_payloads.extend(_parse_inline_math(line, line_number))

    if current_display is not None:
        raise AssertionError("README contains an unclosed display-math block")

    return display_payloads, inline_payloads


class ReadmeMathTests(unittest.TestCase):
    def test_readme_has_no_legacy_math_delimiters_outside_code(self) -> None:
        text = README.read_text(encoding="utf-8")
        prose = "\n".join(_outside_code_lines(text))
        for token in (r"\(", r"\)", r"\[", r"\]"):
            self.assertNotIn(token, prose)

    def test_readme_uses_balanced_github_math_delimiters(self) -> None:
        text = README.read_text(encoding="utf-8")
        display, inline = _parse_github_math(text)
        payloads = display + inline

        for expected in (
            r"Raw Persona State",
            r"Same Persona",
            r"\lambda",
            r"L_t",
            r"\alpha",
            r"H\in\lbrace 3,10\rbrace",
            r"d\in\lbrace 0,1,2,3\rbrace",
            r"\eta=0.8",
        ):
            self.assertTrue(
                any(expected in payload for payload in payloads),
                f"missing rendered README formula: {expected}",
            )

    def test_math_scanner_controls(self) -> None:
        valid = (
            r"Inline $L_t$ and escaped currency \$5.",
            r"Math with a numeric first term: $5 + x$.",
            "Currency $5, $5.00, $1,000, US$10, A$10, and $5–$10.",
            "$$\nx^2\n$$",
            "~~~text\n$ ignored in code\n~~~",
            "inline `$ ignored in code`",
            "inline ``$ ignored in code``",
            "    $$ indented code, not display math $$",
        )
        for sample in valid:
            with self.subTest(valid=sample):
                _parse_github_math(sample)

        invalid = (
            "$L_t",
            "L_t$",
            "$ x$",
            "$x $",
            "$$\n$$",
            "$$x$$",
            "`$x``",
        )
        for sample in invalid:
            with self.subTest(invalid=sample):
                with self.assertRaises(AssertionError):
                    _parse_github_math(sample)


if __name__ == "__main__":
    unittest.main()
