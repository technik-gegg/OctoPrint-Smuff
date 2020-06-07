#coding=utf-8

from __future__ import absolute_import
from threading import Thread, Lock, Event

from octoprint.util import RepeatedTimer
from octoprint.printer import UnknownScript
from octoprint.events import Events
import octoprint.plugin

import serial                    # we need this for the serial communcation with the SMuFF
import os, fnmatch
import re
import time
import sys
import traceback
import logging
import binascii

# change the baudrate and port here if you have to
# this might move into the settings some day
SERBAUD		= 115200
SERDEVS		= [ "ttyS0", "ttyAMA1" ]

SERDEV		= ""	# will be initialized later on
AT_SMUFF 	= "@SMuFF"
M115	 	= "M115"
M119	 	= "M119"
M280	 	= "M280 P"
M18			= "M18"
G12			= "G12 S200 I130 J160 P10 R10"
TOOL 		= "T"
NOTOOL		= "T255"
G1_E	 	= "G1 E"
ALIGN 	 	= "ALIGN"
REPEAT 		= "REPEAT"
LOAD 		= "LOAD"
SERVO		= "SERVO"
WIPE		= "WIPE"
MOTORS		= "MOTORS"
PRINTER		= "PRINTER"
ALIGN_SPEED	= " F"
ESTOP_ON	= "on"
LOGGER 		= "octoprint.plugins.SMuFF"
ACTION_CMD 	= "//action:"

