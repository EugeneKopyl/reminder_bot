from bot.domain.reminders import Priority
from bot.nlu.facts import DayPeriod, Unit

CARDINALS: dict[str, int] = {
    "ноль": 0,
    "нуля": 0,
    "один": 1,
    "одна": 1,
    "одно": 1,
    "одну": 1,
    "одного": 1,
    "одной": 1,
    "два": 2,
    "две": 2,
    "двух": 2,
    "пару": 2,
    "пара": 2,
    "три": 3,
    "трех": 3,
    "четыре": 4,
    "четырех": 4,
    "пять": 5,
    "пяти": 5,
    "шесть": 6,
    "шести": 6,
    "семь": 7,
    "семи": 7,
    "восемь": 8,
    "восьми": 8,
    "девять": 9,
    "девяти": 9,
    "десять": 10,
    "десяти": 10,
    "одиннадцать": 11,
    "одиннадцати": 11,
    "двенадцать": 12,
    "двенадцати": 12,
    "тринадцать": 13,
    "тринадцати": 13,
    "четырнадцать": 14,
    "четырнадцати": 14,
    "пятнадцать": 15,
    "пятнадцати": 15,
    "шестнадцать": 16,
    "шестнадцати": 16,
    "семнадцать": 17,
    "семнадцати": 17,
    "восемнадцать": 18,
    "восемнадцати": 18,
    "девятнадцать": 19,
    "девятнадцати": 19,
    "двадцать": 20,
    "двадцати": 20,
    "тридцать": 30,
    "тридцати": 30,
    "сорок": 40,
    "сорока": 40,
    "пятьдесят": 50,
    "пятидесяти": 50,
    "шестьдесят": 60,
    "шестидесяти": 60,
    "семьдесят": 70,
    "семидесяти": 70,
    "восемьдесят": 80,
    "восьмидесяти": 80,
    "девяносто": 90,
    "девяноста": 90,
    "сто": 100,
    "ста": 100,
    "двести": 200,
    "триста": 300,
    "четыреста": 400,
    "пятьсот": 500,
}

_ORDINAL_STEMS = {
    "перв": 1,
    "втор": 2,
    "четверт": 4,
    "пят": 5,
    "шест": 6,
    "седьм": 7,
    "восьм": 8,
    "девят": 9,
    "десят": 10,
    "одиннадцат": 11,
    "двенадцат": 12,
    "тринадцат": 13,
    "четырнадцат": 14,
    "пятнадцат": 15,
    "шестнадцат": 16,
    "семнадцат": 17,
    "восемнадцат": 18,
    "девятнадцат": 19,
    "двадцат": 20,
    "тридцат": 30,
}
_ORDINAL_ENDINGS = (
    "ый", "ой", "ая", "ое", "ую", "ого", "ому", "ом", "ые", "ых", "ым", "ыми",
)  # fmt: skip
_THIRD_FORMS = (
    "третий", "третья", "третье", "третью", "третьего", "третьему", "третьей", "третьем",
    "третьи", "третьих",
)  # fmt: skip

ORDINALS: dict[str, int] = {
    stem + ending: value for stem, value in _ORDINAL_STEMS.items() for ending in _ORDINAL_ENDINGS
} | dict.fromkeys(_THIRD_FORMS, 3)

ORDINAL_SUFFIXES = frozenset(
    {"го", "е", "ое", "ого", "й", "ый", "ой", "я", "ая", "ю", "ую", "ее", "его", "м", "ом"}
)

HOUR_GENITIVE_ORDINALS: dict[str, int] = {
    "первого": 1,
    "второго": 2,
    "третьего": 3,
    "четвертого": 4,
    "пятого": 5,
    "шестого": 6,
    "седьмого": 7,
    "восьмого": 8,
    "девятого": 9,
    "десятого": 10,
    "одиннадцатого": 11,
    "двенадцатого": 12,
}

