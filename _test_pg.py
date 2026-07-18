import sys
print("Python OK")
try:
    import asyncpg
    print("asyncpg imported")
except ImportError:
    print("asyncpg NOT installed")
    sys.exit(1)

import asyncio

async def test():
    print("Connecting...")
    try:
        conn = await asyncio.wait_for(
            asyncpg.connect("postgresql://postgres:postgres@172.25.165.112:5432/niche_finder"),
            timeout=5
        )
        print("Connected!")
        row = await conn.fetchrow("SELECT 1 as ok")
        print("Query result:", row["ok"])
        await conn.close()
    except asyncio.TimeoutError:
        print("ERROR: Connection timeout")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")

asyncio.run(test())
