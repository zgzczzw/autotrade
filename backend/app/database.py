import os

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./autotrade.db")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session


async def init_db():
    from app.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 增量迁移：添加新列（忽略已存在错误）
        try:
            await conn.execute(text(
                "ALTER TABLE strategies ADD COLUMN sell_size_pct REAL NOT NULL DEFAULT 100.0"
            ))
        except Exception:
            pass  # 列已存在

    # Seed default SimAccount if empty
    async with async_session() as session:
        from sqlalchemy import select
        from app.models import SimAccount

        result = await session.execute(select(SimAccount))
        if result.scalar_one_or_none() is None:
            initial_balance = float(
                os.getenv("SIMULATED_INITIAL_BALANCE", "100000")
            )
            session.add(
                SimAccount(
                    initial_balance=initial_balance,
                    balance=initial_balance,
                    total_pnl=0.0,
                )
            )
            await session.commit()
