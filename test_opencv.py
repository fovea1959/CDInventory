import cv2
import pyzbar.pyzbar

# Initialize camera
cap = cv2.VideoCapture(0)

last_data = None
while True:
    # Read frame
    ret, frame = cap.read()
    if not ret: break

    # Process: Convert to grayscale and blur
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    cv2.imshow('Gray', gray)

    zbar = pyzbar.pyzbar.decode(gray)
    if len(zbar) > 0:
        d = zbar[0].data
        if d != last_data:
            print(d, zbar)
            last_data = d

    # processed = cv2.GaussianBlur(gray, (15, 15), 0)
    # cv2.imshow('Processed', processed)

    # Exit with 'q'
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Cleanup
cap.release()
cv2.destroyAllWindows()
