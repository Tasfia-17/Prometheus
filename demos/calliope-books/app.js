/**
 * Calliope Books — Express.js demo with injected route ordering bug.
 *
 * BUG: The catch-all route GET /api/books/:id is registered BEFORE
 * GET /api/books/search. Express matches routes in registration order,
 * so "search" is treated as a book ID → 404 for every search request.
 * This produces 100% failure rate on the search endpoint under load.
 */
const express = require("express");
const initSqlJs = require("sql.js");

const app = express();
app.use(express.json());

const VALID_TOKEN = "test-token-calliope";

function requireAuth(req, res, next) {
  const auth = req.headers["authorization"];
  if (auth !== `Bearer ${VALID_TOKEN}`) {
    return res.status(401).json({ detail: "Unauthorized" });
  }
  next();
}

let db;

async function initDb() {
  const SQL = await initSqlJs();
  db = new SQL.Database();
  db.run(`
    CREATE TABLE books (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      author TEXT NOT NULL,
      genre TEXT,
      price REAL DEFAULT 0,
      stock INTEGER DEFAULT 0
    );
    CREATE TABLE reviews (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      book_id INTEGER NOT NULL,
      rating INTEGER NOT NULL,
      comment TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );
    INSERT INTO books (title, author, genre, price, stock) VALUES
      ('The Great Gatsby', 'F. Scott Fitzgerald', 'Fiction', 12.99, 50),
      ('To Kill a Mockingbird', 'Harper Lee', 'Fiction', 10.99, 30),
      ('1984', 'George Orwell', 'Dystopia', 9.99, 75),
      ('Dune', 'Frank Herbert', 'Sci-Fi', 14.99, 20),
      ('Clean Code', 'Robert Martin', 'Tech', 39.99, 15);
    INSERT INTO reviews (book_id, rating, comment) VALUES
      (1, 5, 'Classic'), (2, 5, 'Masterpiece'), (3, 5, 'Chilling');
  `);
}

app.get("/api/health", (req, res) => res.json({ status: "ok", service: "calliope-books" }));

app.get("/api/books", requireAuth, (req, res) => {
  const { limit = 20, offset = 0 } = req.query;
  const rows = db.exec(`SELECT id, title, author, genre, price, stock FROM books LIMIT ${+limit} OFFSET ${+offset}`);
  const books = rows[0]
    ? rows[0].values.map(([id, title, author, genre, price, stock]) => ({ id, title, author, genre, price, stock }))
    : [];
  res.json({ books, total: books.length });
});

// BUG: This catch-all is registered BEFORE /api/books/search
// Express will match "search" as :id → 404
app.get("/api/books/:id", requireAuth, (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (isNaN(id)) return res.status(404).json({ detail: "Book not found" });
  const rows = db.exec(`SELECT id, title, author, genre, price, stock FROM books WHERE id=${id}`);
  if (!rows[0]) return res.status(404).json({ detail: "Book not found" });
  const [bid, title, author, genre, price, stock] = rows[0].values[0];
  res.json({ id: bid, title, author, genre, price, stock });
});

// BUG: This should be BEFORE /:id but it's registered after — always shadowed
app.get("/api/books/search", requireAuth, (req, res) => {
  const { q = "" } = req.query;
  const rows = db.exec(`SELECT id, title, author, genre, price, stock FROM books WHERE title LIKE '%${q}%' OR author LIKE '%${q}%' LIMIT 20`);
  const books = rows[0]
    ? rows[0].values.map(([id, title, author, genre, price, stock]) => ({ id, title, author, genre, price, stock }))
    : [];
  res.json({ books });
});

app.get("/api/books/:id/reviews", requireAuth, (req, res) => {
  const rows = db.exec(`SELECT id, book_id, rating, comment, created_at FROM reviews WHERE book_id=${+req.params.id}`);
  const reviews = rows[0]
    ? rows[0].values.map(([id, book_id, rating, comment, created_at]) => ({ id, book_id, rating, comment, created_at }))
    : [];
  res.json({ reviews });
});

app.post("/api/books/:id/reviews", requireAuth, (req, res) => {
  const { rating, comment = "" } = req.body;
  if (!rating || rating < 1 || rating > 5) return res.status(400).json({ detail: "Rating must be 1-5" });
  const bookRows = db.exec(`SELECT id FROM books WHERE id=${+req.params.id}`);
  if (!bookRows[0]) return res.status(404).json({ detail: "Book not found" });
  db.run(`INSERT INTO reviews (book_id, rating, comment) VALUES (${+req.params.id}, ${+rating}, '${comment.replace(/'/g, "''")}')`);
  const idRows = db.exec("SELECT last_insert_rowid()");
  const id = idRows[0].values[0][0];
  res.status(201).json({ id, book_id: +req.params.id, rating: +rating, comment });
});

initDb().then(() => {
  app.listen(3000, () => console.log("Calliope Books running on :3000"));
});
