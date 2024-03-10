# System Hardware and Flashing 
## Electronics Hardware 
### IO Board and Compute Module
- [Raspberry Pi Compute Module](https://www.pishop.us/product/raspberry-pi-compute-module-4-wireless-8gb-16gb-cm4108016/)
	- 8gb RAM 16gb EMMC
	- Contains EMMC - no memory card required for support. 
- [Raspberry Pi Compute Module IO Board](https://www.pishop.us/product/raspberry-pi-compute-module-cm4io-board/)
	- Includes NO jumpers for configuring - you'll have to have at least 3 2-pin jumpers available for use in this project. 
- [Barrel Power Adapter](https://www.pishop.us/product/12v-2a-power-supply-5-5x2-1mm-dc-jack-for-cm4/) simple 12v barrel power for the CM4 board
### Case
- [Waveshare CM4 IO Case](https://www.pishop.us/product/metal-box-a-for-raspberry-pi-compute-module-4-io-board-with-cooling-fan/) CM4-IO-BOARD-CASE-A
	- Includes a Right Angle adapter for the 40-pin header (rpi header)
- [2.5/5Ghz Antenna Stub + Antenna](https://www.amazon.com/dp/B07PBFKJSN?psc=1&ref=ppx_yo2ov_dt_b_product_details)
	- The outlet of the case is slightly undersized to use any ordinary SMA antenna plug-in directly (from what I saw) because normally those direct-to-antenna cabled don't have the 'D' thread flat which the case DOES have.  So buying the stub cable provided the needed setup and made it look a little cleaner. 
	- The SMA connector goes internally directly to the Compute Module

### Cameras and Optics
- [Raspberry Pi HQ Camera from CanaKit](https://www.canakit.com/raspberry-pi-hq-camera.html)
- [Raspberry Pi HQ Telephoto Lens](https://www.canakit.com/raspberry-pi-hq-camera-16mm-telephoto-lens.html)
- [30cm Camera Adapter Cable (IO Board supports the 'Mini' type ribbon cable)](https://www.amazon.com/dp/B08C2D57N2?psc=1&ref=ppx_yo2ov_dt_b_product_details)
- [Polarizing Filter](https://www.amazon.com/dp/B0C2P9P833?psc=1&ref=ppx_yo2ov_dt_b_product_details)
- [20mm Side-Length 45deg 50/50 Beam Splitter](https://www.amazon.com/dp/B0B34FK2GF?psc=1&ref=ppx_yo2ov_dt_b_product_details)
### LED Array
- [9-Ring LED Array](https://www.amazon.com/dp/B083VWVP3J?psc=1&ref=ppx_yo2ov_dt_b_product_details)

## Flashing and First Startup
1) Flash the device by setting jumper set 1 at J2
	1) Flash with 64-bit PI4 image
2) Enable the Camera inputs
	1) ![[Cm4 jumper config 1.jpg]]
3) Jumper both positions at J6 (i2c fix)
	1) This jumper-ing being set, negates instructions (out of date) that suggest you need to 'map' the i2c 0 pins to the CAM0 connection

The hardware should be bootable and ready to be configured now 
# Camera and Configuration
The below steps are largely from: [Raspberry Pi Camera Hookup Documentation](https://www.raspberrypi.com/documentation/computers/compute-module.html#attaching-a-raspberry-pi-camera-module) and can be found frozen as a pdf in: [[Raspberry Pi Documentation - Compute Module hardware.pdf]]

1) open the boot config, and turn on the CAM0 output
	1) `sudo nano /boot/firmware/config.txt`
	2) Uncomment and configure the lines:
		1) `camera_auto_detect=1`
		2) `dtparam=i2c_arm=on`
	3) Add the lines after the `[cm4]` section: 
		1) `dtparam=cam0_reg` Knowing here that you should set 0 or 1 for the cam number being activated (same as the connector label)
		2) `dtoverlay=imx477,cam0`
			1) 
				|v1 camera|`dtoverlay=ov5647,cam1`|
				|v2 camera|`dtoverlay=imx219,cam1`|
				|v3 camera|`dtoverlay=imx708,cam1`|
				|HQ camera|`dtoverlay=imx477,cam1`|
				|GS camera|`dtoverlay=imx296,cam1`|
	1) Then reboot: 
		1) `sudo reboot`
2) Check the system's use of the camera:  _**THE LIBRARY rpicam IS DEAD IN 64-BIT OS**_
	1) `libcamera-hello` should yield a list of frame status' along with a 'good'
	2) `libcamera-still -o './imgTest.jpeg` should deposit the still. 

**The Camera should WORK at this point**

# Python
You have to remove the 'EXTERNALLY MANAGED' file found in 
`/usr/lib/python3.11`
![[Pasted image 20240215203122.png]]

This is a new default file distributed in Raspberry PI's OS - and is aimed at managing docker installed stuff and doesn't matter for this purpose-built system.  Just delete the file and this will permit the use of 'pip' installation of python libraries 

## Install the following libraries
- `sudo pip install opencv-python`
- `sudo pip install rpi-ws281x`
- `sudo pip install picamera2`
- `sudo pip install numpy`
