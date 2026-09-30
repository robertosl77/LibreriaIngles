import os


# Los tests nunca deben apuntar a la base SQLite de desarrollo.
# Se establece antes de importar la aplicación.
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
