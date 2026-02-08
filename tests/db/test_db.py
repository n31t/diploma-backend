#!/usr/bin/env python3
"""
Simple script to test database connectivity.
Run this to quickly check if your database connection is working.
"""

import asyncio
import sys
import os
import pytest

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

@pytest.mark.asyncio
async def test_db_connection():
    """Quick database connection test."""
    try:
        from src.db.database import check_db_connection, engine
        from sqlalchemy import text
        
        print("🔄 Testing database connection...")
        
        is_connected = await check_db_connection()
        if is_connected:
            print("✅ Database connection check passed!")
        else:
            print("❌ Database connection check failed!")
            return False
            
        # Test 2: Direct query
        print("🔄 Testing direct query...")
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 'Hello Database!' as message, NOW() as timestamp"))
            row = result.fetchone()
            print(f"✅ Query successful: {row.message} at {row.timestamp}")
            
        print("🎉 All database tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\n💡 Make sure your .env file has the correct database credentials:")
        print("   DB_USER=your_username")
        print("   DB_PASSWORD=your_password") 
        print("   DB_HOST=localhost")
        print("   DB_PORT=5432")
        print("   DB_NAME=your_database")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_db_connection())
    sys.exit(0 if success else 1)