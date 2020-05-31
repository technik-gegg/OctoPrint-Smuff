#coding=utf-8

from __future__ import absolute_import

from octoprint.util import RepeatedTimer
from octoprint.printer import UnknownScript
from octoprint.events import Events

import serial			# we need this for the serial communcation with the SMuFF
import os, fnmatch
import re
import octoprint.plugin
import threading
import time
import sys
import traceback
import logging
import binascii

# change the baudrate here if you have to
SERBAUD		= 115200
SERDEV		= "serial0"
AT_SMUFF 	= "@SMuFF"
M115	 	= "M115"
M119	 	= "M119"
M280	 	= "M280 P"
M18			= "M18"
TOOL 		= "T"
NOTOOL		= "T255"
G1_E	 	= "G1 E"
ALIGN 	 	= "ALIGN"
REPEAT 		= "REPEAT"
LOAD 		= "LOAD"
SERVO		= "SERVO"
MOTORS		= "MOTORS"
PRINTER		= "PRINTER"
ALIGN_SPEED	= " F"
ESTOP_ON	= "on"

class SmuffPlugin(octoprint.plugin.SettingsPlugin,
                  octoprint.plugin.AssetPlugin,
                  octoprint.plugin.TemplatePlugin,
				  octoprint.plugin.StartupPlugin,
				  octoprint.plugin.ShutdownPlugin):

	def __init__(self):
		self._fw_info 		= "?"
		self._cur_tool 		= "?"
		self._pre_tool 		= "?"
		self._pending_tool 	= "?"
		self._endstops		= "?"
		self._selector 		= False
		self._revolver 		= False
		self._feeder 		= False
		self._feeder2		= False
		self._is_aligned 	= False
		self._got_response	= False
		self._response		= None
		self._in_file_list	= False

	##~~ ShutdownPlugin mixin
	
	def on_shutdown(self):
		close_SMuFF_serial(self._logger)
		self._logger.debug("Shutting down")

	##~~ StartupPlugin mixin

	def on_timer_event(self):
		# send SMuFF status updates periodically
		self._plugin_manager.send_plugin_message(self._identifier, {'type': 'status', 'tool': self._cur_tool, 'feeder': self._feeder, 'feeder2': self._feeder2 })
		
	def on_after_startup(self):
		# set up a timer to poll the SMuFF
		self._timer = RepeatedTimer(2.5, self.on_timer_event)
		self._timer.start()


	##~~ EventHandler mixin
	
	#def on_event(self, event, payload):
	#	self._logger.debug("Event: [" + event + ", {0}".format(payload) + "]")

	##~~ SettingsPlugin mixin

	def get_settings_defaults(self):
		#state, ser1_port, ser1_baud, profile = self._printer.get_current_connection()
		self._logger.debug("SMuFF plugin loaded, getting defaults [{0}]".format(self._printer.get_current_connection()))


		params = dict(
			firmware_info	= "No data. Please check connection!",
			baudrate		= SERBAUD,
			tty 			= "Not found. Please enable the UART on your Raspi!",
			tool			= self._cur_tool,
			selector_end	= self._selector,
			revolver_end	= self._revolver,
			feeder_end		= self._feeder,
			feeder2_end		= self._feeder
		)

		# request firmware info from SMuFF 
		self._fw_info = self.send_SMuFF_and_wait(M115)
		if self._fw_info:
			params['firmware_info'] = self._fw_info
		
		# look up the serial port driver
		if sys.platform == "win32":
			if SERDEV.startswith("serial"):
				params['tty'] = "Wrong device on WIN32 ({0})".format(SERDEV)
			else:
				params['tty'] = SERDEV
		else:
			drvr = self.find_file(SERDEV, "/dev")
			if len(drvr) > 0:
				params['tty'] = "Found! (/dev/" + SERDEV +")"

		return  params


	def get_template_configs(self):
		# self._logger.debug("Settings-Template was requested")
		return [
			dict(type="settings", custom_bindings=True, template='SMuFF_settings.jinja2'),
			dict(type="navbar", custom_bindings=True, template='SMuFF_navbar.jinja2')
		]

	##~~ AssetPlugin mixin

	def get_assets(self):
		# Define your plugin's asset files to automatically include in the
		# core UI here.
		return dict(
			js=["js/SMuFF.js"],
			css=["css/SMuFF.css"],
			less=["less/SMuFF.less"]
		)

	##~~ Softwareupdate hook

	def get_update_information(self):
		# Define the configuration for your plugin to use with the Software Update
		# Plugin here. See https://github.com/foosel/OctoPrint/wiki/Plugin:-Software-Update
		# for details.
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
			# if the tool that's already loaded is addressed, ignore the filament change
			if cmd == self._cur_tool:
				self._logger.warning(cmd + " equals " + self._cur_tool + " -- aborting tool change")
				return None
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
			
			# @SMuFF T0...99
			if action and action.startswith(TOOL):
				if self._printer.set_job_on_hold(True, False):
					try:
						self._pending_tool = str(action)
						# self._logger.debug("2>> TN: Feeder: " + str(self._feeder) + ", Pending: " + str(self._pending_tool) + ", Current: " + str(self._cur_tool))
						# check if there's some filament loaded
						if self._feeder:
							# send the "Before Tool Change" script to the printer
							#self._logger.debug("2>> calling script")
							self._printer.script("beforeToolChange")
						else:
							#self._logger.debug("2>> calling SMuFF LOAD")
							self._printer.commands(AT_SMUFF + " " + LOAD)

					except UnknownScript:
						self._logger.error("Script 'beforeToolChange' not found!")
					finally:
						self._printer.set_job_on_hold(False)

			# @SMuFF LOAD
			if action and action == LOAD:
				if self._printer.set_job_on_hold(True, False):
					try:
						self._logger.debug("1>> LOAD: Feeder: " + str(self._feeder) + ", Pending: " + str(self._pending_tool) + ", Current: " + str(self._cur_tool))
						retry = 3	# retry up to 3 times
						while retry > 0:
							# send a tool change command to SMuFF
							res = self.send_SMuFF_and_wait(self._pending_tool)

							if str(res) == str(self._pending_tool):
								self._pre_tool = self._cur_tool
								self._cur_tool = self._pending_tool
								# send the "After Tool Change" script to the printer
								self._printer.script("afterToolChange")
								retry = 0
							else:
								# not the result expected, retry
								self._logger.warning("Tool change failed, retrying  <" + str(res) + "> != <" + str(self._pending_tool) + ">")
								retry -= 1

					except UnknownScript:
						self._logger.error("Script 'afterToolChange' not found!")
					
					finally:
						self._printer.set_job_on_hold(False)
			
		
	def extend_script_variables(self, comm_instance, script_type, script_name, *args, **kwargs):
		if script_type and script_type == "gcode":
			variables = dict(
				feeder	= "on" if self._feeder else "off",
				feeder2	= "on" if self._feeder2 else "off",
				tool	= self._cur_tool,
				aligned = "yes" if self._is_aligned else "no"
			)
			self._logger.debug(" >> Script vars query: [" + str(script_type) + "," + str(script_name) + "] {0}".format(variables))
			return None, None, variables
		return None

	def extend_gcode_received(self, comm_instance, line, *args, **kwargs):
		if 	line == "" \
			or line.startswith("\n") \
			or line.startswith("start") \
			or line.startswith("echo:") \
			or line.startswith("FIRMWARE") \
			or line.startswith("Cap:") \
			or line.startswith("Begin file list") \
			or line.startswith("End file list") \
			or line.startswith(" T:"):
			# not interessed in those
			if line.startswith("Begin file list"):
				self._in_file_list = True
			if line.startswith("End file list"):
				self._in_file_list = False
		else:
			if self._in_file_list == False:
				# self._logger.debug("Printer sent [" + line.rstrip("\n") +"]")
				return line
		return line
	
	##~~ helper functions

	# sending data to SMuFF
	def send_SMuFF_and_wait(self, data):
		if __ser0__ and __ser0__.is_open:
			try:
				__ser0__.write_timeout = 5
				b = bytearray()
				b = data + "\n".encode("ascii")
				self._logger.debug("Sending: " + binascii.hexlify(b))
				__ser0__.write(b)
				__ser0__.flush()
			except (OSError, serial.SerialException):
				self._logger.error("Can't send to SMuFF")
				return None
			
			# self._logger.debug(">>> " + data)
			timeout = 5 	# wait max. 5 seconds for response
			start = time.time()
			self._is_busy = False
			ret = None
			while True:
				time.sleep(.1)
				if self._is_busy:
					start = time.time()

				if not self._got_response:
					if time.time() - start >= timeout:
						return None
					continue
				else:
					self._logger.info("{" + str(data) +"} SMuFF says [" + str(self._response) +"]")
					if self._response.startswith('echo:'):
						start = time.time()
						continue
					ret = self._response
					break
			return ret
		else:
			self._logger.error("Serial not open")
			return None

	def find_file(self, pattern, path):
		result = []
		for root, dirs, files in os.walk(path):
			for name in files:
				if fnmatch.fnmatch(name, pattern):
					result.append(os.path.join(root, name))
		return result

	def set_busy(self, busy):
		self._is_busy = busy

	def set_response(self, response):
		if not response == None:
			self._got_response = True
			self._response = response
			self._logger.debug("Got response [" + response + "]")
		else:
			self._got_response = False

	def parse_states(self, states):
		self._logger.debug("Endstop states: [" + states + "]")
		if len(states) == 0:
			return False
		# Note: SMuFF sends: "echo: states: T: T4     S: off  R: off  F: off  F2: off"
		m = re.search(r'^((\w+:.)(\w+:))\s([T]:\s)(\w+)\s([S]:\s)(\w+)\s([R]:\s)(\w+)\s([F]:\s)(\w+)\s([F,2]+:\s)(\w+)', states)
		if m:
			self._cur_tool 	= m.group(5).strip()
			self._selector 	= m.group(7).strip() == ESTOP_ON
			self._revolver 	= m.group(9).strip() == ESTOP_ON
			self._feeder 	= m.group(11).strip() == ESTOP_ON
			self._feeder2  	= m.group(13).strip() == ESTOP_ON
			return True
		else:
			self._logger.error("No match in parse_states: [" + states + "]")
		return False
	
	def get_feeder(self):
		return self._feeder

	def get_feeder2(self):
		return self._feeder2

	def get_tool(self):
		return self._cur_tool

	def hex_dump(self, s):
		self._logger.debug(":".join("{:02x}".format(ord(c)) for c in s))
		

