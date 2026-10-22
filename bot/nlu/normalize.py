from collections.abc import Callable, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from bot.nlu.tokens import Token, TokenKind, classify_piece, split_pieces
from bot.nlu.vocabulary import (
    CARDINALS,
    COMPOUND_DURATIONS,
    HALF_UNIT_DURATIONS,
    HOUR_GENITIVE_ORDINALS,
    ONE_AND_HALF_DURATIONS,
    ORDINALS,
    UNITS,
    can_follow_time,
)

CLOCK_LEADERS = frozenset({"в", "во", "к", "ко", "до", "с", "со", "на", "около", "и"})
HALF_WORDS = frozenset({"пол", "половина", "половине", "половину"})
ONE_AND_HALF_WORDS = frozenset({"полтора", "полторы"})

Rewrite = Callable[[Sequence[Token], int], tuple[list[Token], int] | None]


@dataclass(frozen=True, slots=True)
class TokenizedText:
    pieces: tuple[str, ...]
    tokens: tuple[Token, ...]


def tokenize(text: str) -> TokenizedText:
    pieces = split_pieces(text)
    tokens: list[Token] = [classify_piece(piece, index) for index, piece in enumerate(pieces)]
    tokens = expand_compound_words(tokens)
    tokens = merge_number_words(tokens)
    tokens = apply_rewrites(tokens, (rewrite_half_hour, rewrite_quarter_past, rewrite_minutes_to))
    tokens = apply_rewrites(tokens, (rewrite_fractional_duration,))
    tokens = apply_rewrites(tokens, (rewrite_spoken_clock,))
    return TokenizedText(pieces, tuple(tokens))


def apply_rewrites(tokens: Sequence[Token], rewrites: Sequence[Rewrite]) -> list[Token]:
    result: list[Token] = []
    position = 0
    while position < len(tokens):
        for rewrite in rewrites:
            rewritten = rewrite(tokens, position)
            if rewritten is not None:
                replacement, position = rewritten
                result.extend(replacement)
                break
        else:
            result.append(tokens[position])
            position += 1
    return result


def expand_compound_words(tokens: Sequence[Token]) -> list[Token]:
    result: list[Token] = []
    for token in tokens:
        if token.kind is not TokenKind.WORD:
            result.append(token)
        elif token.text in COMPOUND_DURATIONS:
            amount, unit_word = COMPOUND_DURATIONS[token.text]
            result.extend(duration_tokens(amount, unit_word, token.span))
        elif (hour := half_past_hour(token.text)) is not None:
            result.append(clock_token(previous_hour(hour), 30, token.span))
        else:
            result.append(token)
    return result


def half_past_hour(word: str) -> int | None:
    if not word.startswith("пол"):
        return None
    return HOUR_GENITIVE_ORDINALS.get(word.removeprefix("пол").lstrip("-"))


def merge_number_words(tokens: Sequence[Token]) -> list[Token]:
    result: list[Token] = []
    position = 0
    while position < len(tokens):
        run = read_number_run(tokens, position)
        if run is None:
            result.append(tokens[position])
            position += 1
            continue
        value, is_ordinal, end = run
        first, last = tokens[position], tokens[end - 1]
        result.append(
            Token(
                TokenKind.NUMBER,
                " ".join(token.text for token in tokens[position:end]),
                (first.span[0], last.span[1]),
                value=value,
                ordinal=is_ordinal,
                spoken=True,
            )
        )
        position = end
    return result


def read_number_run(tokens: Sequence[Token], start: int) -> tuple[int, bool, int] | None:
    total = 0
    previous_rank: int | None = None
    is_ordinal = False
    position = start
    while position < len(tokens) and not is_ordinal:
        token = tokens[position]
        if token.kind is not TokenKind.WORD:
            break
        if token.text in CARDINALS:
            value, word_is_ordinal = CARDINALS[token.text], False
        elif token.text in ORDINALS:
            value, word_is_ordinal = ORDINALS[token.text], True
        else:
            break
        rank = number_rank(value)
        if previous_rank is not None and not can_follow(previous_rank, rank, value):
            break
        total += value
        previous_rank = rank
        is_ordinal = word_is_ordinal
        position += 1
    if position == start:
        return None
    return total, is_ordinal, position


def number_rank(value: int) -> int:
    if value >= 100:
        return 3
    if value >= 20:
        return 2
    return 1


def can_follow(previous_rank: int, rank: int, value: int) -> bool:
    if rank >= previous_rank or value == 0:
        return False
    return not (previous_rank == 2 and value >= 10)


def rewrite_half_hour(tokens: Sequence[Token], position: int) -> tuple[list[Token], int] | None:
    if not is_word(tokens, position, HALF_WORDS):
        return None
    hour = ordinal_hour(tokens, position + 1)
    if hour is None:
        return None
    span = merged_span(tokens, position, position + 2)
    return [clock_token(previous_hour(hour), 30, span)], position + 2