class SmuffPlugin(octoprint.plugin.SettingsPlugin,
                  octoprint.plugin.AssetPlugin,
                  octoprint.plugin.TemplatePlugin,
				  octoprint.plugin.StartupPlugin,
				  octoprint.plugin.EventHandlerPlugin,
				  octoprint.plugin.ShutdownPlugin):

	def __init__(self, _logger, _lock):
		self._serial 		= None		# serial instance to communicate with the SMuFF
		self._serlock		= _lock		# lock object for reading/writing
		self._serevent		= Event()	# event raised when a valid response has been received
		self._fw_info 		= "?"		# SMuFFs firmware info
		self._cur_tool 		= "-1"		# the current tool
		self._pre_tool 		= "-1"		# the previous tool
		self._pending_tool 	= "?"		# the tool on a pending tool change
		self._selector 		= False		# status of the Selector endstop
		self._revolver 		= False		# status of the Revolver endstop
		self._feeder 		= False		# status of the Feeder endstop
		self._feeder2		= False		# status of the 2nd Feeder endstop
		self._is_busy		= False		# flag set when SMuFF signals "Busy"
		self._is_error		= False		# flag set when SMuFF signals "Error" 
		self._is_aligned 	= False		# flag set when Feeder endstop is reached (not used yet)
		self._response		= None		# the response string from SMuFF


	##~~ ShutdownPlugin mixin

	def on_startup(self, host, port):
		self._logger.info("Yeah... starting up...")

	def on_shutdown(self):
		close_SMuFF_serial()
		self._logger.debug("Booo... shutting down...")

	##~~ StartupPlugin mixin

	def on_after_startup(self):
		# nothing to do here yet...
		pass

	##~~ EventHandler mixin

	def on_event(self, event, payload):
		#self._logger.debug("Event: [" + event + ", {0}".format(payload) + "]")
		if event == Events.SHUTDOWN:
			self._logger.debug("Shutting down, closing serial")
			close_SMuFF_serial()

	##~~ SettingsPlugin mixin

	def get_settings_defaults(self):
		self._logger.debug("SMuFF plugin loaded, getting defaults")

		params = dict(
			firmware_info	= "No data. Please check connection!",
			baudrate	= SERBAUD,
			tty 		= "Not found. Please enable the UART on your Raspi!",
			tool		= self._cur_tool,
			selector_end	= self._selector,
			revolver_end	= self._revolver,
			feeder_end	= self._feeder,
			feeder2_end	= self._feeder
		)

		# look up the serial port driver
		if sys.platform == "win32":
			if SERDEV.startswith("tty"):
				params['tty'] = "Wrong device on WIN32 ({})".format(SERDEV)
			else:
				params['tty'] = SERDEV
		else:
			drvr = self.find_file(SERDEV, "/dev")
			if len(drvr) > 0:
				params['tty'] = "/dev/{}".format(SERDEV)

		# request firmware info from SMuFF 
		if self._serial.is_open:
			self._fw_info = self.send_SMuFF_and_wait(M115)
			if self._fw_info:
				params['firmware_info'] = self._fw_info

		return  params

	def get_template_configs(self):
		# self._logger.debug("Settings-Template was requested")
		return [
			dict(type="settings", custom_bindings=True, template='SMuFF_settings.jinja2'),
			dict(type="navbar", custom_bindings=True, template='SMuFF_navbar.jinja2')
		]

	##~~ AssetPlugin mixin

	def get_assets(self):
		return dict(
			js=["js/SMuFF.js"],
			css=["css/SMuFF.css"],
			less=["less/SMuFF.less"]
		)

	##~~ Softwareupdate hook

	def get_update_information(self):
		return dict(
			SMuFF=dict(
				displayName="SMuFF Plugin",
				displayVersion=self._plugin_version,

				# version check: github repository
				type="github_release",
				user="technik-gegg",
				repo="OctoPrint-Smuff",
				current=self._plugin_version,

				# update method: pip
				pip="https://github.com/technik-gegg/OctoPrint-Smuff/archive/{target_version}.zip"
			)
		)

	##~~ GCode hooks

	def extend_tool_queuing(self, comm_instance, phase, cmd, cmd_type, gcode, subcode, tags, *args, **kwargs):
		# self._logger.debug("Processing queuing: [" + cmd + "," + str(cmd_type)+ "," + str(tags) + "]")

		if gcode and gcode.startswith(TOOL):
			self._logger.debug("OctoPrint current tool: {0}".format(comm_instance._currentTool))
			# if the tool that's already loaded is addressed, ignore the filament change
			if cmd == self._cur_tool and self._feeder:
				self._logger.info(cmd + " equals " + self._cur_tool + " -- no tool change needed")
				return "M117 Tool already selected"
			self._is_aligned = False
			# replace the tool change command
			return [ AT_SMUFF + " " + cmd ]

		if cmd and cmd.startswith(AT_SMUFF):
			v1 = None
			v2 = None
			spd = 300
			action = None
			tmp = cmd.split()
			if len(tmp):
				action = tmp[1]
				if len(tmp) > 2:
					v1 = int(tmp[2])
				if len(tmp) > 3:
					v2 = int(tmp[3])
				if len(tmp) > 4:
					spd = int(tmp[4])

			# self._logger.debug("1>> " + cmd + "  action: " + str(action) + "  v1,v2: " + str(v1) + ", " + str(v2))

			# @SMuFF SERVO
			if action and action == SERVO:
				# send a servo command to SMuFF
				self.send_SMuFF_and_wait(M280 + str(v1) + " R" + str(v2))
				return ""

			# @SMuFF WIPE
			if action and action == WIPE:
				# send a servo wipe command to SMuFF
				self.send_SMuFF_and_wait(G12)
				return ""

			# @SMuFF MOTORS
			if action and action == MOTORS:
				# send a servo command to SMuFF
				self.send_SMuFF_and_wait(M18)
				return ""


	def extend_tool_sending(self, comm_instance, phase, cmd, cmd_type, gcode, subcode, tags, *args, **kwargs):

		if gcode and gcode.startswith(TOOL):
			return ""

		# is this the replaced tool change command?
		if cmd and cmd.startswith(AT_SMUFF):
			v1 = None
			v2 = None
			spd = 300
			action = None
			tmp = cmd.split()
			if len(tmp):
				action = tmp[1]
				if len(tmp) > 2:
					v1 = int(tmp[2])
				if len(tmp) > 3:
					v2 = int(tmp[3])
				if len(tmp) > 4:
					spd = int(tmp[4])

			self._logger.debug("2>> " + cmd + "  action: " + str(action) + "  v1,v2: " + str(v1) + ", " + str(v2))

			# @SMuFF T0...T99
			if action and action.startswith(TOOL):
				if self._printer.set_job_on_hold(True, False):
					try:
						# store the new tool for later
						self._pending_tool = str(action)
						# check if there's filament loaded
						if self._feeder:
							self._logger.debug("2>> calling script 'beforeToolChange'")
							# if so, send the OctoPrints default "Before Tool Change" script to the printer
							self._printer.script("beforeToolChange")
						else:
							self._logger.debug("2>> calling SMuFF LOAD")
							# not loaded, nothing to retract, so send the tool change to the SMuFF
							self._printer.commands(AT_SMUFF + " " + LOAD)

					except UnknownScript:
						self._logger.error("Script 'beforeToolChange' not found!")
					# Notice: set_job_on_hold(False) must not be set yet since the
					# whole tool change procedure isn't finished yet. Setting it now
					# will unpause OctoPrint and it'll continue printing without filament! 
					#finally:
						#self._printer.set_job_on_hold(False)

			# @SMuFF LOAD
			if action and action == LOAD:
				with self._printer.job_on_hold():
					try:
						self._logger.debug("1>> LOAD: Feeder: " + str(self._feeder) + ", Pending: " + str(self._pending_tool) + ", Current: " + str(self._cur_tool))
						retry = 3	# retry up to 3 times
						while retry > 0:
							# send a tool change command to SMuFF
							res = self.send_SMuFF_and_wait(self._pending_tool)
							# do we have the tool requested now?
							if str(res) == str(self._pending_tool):
								self._pre_tool = self._cur_tool
								self._cur_tool = self._pending_tool
								comm_instance._currentTool = self.parse_tool_number(self._cur_tool)
								self._logger.debug("2>> calling script 'afterToolChange'")
								# send the default OctoPrint "After Tool Change" script to the printer
								self._printer.script("afterToolChange")
								retry = 0
							else:
								# not the result expected, do it all again
								self._logger.warning("Tool change failed, retrying (<{0}> not <{1}>)".format(res, self._pending_tool))
								retry -= 1

					except UnknownScript:
						# shouldn't happen at all, since we're using default OctoPrint scripts
						# but you never know
						self._logger.error("Script 'afterToolChange' not found!")

					finally:
						# now is the time to release the hold and continue printing
						self._printer.set_job_on_hold(False)


	def extend_script_variables(self, comm_instance, script_type, script_name, *args, **kwargs):
		# This section was supposed to pass the current endstop states to OctoPrint scripts when requested.
		# Unfortunatelly, OctoPrint caches the variables after the very first call and doesn't update
		# them on consecutive calls while in the same script.
		# This renders my attempt aligning the position of the filament based on the Feeder endstop trigger
		# unusable until OctoPrint updates this feature someday in the future.
		if script_type and script_type == "gcode":
			variables = dict(
				feeder	= "on" if self._feeder else "off",
				feeder2	= "on" if self._feeder2 else "off",
				tool	= self._cur_tool,
				aligned = "yes" if self._is_aligned else "no"
			)
			#self._logger.debug(" >> Script vars query: [" + str(script_type) + "," + str(script_name) + "] {0}".format(variables))
			return None, None, variables
		return None

	def extend_gcode_received(self, comm_instance, line, *args, **kwargs):
		# Refresh the current tool in OctoPrint on each command coming from the printer - just in case
		# This is needed because OctoPrint manages the current tool itself and it might try to swap
		# tools because of the wrong information.
		comm_instance._currentTool = self.parse_tool_number(self._cur_tool)
		# don't process any of the GCodes received
		return line

	##~~ helper functions

	# sending data to SMuFF
	def send_SMuFF(self, data):
		if self._serial and self._serial.is_open:
			try:
				b = bytearray(80)		# not expecting commands longer then that
				b = "{}\n".format(data).encode("ascii")
				# lock down the reader thread just in case 
				# (shouldn't be needed at all, since simultanous read/write operations should
				# be no big deal)
				self._serlock.acquire()
				n = self._serial.write(b)
				self._serlock.release()
				self._logger.debug("Sending {1} bytes: [{0}]".format(b, n))
				return True
			except (OSError, serial.SerialException):
				self._serlock.release()
				self._logger.error("Can't send command to SMuFF")
				return False
		else:
			self._logger.error("Serial not open")
			return False
		
	# sending data to SMuFF and waiting for a response
	def send_SMuFF_and_wait(self, data):
		if self.send_SMuFF(data) == False:
			return None

		timeout = 10 	# wait max. 10 seconds for a response
		done = False
		resp = None
		self.set_busy(False)	# reset busy and
		self.set_error(False)	# error flags
		while not done:
			self._serevent.clear()
			is_set = self._serevent.wait(timeout)
			if is_set:
				self._logger.info("To [{0}] SMuFF says [{1}] (is_error = {2})".format(data, self._response, self._is_error))
				resp = self._response
				if self._response == None or self._is_error:
					done = True
				elif not self._response.startswith('echo:'):
					done = True

				self._response = None
			else:
				self._logger.info("No event received... aborting")
				if self._is_busy == False:
					done = True
		return resp

	def find_file(self, pattern, path):
		result = []
		for root, dirs, files in os.walk(path):
			for name in files:
				if fnmatch.fnmatch(name, pattern):
					result.append(os.path.join(root, name))
		return result

	def set_busy(self, busy):
		self._is_busy = busy

	def set_error(self, error):
		self._is_error = error

	def set_response(self, response):
		self._response = response

	def parse_states(self, states):
		#self._logger.debug("States received: [" + states + "]")
		if len(states) == 0:
			return False
		# Note: SMuFF sends periodically states in this notation: 
		# 	"echo: states: T: T4     S: off  R: off  F: off  F2: off"
		m = re.search(r'^((\w+:.)(\w+:))\s([T]:\s)(\w+)\s([S]:\s)(\w+)\s([R]:\s)(\w+)\s([F]:\s)(\w+)\s([F,2]+:\s)(\w+)', states)
		if m:
			self._cur_tool 	= m.group(5).strip()
			self._selector 	= m.group(7).strip() == ESTOP_ON
			self._revolver 	= m.group(9).strip() == ESTOP_ON
			self._feeder 	= m.group(11).strip() == ESTOP_ON
			self._feeder2  	= m.group(13).strip() == ESTOP_ON
			if hasattr(self, "_plugin_manager"):
				self._plugin_manager.send_plugin_message(self._identifier, {'type': 'status', 'tool': self._cur_tool, 'feeder': self._feeder, 'feeder2': self._feeder2 })
			return True
		else:
			self._logger.error("No match in parse_states: [" + states + "]")
		return False

	def parse_tool_number(self, tool):
		try:
			return int(re.findall(r'[-\d]+', tool)[0])
		except Exception:
			self._logger.error("Can't parse tool number in {0}".format(tool))
		return -1

	def hex_dump(self, s):
		self._logger.debug(":".join("{:02x}".format(ord(c)) for c in s))


	# parse the response we've got from the SMuFF
	def parse_serial_data(self, data):
		if self == None:
			return

		#self._logger.debug("Raw data: [{0}]".format(data.rstrip("\n")))

		global last_response
		self._serevent.clear()

		# after first connect the response from the SMuFF is supposed to be 'start'
		if data.startswith('start\n'):
			self._logger.debug("SMuFF has sent \"start\" response")
			return

		if data.startswith("echo:"):
			# don't process any general debug messages
			if data[6:].startswith("dbg:"):
				self._logger.debug("SMuFF has sent a debug response: [" + data.rstrip() + "]")
			# but do process the tool/endstop states
			elif data[6:].startswith("states:"):
				last_response = None
				self.parse_states(data.rstrip())
			# and register whether SMuFF is busy
			elif data[6:].startswith("busy"):
				self._logger.debug("SMuFF has sent a busy response: [" + data.rstrip() + "]")
				self.set_busy(True)
			return

		if data.startswith("error:"):
			self._logger.info("SMuFF has sent a error response: [" + data.rstrip() + "]")
			# maybe the SMuFF has received garbage
			if data[7:].startswith("Unknown command:"):
				self._serial.flushOutput()
			self.set_error(True)
			return

		if data.startswith(ACTION_CMD):
			self._logger.info("SMuFF has sent an action request: [" + data.rstrip() + "]")
			# what action is it? is it a tool change?
			if data[10:].startswith("T"):
				tool = self.parse_tool_number(data[10:])
				# only if the printer isn't printing
				state = self._printer.get_state_id()
				self._logger.debug("SMuFF requested an action while printer in state '{}'".format(state))
				if state == "OPERATIONAL":
					# query the nozzle temp
					temps = self._printer.get_current_temperatures()
					try:
						if temps['tool0']['actual'] > 160:
							self._logger.debug("Nozzle temp. > 160")
							self._printer.change_tool("tool{}".format(tool))
							self.send_SMuFF("{0} T: OK".format(ACTION_CMD))
						else:
							self._logger.error("Can't change to tool {}, nozzle too cold".format(tool))
							self.send_SMuFF("{0} T: \"Nozzle too cold\"".format(ACTION_CMD))
					except:
						self._logger.debug("Can't query temperatures. Aborting.")
						self.send_SMuFF("{0} T: \"No nozzle temp. avail.\"".format(ACTION_CMD))
				else:
					self._logger.error("Can't change to tool {}, printer not ready or printing".format(tool))
					self.send_SMuFF("{0} T: \"Printer not ready\"".format(ACTION_CMD))
			return

		if data.startswith("ok\n"):
			if self._is_error:
				self.set_response(None)
			else:
				self.set_response(last_response)
			self._serevent.set()
			return

		# store the last response before the "ok"
		last_response = data.rstrip("\n")
		self._logger.debug("Received response: [{0}]".format(last_response))


