from threading import Thread, Event
from pprint import pformat

import json
import re
import time
import sys
import traceback
import logging

try:
    import serial
except ImportError:
    logging.critical("SMuFF: Python library 'pySerial' is missing. Please use 'pip install pyserial' first!")

VERSION_NUMBER 	= 1.13 					# Module version number (for scripting)
VERSION_DATE 	= "2022/06/22"
VERSION_STRING	= "SMuFF Module V{0} ({1})" # Module version string

FWINFO			= "M115"        		# SMuFF GCode to query firmware info
PERSTATE    	= "M155"     			# SMuFF GCode for enabling sending periodical states
OPT_ON 			= " S1" 				# SMuFF GCode option for turning features on
OPT_OFF			= " S0"					# SMuFF GCode option for turning features off
WIPE			= "G12"         		# SMuFF GCode to wipe nozzle
CUT				= "G12 C"        		# SMuFF GCode to cut filament
SETSERVO		= "M280 P{0} S{1}" 		# SMuFF GCode to position a servo
LIDOPEN			= "M280 R0"     		# SMuFF GCode to open Lid servo
LIDCLOSE		= "M280 R1"     		# SMuFF GCode to close lid servo
TOOL			= "T"           		# SMuFF GCode to swap tools
HOME 			= "G28"					# SMuFF GCode for homing
GETCONFIG 		= "M503 S{0}W"			# SMuFF Gcode to query configuration settings (in JSON format)
SETPARAM 		= "M205 P\"{0}\"S{1}"	# SMuFF GCode for setting config params
LOADFIL			= "M700"				# SMuFF GCode to load active tool
UNLOADFIL		= "M701"				# SMuFF GCode to unload active tool
MOTORSOFF		= "M18"					# SMuFF GCode to turn stepper motors off
UNJAM 			= "M562"				# SMuFF GCode to reset the Feeder jammed flag
RESET 			= "M999"				# SMuFF GCode to reset the device
AUTOLOAD		= " S1"          		# additional parameter for auto load after tool swap
FAN_ON 			= "M106 S100"			# SMuFF GCode to turn on housing fan (100%)
FAN_OFF 		= "M107"				# SMuFF GCode to turn off housing fan
ANY 			= "ANY"

# Texts used in console response
T_OK 				= "Ok."
T_ON				= "ON"
T_OFF				= "OFF"
T_YES 				= "YES"
T_NO 				= "NO"
T_TRIGGERED 		= "TRIGGERED"
T_NOT_TRIGGERED 	= "NOT " + T_TRIGGERED
T_REMOVED			= "REMOVED"
T_INSERTED			= "INSERTED"
T_OPENED			= "OPENED"
T_CLOSED			= "CLOSED"
T_EXTERNAL 			= "EXTERN"
T_INTERNAL 			= "INTERN"
T_NO_TOOL 			= "NO TOOL"
T_TO_SPLITTER		= "TO SPLITTER"
T_TO_SELECTOR 		= "TO SELECTOR"
T_TO_DDE 			= "TO DDE"
T_INVALID_STATE 	= "UNKNOWN"
T_CFG_GCODE_ERR		= "SMuFF requires [{0}] to work, please add it to your config!"
T_CFG_ERR 			= "No serial port defined for SMuFF. Put serial=/dev/serial/xxx into 'smuff.cfg', where xxx is the 'by-id' value of the tty the SMuFF is connected to."
T_NOT_CONN			= "SMuFF is not yet connected. Use SMUFF_CONNECT first and check 'smuff.cfg' for the correct 'serial' setting."
T_SMUFF_ERR 		= "SMuFF responded with error! [{0}]."
T_SMUFF_RESPONSE 	= "SMuFF responded with {0}."
T_NO_PARAM 			= "No parameter specified ({0}='...')."
T_NO_VALUE 			= "No parameter value specified ({0}='...')."
T_FW_INFO 			= "SMuFF: FW-Info:\n{0}."
T_ERR_SERVOPOS 		= "Servo position must be between 0 and 180."
T_CONN_EX 			= "Connecting to SMuFF has thrown an exception:\n\t{0}."
T_CONN 				= "Connected to SMuFF."
T_DISC 				= "Disconnected from SMuFF"
T_DISC_EX 			= "Disconnecting from SMuFF has thrown an exception:\n\t{0}."
T_IS_CONN 			= "SMuFF is connected on {}."
T_ALDY_CONN 		= "SMuFF is already connected."
T_ISNT_CONN 		= "SMuFF is currently not connected."
T_NO_SEL_TOOL		= "SMuFF tool change: Selected tool (T{0}) exceeds existing tools ({1})."
T_SKIP_TOOL 		= "Selected tool (T{0}) is already loaded. Skipping tool change."
T_DUMP_RAW 			= "SMuFF dump raw serial data is {0}"
T_WIPING			= "Wiping nozzle..."
T_CUTTING			= "Cutting filament..."
T_OPENING_LID		= "Opening lid..."
T_CLOSING_LID		= "Closing lid..."
T_POSITIONING		= "Positioning servo {0} to {1} deg."
T_MOTORS_OFF 		= "Motors have been turned off"
T_FAN 				= "Housing fan turned {0}"
T_UNJAMMED 			= "Jam flag has been reset"
T_RESET 			= "SMuFF has been reset"
T_RELOADING 		= "Loading filament again..."
T_UNLOADING 		= "Unloading filament..."
T_NOT_READY 		= "Busy with other async task, aborting!"
T_STATE_INFO_NC		= """SMuFF Status:
Connected:\t{0}
Port:\t\t{1}"""
T_STATE_INFO		= """{0}
------------------------
Device name:\t{1}
Tool count:\t{2}
------------------------
Active tool:\t{3}
Selector:\t{4}
Feeder:\t\t{5}
Feeder 2:\t{6}
Lid:\t\t{7}
Relay state:\t{8}
SD-Card:\t{9}
Idle:\t\t{10}
Config changed:\t{11}
Feeder loaded:\t{12}
Feeder jammed:\t{13}
------------------------
FW-Version:\t{14}
FW-Board:\t{15}
FW-Mode:\t{16}
FW-Options:\t{17}
------------------------
Tool changes:\t{18}
Average duration:\t{19} s\n"""

