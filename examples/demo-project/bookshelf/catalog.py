"""The books on the shelf."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    title: str
    author: str
    year: int


class Catalog:
    """Books, by title."""

    def __init__(self):
        self.books = {}

    def add(self, book):
        """Add a book; a title already on the shelf is replaced."""
        self.books[book.title] = book

    def by_author(self, author):
        return sorted(
            (book for book in self.books.values() if book.author == author),
            key=lambda book: book.year,
        )

    def remove(self, title):
        return self.books.pop(title)