def open_SMuFF_serial():
	global __stop_ser__
	global __ser0__
	global SERDEV

	_logger = logging.getLogger(LOGGER)
	__stop_ser__ = False

	SERDEV = SERDEVS[0]			# default is ttyS0
	mod = get_pi_model()		# query current model
	if mod == 4:
		SERDEV = SERDEVS[1]		# switch to ttyAMA1 on Pi 4

	try:
		__ser0__ = serial.Serial("/dev/{}".format(SERDEV), baudrate=SERBAUD, timeout=10)
		_logger.debug("Serial port /dev/{} is open".format(SERDEV))
	except (OSError, serial.SerialException):
		exc_type, exc_value, exc_traceback = sys.exc_info()
		tb = traceback.format_exception(exc_type, exc_value, exc_traceback)
		_logger.error("Can't open serial port /dev/{0}! Exc: {1}".format(SERDEV, tb))
		return False
	return True

def close_SMuFF_serial():
	global __stop_ser__
	global __ser0__

	_logger = logging.getLogger(LOGGER)
	__stop_ser__ = True
	# shutdown the reader thread first
	if not __sreader__ == None:
		__sreader__.join()
	# then close the serial port
	try:
		if __ser0__.is_open:
			__ser0__.close()
		_logger.debug("Serial port {} closed".format(__ser0__.port))

	except (OSError, serial.SerialException):
		exc_type, exc_value, exc_traceback = sys.exc_info()
		tb = traceback.format_exception(exc_type, exc_value, exc_traceback)
		_logger.error("Can't close serial port /dev/{0}! Exc: {1}".format(SERDEV, tb))

