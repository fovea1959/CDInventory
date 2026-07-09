import csv
import datetime

locations = {}
with open('locations.csv', newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        locations[row['location_description']] = row['location_id']

print(locations)

update_seen = set()
update_location = {}

with open('fix_locations.csv', newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        id = row['cd_id']

        fixed = row['fixed']
        seen = row['seen']

        if len(seen) > 0:
            update_seen.add(id)

        if len(fixed) > 0:
            update_location[id] = locations[fixed]

print(update_seen)
print(update_location)

now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
for id in update_seen:
    print(f"update cds set cd_last_seen = '{now}' where cd_id = {id};")

for id, location_id in update_location.items():
    print(f"update cds set cd_location_id = '{location_id}' where cd_id = {id};")