LAST_WORDS = frozenset({"последний", "последнюю", "последнее", "последнего", "последней"})

UNITS: dict[str, Unit] = {
    "минута": Unit.MINUTE,
    "минуту": Unit.MINUTE,
    "минуты": Unit.MINUTE,
    "минут": Unit.MINUTE,
    "минутку": Unit.MINUTE,
    "мин": Unit.MINUTE,
    "час": Unit.HOUR,
    "часа": Unit.HOUR,
    "часов": Unit.HOUR,
    "часик": Unit.HOUR,
    "ч": Unit.HOUR,
    "день": Unit.DAY,
    "дня": Unit.DAY,
    "дней": Unit.DAY,
    "сутки": Unit.DAY,
    "суток": Unit.DAY,
    "неделя": Unit.WEEK,
    "неделю": Unit.WEEK,
    "недели": Unit.WEEK,
    "недель": Unit.WEEK,
    "месяц": Unit.MONTH,
    "месяца": Unit.MONTH,
    "месяцев": Unit.MONTH,
    "год": Unit.YEAR,
    "года": Unit.YEAR,
    "лет": Unit.YEAR,
}

HOUR_WORDS = frozenset({"час", "часа", "часов", "ч"})
MINUTE_WORDS = frozenset({"минута", "минуту", "минуты", "минут", "мин"})

COMPOUND_DURATIONS: dict[str, tuple[int, str]] = {
    "полчаса": (30, "минут"),
    "полчасика": (30, "минут"),
    "полдня": (12, "часов"),
    "полгода": (6, "месяцев"),
}
HALF_UNIT_DURATIONS: dict[Unit, tuple[int, str]] = {
    Unit.HOUR: (30, "минут"),
    Unit.DAY: (12, "часов"),
    Unit.YEAR: (6, "месяцев"),
}
ONE_AND_HALF_DURATIONS: dict[Unit, tuple[int, str]] = {
    Unit.HOUR: (90, "минут"),
    Unit.DAY: (36, "часов"),
    Unit.MONTH: (45, "дней"),
    Unit.YEAR: (18, "месяцев"),
}

MONTHS: dict[str, int] = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

WEEKDAYS_ACCUSATIVE: dict[str, int] = {
    "понедельник": 0,
    "вторник": 1,
    "среду": 2,
    "среда": 2,
    "четверг": 3,
    "пятницу": 4,
    "пятница": 4,
    "субботу": 5,
    "суббота": 5,
    "воскресенье": 6,
}
WEEKDAYS_GENITIVE: dict[str, int] = {
    "понедельника": 0,
    "вторника": 1,
    "среды": 2,
    "четверга": 3,
    "пятницы": 4,
    "субботы": 5,
    "воскресенья": 6,
}
WEEKDAYS_PLURAL_DATIVE: dict[str, int] = {
    "понедельникам": 0,
    "вторникам": 1,
    "средам": 2,
    "четвергам": 3,
    "пятницам": 4,
    "субботам": 5,
    "воскресеньям": 6,
}
WORKDAYS = (0, 1, 2, 3, 4)
WEEKEND = (5, 6)
WEEKDAY_CODES = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")

WEEKDAY_QUALIFIERS: dict[str, bool] = {
    "этот": False,
    "эту": False,
    "это": False,
    "ближайший": False,
    "ближайшую": False,
    "ближайшее": False,
    "следующий": True,
    "следующую": True,
    "следующее": True,
    "следующей": True,
}

DAY_OFFSETS: dict[str, int] = {"сегодня": 0, "завтра": 1, "послезавтра": 2}
DAY_OFFSETS_GENITIVE: dict[str, int] = {
    "сегодняшнего": 0,
    "завтрашнего": 1,
    "послезавтрашнего": 2,
}

