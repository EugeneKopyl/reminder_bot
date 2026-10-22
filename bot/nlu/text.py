import re
from collections.abc import Sequence

from bot.nlu.tokens import Token, normalize_word

COMMAND_WORDS = frozenset(
    {"напомни", "напомните", "напомнить", "напоминай", "напоминайте", "напоминать", "напомню"}
)
ADDRESSEE_WORDS = frozenset({"мне", "нам"})
POLITE_WORDS = frozenset({"пожалуйста", "плиз"})
LEADING_FILLERS = frozenset(
    {"что", "чтобы", "о", "об", "про", "мне", "нам", "надо", "нужно", "и", "а", "ну"}
)
TRAILING_FILLERS = frozenset(
    {"и", "а", "в", "во", "на", "к", "ко", "с", "со", "до", "по", "за", "что", "чтобы"}
)
PUNCTUATION = frozenset(",.;:!?—–-…")
SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,.;:!?…)»])")
SPACE_AFTER_BRACKET = re.compile(r"([(«])\s+")


def consumed_pieces(tokens: Sequence[Token], consumed: Sequence[bool]) -> frozenset[int]:
    return frozenset(
        index
        for token, is_consumed in zip(tokens, consumed, strict=True)
        if is_consumed
        for index in range(*token.span)
    )


def compose_text(pieces: Sequence[str], consumed: frozenset[int]) -> str:
    words = [piece for index, piece in enumerate(pieces) if index not in consumed]
    words = drop_command_words(words)
    words = [word for word in words if normalize_word(word) not in POLITE_WORDS]
    words = collapse_punctuation(words)
    words = strip_edges(words)
    text = SPACE_AFTER_BRACKET.sub(r"\1", SPACE_BEFORE_PUNCTUATION.sub(r"\1", " ".join(words)))
    if not any(character.isalpha() for character in text):
        return ""
    return text[0].upper() + text[1:]


def drop_command_words(words: Sequence[str]) -> list[str]:
    result: list[str] = []
    after_command = False
    for word in words:
        normalized = normalize_word(word)
        if normalized in COMMAND_WORDS or (after_command and normalized in ADDRESSEE_WORDS):
            after_command = True
            continue
        after_command = False
        result.append(word)
    return result


def collapse_punctuation(words: Sequence[str]) -> list[str]:
    result: list[str] = []
    for word in words:
        if is_punctuation(word) and result and is_punctuation(result[-1]):
            continue
        result.append(word)
    return result


def strip_edges(words: Sequence[str]) -> list[str]:
    start, end = 0, len(words)
    while start < end and (
        is_punctuation(words[start]) or normalize_word(words[start]) in LEADING_FILLERS
    ):
        start += 1
    while end > start and (
        is_punctuation(words[end - 1]) or normalize_word(words[end - 1]) in TRAILING_FILLERS
    ):
        end -= 1
    return list(words[start:end])


def is_punctuation(word: str) -> bool:
    return all(character in PUNCTUATION for character in word)
