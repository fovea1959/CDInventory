import datetime
import eyed3

def test(s):
    try:
        v1, v2 = eyed3.core.Date._validateFormat(s)
        d = eyed3.core.Date.parse(s)
        print(f"'{s}' -> '{d}' {v1} '{v2}'")
    except Exception as e:
        print(f"'{s}' -> {e}")

now = datetime.datetime.now()

test(now.isoformat()[:19])

d = eyed3.core.Date(year=now.year, month=now.month, day=now.day, hour=now.hour, minute=now.minute, second=now.second)
print(d)


