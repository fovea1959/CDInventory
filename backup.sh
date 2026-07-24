#!/bin/bash

# Configuration
DB_FILE="CDInventory.db"

TS=$(date +%Y%m%d-%H%M%S)
OUTPUT_FILE="cdinventory_backups/${DB_FILE}_${TS}_data_only.sql"

# Clear any existing backup file
> "$OUTPUT_FILE"

# Get all table names, ignoring SQLite internal system tables
TABLES=$(sqlite3 "$DB_FILE" "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")

# Loop through each table and extract rows as INSERT statements
for TABLE in $TABLES; do
    echo "Backing up data from table: $TABLE"
    sqlite3 "$DB_FILE" ".mode insert $TABLE" ".headers on" "SELECT * FROM $TABLE;" >> "$OUTPUT_FILE"
done

echo "Data only backup complete! Saved to $OUTPUT_FILE"

OUTPUT_FILE="cdinventory_backups/${DB_FILE}_${TS}_full.sql"

sqlite3 "$DB_FILE" .dump > "$OUTPUT_FILE"

echo "Full backup complete! Saved to $OUTPUT_FILE"

