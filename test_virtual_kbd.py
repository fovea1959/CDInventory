from evdev import UInput, ecodes as e, InputDevice
import sys

# Replace with your keyboard device path
PHYSICAL_KBD = '/dev/input/event6'

# 1. Grab the physical device
dev = InputDevice(PHYSICAL_KBD)
dev.grab() # Prevents keys from reaching the system

# 2. Define the new virtual device capabilities
capabilities = {
    e.EV_KEY: [e.KEY_A, e.KEY_B, e.KEY_C, e.KEY_SPACE, e.KEY_ENTER]
}

# 3. Create the virtual device
with UInput(capabilities, name='virtual-usb-keyboard') as ui:
    print(f"Virtual device {ui.name} created.")
    for event in dev.read_loop():
        if event.type == e.EV_KEY:
            # Example: Map KEY_A to KEY_B
            if event.code == e.KEY_A:
                event.code = e.KEY_B

            # Re-emit the event
            ui.write(e.EV_KEY, event.code, event.value)
            ui.write(e.EV_KEY, event.code, event.value)
            ui.syn()