__plugin_name__ = "SMuFF Plugin"

def __plugin_load__():
	global __plugin_implementation__
	global __plugin_hooks__
	global __t_serial__
	_logger = logging.getLogger("octoprint.plugins.SMuFF")

	__plugin_implementation__ = SmuffPlugin()

	__plugin_hooks__ = {
		"octoprint.comm.protocol.gcode.received":		__plugin_implementation__.extend_gcode_received,
		"octoprint.comm.protocol.scripts": 				__plugin_implementation__.extend_script_variables,
    	"octoprint.comm.protocol.gcode.sending": 		__plugin_implementation__.extend_tool_sending,
    	"octoprint.comm.protocol.gcode.queuing": 		__plugin_implementation__.extend_tool_queuing,
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}


	# set up a thread for reading the incoming SMuFF messages
	__t_serial__ = threading.Thread(target = serial_reader, args = (__plugin_implementation__, _logger))
	__t_serial__.daemon = True

	if open_SMuFF_serial(_logger):
		try:
			__t_serial__.start()
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			tb = traceback.format_exception(exc_type, exc_value, exc_traceback)
			_logger.error("Unable to start serial reader thread: ".join(tb))


def open_SMuFF_serial(_logger):
	global __ser0__
	global __stop_ser__

	__stop_ser__ = False
	__ser0__ = None
	try:
		__ser0__ = serial.Serial("/dev/"+SERDEV, SERBAUD, timeout=1)
		_logger.debug("Serial port /dev/{0} opened".format(SERDEV))
		return True
	except (OSError, serial.SerialException):
		exc_type, exc_value, exc_traceback = sys.exc_info()
		tb = traceback.format_exception(exc_type, exc_value, exc_traceback)
		_logger.error("Can't open serial port /dev/{0}!".format(SERDEV)+"  Exc: {0}".format(tb))
	return False