def rewrite_quarter_past(tokens: Sequence[Token], position: int) -> tuple[list[Token], int] | None:
    if not is_word(tokens, position, {"четверть"}):
        return None
    hour = ordinal_hour(tokens, position + 1)
    if hour is None:
        return None
    span = merged_span(tokens, position, position + 2)
    return [clock_token(previous_hour(hour), 15, span)], position + 2


def rewrite_minutes_to(tokens: Sequence[Token], position: int) -> tuple[list[Token], int] | None:
    if not is_word(tokens, position, {"без"}) or position + 2 >= len(tokens):
        return None
    minutes_token, hour_token = tokens[position + 1], tokens[position + 2]
    if minutes_token.kind is TokenKind.WORD and minutes_token.text == "четверти":
        minutes = 15
    elif is_cardinal(minutes_token, 1, 30):
        minutes = minutes_token.value
    else:
        return None
    if hour_token.kind is TokenKind.WORD and hour_token.text == "час":
        hour = 1
    elif is_cardinal(hour_token, 1, 12):
        hour = hour_token.value
    else:
        return None
    span = merged_span(tokens, position, position + 3)
    return [clock_token(previous_hour(hour), 60 - minutes, span)], position + 3


def rewrite_fractional_duration(
    tokens: Sequence[Token], position: int
) -> tuple[list[Token], int] | None:
    if position + 1 >= len(tokens) or tokens[position + 1].kind is not TokenKind.WORD:
        return None
    unit = UNITS.get(tokens[position + 1].text)
    if unit is None:
        return None
    if is_word(tokens, position, {"пол"}):
        table = HALF_UNIT_DURATIONS
    elif is_word(tokens, position, ONE_AND_HALF_WORDS):
        table = ONE_AND_HALF_DURATIONS
    else:
        return None
    if unit not in table:
        return None
    amount, unit_word = table[unit]
    return duration_tokens(amount, unit_word, merged_span(tokens, position, position + 2)), (
        position + 2
    )


def rewrite_spoken_clock(tokens: Sequence[Token], position: int) -> tuple[list[Token], int] | None:
    if position == 0 or not is_word(tokens, position - 1, CLOCK_LEADERS):
        return None
    hour_token = tokens[position]
    if not is_cardinal(hour_token, 0, 23):
        return None
    following = tokens[position + 1 : position + 3]
    if hour_token.spoken:
        minute_and_end = read_spoken_minute(following, position)
    else:
        minute_and_end = read_typed_minute(following, position)
    if minute_and_end is None:
        return None
    minute, end = minute_and_end
    span = merged_span(tokens, position, end)
    return [clock_token(hour_token.value, minute, span, spoken=hour_token.spoken)], end


def read_spoken_minute(following: Sequence[Token], position: int) -> tuple[int, int] | None:
    if following and is_spoken_cardinal(following[0], 10, 59):
        return following[0].value, position + 2
    if (
        len(following) == 2
        and is_spoken_cardinal(following[0], 0, 0)
        and is_spoken_cardinal(following[1], 0, 9)
    ):
        return following[1].value, position + 3
    return None


def read_typed_minute(following: Sequence[Token], position: int) -> tuple[int, int] | None:
    if not following:
        return None
    minute = following[0]
    if minute.spoken or len(minute.text) != 2 or not is_cardinal(minute, 0, 59):
        return None
    follower = following[1] if len(following) == 2 else None
    if follower is not None and is_time_blocker(follower):
        return None
    return minute.value, position + 2


def is_time_blocker(token: Token) -> bool:
    return token.kind is TokenKind.WORD and not can_follow_time(token.text)


def ordinal_hour(tokens: Sequence[Token], position: int) -> int | None:
    if position >= len(tokens):
        return None
    token = tokens[position]
    if token.kind is TokenKind.NUMBER and token.ordinal and 1 <= token.value <= 12:
        return token.value
    return None


def is_word(tokens: Sequence[Token], position: int, options: AbstractSet[str]) -> bool:
    if not 0 <= position < len(tokens):
        return False
    token = tokens[position]
    return token.kind is TokenKind.WORD and token.text in options


def is_cardinal(token: Token, low: int, high: int) -> bool:
    return token.kind is TokenKind.NUMBER and not token.ordinal and low <= token.value <= high


def is_spoken_cardinal(token: Token, low: int, high: int) -> bool:
    return is_cardinal(token, low, high) and token.spoken


def previous_hour(hour: int) -> int:
    return hour - 1 if hour > 1 else 12


def merged_span(tokens: Sequence[Token], start: int, end: int) -> tuple[int, int]:
    return tokens[start].span[0], tokens[end - 1].span[1]


def clock_token(hour: int, minute: int, span: tuple[int, int], *, spoken: bool = True) -> Token:
    return Token(
        TokenKind.CLOCK, f"{hour}:{minute:02d}", span, value=hour, minute=minute, spoken=spoken
    )


def duration_tokens(amount: int, unit_word: str, span: tuple[int, int]) -> list[Token]:
    return [
        Token(TokenKind.NUMBER, str(amount), span, value=amount, spoken=True),
        Token(TokenKind.WORD, unit_word, span),
    ]
