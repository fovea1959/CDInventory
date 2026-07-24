import hid

# You can get Vendor ID and Product ID via 'lsusb'
vendor_id = 0x1d57
product_id = 0x001c

try:
    device = hid.Device(vendor_id, product_id)
    print(f"Connected to: {device.manufacturer}")

    while True:
        # Read up to 64 bytes with a timeout (ms)
        data = device.read(64)
        if data:
            print(f"Data: {data}")
except Exception as e:
    print(f"Error: {e}")
finally:
    device.close()
