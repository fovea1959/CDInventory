#!/bin/bash

# Configuration
DB_FILE="CDInventory.db"
OUTPUT_FILE="data_only.sql"

# Clear any existing backup file
> "$OUTPUT_FILE"

# Get all table names, ignoring SQLite internal system tables
TABLES=$(sqlite3 "$DB_FILE" "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")

# Loop through each table and extract rows as INSERT statements
for TABLE in $TABLES; do
    echo "Backing up data from table: $TABLE"
    sqlite3 "$DB_FILE" ".mode insert $TABLE" "SELECT * FROM $TABLE;" >> "$OUTPUT_FILE"
done

echo "Backup complete! Saved to $OUTPUT_FILE"

