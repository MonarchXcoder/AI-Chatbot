import sqlite3

def setup_database():
    conn = sqlite3.connect('bookings.db')
    cursor = conn.cursor()

    # 1. Create Customers Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            phone TEXT
        )
    ''')

    # 2. Create Bookings Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            booking_type TEXT,
            date TEXT,
            time TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers (id)
        )
    ''')

    conn.commit()
    conn.close()
    print("Database and tables created successfully!")

if __name__ == "__main__":
    setup_database()