# Help texts for commands
T_HELP_CONN 		= "Connect to the SMuFF."
T_HELP_DISC			= "Disconnect from the SMuFF."
T_HELP_CONNECTED	= "Show current connection status."
T_HELP_CUT			= "Cut filament."
T_HELP_WIPE			= "Wipe nozzle."
T_HELP_LID_OPEN		= "Open lid servo."
T_HELP_LID_CLOSE	= "Close lid servo."
T_HELP_SET_SERVO	= "Position a servo."
T_HELP_TOOL_CHANGE	= "Change the current tool."
T_HELP_INFO			= "Query the firmware info from SMuFF."
T_HELP_STATUS		= "Query the status from SMuFF."
T_HELP_SEND			= "Send GCode to the SMuFF."
T_HELP_PARAM		= "Send configuration parameters to the SMuFF."
T_HELP_MATERIALS	= "Query the materials configured on the SMuFF."
T_HELP_SWAPS		= "Query the tool swaps configured on the SMuFF."
T_HELP_LIDMAPPINGS	= "Query the lid servo mappings configured on the SMuFF."
T_HELP_LOAD			= "Load filament on active tool on the SMuFF."
T_HELP_UNLOAD		= "Unload filament from active tool on the SMuFF."
T_HELP_HOME			= "Home Selector (and Revolver if configured) on the SMuFF."
T_HELP_MOTORS_OFF	= "Turn stepper motors on the SMuFF off."
T_HELP_CLEAR_JAM	= "Resets the Feeder Jammed flag on the SMuFF."
T_HELP_RESET		= "Resets the SMuFF."
T_HELP_VERSION		= "Query the version of this module."
T_HELP_RESET_AVG	= "Reset tool change average statistics."
T_HELP_DUMP_RAW		= "Prints out raw sent/received data (for debugging only)."

# Response strings coming from SMuFF
R_START			= "start\n"
R_OK			= "ok\n"
R_ECHO			= "echo:"
R_DEBUG			= "dbg:"
R_ERROR			= "error:"
R_BUSY			= "busy"
R_STATES		= "states:"
R_UNKNOWNCMD	= "Unknown command:"
R_JSON			= "{"
R_JSONCAT		= "/*"
R_FWINFO		= "FIRMWARE_"

# Some keywords sent by the SMuFF (as JSON config header)
C_BASIC 		= "basic"
C_STEPPERS 		= "steppers"
C_TMC 			= "tmc driver"
C_MATERIALS 	= "materials"
C_SWAPS 		= "tool swaps"
C_SERVOMAPS 	= "servo mapping"
C_FEEDSTATE 	= "feed state"

CFG_BASIC 		= 1
CFG_STEPPERS 	= 2
CFG_TMC			= 3
CFG_SERVOMAPS 	= 4
CFG_MATERIALS	= 5
CFG_SWAPS 		= 6
CFG_FEEDSTATE	= 8

# Action commands coming from/sent to the SMuFF
ACTION_CMD		= "//action:"
ACTION_WAIT		= "WAIT"
ACTION_CONTINUE	= "CONTINUE"
ACTION_ABORT	= "ABORT"
ACTION_PING		= "PING"
ACTION_PONG		= "PONG"

# Klipper printer states
ST_IDLE			= "Idle"
ST_PRINTING		= "Printing"
ST_READY		= "Ready"

# GCode parameters
P_TOOL_S		= "T"       		# used in SMUFF_TOOL_CHANGE (i.e. T=0)
P_TOOL_L		= "TOOL"       		# used in SMUFF_TOOL_CHANGE (i.e. TOOL=0)
P_SERVO			= "SERVO"   		# used in SMUFF_SET_SERVO (i.e. SERVO=0)
P_ANGLE			= "ANGLE"   		# used in SMUFF_SET_SERVO (i.e. ANGLE=95)
P_GCODE			= "GCODE"   		# used in SMUFF_SEND (i.e. GCODE="M119")
P_PARAM			= "PARAM" 			# used in SMUFF_PARAM (i.e. PARAM="BowdenLen")
P_PARAMVAL		= "VALUE"  			# used in SMUFF_PARAM (i.e. VALUE="620")
P_ENABLE 		= "ENABLE"			# used in SMUFF_DUMP_RAW

# GCode macros called
PRE_TC 			= "PRE_TOOLCHANGE"
POST_TC 		= "POST_TOOLCHANGE"
G_PRE_TC 		= PRE_TC +" T={0}"
G_POST_TC 		= POST_TC +" P={0} T={1}"


