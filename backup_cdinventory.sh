#!/bin/bash

R="/media/wegscd/EF5F-E606/restic_Music_raw"

restic -r $R/ -p $R/password --verbose backup cdinventory_backups/ CDInventory.db
