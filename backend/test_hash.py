import asyncio
from sqlalchemy import text
from app.core.database import engine

async def test():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT hashed_password FROM users WHERE email='admin@salesiq.ai'"))
        row = result.first()
        if row:
            h = row[0]
            print('Hash prefix:', h[:10])
            print('Full hash:', h)
            import bcrypt
            ok = bcrypt.checkpw('Admin@2024'.encode(), h.encode())
            print('Verify existing hash:', ok)

asyncio.run(test())
