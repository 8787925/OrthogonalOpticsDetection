#!/usr/bin/env python3
import cv2
import numpy as np
import glob
import os

# v3.00
valid = 0

def imageGreenExtraction(numpyRAWMatrix, fileName, saveFile):
    image = numpyRAWMatrix
    # check size
    if image.size == 1658880:  #Pi3 1536x864
        cols = 1536
        rows = 864
        valid = 1
    elif image.size == 14929920: #Pi3 4608x2592
        cols = 4608
        rows = 2592
        valid = 1
    elif image.size == 3732480: #Pi3 2304x1296
        cols = 2304
        rows = 1296
        valid = 1
    elif image.size == 384000:  #Pi2 640x480
        cols = 640
        rows = 480
        valid = 1
    elif image.size == 2562560: #Pi2 800x600
        cols = 1664
        rows = 1232
        valid = 1
    elif image.size == 10171392: #Pi2 3280x2464
        cols = 3280
        rows = 2464
        valid = 1
    elif image.size == 2592000:  #Pi2 1920x1080
        cols = 1920
        rows = 1080
        valid = 1
    elif image.size == 1586304:  #Pi1 1296x972
        cols = 1296
        rows = 972
        valid = 1
    elif image.size == 6345216:  #Pi1 2592x1944
        cols = 2600
        rows = 1944
        valid = 1
    elif image.size == 4669440:  #PiHQ 2028x1520
        cols = 2048
        rows = 1520
        valid = 2
    elif image.size == 3317760:  #PiHQ 2028x1080
        cols = 2048
        rows = 1080
        valid = 2
    elif image.size == 18580480:  #PiHQ 4056x3040
        cols = 4056
        rows = 3040
        valid = 2
    else:
        valid = 0
        print("Failed to find suitable file ",files[x])

    # process if a valid size
    if valid > 0:
        # trim off 
        if image.size == 10171392:
            image = image.reshape(int(image.size/4128),4128)
            for j in range(4127,4099,-1):
                image  = np.delete(image, j, 1)
        elif image.size == 6345216:
            image = image.reshape(int(image.size/3264),3264)
            for j in range(3263,3249,-1):
                image  = np.delete(image, j, 1)
        elif image.size == 18580480:
            image = image.reshape(int(image.size/6112),6112)
            for j in range(6111,6083,-1):
                image  = np.delete(image, j, 1)
        elif image.size == 1586304:
            image = image.reshape(int(image.size/1632),1632)
            for j in range(1631,1619,-1):
                image  = np.delete(image, j, 1)
        
        # extract data
        if valid == 2:
            A = image.reshape(int(image.size/3),3) #arrange the A matrix so that columns 0 and 1 are all 'unmixed' data and column 2 is 'mixed'
            B  = np.split(A, [2,3], axis=1) #Extract the first 2 columns in to B[0] and the final column (mixed data) into B[1]

        B[0] = B[0] * 256 #the matrix which contains the whole upper bytes only.  B/G/R 4::11... this is 'shifting' this whole byte FIRST - by 4 bits (16) to accomodate the lower 4 bits of the total 12 (of which this matrix is the upper 8) AND SECOND - to scale the 12-bits UP to the 16-bit range it will eventually occupy.  Total shift being 8-bits
        C  = B[0].reshape(int(rows/2),int(cols*2)) #twice the number of columns (because??) - half the number of rows because of the next step (we'll be separating a matrix of BlueGreen rows and RedGreen rows )
        D  = np.split(C, 2, axis=1) #D[0] is BlueGreen row data only, D[1] is GreenRed row data only D is now the shape of (1/2Rows x Columns) of a full frame - split into the two types of Bayer filter lines
        
        #Work to decode all the green/blue row content
        H  = D[0].reshape(int(D[0].size/2),2) #green/blue row content
        I  = np.split(H, 2, axis=1) #I[0] contains the single-dimm list of all Green values (umixed greens) of even rows, I[1] contains all the Blue values
        if valid == 2:
            E  = B[1].reshape(int(B[1].size/2),2) #Remember that B[1] is all the 'mixed' values - which contain bits from two different colors within their uint8
            F  = np.split(E, 2, axis=1)
            #These fractional bits are the lower 4 bits of the total 12.  But they're being shifted by an additional 4 - to shift-multiply/scale the 12-bits into 16.
            I[0] = I[0] + (np.unpackbits(F[0], axis=1)[:,0:1]*128) + (np.unpackbits(F[0], axis=1)[:,1:2]*64) + (np.unpackbits(F[0], axis=1)[:,2:3]*32) + (np.unpackbits(F[0], axis=1)[:,3:4]*16)
            I[1] = I[1] + (np.unpackbits(F[1], axis=1)[:,4:5]*128) + (np.unpackbits(F[1], axis=1)[:,5:6]*64) + (np.unpackbits(F[1], axis=1)[:,6:7]*32) + (np.unpackbits(F[1], axis=1)[:,7:8]*16)
        b  = I[0].reshape(int(rows/2),int(cols/2))
        g0 = I[1].reshape(int(rows/2),int(cols/2))

        #Start to work for decoding the Green/Red row content
        L  = D[1].reshape(int(D[0].size/2),2) #green/red row content
        M  = np.split(L, 2, axis=1) #M is the matrix of all the 'odd' row greens and all red values (M[1] = red)
        if valid == 2:
            E  = B[1].reshape(int(B[1].size/2),2)
            F  = np.split(E, 2, axis=1) #F now contains all the fractional (mixed) bytes
            M[0] = M[0] + (np.unpackbits(F[0], axis=1)[:,0:1]*128) + (np.unpackbits(F[0], axis=1)[:,1:2]*64) + (np.unpackbits(F[0], axis=1)[:,2:3]*32) + (np.unpackbits(F[0], axis=1)[:,3:4]*16)
            M[1] = M[1] + (np.unpackbits(F[1], axis=1)[:,4:5]*128) + (np.unpackbits(F[1], axis=1)[:,5:6]*64) + (np.unpackbits(F[1], axis=1)[:,6:7]*32) + (np.unpackbits(F[1], axis=1)[:,7:8]*16)
        g1 = M[0].reshape(int(rows/2),int(cols/2))
        r  = M[1].reshape(int(rows/2),int(cols/2))

        if saveFile: 
            # some basic colour correction
            Red   = r * 1
            Blue  = b * 1
            Green = ((g0/2) + (g1/2)) * 0.7
            Green = Green.astype(np.uint16)

            # combine B,G,R
            BGR=np.dstack((Blue,Green,Red)).astype(np.uint16)
            res = cv2.resize(BGR, dsize=(cols,rows), interpolation=cv2.INTER_CUBIC)
            res = res.astype(np.uint16)
                    
            # save output
            cv2.imwrite(fileName + ".tif", res)
        return [g0, g1]
        # show corrected result
        #result = cv2.resize(res, dsize=(int(cols/4),int(rows/4)), interpolation=cv2.INTER_CUBIC)
    else: 
        print('Cannot load photo, unrecognized shape')