# Serial reader thread
def serial_reader(_logger, _serial, _instance, _lock):
	global __stop_ser__

	_logger.debug("Entering serial port receiver for {0}".format(_serial.port))
	cnt = 0

	# this loop basically runs forever, unless __stop_ser__ is set or the
	# serial port gets closed
	while not __stop_ser__: 
		if _serial.is_open:
			b = _serial.in_waiting
			#_logger.debug("{} bytes received".format(b))
			if b > 0:
				try:
					_lock.acquire()
					data = _serial.readline().decode("ascii")	# read to EOL
					_lock.release()
					#_logger.debug("Incoming data: [{}]".format(data))
					_instance.parse_serial_data(data)
				except:
					exc_type, exc_value, exc_traceback = sys.exc_info()
					tb = traceback.format_exception(exc_type, exc_value, exc_traceback)
					_logger.error("Serial reader error: ".join(tb))
		else:
			_logger.error("Serial {} has been closed".format(_serial.port))
			break

		cnt += 1
		time.sleep(0.01)
		if cnt >= 6000:		# send some "I'm still alive" signal every 60 seconds
			_logger.debug("Serial Reader Ping...")
			cnt = 0

	_logger.info("Exiting serial port receiver")

def get_pi_model():
	# get Pi model from cpuinfo
	_logger = logging.getLogger(LOGGER)
	model = 4
	try:
		f = open("/proc/cpuinfo","r")
		for line in f:
			if line.startswith("Model"):
				if line.find("Pi 4") == -1:
					model = 3
				_logger.info("Running on Pi {}".format(model))
		f.close()
	except:
		_logger.info("Can't read cpuinfo, assuming  Pi 3")
		model = 3
	return model

