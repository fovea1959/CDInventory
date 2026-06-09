import json

import musicbrainzngs as mb

mb.set_useragent("MyCDLookupApp", "0.1", "https://github.com")

# Formulate a strict query filtering for the 'CD' format
query = 'barcode:"4011222045416"'

result = mb.search_releases(query=query, limit=5)

if "release-list" in result:
    for release in result["release-list"]:
        album_name = release.get("title")
        artist = release.get("artist-credit-phrase")
        mbid = release.get("id")  # MusicBrainz Identifier

        print(f"Match: {album_name} - {artist} (MBID: {mbid})")
        print(json.dumps(release))

else:
    print("No matching CD found.")
