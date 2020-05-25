#coding=utf-8

from __future__ import absolute_import

from octoprint.util import RepeatedTimer
import serial			# we need this for the serial communcation with the SMuFF
import os, fnmatch
import re
import octoprint.plugin
import time
import sys

class SmuffPlugin(octoprint.plugin.SettingsPlugin,
                  octoprint.plugin.AssetPlugin,
                  octoprint.plugin.TemplatePlugin,
				  octoprint.plugin.StartupPlugin):

	
	def __init__(self):
		global __fw_info__
		global __cur_tool__
		global __pre_tool__
		global __tool_no__
		global __toolchange__
		global __endstops__
		global __selector__
		global __revolver__
		global __feeder__
		global __feeder2__
		global __timer__
		global __no_log__

		__fw_info__ 	= "?"
		__cur_tool__ 	= "?"
		__pre_tool__ 	= "?"
		__tool_no__ 	= -1
		__toolchange__ 	= False
		__endstops__	= "?"
		__selector__ 	= False
		__revolver__ 	= False
		__feeder__ 		= False
		__feeder2__		= False
		__no_log__		= False


	##~~ StartupPlugin mixin

	def on_timer_event(self):
		global __no_log__
		# poll tool active and endstop states periodically
		if __toolchange__ == False:
			__no_log__ = True
			self.get_tool()
			self.get_endstops()
			__no_log__ = False
		
		self._plugin_manager.send_plugin_message(self._identifier, {'type': 'status', 'tool': __cur_tool__, 'feeder': __feeder__, 'feeder2': __feeder2__ })

	def on_after_startup(self):
		# set up a timer to poll the SMuFF
		__timer__ = RepeatedTimer(1.0, self.on_timer_event)
		__timer__.start()

	##~~ SettingsPlugin mixin

	def get_settings_defaults(self):
		self._logger.info("SMuFF plugin loaded, getting defaults")

		params = dict(
			firmware_info	= "No data. Please check connection!",
			baudrate		= __ser_baud__,
			tty 			= "Not found. Please enable the UART on your Raspi!",
			tool			= __cur_tool__,
			selector_end	= __selector__,
			revolver_end	= __revolver__,
			feeder_end		= __feeder__,
			feeder2_end		= __feeder__,
			before_script	= __before_script__,
			after_script	= __after_script__
		)

		__ser0__.timeout = 1

		# request firmware info from SMuFF 
		__fw_info__ = self.send_and_wait("M115")
		if __fw_info__:
			params['firmware_info'] = __fw_info__
		
		# request the currently active tool
		if self.get_tool() == True:
			params['tool'] = __cur_tool__

		# request the endstop states
		if self.get_endstops() == True:
			params['selector_end'] = __selector__
			params['revolver_end'] = __revolver__
			params['feeder_end']   = __feeder__
			params['feeder2_end']  = __feeder2__

		# look up the serial port driver
		drvr = self.find_file(__ser_drvr__, "/dev")
		if len(drvr) > 0:
			params['tty'] = "Found! (/dev/" + __ser_drvr__ +")"

		return  params


		def get_template_configs(self):
			self._logger.info("Settings-Template was requested")
			return [
				dict(type="settings", custom_bindings=True, template='SMuFF_settings.jinja2')
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
		
		if gcode and gcode.startswith('T'):
			#self._logger.info("Processing queuing: [" + cmd + "," + str(cmd_type)+ "," + str(tags) + "]")

			# if the tool that's already loaded is addressed, ignore the filament change
			if cmd == __cur_tool__:
				self._logger.info(cmd + " equals " + __cur_tool__ + "aborting tool change")
				return None
			# replace the tool change command
			return [ "@SMuFF " + cmd ]


	def extend_tool_sending(self, comm_instance, phase, cmd, cmd_type, gcode, subcode, tags, *args, **kwargs):
		global __toolchange__
		global __cur_tool__
		global __pre_tool__
		global __tool_no__
		global __pending_tool__
		global __feeder__
		global __feeder2__

		if gcode and gcode.startswith('T'):
			return ""

		# is this the replaced tool change command?
		if cmd and cmd.startswith('@SMuFF '):
			self._logger.info(">> " + cmd)
			
			# @SMuFF T0...9
			if cmd[7:8] == "T":		
				if self._printer.set_job_on_hold(True):
					try:
						__pending_tool__ = cmd[7:]
						self._logger.info("Feeder is: " + str(__feeder__))
						# check if there's some filament loaded
						if __feeder__:
							# send the "Before Tool Change" script to the printer
							self._printer.script("beforeToolChange")
						else:
							self._printer.commands("@SMuFF LOAD")
						
					except UnknownScriptException:
						self._logger.info("Script 'beforeToolChange' not found!")
						self._printer.set_job_on_hold(False)

			# @SMuFF CHECK
			if cmd[7:] == "ALIGN":
				if self._printer.job_on_hold():
					try:
						v1 = -10
						v2 = -50
						m = re.search(r'^@\w+.\w+.(\d+).(\d+)', cmd)
						if m:
							v1 = int(m.group(1))
							v2 = int(m.group(2))

						# check the feeder and keep retracting 10mm as long as 
						# the feeder endstop is on
						while __feeder__:
							self._printer.commands("G1 E" + str(v1))
							time.sleep(.75)
							self.get_endstops()
						
						self._logger.info("Feeder is: " + str(__feeder__))
						
						#finally retract from selector
						self._printer.commands("G1 E" + str(v2))
						time.sleep(2)

			# @SMuFF LOAD
			if cmd[7:] == "LOAD":		
				if self._printer.job_on_hold():
					try:
						__toolchange__ = True
						# send a tool change command to SMuFF
						stat = self.send_and_wait(__pending_tool__)
						__toolchange__ = False

						if stat != None:
							__pre_tool__ = __cur_tool__
							__cur_tool__ = __pending_tool__
							__tool_no__ = self.parse_tool_number(__cur_tool__)
						# send the "After Tool Change" script to the printer
						self._printer.script("afterToolChange")
					except UnknownScriptException:
						self._logger.info("Script 'afterToolChange' not found!")
					finally:
						self._printer.set_job_on_hold(False)
			
			return None

	def extend_script_variables(comm_instance, script_type, script_name, *args, **kwargs):
		if script_type and script_type == "gcode":
			variables = dict(
				feeder	= __feeder__,
				feeder2	= __feeder2__,
				tool	= __cur_tool__
			)
			return None, None, variables
		return None
	
	##~~ helper functions

	def send_and_wait(self, data):
		if __ser0__.is_open:
			__ser0__.write("{}\n".format(data))
			__ser0__.flush()
			prev_resp = ""
			retry = 15 	# wait max. 15 seconds for response
			while True:
				response = __ser0__.readline()
				if response.startswith('ok\n'):
					return prev_resp
				else:
					prev_resp = response.rstrip("\n")
					if prev_resp:
						if __no_log__ == False:
							self._logger.info("SMuFF says [" + prev_resp + "] to [" + data +"]")
					retry -= 1
					if retry == 0:
						return None
		else:
			self._logger.info("Serial not open")
			return None


	def find_file(self, pattern, path):
		result = []
		for root, dirs, files in os.walk(path):
			for name in files:
				if fnmatch.fnmatch(name, pattern):
					result.append(os.path.join(root, name))
		return result


	def get_tool(self):
		global __cur_tool__
		global __tool_no__
		__cur_tool__ = self.send_and_wait("T")
		#self._logger.info("SMuFF says Tool is: [" + __cur_tool__ +"]")
		if __cur_tool__:
			__tool_no__ = self.parse_tool_number(__cur_tool__)
			#self._logger.info("Plugin says Tool is: [" + str(__tool_no__) +"]")
			return True
		return False


	def get_endstops(self):
		global __endstops__
		__endstops__ = self.send_and_wait("M119")
		if __endstops__:
			self.parse_endstop_states(__endstops__)
			return True
		return False


	def parse_tool_number(self, tool):
		result = -1
		
		if len(tool) == 0:
			return result

		try:
			result = int(re.search(r'\d+', tool).group(0))
		except ValueError:
			self._logger.into("Can't parse tool number: [" + tool + "]")
		except:
			self._logger.info("Can't parse tool number: [Unexpected error]")
		return result


	def parse_endstop_states(self, states):
		global __selector__
		global __revolver__
		global __feeder__
		global __feeder2__
		#self._logger.info("Endstop states: [" + states + "]")
		if len(states) == 0:
			return False
		trg = "triggered"
		m = re.search(r'^(\w+:.)(\w+).(\w+:.)(\w+).(\w+:.)(\w+)', states)
		if m:
			__selector__ = m.group(2).strip() == trg
			__revolver__ = m.group(4).strip() == trg
			__feeder__ 	 = m.group(6).strip() == trg
			__feeder2__  = False # m.group(8).strip() == trg
			#self._logger.info("SELECTOR: [" + str(__selector__) + "] REVOLVER: [" + str(__revolver__) + "] FEEDER: [" + str(__feeder__) +"]")
			return True
		return False
		
	def _feeder(self):
		return __feeder__

	def _feeder2(self):
		return __feeder2__

	def _tool(self):
		return __cur_tool__
	


__plugin_name__ = "Smuff Plugin"

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = SmuffPlugin()

	global __plugin_hooks__
	
	__plugin_hooks__ = {
		"octoprint.comm.protocol.scripts": 				__plugin_implementation__.extend_script_variables,
    	"octoprint.comm.protocol.gcode.sending": 		__plugin_implementation__.extend_tool_sending,
    	"octoprint.comm.protocol.gcode.queuing": 		__plugin_implementation__.extend_tool_queuing,
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}
	global __before_script__
	global __after_script__
	global __ser0__
	global __ser_drvr__
	global __ser_baud__

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
			self._logger.info("SMuFF has sent \"start\" response")

	except (OSError, serial.SerialException):
		self._logger.info("Serial port not found!")
		#pass

	# read before and after ToolChange scripts from the default OctoPrint folder
	file = open("/home/pi/.octoprint/scripts/gcode/SMuFF_beforeToolChange", "r") 
	__before_script__ = file.read();
	file.close();

	file = open("/home/pi/.octoprint/scripts/gcode/SMuFF_afterToolChange", "r") 
	__after_script__ = file.read();
	file.close();


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
