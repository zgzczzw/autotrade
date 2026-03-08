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
        from app.models import SimAccount, SystemSetting

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

    # Seed default SystemSetting if empty
    async with async_session() as session:
        from sqlalchemy import select
        from app.models import SystemSetting

        result = await session.execute(
            select(SystemSetting).where(SystemSetting.key == "data_source")
        )
        if result.scalar_one_or_none() is None:
            # USE_MOCK_DATA 环境变量向后兼容：若设置则默认 mock
            use_mock = os.getenv("USE_MOCK_DATA", "false").lower() == "true"
            default_source = "mock" if use_mock else "binance"
            session.add(SystemSetting(key="data_source", value=default_source))
            session.add(SystemSetting(key="cryptocompare_api_key", value=""))
            await session.commit()