def close_SMuFF_serial(_logger):
	global __stop_ser__
	global __ser0__
	global __t_serial__
	
	__stop_ser__ = True
	if 	not __t_serial__ == None:
		__t_serial__.join()
	try:
		if __ser0__.is_open:
			__ser0__.close()
			_logger.debug("Serial port closed")
	except (OSError, serial.SerialException):
		exc_type, exc_value, exc_traceback = sys.exc_info()
		tb = traceback.format_exception(exc_type, exc_value, exc_traceback)
		_logger.error("Can't close serial port /dev/{0}!".format(SERDEV)+"  Exc: {0}".format(tb))


def __plugin_unload__():
	_logger = logging.getLogger("octoprint.plugins.SMuFF")
	close_SMuFF_serial(_logger)


def __plugin_disabled():
	_logger = logging.getLogger("octoprint.plugins.SMuFF")
	close_SMuFF_serial(_logger)

def serial_reader(_instance, _logger):
	global __ser0__
	global __stop_ser__

	_logger.debug("Entering serial receiver thread on {0}".format(__ser0__.port))
	
	retryOpen = 3
	while not __stop_ser__:
		if __ser0__ and __ser0__.is_open:
			b = __ser0__.in_waiting
			#_logger.debug("{0}".format(b))
			if b > 0:
				_logger.debug("Chars waiting: {0}".format(b))
				data = __ser0__.read_until()	# read to EOL

				_logger.debug("Raw data: [{0}]".format(data.rstrip("\n")))

				# after first connect the response from the SMuFF
				# is supposed to be 'start'
				if data.startswith('start\n'):
					_logger.debug("SMuFF has sent \"start\" response")
					continue

				if data.startswith("echo:"):
					_logger.debug("ECHO-MSG: {0}".format(data[6:]))
					# don't process any debug messages
					if data[6:].startswith("dbg:"):
						_logger.debug("SMuFF has sent a debug response: [" + data.rstrip() + "]")
						continue

					if data[6:].startswith("states:"):
						_logger.debug("SMuFF has sent states: [" + data.rstrip() + "]")
						_instance.parse_states(data.rstrip())
						continue

					if data[6:].startswith("busy"):
						_logger.debug("SMuFF has sent a busy response: [" + data.rstrip() + "]")
						_instance.set_busy(True)
						continue

				if data.startswith("error:"):
					_logger.info("SMuFF has sent a error response: [" + data.rstrip() + "]")
					continue

				if data.startswith("ok\n"):
					_instance.set_response(last_response)
					continue

				last_response = data.rstrip("\n")
				_logger.debug("Got data: [" + last_response + "]")

		else:
			_logger.error("Serial is closed")
			if not __stop_ser__ and retryOpen > 0:
				retryOpen -= 1
				_logger.error("Trying to reopen serial port")
				open_SMuFF_serial(_logger)
			else:
				break

	_logger.info("Exiting serial port receiver")