PERIOD_WORDS: dict[str, DayPeriod] = {
    "утром": DayPeriod.MORNING,
    "утречком": DayPeriod.MORNING,
    "днем": DayPeriod.AFTERNOON,
    "вечером": DayPeriod.EVENING,
    "вечерком": DayPeriod.EVENING,
    "ночью": DayPeriod.NIGHT,
}
PERIOD_PHRASES: dict[tuple[str, str], DayPeriod] = {
    ("с", "утра"): DayPeriod.MORNING,
    ("к", "обеду"): DayPeriod.AFTERNOON,
    ("в", "обед"): DayPeriod.AFTERNOON,
    ("после", "обеда"): DayPeriod.AFTERNOON,
    ("к", "вечеру"): DayPeriod.EVENING,
    ("под", "вечер"): DayPeriod.EVENING,
    ("перед", "сном"): DayPeriod.NIGHT,
    ("на", "ночь"): DayPeriod.NIGHT,
}
MERIDIEMS: dict[str, DayPeriod] = {
    "утра": DayPeriod.MORNING,
    "дня": DayPeriod.AFTERNOON,
    "вечера": DayPeriod.EVENING,
    "ночи": DayPeriod.NIGHT,
}
RECURRING_PERIODS: dict[str, DayPeriod] = {
    "утро": DayPeriod.MORNING,
    "вечер": DayPeriod.EVENING,
    "ночь": DayPeriod.NIGHT,
}
PLURAL_PERIODS: dict[str, DayPeriod] = {
    "утрам": DayPeriod.MORNING,
    "вечерам": DayPeriod.EVENING,
    "ночам": DayPeriod.NIGHT,
}
NAMED_TIMES: dict[str, tuple[int, int]] = {"полдень": (12, 0), "полночь": (0, 0)}

EVERY_WORDS = frozenset({"каждый", "каждую", "каждое", "каждые", "каждого", "каждой", "каждом"})
ADVERB_FREQUENCIES: dict[str, Unit] = {
    "ежеминутно": Unit.MINUTE,
    "ежечасно": Unit.HOUR,
    "ежедневно": Unit.DAY,
    "еженедельно": Unit.WEEK,
    "ежемесячно": Unit.MONTH,
    "ежегодно": Unit.YEAR,
}

PRIORITY_WORDS: dict[str, Priority] = {
    "важно": Priority.IMPORTANT,
    "срочно": Priority.CRITICAL,
    "критично": Priority.CRITICAL,
}
PRIORITY_SYMBOLS: dict[str, Priority] = {
    "‼": Priority.CRITICAL,
    "❗": Priority.IMPORTANT,
    "❕": Priority.IMPORTANT,
}
PRIORITY_INTENSIFIERS = frozenset({"очень", "критически"})

COMPLETION_REFERENCE_QUALIFIERS = frozenset(
    {"последнего", "последней", "предыдущего", "предыдущей", "прошлого", "прошлой"}
)
NON_COMPLETION_REFERENCES = frozenset({"работы", "обеда", "ужина", "завтрака", "школы", "сна"})

ANNIVERSARY_MARKERS = frozenset(
    {"рождения", "др", "годовщина", "годовщину", "годовщины", "юбилей", "юбилея"}
)

YEAR_WORDS = frozenset({"год", "года", "году", "г"})
MONTH_DAY_WORDS = frozenset({"число", "числа", "числу"})

NOT_A_TIME_FOLLOWERS = (
    frozenset({*MONTHS, *MONTH_DAY_WORDS, *UNITS, "раз", "раза", "процентов"}) - HOUR_WORDS
)
NOMINATIVE_NEUTER_ENDINGS = ("ие", "ье", "ое", "ее")


def can_follow_time(word: str) -> bool:
    if word in NOT_A_TIME_FOLLOWERS:
        return False
    looks_like_location = (
        len(word) >= 5 and word.endswith("е") and not word.endswith(NOMINATIVE_NEUTER_ENDINGS)
    )
    return not looks_like_location
