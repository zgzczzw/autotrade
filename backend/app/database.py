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
        # Create all tables (idempotent)
        await conn.run_sync(Base.metadata.create_all)

        # Incremental migrations (ignore errors if column already exists)
        migrations = [
            "ALTER TABLE strategies ADD COLUMN sell_size_pct REAL NOT NULL DEFAULT 100.0",
            "ALTER TABLE strategies ADD COLUMN user_id INTEGER REFERENCES users(id)",
            "ALTER TABLE positions ADD COLUMN user_id INTEGER REFERENCES users(id)",
            "ALTER TABLE sim_accounts ADD COLUMN user_id INTEGER REFERENCES users(id)",
            "ALTER TABLE backtest_results ADD COLUMN user_id INTEGER REFERENCES users(id)",
            "ALTER TABLE trigger_logs ADD COLUMN position_effect VARCHAR",
            # Multi-symbol strategy support
            "ALTER TABLE trigger_logs ADD COLUMN symbol VARCHAR",
            "ALTER TABLE backtest_results ADD COLUMN batch_id VARCHAR",
        ]
        for sql in migrations:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass  # Column already exists

    # Backfill: ensure admin user exists and all existing data is assigned to them
    async with async_session() as session:
        from sqlalchemy import select
        from app.models import BacktestResult, Position, SimAccount, Strategy, User
        import bcrypt as _bcrypt

        def _hash_pw(pw: str) -> str:
            return _bcrypt.hashpw(pw.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")

        # Check if admin user exists
        result = await session.execute(select(User).where(User.username == "admin"))
        admin = result.scalar_one_or_none()

        if admin is None:
            admin_password = os.getenv("ADMIN_PASSWORD", "changeme")
            admin = User(
                username="admin",
                password_hash=_hash_pw(admin_password),
                is_admin=True,
            )
            session.add(admin)
            await session.flush()  # get admin.id

        admin_id = admin.id

        # Backfill existing rows
        await session.execute(
            text("UPDATE strategies SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": admin_id},
        )
        await session.execute(
            text("UPDATE positions SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": admin_id},
        )
        await session.execute(
            text("UPDATE sim_accounts SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": admin_id},
        )
        await session.execute(
            text("UPDATE backtest_results SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": admin_id},
        )

        # Backfill strategy_symbols from existing strategies
        from app.models import StrategySymbol
        existing_symbols_result = await session.execute(
            select(StrategySymbol).limit(1)
        )
        if existing_symbols_result.scalar_one_or_none() is None:
            # First run after migration: copy strategy.symbol → strategy_symbols
            all_strategies = await session.execute(select(Strategy))
            for s in all_strategies.scalars().all():
                session.add(StrategySymbol(
                    strategy_id=s.id,
                    symbol=s.symbol or "BTCUSDT",
                ))

        # Backfill trigger_logs.symbol from strategy.symbol
        await session.execute(
            text("""
                UPDATE trigger_logs SET symbol = (
                    SELECT strategies.symbol FROM strategies
                    WHERE strategies.id = trigger_logs.strategy_id
                ) WHERE trigger_logs.symbol IS NULL
            """)
        )

        # If no sim_account exists for admin, create one
        result = await session.execute(
            select(SimAccount).where(SimAccount.user_id == admin_id)
        )
        if result.scalar_one_or_none() is None:
            initial_balance = float(os.getenv("SIMULATED_INITIAL_BALANCE", "100000"))
            session.add(SimAccount(
                user_id=admin_id,
                initial_balance=initial_balance,
                balance=initial_balance,
                total_pnl=0.0,
            ))

        await session.commit()

    # Seed default SystemSetting if empty
    async with async_session() as session:
        from sqlalchemy import select
        from app.models import SystemSetting

        result = await session.execute(
            select(SystemSetting).where(SystemSetting.key == "data_source")
        )
        if result.scalar_one_or_none() is None:
            use_mock = os.getenv("USE_MOCK_DATA", "false").lower() == "true"
            default_source = "mock" if use_mock else "binance"
            session.add(SystemSetting(key="data_source", value=default_source))
            session.add(SystemSetting(key="cryptocompare_api_key", value=""))
            await session.commit()
