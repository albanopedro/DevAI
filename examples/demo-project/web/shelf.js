/** "Title (Year)", the way the shelf shows a book. */
export function formatBook(book) {
  return `${book.title} (${book.year})`;
}

export function renderShelf(books) {
  return books.map(formatBook).join('\n');
}
