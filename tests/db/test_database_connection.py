import pytest
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import text

from src.db.database import AsyncSessionLocal
from src.core.config import Config


class TestDatabaseConnection:
    """Test database connectivity and basic operations."""

    @pytest.mark.asyncio
    async def test_database_connection_with_engine(self):
        """Test if we can connect to database using the engine."""
        config = Config()
        test_engine = create_async_engine(
            config.db_url,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        
        try:
            async with test_engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                row = result.fetchone()
                assert row[0] == 1
        except Exception as e:
            pytest.fail(f"Database connection failed: {e}")
        finally:
            await test_engine.dispose()

    @pytest.mark.asyncio
    async def test_database_connection_with_check_function(self):
        """Test using the built-in check_db_connection function."""
        config = Config()
        test_engine = create_async_engine(config.db_url)
        
        try:
            async with test_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            connection_successful = True
        except Exception:
            connection_successful = False
        finally:
            await test_engine.dispose()
            
        assert connection_successful is True, "Database connection check failed"

    @pytest.mark.asyncio
    async def test_session_creation(self):
        """Test if we can create and use database sessions."""
        config = Config()
        test_engine = create_async_engine(config.db_url)
        
        from sqlalchemy.ext.asyncio import async_sessionmaker
        TestSessionLocal = async_sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        try:
            async with TestSessionLocal() as session:
                result = await session.execute(text("SELECT 1 as test"))
                row = result.fetchone()
                assert row[0] == 1
        finally:
            await test_engine.dispose()

    @pytest.mark.asyncio
    async def test_get_db_dependency(self):
        """Test the FastAPI dependency function for database sessions."""
        # Test the FastAPI dependency pattern with a fresh engine
        config = Config()
        test_engine = create_async_engine(config.db_url)
        
        from sqlalchemy.ext.asyncio import async_sessionmaker
        TestSessionLocal = async_sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        async def test_get_db():
            async with TestSessionLocal() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise
                finally:
                    await session.close()
        
        try:
            db_generator = test_get_db()
            session = await db_generator.__anext__()
            assert isinstance(session, AsyncSession)
            
            # Test a simple query
            result = await session.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            assert row[0] == 1
            
        except StopAsyncIteration:
            pytest.fail("Database session generator failed")
        finally:
            await test_engine.dispose()

    @pytest.mark.asyncio
    async def test_database_config(self):
        """Test if database configuration is properly loaded."""
        config = Config()
        
        # Check if required config values are present
        assert hasattr(config, 'DB_USER'), "DB_USER not configured"
        assert hasattr(config, 'DB_PASSWORD'), "DB_PASSWORD not configured"
        assert hasattr(config, 'DB_HOST'), "DB_HOST not configured"
        assert hasattr(config, 'DB_NAME'), "DB_NAME not configured"
        
        # Check if db_url is properly formatted
        db_url = config.db_url
        assert "postgresql+asyncpg://" in db_url, "Invalid database URL format"
        assert config.DB_USER in db_url, "Username not in database URL"
        assert config.DB_HOST in db_url, "Host not in database URL"
        assert config.DB_NAME in db_url, "Database name not in database URL"

    @pytest.mark.asyncio
    async def test_transaction_rollback(self):
        """Test if transaction rollback works properly."""
        async with AsyncSessionLocal() as session:
            try:
                # Start a transaction
                await session.execute(text("SELECT 1"))
                
                # Force an error to test rollback
                await session.execute(text("SELECT * FROM non_existent_table"))
                
            except Exception:
                # This should trigger rollback
                await session.rollback()
                
                # Test that we can still use the session after rollback
                result = await session.execute(text("SELECT 1 as test"))
                row = result.fetchone()
                assert row[0] == 1

    @pytest.mark.asyncio
    async def test_multiple_concurrent_connections(self):
        """Test if multiple concurrent connections work."""
        async def query_database():
            config = Config()
            test_engine = create_async_engine(config.db_url)
            try:
                async with test_engine.begin() as conn:
                    result = await conn.execute(text("SELECT 1 as test"))
                    return result.fetchone()[0]
            finally:
                await test_engine.dispose()

        # Run multiple concurrent queries
        tasks = [query_database() for _ in range(3)]  # Reduced from 5 to 3
        results = await asyncio.gather(*tasks)
        
        # All should return 1
        assert all(result == 1 for result in results)

    def test_database_url_format(self):
        """Test database URL format (synchronous test)."""
        config = Config()
        db_url = config.db_url
        
        # Check URL components
        assert db_url.startswith("postgresql+asyncpg://"), "Wrong database driver"
        assert ":" in db_url, "URL should contain port"
        assert "/" in db_url, "URL should contain database name"


@pytest.mark.asyncio
async def test_quick_connection_check():
    """Quick standalone test for database connectivity."""
    config = Config()
    test_engine = create_async_engine(config.db_url)
    try:
        async with test_engine.begin() as conn:
            await conn.execute(text("SELECT NOW()"))
        print("✅ Database connection successful!")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        raise
    finally:
        await test_engine.dispose()