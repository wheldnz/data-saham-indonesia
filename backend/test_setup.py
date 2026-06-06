from fastapi.testclient import TestClient
from sqlalchemy import inspect
from app.main import app
from app.db.database import engine

def run_tests():
    print("Testing FastAPI...")
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    print("FastAPI /health endpoint is working!")
    
    print("Testing Database Tables...")
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    expected_tables = ['alembic_version', 'daily_ohlcv', 'stocks', 'technical_features', 'watchlist_items', 'watchlist_scores', 'watchlists']
    
    for table in expected_tables:
        assert table in tables, f"Missing table: {table}"
        print(f"  Found table: {table}")
        
    print("All tests passed successfully!")

if __name__ == "__main__":
    run_tests()
