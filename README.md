# OctoPrint-Smuff

This is a plugin for OctoPrint which handles tool changes for the SMuFF ([as published on Thingiverse](https://www.thingiverse.com/thing:3431438/)).
This plugin runs in the background and tracks tool changes (**Tx**) via the **octoprint.comm.protocol.gcode.queuing** and **octoprint.comm.protocol.gcode.send** hooks of OctoPrint.
When triggered, the plugin will send the according **Tx** command to the SMuFF via the Raspberry's second onboard UART **ttyS0** (RPI-3) or **ttyAMA1** (RPI-4).

## Setup

Install via the bundled [Plugin Manager](https://github.com/foosel/OctoPrint/wiki/Plugin:-Plugin-Manager)
or manually using this URL:

    https://github.com/technik-gegg/OctoPrint-Smuff/archive/master.zip

In order to make this plugin working as expected, you have to do two additional things:

- Setup the UART mode in your Raspberry
- connect the Raspberry to your SMuFF controller (via 3-Wire serial interface)

## Setting up your Raspberry Pi

Open the **/boot/config.txt** file on your Raspberry Pi and add the following lines to it:

![Raspi-Config](https://github.com/technik-gegg/OctoPrint-Smuff/blob/master/extras/Raspi-Config-txt.jpg)

Save the configuration and reboot. After rebooting, make sure you'll see the **ttyS0** device (RPI-3) or the **ttyAMA1** device (RPI-4) in your **/dev** folder.

For the physical, serial connection take a 3-Wire cable and connect the pins **6 or 9 (GND)**, **8 (TX, aka GPIO14 aka UART0_TXD)** and **10 (RX aka GPIO15 aka UART0_RXD)** of the Raspi-3 extension connector to the serial interface of your SMuFF (on the SKR V1.1 mini that's the header named **TFT**).

![Raspi-Connector](https://github.com/technik-gegg/OctoPrint-Smuff/blob/master/extras/Raspi3-GPIO.jpg)

*Image: Raspberry Pi-3 expansion header*

For the Raspberry Pi 4 it's recommended using the 2nd UART from the PLO11, since it's a "real" UART. The TX and RX signals for this UART can be found at the pins GPIO0 and GPIO1.

![Raspi-Connector](https://github.com/technik-gegg/OctoPrint-Smuff/blob/master/extras/Raspi4-GPIO.jpg)

*Image: Raspberry Pi-4 expansion header*

Make sure that you have a cross-over connection for the TX and RX lines:

- GND goes to GND
- TX goes to RX
- and RX goes to TX

**Notice**: *You don't have to wire any of the power pins (+5V or +3.3V), since both, the Raspberry and the SMuFF, are supposed to be powered on their own.*

Please make sure you have your SMuFF configured for **115200 baud** as well.

## Interfacing

Here's a picture how all the stuff comes together:

![OctoPrint Config](https://github.com/technik-gegg/SMuFF-Ifc/blob/master/images/Config_OctoPrint.png)

The main difference to point out would be, that your printers extuder stepper driver (E0/E1) is not connected to your extruder anymore but instead to the Feeder of the SMuFF directly.
OctoPrint is controlling your printer and feeding it with the GCodes, while it's also controlling the SMuFF when a tool change is pending.
All necessary operations for a tool change (i.e. unloading current filament, loading new filament, purging etc.) need to be configured in the OctoPrint settings within the GCode-Scripts section **Before tool change** and **After tool change**.

## Configuration

There's not much configuration going on here, since the only relevant paramters are the baudrate and the serial port used to connect the Raspberry Pi to the SMuFF.
The baudrate has been set constantly to **115200 baud**, which ought to be fast enough.
If you have to change the baudrate or the port, you'll have to modify it within the __init__.py source file at the very top.

As you open the **Settings** dialog for the plugin, you'll be provided with some information whether or not the plugin was able to connect to the SMuFF. If the connection was sucessful, you'll see the firmware information coming directly from the SMuFF.
If you don't see the firmware info here, you'll need to check your physical connection.

![OctoPrint SMuFF plugin](https://github.com/technik-gegg/OctoPrint-Smuff/blob/master/extras/Settings-Screen.jpg)

Also, there's an indicator in the navbar of OctoPrint, showing you which tool is currently selected and whether or not filament has been loaded (i.e. Feeder endstop has triggered). Please notice, that the navbar indicator is being updated frequently.

![OctoPrint SMuFF plugin Navbar](https://github.com/technik-gegg/OctoPrint-Smuff/blob/master/extras/Navbar.jpg)

## Additional setup

The main configuration will happen in the **OctoPrint GCODE Scripts section**.
You have to apply the GCodes that will be executed **before** and **after** the tool change triggers. In those scripts you have to configure all the movements and retractions/feeds needed for a successful filament swapping.
The picture below shows you a sample of such scripts. Be aware that you have to modify these scripts to accomodate your printer setup (i.e. bowden tube length, speeds, etc.).

![OctoPrint GCODE Scripts](https://github.com/technik-gegg/OctoPrint-Smuff/blob/master/extras/OctoPrint-Scripts.jpg)

Here are the sample scripts in detail. Simply copy and paste this into your OctoPrint GCodes.
Needless to say that you have to adopt these scripts (bowden length, hotend length) to the setup of your printer.

    ;-------------------------------------------
    ; beforeToolChange script
    ;-------------------------------------------
    M400				; wait for move to complete
    G60 S1				; save current positions (must be enabled in the FW)
    M83				; set extruder to relative mode (important)
    G1 E-5 F5000			; retract 5 mm to avoid oozing
    G91				; switch to relative positioning
    G1 Z15 F8000			; lift nozzle
    G90				; switch back to absolute positioning
    G1 X0 Y0 F15000			; move to change position
    M83				; set extruder to relative mode (important)
    ;-------------------------------------------
    ; the next two lines must match your setup
    ; that's bowden length (500) + hotend length (45), 
    ; SMuFF selector width (90)
    ;-------------------------------------------
    G1 E-45 F5000 	; Retract from nozzle
    G1 E-255 F4000	; Retract filament according to your bowden length
    G1 E-240 F4000	; Retract filament according to your bowden length
    G1 E-65 F1200	; Retract from selector (slowly)

    M400		; wait for move to complete
    ;-------------------------------------------
    ; the next line is important and must not be removed!
    ;-------------------------------------------
    @SMuFF LOAD

    
    ;-------------------------------------------
    ; afterToolChange script
    ;-------------------------------------------
    M83		; set extruder to relative mode (important)
    G1 E65 F1500	; Feed slowly from Selector into the bowden tube
    G1 E300 F4000	; Feed to hot end (fast)
    G1 E200 F4000	; Feed to hot end (fast)
    G1 E45 F500	; Feed down to nozzle (slow)
    ;-------------------------------------------
    ; use the next line only if you're not 
    ; printing with a purge tower!
    ;-------------------------------------------
    ;G1 E100 F240	; Purge out old filament

    M400			; wait for move to finish
    G61 S1 XYZ F2400	; restore saved positions (must be enabled in the FW)

## Testing your GCode scripts

The easiest way to test out your GCode scripts is allowing the printer doing cold extrusions (**M302 S0**) and by initiating tool changes by sending **Tx** commands from the OctoPrint Terminal.

I did it by utilizing the [Teminal Commands Extend plugin](https://github.com/jneilliii/OctoPrint-TerminalCommandsExtended) from author *jneilliii*.

![Marlin Extruder Configuration](https://github.com/technik-gegg/OctoPrint-Smuff/blob/master/extras/Terminal-Commands.jpg)

As you may have spotted in the picture, there are some convenience commands such as Servo open/close. The (pseudo) GCode for this is *@SMuFF SERVO 1 1* for closing and *@SMuFF SERVO 1 0* for opening the servo.

**Important:** Remove the bowden tube from the hotend before you do this.

If your scripts are set up correctly, the tool changing will end up with filament sticking out at the end of the bowden tube. The length of the filament sticking out is supposed to be the length of your hotend (more or less the distance from inlet/fitting to nozzle).

## Marlin setup (IMPORTANT!)

In order to make it all play well together with Marlin, you have to modify some settings in your firmware, recompile and flash it to your printer.
If you haven't updated your firmware to Marlin 2.0.x yet, this might be the right moment to do this.

First of all, you need to tell your Marlin it's a multi extruder setup by defining the number of tools used:

![Marlin Extruder Configuration](https://github.com/technik-gegg/OctoPrint-Smuff/blob/master/extras/Extruders-Config.jpg)

Also important: Remove the comments in front of the **SINGLENOZZLE** definition.

Event though OctoPrint controls tool changes via the SMuFF and the printer won't receive any T*x* GCode, it'll send the initial temperature settings for each "Extruder", which usually come out of your slicers GCode. If the Printer isn't configured for multi material, this will lead to error messages and OctoPrint might reset the current tool to T0 - which will eventually select the wrong tool.

Next, you have to set up fake steppers, to satisfy the Marlin sanity check. Do so by duplicating the **E*x*_STEP_PIN**, **E*x*_DIR_PIN** and **E*x*_ENABLE_PIN** in your printers *Configuration.h* or your printers *Pins.h* for each extruder defined in the first step and set them all to the same pin numbers as for **E0_*xxx*_PIN**:

![Marlin Fake Steppers](https://github.com/technik-gegg/OctoPrint-Smuff/blob/master/extras/Fake-Stepper-Pins.jpg)

Next, comment out **PREVENT_LENGTHY_EXTRUDE**. Otherwise this will lead to problems while trying to swap the filament:

![Marlin Extrusion Length](https://github.com/technik-gegg/OctoPrint-Smuff/blob/master/extras/Extrusion-Length.jpg)

You may leave it in there and redefine the **EXTRUDE_MAXLENGTH**, as I've tried to, but it didn't work out for negative extrusions (a.k.a retractions). The Marlin firmware still reported an error.

Finally, enable the option to store/restore positions by the **G60/G61** GCodes, since this feature is being used in the after-/beforeToolChange scripts:

![Marlin G60/G61](https://github.com/technik-gegg/OctoPrint-Smuff/blob/master/extras/G60-Enable.jpg)

## Slicing multi material models

To set up a test print, you need to slice a multi material model first and then upload it to OctoPrint.
Please notice: This plugin won't work if you copy the sliced model directly to your printers SD-Card. You have to use the OctoPrints internal storage for this.

To be able to slice multi material models you need to set up you slicer accordingly. There is a fantastic video on this topic from [Michael (a.k.a.Teaching Tech)](https://www.youtube.com/channel/UCbgBDBrwsikmtoLqtpc59Bw) which covers all the known slicers [here](https://www.youtube.com/watch?v=xRtvbICRh1w).
