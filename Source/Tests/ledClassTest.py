

from LargeLEDArray import *
import argparse
import time

# Main program logic follows:
if __name__ == '__main__':
    # Process arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--clear', action='store_true', help='clear the display on exit')
    args = parser.parse_args()

    LEDArray = LargeLEDArray()

    print ('Press Ctrl-C to quit.')
    if not args.clear:
        print('Use "-c" argument to clear LEDs on exit')

    try:
        testColorList = [[50, 0, 0], [0, 255, 0], [0, 0, 50]]
        ringList = [0, 1, 2, 3]
        addressList = [[0, 1, 2], [0, 1, 2], [0, 1, 2], [0, 1]]
        while True:
            #for each ring
            for colorList in testColorList:
                LEDArray.appendLEDRingAddress_Append(colorList, ringList, addressList)

                LEDArray.ledUpdate()
                time.sleep(1)

            for colors in testColorList:
                LEDArray.setAllLEDs(colors)
                time.sleep(1)

    except KeyboardInterrupt:
        LEDArray.ledClearAll()
        time.sleep(150/1000)

        if args.clear:
            print('Exit test')