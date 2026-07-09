import csv

unmatched = []
with open('matchup.csv', newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    unmatched = list(reader)

with open('matchup.html', 'w') as h:
    print('<!DOCTYPE html><html lang="en"><body>', file=h)
    for row in unmatched:
        rid = row["cd_musicbrainz_release_id"]
        title = row["cd_title"]
        artists = row["cd_artists"]
        print(f'<div><a href="http://localhost:8000/openalbum?id={rid}" target="_blank">{artists} {title}</a></div>', file=h)

    print('</body></html>', file=h)
