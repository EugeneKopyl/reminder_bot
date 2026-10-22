import re
from dataclasses import dataclass
from enum import StrEnum

from bot.nlu.vocabulary import ORDINAL_SUFFIXES

PIECE_PATTERN = re.compile(
    r"#[^\W_][\w-]*"
    r"|\d{1,2}:\d{2}(?!\d)"
    r"|\d{1,2}\.\d{1,2}(?:\.\d{2,4})?(?![\d.])"
    r"|\d+(?:-[^\W\d_]+)?"
    r"|[^\W\d_]+(?:-[^\W\d_]+)*"
    r"|\S"
)
CLOCK_PATTERN = re.compile(r"(?P<hour>\d{1,2}):(?P<minute>\d{2})")
DOTTED_PATTERN = re.compile(r"\d{1,2}\.\d{1,2}(?:\.\d{2,4})?")
NUMBER_PATTERN = re.compile(r"(?P<digits>\d{1,6})(?:-(?P<suffix>[^\W\d_]+))?")
INVISIBLE_CHARACTERS = dict.fromkeys(map(ord, "️‍​"))


class TokenKind(StrEnum):
    WORD = "word"
    NUMBER = "number"
    CLOCK = "clock"
    DOTTED = "dotted"
    HASHTAG = "hashtag"
    SYMBOL = "symbol"


@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    text: str
    span: tuple[int, int]
    value: int = 0
    minute: int = 0
    ordinal: bool = False
    spoken: bool = False

    @property
    def has_ambiguous_hour(self) -> bool:
        return self.spoken and 1 <= self.value <= 11


def normalize_word(word: str) -> str:
    return word.lower().replace("ё", "е")


def split_pieces(text: str) -> tuple[str, ...]:
    cleaned = text.translate(INVISIBLE_CHARACTERS)
    return tuple(match.group() for match in PIECE_PATTERN.finditer(cleaned))


def classify_piece(piece: str, index: int) -> Token:
    span = (index, index + 1)
    if piece.startswith("#") and len(piece) > 1:
        return Token(TokenKind.HASHTAG, piece[1:].lower(), span)
    if clock := CLOCK_PATTERN.fullmatch(piece):
        hour, minute = int(clock["hour"]), int(clock["minute"])
        if hour <= 23 and minute <= 59:
            return Token(TokenKind.CLOCK, piece, span, value=hour, minute=minute)
        return Token(TokenKind.SYMBOL, piece, span)
    if DOTTED_PATTERN.fullmatch(piece):
        return Token(TokenKind.DOTTED, piece, span)
    if number := NUMBER_PATTERN.fullmatch(piece):
        suffix = number["suffix"]
        is_ordinal = suffix is not None and normalize_word(suffix) in ORDINAL_SUFFIXES
        return Token(
            TokenKind.NUMBER, piece.lower(), span, value=int(number["digits"]), ordinal=is_ordinal
        )
    if piece[0].isalpha():
        return Token(TokenKind.WORD, normalize_word(piece), span)
    return Token(TokenKind.SYMBOL, piece, span)
