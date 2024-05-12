import cv2
import numpy as np
import pickle

def align_images(img1, img2, alignedImageName=''):
    # Convert images to grayscale after guaranteeing 8 bit
    if img1.dtype == 'uint16': 
        img1 = cv2.normalize(img1, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        img2 = cv2.normalize(img2, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

    # Detect keypoints and descriptors using SIFT
    sift = cv2.SIFT_create()
    keypoints1, descriptors1 = sift.detectAndCompute(gray1, None)
    keypoints2, descriptors2 = sift.detectAndCompute(gray2, None)

    # Match descriptors between the two images
    matcher = cv2.DescriptorMatcher_create(cv2.DescriptorMatcher_FLANNBASED)
    matches = matcher.knnMatch(descriptors1, descriptors2, k=2)

    # Filter good matches using Lowe's ratio test
    good_matches = []
    for m, n in matches:
        if m.distance < 0.75 * n.distance:
            good_matches.append(m)

    # Extract keypoints of good matches
    src_pts = np.float32([keypoints1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([keypoints2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    # Find homography matrix
    H, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

    if alignedImageName != '':
        # Warp img1 to img2 using the homography matrix
        aligned_img_reference = cv2.warpPerspective(img1, H, (img2.shape[1], img2.shape[0]))
        #aligned_img_tgt = cv2.warpPerspective(img3, H, (img4.shape[1], img4.shape[0]))

        #cv2.imwrite(targetImgName + '.tiff', aligned_img_tgt)
        cv2.imwrite(alignedImageName + '.tiff', aligned_img_reference)

    return H

def align_fromHomography(image, homographyMatrix): 
    aligned_img_tgt = cv2.warpPerspective(image, homographyMatrix, (image.shape[1], image.shape[0]))
    return aligned_img_tgt

def align_affine(img1, img2): 
    image1 = img1 #cv2.imread('image1.jpg', cv2.IMREAD_GRAYSCALE)
    image2 = img2 #cv2.imread('image2.jpg', cv2.IMREAD_GRAYSCALE)

    # Detect keypoints and compute affine transformation
    orb = cv2.ORB_create()
    kp1, des1 = orb.detectAndCompute(image1, None)
    kp2, des2 = orb.detectAndCompute(image2, None)

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des1, des2)

    src_pts = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)

    H, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

    # Apply the affine transformation to image1
    aligned_image = cv2.warpAffine(image2, H[:2], (image2.shape[1], image2.shape[0]))
    return H

# Load images
def imageCalibrationTests(): 
    image1 = cv2.imread('walltest_cam0.tiff')
    image2 = cv2.imread('walltest_cam1.tiff')
    #image3 = cv2.imread('led_on_rawImage_Test_Camera_0.tiff')
    #image4 = cv2.imread('led_on_rawImage_Test_Camera_1.tiff')

    # Align the images
    aligned_image = align_images(image1, image2, 'walltest_alternateAlignment', 'alignedReference_alternatAlignment.pickle')
    cv2.imwrite('walltest_secondSaveAlternate.tiff', aligned_image)
