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
ESTOP_TRG 	= "triggered"
ESTOP_ON	= "on"

class SmuffPlugin(octoprint.plugin.SettingsPlugin,
                  octoprint.plugin.AssetPlugin,
                  octoprint.plugin.TemplatePlugin,
				  octoprint.plugin.StartupPlugin,
				  octoprint.plugin.EventHandlerPlugin):

	def __init__(self):
		self._fw_info 		= "?"
		self._cur_tool 		= "?"
		self._pre_tool 		= "?"
		self._pending_tool 	= "?"
		self._endstops		= "?"
		self._skip_timer	= False
		self._selector 		= False
		self._revolver 		= False
		self._feeder 		= False
		self._feeder2		= False
		self._no_log		= False
		self._is_aligned 	= False
		self._ser1			= None
		self._ser1_port 	= None
		self._ser1_baud		= None
		self._ser1_state	= None
		self._ser1_init		= False
		self._got_response	= False
		self._response		= None
		self._in_file_list	= False
	
	##~~ StartupPlugin mixin

	def on_timer_event(self):
		# send SMuFF status updates periodically
		self._plugin_manager.send_plugin_message(self._identifier, {'type': 'status', 'tool': self._cur_tool, 'feeder': self._feeder, 'feeder2': self._feeder2 })
		

	def on_after_startup(self):
		# set up a timer to poll the SMuFF
		self._timer = RepeatedTimer(2.5, self.on_timer_event)
		self._timer.start()


	##~~ EventHandler mixin
	
	def on_event(self, event, payload):
		
		if event == "XXX_XXX": #Events.CONNECTED:
			self._logger.info("Event: [" + event + "]")
			# request the printers serial connection
			state, self._ser1_port, self._ser1_baud, profile = self._printer.get_current_connection()
			self._ser1_state = event

			if self._ser1_init == False:
				try:
					self._ser1 = serial.Serial(self._ser1_port, self._ser1_baud, timeout=1)
					self._ser1_init = True
					self._logger.info("Printers serial port has been opened")
				except (OSError, serial.SerialException):
					self._ser1_init = False
					self._logger.info("Can't open printers serial port")

		if event == Events.DISCONNECTED:
			self._logger.info("Event: [" + event + "]")
			try:
				if self._ser1 and self._ser1.is_open:
					self._ser1.close()
			except (OSError, serial.SerialException):
				pass
			self._ser1 = None
			self._ser1_init = False
			self._ser1_state = event
			self._logger.info("Printers serial port has been closed")

		if event == Events.PRINT_PAUSED:
			self._logger.info("Event: [" + event + "]")

		if event == Events.PRINT_RESUMED:
			self._logger.info("Event: [" + event + "]")
		
		if event == Events.TOOL_CHANGE:
			self._logger.info("Event: [" + event + "," + payload + "]")

		if event == Events.WAITING:
			self._logger.info("Event: [" + event + "]")

	##~~ SettingsPlugin mixin

	def get_settings_defaults(self):
		self._logger.info("SMuFF plugin loaded, getting defaults")

		params = dict(
			firmware_info	= "No data. Please check connection!",
			baudrate		= __ser_baud__,
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
		drvr = self.find_file(__ser_drvr__, "/dev")
		if len(drvr) > 0:
			params['tty'] = "Found! (/dev/" + __ser_drvr__ +")"

		return  params


		def get_template_configs(self):
			self._logger.info("Settings-Template was requested")
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
		
		# self._logger.info("Processing queuing: [" + cmd + "," + str(cmd_type)+ "," + str(tags) + "]")
		
		if gcode and gcode.startswith(TOOL):
			# if the tool that's already loaded is addressed, ignore the filament change
			if cmd == self._cur_tool:
				self._logger.info(cmd + " equals " + self._cur_tool + " -- aborting tool change")
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

			self._logger.info("1>> " + cmd + "  action: " + str(action) + "  v1,v2: " + str(v1) + ", " + str(v2))

			# @SMuFF SERVO
			if action and action == SERVO:
				self._skip_timer = True
				# send a servo command to SMuFF
				self.send_SMuFF_and_wait(M280 + str(v1) + " S" + str(v2))
				self._skip_timer = False
				return ""

			# @SMuFF MOTORS
			if action and action == MOTORS:
				self._skip_timer = True
				# send a servo command to SMuFF
				self.send_SMuFF_and_wait(M18)
				self._skip_timer = False
				return ""

			# @SMuFF PRINTER
			if action and action == PRINTER:
				self.send_printer_and_wait("M20")
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

			self._logger.info("2>> " + cmd + "  action: " + str(action) + "  v1,v2: " + str(v1) + ", " + str(v2))
			
			# @SMuFF T0...99
			if action and action.startswith(TOOL):
				if self._printer.set_job_on_hold(True):
					try:
						self._pending_tool = action
						self._logger.info("2>> TN: Feeder: " + str(self._feeder) + ", Pending: " + str(self._pending_tool) + ", Current: " + str(self._cur_tool))
						# check if there's some filament loaded
						if self._feeder:
							# send the "Before Tool Change" script to the printer
							self._logger.info("2>> calling script")
							self._printer.script("beforeToolChange")
						else:
							self._logger.info("2>> calling SMuFF LOAD")
							self._printer.commands(AT_SMUFF + " " + LOAD)

					except UnknownScript:
						self._logger.info("Script 'beforeToolChange' not found!")
					finally:
						self._printer.set_job_on_hold(False)

			# @SMuFF ALIGN
			if action and action == ALIGN:
				if self._is_aligned:
					return ""
				# check the feeder and keep retracting v1 as long as 
				# the feeder endstop is on
				if self._feeder:
					self._logger.info(action + " Feeder is: " + str(self._feeder) + " Cmd is:" + G1_E + str(v1))
					self._printer.commands(G1_E + str(v1) + ALIGN_SPEED + str(spd))
					# self.send_printer_and_wait(G1_E + str(v1) + ALIGN_SPEED + str(spd))
				else:
					self._is_aligned = True
					self._logger.info("Aligned now, cmd is: " + G1_E + str(v2))
					# finally retract from selector (distance = v2)
					self._printer.commands(G1_E + str(v2) + ALIGN_SPEED + str(spd))
					#self.send_printer_and_wait(G1_E + str(v2) + ALIGN_SPEED + str(spd))
				return ""

			# @SMuFF LOAD
			if action and action == LOAD:
				if self._printer.set_job_on_hold(True):
					try:
						self._logger.info("1>> LOAD: Feeder: " + str(self._feeder) + ", Pending: " + str(self._pending_tool) + ", Current: " + str(self._cur_tool))
						self._skip_timer = True
						# send a tool change command to SMuFF
						stat = self.send_SMuFF_and_wait(self._pending_tool)
						self._skip_timer = False

						if stat != None:
							self._pre_tool = self._cur_tool
							self._cur_tool = self._pending_tool
							# send the "After Tool Change" script to the printer
							self._printer.script("afterToolChange")

					except UnknownScript:
						self._logger.info("Script 'afterToolChange' not found!")
					
					finally:
						self._printer.set_job_on_hold(False)
			
		

	def extend_script_variables(self, comm_instance, script_type, script_name, *args, **kwargs):
		self._logger.info("Script called: [" + str(script_type) + "," + str(script_name) + "]")
		if script_type and script_type == "gcode":
			variables = dict(
				feeder	= self._feeder,
				feeder2	= self._feeder2,
				tool	= self._cur_tool,
				aligned = self._is_aligned
			)
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
				#self._logger.info("<<< [" + line.rstrip("\n") +"]")
		return line
	
	##~~ helper functions

	# sending data to SMuFF
	def send_SMuFF_and_wait(self, data):
		if __ser0__.is_open:
			__ser0__.write("{}\n".format(data))
			__ser0__.flush()
			# self._logger.debug(">>> " + data)
			self._is_busy = False
			prev_resp = ""
			retry = 15 	# wait max. 15 seconds for response
			while True:
				try:
					if _got_response == False:
						time.sleep(1)
						if self._is_busy == False:
							retry -= 1
						if retry == 0:
							return None
						continue
					elif _response.startswith('echo:'):
						continue
					else:
						if self._no_log == False:
							self._logger.info("SMuFF says [" + str(response) + "] to [" + str(data) +"]")
						return _response

				except (OSError, serial.SerialException):
					self._logger.info("Serial Exception!")
					continue
		else:
			self._logger.info("Serial not open")
			return None

	# sending data directly to printer
	def send_printer_and_wait(self, data):
		if self._ser1 and self._ser1.is_open:
			self._response = None
			self._ser1.write("{}\n".format(data))
			self._ser1.flush()
			# self._logger.debug(">>> " + data)
			retry = 15 	# wait max. 15 seconds for response
			while True:
				if self._got_response and self._response.startswith('ok\n'):
					return self._response.rstrip("\n")
				else:
					self._got_response = None
					time.sleep(.5)
					retry -= 1
					if retry == 0:
						return None

		else:
			self._logger.info("Printer serial not open")
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
			self._logger.info("Got response [" + response + "]")
		else:
			self._got_response = False

	def parse_states(self, states):
		#self._logger.info("Endstop states: [" + states + "]")
		if len(states) == 0:
			return False
		# SMuFF sends: echo: states: T: T4     S: off  R: off  F: off  F2: off
		m = re.search(r'^((\w+:.)(\w+:))\s([T]:\s)(\w+)\s([S]:\s)(\w+)\s([R]:\s)(\w+)\s([F]:\s)(\w+)\s([F,2]+:\s)(\w+)', states)
		if m:
			if m.group(3).strip() == "states:":
				self._cur_tool 	= m.group(5).strip()
				self._selector 	= m.group(7).strip() == ESTOP_ON
				self._revolver 	= m.group(9).strip() == ESTOP_ON
				self._feeder 	= m.group(11).strip() == ESTOP_ON
				self._feeder2  	= m.group(13).strip() == ESTOP_ON
				return True
		return False
		

__plugin_name__ = "SMuFF Plugin"

def __plugin_load__():
	global __plugin_implementation__
	global __plugin_hooks__
	global __ser0__
	global __ser_drvr__
	global __ser_baud__

	_logger = logging.getLogger("octoprint.plugins.SMuFF")

	__plugin_implementation__ = SmuffPlugin()

	__plugin_hooks__ = {
		"octoprint.comm.protocol.gcode.received":		__plugin_implementation__.extend_gcode_received,
		"octoprint.comm.protocol.scripts": 				__plugin_implementation__.extend_script_variables,
    	"octoprint.comm.protocol.gcode.sending": 		__plugin_implementation__.extend_tool_sending,
    	"octoprint.comm.protocol.gcode.queuing": 		__plugin_implementation__.extend_tool_queuing,
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}

	# change the baudrate here if you have to
	__ser_baud__ = 115200
	# do __not__ change the serial port device
	__ser_drvr__ = "ttyS0"

	try:
		__ser0__ = serial.Serial("/dev/"+__ser_drvr__, __ser_baud__, timeout=1)
		# after connecting, read the response from the SMuFF
		resp = __ser0__.readline()
		# which is supposed to be 'start'
		if resp.startswith('start'):
			_logger.info("SMuFF has sent \"start\" response")

		try:
			th_serial = threading.Thread(target = serial_reader, args = (__plugin_implementation__, _logger))
			th_serial.start()
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			tb = traceback.format_exception(exc_type, exc_value, exc_traceback)
			_logger.info("Unable to start serial reader thread: ".join(tb))

	except (OSError, serial.SerialException):
		_logger.info("Serial port not found!")



def __plugin_unload__():
	try:
		if __ser0__.is_open:
			__ser0__.close()
	except (OSError, serial.SerialException):
		pass


def __plugin_disabled():
	try:
		if __ser0__.is_open:
			__ser0__.close()
	except (OSError, serial.SerialException):
		pass

def serial_reader(comm_instance, _logger):
	while 1:
		if __ser0__ and __ser0__.is_open:
			if __ser0__.in_waiting > 0:
				data = __ser0__.read_until()	# read to EOL
				comm_instance.set_response(None)
				
				if data.startswith("echo: states:"):
					comm_instance.parse_states(data)
					continue

				if data.startswith("echo: busy"):
					comm_instance.set_busy(True)
					continue

				if data.startswith("error:"):
					comm_instance.set_response(last_response)
					continue

				if data.startswith("ok\n"):
					comm_instance.set_response(last_response)
					continue

				last_response = data.rstrip("\n")
				_logger.info("Got data: [" + data.rstrip("\n") + "]")
		else:
			_logger.info("Serial is closed")

