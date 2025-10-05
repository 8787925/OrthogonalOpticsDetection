from picamera2 import Picamera2, Preview
import time
import cv2
from Libraries import PiRAW2TIF_16bit

picam2a = Picamera2(0)
camera_configa = picam2a.create_still_configuration(
        raw = {},
        queue = False)
picam2a.configure(camera_configa)
picam2a.set_controls({"ExposureTime": 10000, "AnalogueGain": 5})
#picam2a.start_preview(Preview.QTGL)

picam2b = Picamera2(1)
camera_configb = picam2b.create_still_configuration(
        raw = {},
        queue = True)
picam2b.configure(camera_configb)
picam2b.set_controls({"ExposureTime": 10000, "AnalogueGain": 5})
#picam2b.start_preview(Preview.QTGL)
cameras = []
cameras.append(picam2a)
cameras.append(picam2b)

picam2b.start(show_preview=False)
time.sleep(2)
picam2a.start(show_preview=False)

#print("trigger now")
#time.sleep(3)
captures = 5
data_a = []
data_b = []
DO_TIFF = False
for frame in range(captures): 
        if DO_TIFF:
                data_a.append(picam2a.capture_array("raw"))
                data_b.append(picam2b.capture_array("raw"))
                #img_a = cv2.cvtColor(img1[2], cv2.COLOR_YUV420p2RGB) #alternatively cv2.COLOR_YUV2RGB_I420
        else: 
                data_a.append(picam2a.capture_array())
                data_b.append(picam2b.capture_array())
        #img_b = cv2.cvtColor(img2[2], cv2.COLOR_YUV420p2RGB) #alternatively cv2.COLOR_YUV2RGB_I420
        print("Captured frame " + str(frame))

img1 = []
img2 = []
if DO_TIFF: 
        for frames in range(captures): 
                print('Converting and saving frame ' + str(frames))
                img1 = PiRAW2TIF_16bit.imageGreenExtraction(data_a[frames], 'detectionScript_Camera_' + str(1), False, True)
                img2 = PiRAW2TIF_16bit.imageGreenExtraction(data_b[frames], 'detectionScript_Camera_' + str(1), False, True) 
                cv2.imwrite('camsync1.tiff', img1[2])
                cv2.imwrite('camsync2.tiff', img2[2])
else: 
        for frames in range(captures):
                print('Stitching and saving frame ' + str(frames))
                stitched_image = cv2.hconcat([cv2.resize(data_a[frames], (0,0), fx=0.15, fy=0.15), cv2.resize(data_b[frames], (0,0), fx=0.15, fy=0.15)])
                cv2.imwrite('FrameCapture' + str(frames) + '.jpg', stitched_image)
        #cv2.imshow("image a", cv2.resize(img_a, (0,0), fx=0.15, fy=0.15))
        #cv2.imshow("image b", cv2.resize(img_b, (0,0), fx=0.15, fy=0.15))
        #cv2.imshow("image stitched", stitched_image)


""" while True:
        print("collecting image")
        print("\ta")
        data_a = picam2a.capture_array("main")
        print("\tb")
        data_b = picam2b.capture_array("main")
        #picam2a.close()
        #picam2b.close()
        
        print("\t\tconverting images")
        img_a = cv2.cvtColor(data_a, cv2.COLOR_YUV420p2RGB) #alternatively cv2.COLOR_YUV2RGB_I420
        img_b = cv2.cvtColor(data_b, cv2.COLOR_YUV420p2RGB) #alternatively cv2.COLOR_YUV2RGB_I420
        print("\t\tstitching images")
        stitched_image = cv2.hconcat([cv2.resize(img_a, (0,0), fx=0.15, fy=0.15), cv2.resize(img_b, (0,0), fx=0.15, fy=0.15)])
        #cv2.imshow("image a", cv2.resize(img_a, (0,0), fx=0.15, fy=0.15))
        #cv2.imshow("image b", cv2.resize(img_b, (0,0), fx=0.15, fy=0.15))
        #cv2.imshow("image stitched", stitched_image)
        cv2.imwrite("camerasync.jpg", stitched_image)
        cv2.waitKey() """