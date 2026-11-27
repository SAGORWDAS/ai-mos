import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://ai_mos:ai_mos@localhost:5432/ai_mos")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "dGVzdC1rZXktMzItYnl0ZXMtbG9uZy1iYXNlNjQ=")
