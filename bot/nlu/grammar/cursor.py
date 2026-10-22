from collections.abc import Container, Mapping, Sequence

from bot.nlu.tokens import Token, TokenKind

SEPARATORS = frozenset({"и", ","})


class Cursor:
    def __init__(self, tokens: Sequence[Token], position: int, *, follows_match: bool) -> None:
        self.tokens = tokens
        self.position = position
        self.follows_match = follows_match

    def peek(self, offset: int = 0) -> Token | None:
        index = self.position + offset
        return self.tokens[index] if 0 <= index < len(self.tokens) else None

    def word(self, offset: int = 0) -> str | None:
        token = self.peek(offset)
        if token is None or token.kind is not TokenKind.WORD:
            return None
        return token.text

    def advance(self) -> Token:
        token = self.tokens[self.position]
        self.position += 1
        return token

    def take_word(self, options: Container[str]) -> str | None:
        word = self.word()
        if word is None or word not in options:
            return None
        self.position += 1
        return word

    def take_words(self, *words: str) -> bool:
        if all(self.word(offset) == word for offset, word in enumerate(words)):
            self.position += len(words)
            return True
        return False

    def take_lookup[T](self, table: Mapping[str, T]) -> T | None:
        word = self.word()
        if word is None or word not in table:
            return None
        self.position += 1
        return table[word]

    def take_symbol_lookup[T](self, table: Mapping[str, T]) -> T | None:
        token = self.peek()
        if token is None or token.kind is not TokenKind.SYMBOL or token.text not in table:
            return None
        self.position += 1
        return table[token.text]

    def take_kind(self, kind: TokenKind) -> Token | None:
        token = self.peek()
        if token is None or token.kind is not kind:
            return None
        self.position += 1
        return token

    def take_number(self, low: int, high: int, *, ordinal: bool | None = None) -> Token | None:
        token = self.peek()
        if token is None or token.kind is not TokenKind.NUMBER:
            return None
        if not low <= token.value <= high:
            return None
        if ordinal is not None and token.ordinal != ordinal:
            return None
        self.position += 1
        return token

    def take_separator(self) -> bool:
        token = self.peek()
        if token is None or token.text not in SEPARATORS:
            return False
        if token.kind not in (TokenKind.WORD, TokenKind.SYMBOL):
            return False
        self.position += 1
        return True
