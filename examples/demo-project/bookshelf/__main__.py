"""`python -m bookshelf`: print the shelf."""

from bookshelf.catalog import Book, Catalog


def main():
    catalog = Catalog()
    catalog.add(Book("Dom Casmurro", "Machado de Assis", 1899))
    catalog.add(Book("Memórias Póstumas de Brás Cubas", "Machado de Assis", 1881))
    for book in catalog.by_author("Machado de Assis"):
        print(f"{book.year}  {book.title}")


if __name__ == "__main__":
    main()
