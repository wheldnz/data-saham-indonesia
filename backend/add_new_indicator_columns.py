import sqlite3
import os

def migrate():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'alphahunter.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get existing columns
    cursor.execute("PRAGMA table_info(technical_features)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    
    new_columns = {
        'mfi_14': 'FLOAT',
        'willr_14': 'FLOAT',
        'cci_20': 'FLOAT',
    }
    
    for col_name, col_type in new_columns.items():
        if col_name not in existing_cols:
            print(f"Adding column {col_name} ({col_type})...")
            cursor.execute(f"ALTER TABLE technical_features ADD COLUMN {col_name} {col_type}")
        else:
            print(f"Column {col_name} already exists, skipping.")
    
    conn.commit()
    conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
