import sqlite3
import os

def explore_database(db_path):
    """Explore a SQLite database and show its contents"""
    
    if not os.path.exists(db_path):
        print(f"Database file '{db_path}' does not exist.")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print(f"=== Exploring Database: {db_path} ===\n")
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        if not tables:
            print("No tables found in the database.")
            return
        
        print(f"Found {len(tables)} table(s):")
        for table in tables:
            print(f"  - {table[0]}")
        
        print("\n" + "="*50)
        
        # Explore each table
        for table in tables:
            table_name = table[0]
            print(f"\n--- Table: {table_name} ---")
            
            # Get table schema
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            print("Columns:")
            for col in columns:
                print(f"  {col[1]} ({col[2]})")
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"Rows: {count}")
            
            # Show sample data if any
            if count > 0:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
                rows = cursor.fetchall()
                print("Sample data (first 5 rows):")
                for i, row in enumerate(rows, 1):
                    print(f"  Row {i}: {row}")
            else:
                print("No data in this table.")
            
            print("-" * 30)
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")

def interactive_query(db_path):
    """Interactive SQL query interface"""
    if not os.path.exists(db_path):
        print(f"Database file '{db_path}' does not exist.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"\n=== Interactive Query Mode for {db_path} ===")
    print("Enter SQL queries (type 'quit' to exit):")
    
    while True:
        try:
            query = input("\nSQL> ").strip()
            if query.lower() in ['quit', 'exit', 'q']:
                break
            
            if not query:
                continue
                
            cursor.execute(query)
            
            # Check if it's a SELECT query
            if query.upper().startswith('SELECT'):
                results = cursor.fetchall()
                if results:
                    print(f"\nFound {len(results)} row(s):")
                    for i, row in enumerate(results, 1):
                        print(f"  {i}: {row}")
                else:
                    print("No results found.")
            else:
                conn.commit()
                print("Query executed successfully.")
                
        except sqlite3.Error as e:
            print(f"SQL Error: {e}")
        except KeyboardInterrupt:
            print("\nExiting...")
            break
    
    conn.close()

if __name__ == "__main__":
    # Check which database files exist
    db_files = ["dababase.db", "database.db", "data.db"]
    existing_dbs = [db for db in db_files if os.path.exists(db)]
    
    if not existing_dbs:
        print("No database files found.")
    else:
        print("Available database files:")
        for i, db in enumerate(existing_dbs, 1):
            print(f"  {i}. {db}")
        
        if len(existing_dbs) == 1:
            db_path = existing_dbs[0]
        else:
            try:
                choice = int(input(f"\nSelect database (1-{len(existing_dbs)}): ")) - 1
                db_path = existing_dbs[choice]
            except (ValueError, IndexError):
                print("Invalid choice. Using first database.")
                db_path = existing_dbs[0]
        
        explore_database(db_path)
        
        # Ask if user wants interactive mode
        if input("\nEnter interactive query mode? (y/n): ").lower().startswith('y'):
            interactive_query(db_path)
