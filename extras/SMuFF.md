---
layout: plugin

id: SMuFF
title: OctoPrint-Smuff
description: A plugin for controlling tool changes on the SMuFF from OctoPrint as published on Thingiverse
author: Technik Gegg
license: AGPLv3

date: 2020-02-18

homepage: https://github.com/technik-gegg/OctoPrint-Smuff
source: https://github.com/technik-gegg/OctoPrint-Smuff
archive: https://github.com/technik-gegg/OctoPrint-Smuff/archive/master.zip

tags:
- SMuFF
- MMU
- Multi material
- Multi color
- Multi extruder

screenshots:
- url: https://github.com/technik-gegg/SMuFF-Ifc/blob/master/images/OctoPrint%20plugin.jpg
  alt: Plugin info screen
  caption: Plugin info screen

featuredimage: https://cdn.thingiverse.com/assets/5f/6d/2f/20/0f/featured_preview_SMuFF_Render_newsmall.png

---

This is a very basic plugin for OctoPrint which handles tool changes for the SMuFF (as published on [Thingiverse](https://www.thingiverse.com/thing:3431438)).
This plugin runs in the background and tracks tool changes (Tx) via the **octoprint.comm.protocol.gcode.queuing** hook of OctoPrint.
When triggered, it'll send the according command to the SMuFF via the Raspberry's second onboard UART ttyS0.

For further information on how to configure your Raspberry Pi, please visit this [Github repository](https://github.com/technik-gegg/OctoPrint-Smuff).