class SmuffCore():

	def __init__(self, logger, isKlipper, statusCallback, responseCallback):
		self._log 		= logger
		self._isKlipper = isKlipper
		self._statusCB 	= statusCallback
		self._responseCB 	= responseCallback
		self._reset()
		self._log.debug("SMuFF-Core initialized")

	def _reset(self):
		self._log.info("Resetting core variables")
		self.serialPort			= None      # serial port device name
		self.baudrate			= 0         # serial port baudrate
		self.timeout			= 0.0       # communication timeout
		self.cmdTimeout			= 0.0       # command timeout
		self.tcTimeout			= 0.0       # tool change timeout
		self.wdTimeout			= 60.0 		# watchdog timeout
		self.toolCount			= 0 		# number of tools on the SMuFF
		self.autoConnect		= False		# flag, whether or not to connect at startup
		self.dumpRawData 		= False		# for debugging only
		self.fwInfo 			= "?"		# SMuFFs firmware info
		self.curTool 			= "T-1"		# the current tool
		self.preTool 			= "T-1"		# the previous tool
		self.pendingTool 		= -1		# the tool on a pending tool change
		self.selector 			= False		# status of the Selector endstop
		self.revolver 			= False		# status of the Revolver endstop
		self.feeder 			= False		# status of the Feeder endstop
		self.feeder2			= False		# status of the 2nd Feeder endstop
		self.isBusy				= False		# flag set when SMuFF signals "Busy"
		self.isError			= False		# flag set when SMuFF signals "Error"
		self.isProcessing		= False		# set when SMuFF is supposed to be busy
		self.waitRequested		= False 	# set when SMuFF requested a "Wait" (in case of jams or similar)
		self.abortRequested		= False		# set when SMuFF requested a "Abort"
		self.isConnected		= False     # set after connection has been established
		self.isAligned 			= False		# flag set when Feeder endstop is reached (not used yet)
		self.isDDE 				= False		# flag whether the SMuFF is configured for DDE
		self.hasSplitter 		= False		# flag whether the SMuFF is configured for the Splitter option
		self.hasCutter 			= False		# flag whether the SMuFF is configured for the Cutter option
		self.hasWiper 			= False		# flag whether the SMuFF is configured for the Wiper option
		self.sdcard				= False     # set to True when SD-Card on SMuFF was removed
		self.cfgChange			= False     # set to True when SMuFF configuration has changed
		self.lid				= False     # set to True when Lid on SMuFF is open
		self.isIdle				= False     # set to True when SMuFF is idle
		self.usesTmc			= False     # set to True when SMuFF uses TMC drivers
		self.tmcWarning			= False     # set to True when TMC drivers on SMuFF report warnings
		self.device 			= "" 		# current name of the SMuFF
		self.tcCount 			= 0			# number of tool changes in total (since reset)
		self.durationTotal		= 0.0		# duration of all tool changes (for calculating average)
		self.loadState			= 0			# load state of the current tool
		self.fwVersion			= None		# firmware version on the SMuFF (i.e. "V3.10D")
		self.fwBoard			= None		# board the SMuFF is running on (i.e. "SKR E3-DIP V1.1")
		self.fwMode				= None		# firmware mode on the SMuFF (i.e. "SMUFF" or "PMMU2")
		self.fwOptions			= None		# firmware options installed on the SMUFF (i.e "TMC|NEOPIXELS|DDE|...")
		self.materials	 		= []		# Two dimensional array of materials received from the SMuFF after SMUFF_MATERIALS
		self.swaps	 			= []		# One dimensional array of tool swaps received from the SMuFF after SMUFF_SWAPS
		self.servoMaps			= [] 		# One dimensional array of servo mappings received from the SMuFF after SMUFF_LIDMAPPINGS
		self.feedStates			= [] 		# One dimensional array the feed state for each tool
		self.relay 				= None 		# state of the relay E(xternal) or I(nternal)
		self.isJammed 			= False 	# flag set when feeder is jammed

		self._serial			= None      # serial instance
		self._lastSerialEvent	= 0 		# last time (in millis) a serial receive took place
		self._response			= None		# the response string from SMuFF
		self._isReconnect 	    = False		# set when trying to re-establish serial connection
		self._autoLoad          = True      # set to load new filament automatically after swapping tools
		self._serEvent			= Event()	# event raised when a valid response has been received
		self._serWdEvent		= Event()	# event raised when status data has been received
		self._lastResponse     	= []		# last response SMuFF has sent (multiline)
		self._stopSerial 		= False		# flag set when the serial reader / connector / watchdog need to be discarded
		if self._serial:					# pySerial instance
			self.close_serial()
		self._sreader 			= None		# serial reader thread instance
		self._sconnector		= None		# serial connector thread instance
		self._swatchdog			= None		# serial watchdog thread instance
		self._jsonCat 			= None		# category of the last JSON string received
		self._stCount 			= 0 		# counter for states recevied
		self._tcStartTime 		= 0			# time for tool change duration measurement
		self._initStartTime		= 0			# time for _init_SMuFF timeout checking
		self._okTimer 			= None		# (reactor) timer waiting for OK response
		self._initTimer			= None		# (reactor) timer for _init_SMuFF
		self._tcTimer 			= None		# (reactor) timer waiting for toolchange to finish
		self._tcState			= 0			# tool change state
		self._initState			= 0			# state for _init_SMuFF
		self._lastCmdSent		= None		# GCode of the last command sent to SMuFF
		self._lastCmdDone		= False		# flag if the last command sent has got a response
		self._wdTimeoutDef 		= 60.0 		# default timeout for the serial port watchdog in seconds

	#
	# Set status values to be used within Klipper (scripts, GCode)
	#
	def get_status(self, eventtime=None):
		#self._log.info("get_status being called. M:{0} S:{1} ")
		values = {
			"tools":   		self.toolCount,
			"activetool":   self.get_active_tool(),
			"pendingtool":  self.pendingTool,
			"selector":     self.selector,
			"revolver":     self.revolver,
			"feeder":       self.feeder,
			"feeder2":      self.feeder2,
			"fwinfo":       self.fwInfo,
			"isbusy":       self.isBusy,
			"iserror":      self.isError,
			"isprocessing": self.isProcessing,
			"isconnected":	self.isConnected,
			"isidle": 		self.isIdle,
			"sdstate": 		self.sdcard,
			"lidstate": 	self.lid,
			"hascutter":	self.hasCutter,
			"haswiper":		self.hasWiper,
			"materials": 	self.materials,
			"swaps":		self.swaps,
			"lidmappings":	self.servoMaps,
			"device": 		self.device,
			"version": 		VERSION_NUMBER,
			"fwversion":	self.fwVersion,
			"fwmode":		self.fwMode,
			"fwoptions":	self.fwOptions,
			"loadstate":	self.loadState,
			"isdde":		self.isDDE,
			"hassplitter":	self.hasSplitter,
			"relay":		self.relay,
			"jammed":		self.jammed
		}
		return values

	def set_tool(self):
		self.preTool = self.curTool
		self.curTool = self.pendingTool

	def get_active_tool(self):
		return self._parse_tool_number(self.curTool)

	#
	# Async basic init
	#
	def _async_init(self):
		if self.dumpRawData:
			self._log.info("_async_init: state {0} processing: {1}".format(self._initState, self.isProcessing))
		if self._initState == 1:
			# query some basic configuration settings
			if self.isProcessing == False:
				self.send_SMuFF(GETCONFIG.format(CFG_BASIC))
		elif self._initState == 2:
			# query materials configuration
			if self.isProcessing == False:
				self.send_SMuFF(GETCONFIG.format(CFG_MATERIALS))
		elif self._initState == 3:
			# request firmware info from SMuFF
			if self.isProcessing == False:
				self.send_SMuFF(FWINFO)
		elif self._initState == 4:
			# query tool swap configuration settings
			if self.isProcessing == False:
				self.send_SMuFF(GETCONFIG.format(CFG_SWAPS))
		elif self._initState == 5:
			# query some lid servo mapping settings
			if self.isProcessing == False:
				self.send_SMuFF(GETCONFIG.format(CFG_SERVOMAPS))
		elif self._initState == 6:
			self._log.info("_async_init done")
			self._initState = 0
		else:
			self._initState = 0


	#
	# Connects to the SMuFF via the configured serial interface (/dev/ttySMuFF by default)
	#
	def connect_SMuFF(self, gcmd=None):
		self.isConnected = False
		try:
			self._open_serial()
			if self._serial and self._serial.is_open:
				self.isConnected = True
				self._init_SMuFF() 	# query firmware info and current settings from the SMuFF
				return True
			else:
				self._log.info("Opening serial {0} for SMuFF has failed".format(self.serialPort))
		except Exception as err:
			self._log.error("Connecting to SMuFF has thrown an exception:\n\t{0}".format(err))
		return False

	#
	# Opens the serial port for the communication with the SMuFF
	#
	def _open_serial(self):
		try:
			self._log.info("Opening serial port '{0}'".format(self.serialPort))
			self._serial = serial.Serial(self.serialPort, self.baudrate, timeout=self.timeout, write_timeout=0)
			if self._serial and self._serial.is_open:
				self._log.info("Serial port opened")
				self._stopSerial = False
				try:
					# set up a separate task for reading the incoming SMuFF messages
					self._sreader = Thread(target=self._serial_reader, name="TReader")
					self._sreader.daemon = True
					self._sreader.start()
					self._log.info("Serial reader thread running... ({0})".format(self._sreader))
				except:
					exc_type, exc_value, exc_traceback = sys.exc_info()
					tb = traceback.format_exception(exc_type, exc_value, exc_traceback)
					self._log.error("Unable to start serial reader thread: ".join(tb))
				self._start_watchdog()
		except (OSError, serial.SerialException):
			exc_type, exc_value, exc_traceback = sys.exc_info()
			tb = traceback.format_exception(exc_type, exc_value, exc_traceback)
			err = "Can't open serial port '{0}'!\n\t{1}".format(self.serialPort, tb)
			self._log.error(err)
			if not self._responseCB == None:
				self._responseCB(err)


	#
	# Closes the serial port and cleans up resources
	#
	def close_serial(self):
		if not self._serial:
			self._log.info("Serial wasn't initialized, nothing to do here")
			return
		self._stopSerial = True
		# stop threads
		try:
			if self._sconnector and self._sconnector.is_alive:
				self._sconnector.join()
			else:
				self._log.error("Serial connector isn't alive")
		except Exception as err:
			self._log.error("Unable to shut down serial connector thread:\n\t{0}".format(err))
		try:
			self._serWdEvent.set()
			if self._swatchdog and self._swatchdog.is_alive:
				self._swatchdog.join()
			else:
				self._log.error("Serial watchdog isn't alive")
		except Exception as err:
			self._log.error("Unable to shut down serial watchdog thread:\n\t{0}".format(err))
		try:
			if self._sreader and self._sreader.is_alive:
				self._sreader.join()
			else:
				self._log.error("Serial reader isn't alive")
		except Exception as err:
			self._log.error("Unable to shut down serial reader thread:\n\t{0}".format(err))

		# discard reader, connector and watchdog threads
		del(self._sreader)
		del(self._sconnector)
		del(self._swatchdog)
		self._sreader = None
		self._sconnector = None
		self._swatchdog = None
		# close the serial port
		try:
			self._serial.close()
			if self._serial.is_open == False:
				self._log.info("Serial port '{0}' closed".format(self._serial.port))
			else:
				self._log.error("Closing serial port '{0}' has failed".format(self._serial.port))
			del(self._serial)
			self._serial = None
			self.isConnected = False
		except (OSError, serial.SerialException):
			exc_type, exc_value, exc_traceback = sys.exc_info()
			tb = traceback.format_exception(exc_type, exc_value, exc_traceback)
			err = "Can't close serial port {0}!\n\t{1}".format(self.serialPort, tb)
			self._log.error(err)
			if not self._responseCB == None:
				self._responseCB(err)

	#
	# Serial reader thread
	#
	def _serial_reader(self):
		self._log.info("Entering serial reader thread")
		# this loop basically runs forever, unless _stopSerial is set or the
		# serial port gets closed
		while self._stopSerial == False:
			if self._serial and self._serial.is_open:
				try:
					time.sleep(0.1)
					b = self._serial.in_waiting
					if b > 0:
						try:
							data = self._serial.readline().decode("ascii")	# read to EOL
							self._parse_serial_data(data)
						except UnicodeDecodeError as err:
							self._log.error("Serial reader has thrown an exception:\n\t{0}\n\tData: [{1}]".format(err, data))
							self._serial.reset_input_buffer()
						except:
							exc_type, exc_value, exc_traceback = sys.exc_info()
							tb = traceback.format_exception(exc_type, exc_value, exc_traceback)
							self._log.error("Serial reader error: ".join(tb))
				except serial.SerialException as err:
					self._log.error("Serial reader has thrown an exception:\n\t{0}".format(err))
					self._serEvent.set()
				except serial.SerialTimeoutException as err:
					self._log.error("Serial reader has timed out:\n\t{0}".format(err))
					self._serEvent.set()
			else:
				self._log.error("Serial port {0} has been closed".format(self._serial.port))
				self._serEvent.set()
				break

		self._log.error("Shutting down serial reader")
		if not self._statusCB == None:
			self._statusCB(active=False)

	#
	# Method which starts _serial_connector() in the background.
	#
	def start_connector(self):
		try:
			# set up a separate task for connecting to the SMuFF
			self._sconnector = Thread(target=self._serial_connector, name="TConnector")
			self._sconnector.daemon=True
			self._sconnector.start()
			self._log.info("Serial connector thread running... ({0})".format(self._sconnector))
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			tb = traceback.format_exception(exc_type, exc_value, exc_traceback)
			self._log.error("Unable to start serial connector thread: ".join(tb))

	#
	# Serial connector thread
	# This part runs in a thread in order not to block Klipper during start up
	#
	def _serial_connector(self):
		self._log.info("Entering serial connector thread")
		time.sleep(3)

		while 1:
			if self.isConnected and self._stopSerial == True:
				break
			if self.connect_SMuFF == True:
				break
			time.sleep(3)
			self._log.info("Serial connector looping...")

		# as soon as the connection has been established, cancel the connector thread
		self._log.info("Shutting down serial connector")
		self._sconnector = None

	#
	# Method which starts the serial watchdog in the background.
	#
	def _start_watchdog(self):
		try:
			# set up a separate task for connecting to the SMuFF
			self._swatchdog = Thread(target=self._serial_watchdog, name="TWatchdog")
			self._swatchdog.daemon=True
			self._swatchdog.start()
			self._log.info("Serial watchdog thread running... ({0})".format(self._swatchdog))
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			tb = traceback.format_exception(exc_type, exc_value, exc_traceback)
			self._log.error("Unable to start serial watchdog thread: ".join(tb))

	#
	# Serial watchdog thread
	#
	def _serial_watchdog(self):
		self._log.info("Entering serial watchdog thread")

		while self._stopSerial == False:
			if self._serial.is_open == False:
				break
			self._serWdEvent.clear()
			is_set = self._serWdEvent.wait(self.wdTimeout)
			if self._stopSerial:
				break
			if is_set == False:
				self._log.info("Serial watchdog timed out... (no sign of life within {0} sec.)".format(self.wdTimeout))
				reconnect = Thread(target=self.reconnect_SMuFF, name="TReconnect")
				reconnect.daemon = True
				reconnect.start()
				break

		self._log.info("Shutting down serial watchdog")

    #
	# Tries to reconnect serial port to SMuFF
    #
	def reconnect_SMuFF(self):
		if self._sconnector:
			self._log.info("Connector thread already running, aborting reconnect request...")
			return
		self.close_serial()
		self._isReconnect = True
		self._log.info("Attempting a reconnect...")
		self.connect_SMuFF()
		self._isReconnect = False
		if self.isConnected == False:
			self._log.info("Still not connected, starting connector")
			self.start_connector()
		else:
			if self._serial.is_open:
				self._init_SMuFF()


    #
	# Sends data to SMuFF
    #
	def send_SMuFF(self, data):
		self._set_busy(False)		# reset busy and
		self._set_error(False)		# error flags

		if self._lastCmdSent == None:
			elements = data.split(" ", 1)
			if len(elements):
				self._lastCmdSent = elements[0]
			else:
				self._lastCmdSent = elements

		if self._lastCmdSent == RESET:
			# don't log RESET
			self._lastCmdSent = None

		if self._serial and self._serial.is_open:
			try:
				b = bytearray(len(data)+2)
				b = "{0}\n".format(data).encode("ascii")
				n = self._serial.write(b)
				if self.dumpRawData:
					self._log.info("Sent {1} bytes: [{0}]".format(b, n))
				return True
			except (OSError, serial.SerialException) as err:
				self._log.error("Unable to send command '{0}:\n\t' to SMuFF".format(data, err))
				return False
		else:
			self._log.error("Serial port is closed, can't send data")
			return False

    #
	# Sends data to SMuFF and will wait for a response (which in most cases is 'ok')
    #
	def send_SMuFF_and_wait(self, data):

		if data.startswith(TOOL):
			timeout = self.tcTimeout 	# wait max. 90 seconds for a response while swapping tools
			tmName = "tool change"
		else:
			timeout = self.cmdTimeout	# wait max. 25 seconds for other operations
			tmName = "command"
		self.wdTimeout = timeout
		done = False
		result = None

		if self.send_SMuFF(data) == False:
			self._log.error("Failed to send command to SMuFF, aborting 'send_SMuFF_and_wait'")
			return None
		self._set_processing(True)	# SMuFF is currently doing something

		while not done:
			self._serEvent.clear()
			is_set = self._serEvent.wait(timeout)
			if is_set == True:
				self._log.info("To [{0}] SMuFF says [{1}]  {2}".format(data, self._response, "(Error reported)" if self.isError else "(Ok)"))
				result = self._response
				if self._response == None or self.isError:
					done = True
				elif not self._response.startswith(R_ECHO):
					done = True

				self._response = None
			else:
				self._log.info("Timed out while waiting for a response on cmd '{0}'. Try increasing the {1} timeout (={2} sec.).".format(data, tmName, timeout))
				if self.isBusy == False:
					done = True
					self._set_processing(False)

		self._set_processing(False)	# SMuFF is not supposed to do anything
		self.wdTimeout = self._wdTimeoutDef
		return result

	#
	# Initializes data of this module by requesting runtime setting from the SMuFF
	#
	def _init_SMuFF(self):
		self._log.info("Sending SMuFF init...")
		# turn on sending of periodical states
		self.send_SMuFF(PERSTATE + OPT_ON)

	#
	# set/reset processing flag
	#
	def _set_processing(self, processing):
		self.isProcessing = processing

	#
	# set/reset busy flag
	#
	def _set_busy(self, busy):
		self.isBusy = busy

	#
	# set/reset error flag
	#
	def _set_error(self, error):
		self.isError = error

	#
	# set last response received (i.e. everything below the GCode and above the "ok\n")
	#
	def _set_response(self, response):
		if not response == None:
			if response.rstrip("\n") == RESET:
				self._response = ""
			else:
				self._response = response.rstrip("\n")
		else:
			self._response = ""
		self._lastResponse = []

	#
	# Dump string s as a hex string (for debugging only)
	#
	def hex_dump(self, s):
		self._log.info(":".join("{:02x}".format(ord(c)) for c in s))


	#
	# Parses a JSON response sent by the SMuFF (used for retrieving SMuFF settings)
	#
	def _parse_json(self, data, category):
		if category == None or data == None:
			return
		if self.dumpRawData:
			self._log.info("Parse JSON (category '{1}'):\n\t[{0}]".format(data, category))

		if data:
			resp = ""
			try:
				cfg = json.loads(data)
				if cfg == None:
					return
				# basic configuration
				if category == C_BASIC:
					self.device 		= cfg["Device"]
					self.toolCount 		= cfg["Tools"]
					self.hasCutter		= cfg["UseCutter"]
					self.hasSplitter 	= cfg["UseSplitter"]
					self.isDDE 			= cfg["UseDDE"]
					self._initState += 1

				# stepper configuration
				if category == C_STEPPERS:
					pass

				# TMC driver configuration
				if category == C_TMC:
					pass

				# materials configuration
				if category == C_MATERIALS:
					try:
						self.materials = []
						for i in range(self.toolCount):
							t = "T"+str(i)
							material = [ cfg[t]["Material"], cfg[t]["Color"], cfg[t]["PFactor"] ]
							self.materials.append(material)
							#resp += "Tool {0} is '{2} {1}' with a purge factor of {3}%\n".format(i, material[0], material[1], material[2])
						self._initState += 1
					except Exception as err:
						self._log.error("Parsing materials has thrown an exception:\n\t{0}".format(err))

				# tool swapping configuration
				if category == C_SWAPS:
					try:
						self.swaps = []
						for i in range(self.toolCount):
							t = "T"+str(i)
							swap = cfg[t]
							self.swaps.append(swap)
							#resp += "Tool {0} is assigned to tray {1}\n".format(i, swap)
						self._initState += 1
					except Exception as err:
						self._log.error("Parsing tool swaps has thrown an exception:\n\t{0}".format(err))

				# servo mapping configuration
				if category == C_SERVOMAPS:
					try:
						self.servoMaps = []
						for i in range(self.toolCount):
							t = "T"+str(i)
							servoMap = cfg[t]["Close"]
							self.servoMaps.append(servoMap)
							#resp += "Tool {0} closed @ {1} deg.\n".format(i, servoMap)
						self._initState += 1
					except Exception as err:
						self._log.error("Parsing lid mappings has thrown an exception:\n\t{0}".format(err))

				# feeder states
				if category == C_FEEDSTATE:
					try:
						self.feedStates = []
						for i in range(self.toolCount):
							t = "T"+str(i)
							feedState = cfg[t]
							self.feedStates.append(feedState)
							#resp += "Tool load state {0}\n".format(i, feedState)
					except Exception as err:
						self._log.error("Parsing feed states has thrown an exception:\n\t{0}".format(err))

				if len(resp) and self._isKlipper:
					try:
						self.gcode.respond_info(resp)
					except Exception as err:
						self._log.error("Sending response to Klipper has thrown an exception:\n\t{0}".format(err))
				else:
					if not self._responseCB == None:
						self._responseCB(resp)


			except Exception as err:
				self._log.error("Parse JSON for category {1} has thrown an exception:\n\t{0}\n\t[{1}]".format(err, self._jsonCat, data))

	#
	# Parses the states periodically sent by the SMuFF
	#
	def _parse_states(self, states):
		#self._log.info("States received: [" + states + "]")
		if len(states) == 0:
			return False

		# Note: SMuFF sends periodically states in this notation:
		# 	"echo: states: T: T4  S: off  R: off  F: off  F2: off  TMC: -off  SD: off  SC: off  LID: off  I: off  SPL: 0"
		for m in re.findall(r'([A-Z]{1,3}[\d|:]+).(\+?\w+|-?\d+|\-\w+)+',states):
			if   m[0] == "T:":                          # current tool
				self.curTool      	= m[1].strip()
			elif m[0] == "S:":                          # Selector endstop state
				self.selector      = m[1].strip() == T_ON.lower()
			elif m[0] == "R:":                          # Revolver endstop state
				self.revolver      = m[1].strip() == T_ON.lower()
			elif m[0] == "F:":                          # Feeder endstop state
				self.feeder        = m[1].strip() == T_ON.lower()
			elif m[0] == "F2:":                         # DDE-Feeder endstop state
				self.feeder2       = m[1].strip() == T_ON.lower()
			elif m[0] == "SD:":                         # SD-Card state
				self.sdcard        = m[1].strip() == T_ON.lower()
			elif m[0] == "SC:":                         # Settings Changed
				self.cfgChange     = m[1].strip() == T_ON.lower()
			elif m[0] == "LID:":                        # Lid state
				self.lid           = m[1].strip() == T_ON.lower()
			elif m[0] == "I:":                          # Idle state
				self.isIdle        = m[1].strip() == T_ON.lower()
			elif m[0] == "TMC:":                        # TMC option
				v = m[1].strip()
				self.usesTmc = v.startswith("+")
				self.tmcWarning = v[1:] == T_ON.lower()
			elif m[0] == "SPL:":                        # Splitter/Feeder load state
				self._spl = int(m[1].strip())
				if self.curTool == "-1":
					self.loadState = -1					# no tool selected
				else:
					if self._spl == 0:
						self.loadState = 0					# not loaded
					if self._spl == 0x01 or self._spl == 0x10:
						self.loadState = 1					# loaded to Selector or Splitter
					if self._spl == 0x02 or self._spl == 0x20:
						self.loadState = 2					# loaded to Nozzle
					if self._spl == 0x40:
						self.loadState = 3					# loaded to DDE
			elif m[0] == "RLY:":                        # Relay state (E/I)
				self.relay = m[1].strip()
			elif m[0] == "JAM:":                        # Feeder jammed flag
				self.isJammed = m[1].strip() == T_ON.lower()

			#else:
				#	self._log.error("Unknown state: [" + m[0] + "]")

		if not self._statusCB == None:
			self._statusCB(active=True)

		self._serWdEvent.set()
		self._stCount += 1
		if self._initState > 0:
			self._async_init()
		return True

	#
	# Converts the string 'Tn' into a tool number
	#
	def parse_tool_number(self, tool):
		if not tool or tool == "":
			return -1
		try:
			#self._log.info("Tool: [{}]".format(tool))
			return int(re.findall(r'[-\d]+', tool)[0])
		except Exception as err:
			self._log.error("Can't parse tool number in {0}:\n\t{1}".format(tool, err))
		return -1

	#
	# Parses the response we've got from the SMuFF
	#
	def _parse_serial_data(self, data):
		if data == None or len(data) == 0 or data == "\n":
			return

		if self.dumpRawData:
			self._log.info("Raw data: [{0}]".format(data.rstrip("\n")))

		self._lastSerialEvent = self._nowMS()
		self._serEvent.clear()

		# after first connect the response from the SMuFF is supposed to be 'start'
		if data.startswith(R_START):
			self._log.info("\"start\" response received")
			self._serEvent.set()
			self._init_SMuFF()
			return

		if data.startswith(PERSTATE):
			if self.dumpRawData:
				self._log.info("Periodical states sending is ON")
			self._initState = 1
			return

		if data.startswith(R_ECHO):
			# don't process any general debug messages
			index = len(R_ECHO)+1
			if data[index:].startswith(R_DEBUG):
				self._log.debug("SMuFF has sent a debug response: [{0}]".format(data.rstrip()))
			# but do process the tool/endstop states
			elif data[index:].startswith(R_STATES):
				self._parse_states(data.rstrip())
			# and register whether SMuFF is busy
			elif data[index:].startswith(R_BUSY):
				err = "SMuFF has sent a busy response: [{0}]".format(data.rstrip())
				self._log.debug(err)
				if self._isKlipper:
					self.gcode.respond_info(err)
				else:
					if not self._responseCB == None:
						self._responseCB(err)
				self._set_busy(True)
			return

		if data.startswith(R_ERROR):
			err = "SMuFF has sent an error response: [{0}]".format(data.rstrip())
			self._log.info(err)
			if self._isKlipper:
				self.gcode.respond_info(err)
			else:
				if not self._responseCB == None:
					self._responseCB(err)
			index = len(R_ERROR)+1
			# maybe the SMuFF has received garbage
			if data[index:].startswith(R_UNKNOWNCMD):
				self._serial.reset_output_buffer()
				self._serial.reset_input_buffer()
			self._set_error(True)
			if self._lastCmdSent != None:
				self._lastCmdSent = None
				self._lastCmdDone = True
			return

		if data.startswith(ACTION_CMD):
			self._log.debug("SMuFF has sent an action request: [{0}]".format(data.rstrip()))
			index = len(ACTION_CMD)
			# what action is it? is it a tool change?
			if data[index:].startswith(TOOL):
				tool = self._parse_tool_number(data[10:])
				# only if the printer isn't printing
				if self._is_printing() == False:
					# query the heater
					heater = self._printer.lookup_object("heater")
					try:
						if heater.extruder.can_extrude:
							self._log.debug("Extruder is up to temp.")
							self._printer.change_tool("tool{0}".format(tool))
							self.send_SMuFF("{0} T: OK".format(ACTION_CMD))
						else:
							self._log.error("Can't change to tool {0}, nozzle not up to temperature".format(tool))
							self.send_SMuFF("{0} T: \"Nozzle too cold\"".format(ACTION_CMD))
					except:
						self._log.error("Can't query temperatures. Aborting.")
						self.send_SMuFF("{0} T: \"No nozzle temp. avail.\"".format(ACTION_CMD))
				else:
					self._log.error("Can't change to tool {0}, printer not ready or printing".format(tool))
					self.send_SMuFF("{0} T: \"Printer not ready\"".format(ACTION_CMD))

			if data[index:].startswith(ACTION_WAIT):
				self.waitRequested = True
				self._log.info("Waiting for SMuFF to come clear... (ACTION_WAIT)")

			if data[index:].startswith(ACTION_CONTINUE):
				self.waitRequested = False
				self.abortRequested = False
				self._log.info("Continuing after SMuFF cleared... (ACTION_CONTINUE)")

			if data[index:].startswith(ACTION_ABORT):
				self.waitRequested = False
				self.abortRequested = True
				self._log.info("SMuFF is aborting action operation... (ACTION_ABORT)")

			if data[index:].startswith(ACTION_PONG):
				self._log.info("PONG received from SMuFF (ACTION_PONG)")
			return

		if data.startswith(R_JSONCAT):
			self._jsonCat = data[2:].rstrip("*/\n").strip(" ").lower()
			return

		if data.startswith(R_JSON):
			self._parse_json(data, self._jsonCat)
			self._jsonCat = None
			return

		if data.startswith(R_FWINFO):
			self.fwInfo = data.rstrip("\n")
			if self._isKlipper:
				self.gcode.respond_info(T_FW_INFO.format(self.fwInfo))
			if not self._responseCB == None:
				self._responseCB(T_FW_INFO.format(self.fwInfo))
			self._lastCmdSent = None
			try:
				arr = re.findall(r"FIRMWARE_NAME\:\s(.*)\sFIRMWARE_VERSION\:\s(.*)\sELECTRONICS\:\s(.*)\sDATE\:\s(.*)\sMODE\:\s(.*)\sOPTIONS\:\s(.*)", self.fwInfo)
				if len(arr):
					self.fwVersion 	= arr[0][1]
					self.fwBoard 	= arr[0][2]
					self.fwMode 	= arr[0][4]
					self.fwOptions 	= arr[0][5]
			except Exception as err:
				self._log.error("Can't regex firmware info:\n\t{0}".format(err))
			self._initState += 1
			return

		if data.startswith(R_OK):
			if self.isError:
				self._set_response(None)
				self._lastCmdSent = None
				self._lastCmdDone = True
			else:
				if self.dumpRawData:
					self._log.info("[OK->] LastCommand '{0}'   LastResponse {1}".format(self._lastCmdSent, pformat(self._lastResponse)))

				firstResponse = self._lastResponse[0].rstrip("\n") if len(self._lastResponse) else None

				if firstResponse == RESET:
					firstResponse = None
					self._lastCmdDone = True

				if self._lastCmdSent == ANY:
					self._lastCmdDone = True
				elif firstResponse != None:
					if firstResponse == self._lastCmdSent:
						self._lastCmdDone = True

				if self.dumpRawData and self._lastCmdSent:
					self._log.info("lastCmdDone is {0}".format(self._lastCmdDone))
				self._set_response("".join(self._lastResponse))
			self._lastCmdSent = None
			# set serEvent only after a ok was received
			self._serEvent.set()
			return

		# store all responses before the "ok"
		if data:
			self._lastResponse.append(str(data))
		self._log.debug("Last response received: [{0}]".format(self._lastResponse[len(self._lastResponse)-1]))

	#
	# Helper function to retrieve time in milliseconds
	#
	def _nowMS(self):
		return int(round(time.time() * 1000))

	def get_states(self, gcmd=None):
		connStat = T_STATE_INFO_NC.format(
			T_YES if self.isConnected else T_NO,
			self.serialPort)

		if self.isConnected:
			durationAvg =  (self.durationTotal / self.tcCount) if self.durationTotal > 0 and self.tcCount > 0 else 0
			loadState = {
				-1: T_NO_TOOL,
				0: T_NO,
				1: T_TO_SPLITTER if self.hasSplitter else T_TO_SELECTOR,
				2: T_YES,
				3: T_TO_DDE
			}
			loaded = loadState.get(self.loadState, T_INVALID_STATE)

			try:
				connStat = T_STATE_INFO.format(
					connStat,
					self.device,
					self.toolCount,
					self.curTool if self.curTool != "-1" else "None" ,
					T_TRIGGERED if self.selector else T_NOT_TRIGGERED,
					T_TRIGGERED if self.feeder else T_NOT_TRIGGERED,
					T_TRIGGERED if self.feeder2 else T_NOT_TRIGGERED,
					T_CLOSED if self.lid else T_OPENED,
					T_EXTERNAL if self.relay == "E" else T_INTERNAL,
					T_REMOVED if self.sdcard else T_INSERTED,
					T_YES if self.isIdle else T_NO,
					T_YES if self.cfgChange else T_NO,
					loaded,
					T_YES if self.isJammed else T_NO,
					self.fwVersion,
					self.fwBoard,
					self.fwMode,
					self.fwOptions.replace("|",", ") if self.fwOptions != None else T_INVALID_STATE,
					self.tcCount,
					durationAvg)
			except Exception as err:
				self._log.debug("Status parsing error: {0}".format(err))
		return connStat

	def get_fw_info(self, gcmd=None):
		if not self.isConnected:
			return T_NOT_CONN
		return T_FW_INFO.format(self.fwInfo)

	def start_tc_timer(self):
		self.tcCount +=1
		self._tcStartTime = self._nowMS()

	def stop_tc_timer(self):
		duration = (self._nowMS()-self._tcStartTime)/1000
		self.durationTotal += duration
		return duration

	def reset_avg(self):
		self.tcCount = 0
		self.durationTotal = 0
