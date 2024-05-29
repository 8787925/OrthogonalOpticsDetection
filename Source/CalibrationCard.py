import numpy as np
import cv2

# Class designed to handle prompting a user for input to discover the 6x4 grid of calibration colors within an image
# colors 'known' are defined by the 
class ColorCalibration:

    def __init__(self): 
        # Below is the calibration sRGB data provided for the calibration plaquard
        # Provided data in (R, G, B) order from https://xritephoto.com/documents/literature/en/ColorData-1p_EN.pdf
        data_rgb = [
            (115, 82, 68),
            (194, 150, 130),
            (98, 122, 157),
            (87, 108, 67),
            (133, 128, 177),
            (103, 189, 170),
            (214, 126, 44),
            (80, 91, 166),
            (193, 90, 99),
            (94, 60, 108),
            (157, 188, 64),
            (224, 163, 46),
            (56, 61, 150),
            (70, 148, 73),
            (175, 54, 60),
            (231, 199, 31),
            (187, 86, 149),
            (8, 133, 161),
            (243, 243, 242),
            (200, 200, 200),
            (160, 160, 160),
            (122, 122, 121),
            (85, 85, 85),
            (52, 52, 52)
        ]

        #describe the dimensions of the calibration card
        self.cardRows = 4
        self.cardColumns = 6

        # Convert the data to numpy array
        self.rgb_matrix = np.array(data_rgb)

        # Reorganize the data into BGR format
        self.bgr_matrix = self.rgb_matrix[:, ::-1]

        # Collect the grid of colors from the image input from the user
        self.points = []
        self.clicked = False

        # Storage of the nxn array of calibration tiles
        self.grid_matrices = []
        self.calibrationTransform = []
        self.tileWidth = []
        self.tileHeight = []
        self.tilePercentage_forCalibrating = 0.5 #Use this percentage of the tile size discovered to mean the color there

        #stored reference image
        self.refImage = []

    def select_points(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.points.append((x, y))

            #add the dots to the image of the current list of points
            cloneImage = self.refImage.copy()
            for point in self.points:
                cv2.circle(cloneImage, point, 6, (0, 255, 0), -1)

            self.clicked = True

    def calibrateImage_fromFile(self, imageFile):
        # Load image
        self.refImage = cv2.imread(imageFile)
        self.calibrateImage_byRef(self.refImage, updateRef=False)

    def calibrateImage_byRef(self, image, updateRef=True):
        #Store the reference image if needed 
        if (updateRef): 
            self.refImage = image.copy()

        #Grid matrices for the calibration images
        grid_matrices = []
        cloneImage = image.copy()

        cv2.namedWindow('CalibrationImage')
        cv2.setMouseCallback('CalibrationImage', self.select_points)

        # Display instructions on the screen
        font = cv2.FONT_HERSHEY_SIMPLEX
        org = (50, 200)
        font_scale = 1
        color = (0, 0, 255)
        thickness = 2
        cv2.putText(cloneImage, 'Select the center of the lower left tile, then the lower right, then the upper right.', org, font, font_scale, color, thickness, cv2.LINE_AA)

        # Wait for 3 mouse clicks
        while True:
            cv2.imshow('CalibrationImage', image)
            key = cv2.waitKey(1) & 0xFF

            if len(self.points) == 3:
                break

        # Order the points
        self.points = sorted(self.points, key=lambda x: x[0])

        # Compute the grid
        upper_left, upper_right, lower_right = self.points

        # Compute the vector along the line between the first two points
        vec_x = upper_right[0] - upper_left[0]
        vec_y = upper_right[1] - upper_left[1]
        vec_norm = np.sqrt(vec_x ** 2 + vec_y ** 2)
        vec_x /= vec_norm
        vec_y /= vec_norm

        # Compute the distances
        width = np.sqrt((upper_right[0] - upper_left[0]) ** 2 + (upper_right[1] - upper_left[1]) ** 2)
        height = np.sqrt((lower_right[0] - upper_right[0]) ** 2 + (lower_right[1] - upper_right[1]) ** 2)

        grid_cols = self.cardColumns
        grid_rows = self.cardRows
        tile_width = width / (grid_cols - 1)
        tile_height = height / (grid_rows - 1)

        self.tileHeight = tile_height
        self.tileWidth = tile_width

        # Generate the grid
        grid_matrix = []
        for i in range(grid_rows):
            row = []
            for j in range(grid_cols):
                x = upper_left[0] + j * tile_width * vec_x + i * tile_height * vec_y
                y = upper_left[1] + j * tile_width * vec_y - i * tile_height * vec_x
                row.append((int(x), int(y)))
            grid_matrix.append(row)

        # Draw grid points on the image
        for row in grid_matrix:
            for point in row:
                cv2.circle(cloneImage, point, int((self.tileHeight*self.tilePercentage_forCalibrating)/2), (0, 255, 0), -1)

        #store the grid matrix in the calibration lists
        self.grid_matrices.append(grid_matrix)

        #clear the click data for the mouse callback 
        self.clicked = False
        self.points = []
        
        # Display the grid of points/circles the user has selected
        cv2.imshow('Grid Points', cloneImage)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

        # Begin work now to apply the calibration
        calibration_points = np.flipud(grid_matrix) #points are provided bottom up, adjust by flipping to top-down so that it matches the known-color matrix

        # Extract RGB values of calibration colors from calibration image
        calibrationImage_colors = []
        calAreaWidth = self.tileWidth * self.tilePercentage_forCalibrating
        calAreaHeight = self.tileHeight * self.tilePercentage_forCalibrating

        for row in calibration_points: # bottom up orders
            for point in row:
                #point is in xy format, selection expects yx format - remember
                starty = int(point[1] - (calAreaHeight/2))
                endy = int(point[1] + (calAreaHeight/2))
                startx = int(point[0] - (calAreaWidth/2))
                endx = int(point[0] + (calAreaWidth/2))
                color = np.mean(self.refImage[starty:endy, startx:endx], axis=(0,1))
                calibrationImage_colors.append(color)

        # Known RGB values of calibration colors
        known_colors = self.bgr_matrix 

        # Calculate calibration matrix
        calibration_matrix = np.linalg.lstsq(np.array(calibrationImage_colors), np.array(known_colors), rcond=None)[0]

        # store the calibration results in this class
        self.calibrationTransform = calibration_matrix

        # Apply and display the image correction
        self.applyImageCalibration(self.refImage, displayResult=True)

        # Return calibration matrix for future use (e.g., save to a file)
        return calibration_matrix


    def storeCalibration(self, calibrationMatrix): 
        self.calibrationTransform = calibrationMatrix

    def applyImageCalibration(self, image, displayResult=False):
        if (len(self.calibrationTransform) != 0):
            # Apply calibration matrix to correct colors in new image
            calibrated_image = cv2.transform(image, self.calibrationTransform)

        if displayResult:
            # Display or save calibrated image
            cv2.imshow('Calibrated Image', calibrated_image)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

        return calibrated_image
