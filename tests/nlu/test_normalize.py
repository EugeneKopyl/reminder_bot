import pytest

from bot.nlu.normalize import tokenize
from bot.nlu.tokens import Token, TokenKind, split_pieces


def tokens_of(text: str) -> tuple[Token, ...]:
    return tokenize(text).tokens


def clocks_of(text: str) -> list[tuple[int, int]]:
    return [
        (token.value, token.minute) for token in tokens_of(text) if token.kind is TokenKind.CLOCK
    ]


def test_pieces_keep_times_dates_and_punctuation_apart() -> None:
    assert split_pieces("Завтра в 9:30, 05.11 #дом позвонить!") == (
        "Завтра", "в", "9:30", ",", "05.11", "#дом", "позвонить", "!",
    )  # fmt: skip


def test_words_are_lowercased_and_yo_is_folded() -> None:
    assert [token.text for token in tokens_of("Ещё Раз")] == ["еще", "раз"]


@pytest.mark.parametrize(
    ("text", "value", "ordinal"),
    [
        ("двадцать пять", 25, False),
        ("сто двадцать", 120, False),
        ("пару", 2, False),
        ("второй", 2, True),
        ("третьего", 3, True),
        ("пятнадцатое", 15, True),
        ("двадцать первого", 21, True),
        ("5-го", 5, True),
        ("2-х", 2, False),
    ],
)
def test_numbers(text: str, value: int, ordinal: bool) -> None:
    [token] = tokens_of(text)

    assert token.kind is TokenKind.NUMBER
    assert (token.value, token.ordinal) == (value, ordinal)


def test_number_words_do_not_merge_out_of_order() -> None:
    assert [token.value for token in tokens_of("девять тридцать")] == [9, 30]


@pytest.mark.parametrize(
    ("text", "clock"),
    [
        ("в девять тридцать", (9, 30)),
        ("в восемь ноль пять", (8, 5)),
        ("в двадцать один ноль ноль", (21, 0)),
        ("в 19 30", (19, 30)),
        ("полдевятого", (8, 30)),
        ("пол-девятого", (8, 30)),
        ("полпервого", (12, 30)),
        ("в половине девятого", (8, 30)),
        ("в четверть восьмого", (7, 15)),
        ("без пятнадцати десять", (9, 45)),
        ("без четверти час", (12, 45)),
        ("без двадцати пяти восемь", (7, 35)),
    ],
)
def test_spoken_clocks(text: str, clock: tuple[int, int]) -> None:
    assert clocks_of(text) == [clock]


def test_digit_pairs_are_not_clocks_before_counts() -> None:
    assert clocks_of("в 9 10 раз") == []


@pytest.mark.parametrize(
    ("text", "amount", "unit"),
    [
        ("полчаса", 30, "минут"),
        ("пол часа", 30, "минут"),
        ("полтора часа", 90, "минут"),
        ("полтора дня", 36, "часов"),
        ("полгода", 6, "месяцев"),
    ],
)
def test_fractional_durations(text: str, amount: int, unit: str) -> None:
    number, unit_word = tokens_of(text)

    assert (number.value, unit_word.text) == (amount, unit)


def test_merged_tokens_cover_their_source_pieces() -> None:
    tokenized = tokenize("в девять тридцать позвонить")
    clock = tokenized.tokens[1]

    assert tokenized.pieces[clock.span[0] : clock.span[1]] == ("девять", "тридцать")