__plugin_name__ = "SMuFF Plugin"
__plugin_pythoncompat__ = ">=3,<4"


def __plugin_load__():
	global __plugin_implementation__
	global __plugin_hooks__
	global __ser0__
	global __stop_ser__
	global __sreader__
	global __lock__
	global __event__
	global _logger

	_logger = logging.getLogger(LOGGER)
	__lock__ = Lock()

	__plugin_implementation__ = SmuffPlugin(_logger, __lock__)

	if open_SMuFF_serial():
		__plugin_implementation__._serial = __ser0__
		try:
			# set up a separate task for reading the incoming SMuFF messages
			__sreader__ = Thread(target = serial_reader, args=( _logger, __ser0__, __plugin_implementation__, __lock__, ))
			__sreader__.daemon = True
			__sreader__.start()
			#_logger.debug("P={}".format(__sreader__))

		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			tb = traceback.format_exception(exc_type, exc_value, exc_traceback)
			_logger.error("Unable to start serial reader thread: ".join(tb))

	__plugin_hooks__ = {
		"octoprint.comm.protocol.gcode.received":	__plugin_implementation__.extend_gcode_received,
		"octoprint.comm.protocol.scripts": 		__plugin_implementation__.extend_script_variables,
		"octoprint.comm.protocol.gcode.sending": 	__plugin_implementation__.extend_tool_sending,
		"octoprint.comm.protocol.gcode.queuing": 	__plugin_implementation__.extend_tool_queuing,
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}

def __plugin_unload__():
	close_SMuFF_serial()


def __plugin_disabled():
	close_SMuFF_serial()

