from thefuzz import fuzz

album1 = "Discovery"
album2 = "Discovery: Deluxe Edition"

# Standard ratio
print(f"Ratio: {fuzz.ratio(album1, album2)}")
# Output: 62

# Token Set Ratio (good for extra appended words)
print(f"Token Set Ratio: {fuzz.token_set_ratio(album1, album2)}")
# Output: 100
