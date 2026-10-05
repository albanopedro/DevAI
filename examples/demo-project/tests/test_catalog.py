from bookshelf.catalog import Book, Catalog


def test_books_by_author_oldest_first():
    catalog = Catalog()
    catalog.add(Book("B", "Ana", 2001))
    catalog.add(Book("A", "Ana", 1999))
    catalog.add(Book("C", "Bia", 2000))

    assert [book.title for book in catalog.by_author("Ana")] == ["A", "B"]
