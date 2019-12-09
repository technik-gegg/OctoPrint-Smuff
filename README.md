# OctoPrint-Smuff

This is a very basic plugin for OctoPrint which handles tool changes for the SMuFF ([as published on Thingiverse](https://www.thingiverse.com/thing:3431438/)).
This plugin runs in the background and tracks tool changes (**Tx**) via the **octoprint.comm.protocol.gcode.queuing** hook of OctoPrint.
In such case, it'll send the according command to the SMuFF via the Raspberry's second onboard UART **ttyS0**.

## Setup

Install via the bundled [Plugin Manager](https://github.com/foosel/OctoPrint/wiki/Plugin:-Plugin-Manager)
or manually using this URL:

    https://github.com/technik-gegg/OctoPrint-Smuff/archive/master.zip

In order to make this plugin working as expected, you have to do two additional things:

- Setup the UART mode in your Raspberry
- connect the Raspberry to your SMuFF controller (via 3-Wire serial interface)

## Setting up your Raspberry Pi

Simply launch **raspi-config** in a terminal window on your Raspberry Pi, then go to **Interfacing Options** and choose **Serial**.
Set **login shell over serial** to **No** and **serial port hardware enabled** to **Yes**.
Finish raspi-config and reboot. After rebooting, make sure you'll see the **ttyS0** device in your **/dev** folder.
Here's a nice article on that configuration from [ABelectronics UK](https://www.abelectronics.co.uk/kb/article/1035/raspberry-pi-3--4-and-zero-w-serial-port-usage).

For the physical, serial connection take a 3-Wire cable and connect the pins **6 or 9 (GND)**, **8 (TX, aka GPIO14 aka UART0_TXD)** and **10 (RX aka GPIO15 aka UART0_RXD)** of the Raspi extension connector to the serial interface of your SMuFF (on the SKR V1.1 mini that's the port named TFT).

![Raspi-Connector](https://www.rs-online.com/designspark/rel-assets/dsauto/temp/uploaded/githubpin.JPG)

Image: Raspberry Pi extension connector

Make sure that you have a cross-over connection:

- GND goes to GND
- TX goes to RX
- and RX goes to TX

You don't have to wire any of the power pins (+5V or +3.3V).
Please make sure you have your SMuFF configured for **115200 baud** as well.

## Interfacing

Here's a picture how all the stuff comes together:

![OctoPrint Config](https://github.com/technik-gegg/SMuFF-Ifc/blob/master/images/Config_OctoPrint.png)

The main difference to point out would be, that your printers extuder stepper driver (E0/E1) is not connected to your extruder anymore but instead to the Feeder of the SMuFF directly.
OctoPrint is controlling your printer and feeding it with the GCodes, while it's also controlling the SMuFF when a tool change is pending.
All necessary operations for a tool change (i.e. unloading current filament, loading new filament, purging etc.) need to be configured in the OctoPrint settings within the GCode-Scripts section **Before tool change** and **After tool change**.

## Configuration

There's not much configuration going on here, since the only relevant paramter is the baudrate using to connect between from the Raspberry Pi to the SMuFF.
This has been constantly set to **115200 baud**, which ought to be fast enough.
If, for some reason, you have to change this baudrate, you'll have to modify it within the __init__.py source file.
