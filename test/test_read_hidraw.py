import os

# Replace '0' with your actual device number
device_path = "/dev/barcode"

try:
    with open(device_path, "rb") as f:
        print(f"Reading from {device_path}...")
        while True:
            # Keyboards typically send 8-byte reports
            report = f.read(8)
            if report:
                # Output will be a byte string like b'\x00\x00\x1e\x00...'
                print(f"Raw Report: {report.hex(' ')}")
except PermissionError:
    print("Error: Must run as root (sudo) or fix permissions.")
except FileNotFoundError:
    print(f"Error: Device {device_path} not found.")

