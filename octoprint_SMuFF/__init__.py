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
			firmware_info	="No data. Please check connection!",
			baudrate		=__ser_baud__,
			tty 			="Not found. Please enable the UART on your Raspi!",
			tool			=__cur_tool__,
			selector_end	="?",
			revolver_end	="?",
			feeder_end		="?",
			feeder2_end		="?"
		)

		__ser0__.timeout = 1

		# request firmware info from SMuFF 
		__fw_info__ = self.send_and_wait("M115")
		if __fw_info__:
			params['firmware_info'] = __fw_info__
		
		# request the currently active tool
		if self.get_tool() == True:
			params['tool'] = __cur_tool__
			self._logger.info("Current tool on SMuFF [" + __cur_tool__ + "]")

		# request the endstop states
		if self.get_endstops() == True:
			self._logger.info("Endstops: [" + __endstops__ +"]")
			params['feeder_end']   = __feeder__ == "triggered"
			params['feeder2_end']  = __feeder2__ == "triggered"

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

	##~~ GCode hook

	def extend_tool_change(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
		if gcode and gcode.startswith('@SMuFF-B'):
			self._logger.info("@SMuFF-B received: ")
			return None

		if gcode and gcode.startswith('@SMuFF-A'):
			self._logger.info("@SMuFF-A received: ")
			return None

		if gcode and gcode.startswith('T'):
			self._logger.info("Sending tool change: " + cmd)
			__toolchange__ = True		# signal tool change in progress

			if self.send_and_wait(cmd):
				__pre_tool__ = __cur_tool__
				__cur_tool__ = cmd.rstrip("\n")
				__tool_no__ = self.parse_tool_number()
			
			__toolchange__ = False
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
							self._logger.info("SMuFF says: [" + prev_resp +"]")
					retry -= 1
					if retry == 0:
						return None
		else:
			self._logger.info("Serial not open")


	def find_file(self, pattern, path):
		result = []
		for root, dirs, files in os.walk(path):
			for name in files:
				if fnmatch.fnmatch(name, pattern):
					result.append(os.path.join(root, name))
		return result


	def get_tool(self):
		__cur_tool__ = self.send_and_wait("T")
		if __cur_tool__:
			__tool_no__ = self.parse_tool_number()
			return True
		return False


	def get_endstops(self):
		__endstops__ = self.send_and_wait("M119")
		if __endstops__:
			self.parse_endstop_states(__endstops__)
			return True
		return False


	def parse_tool_number(self):
		result = -1
		try:
			result = int(re.search(r'\d+', __cur_tool__).group(0))
		except ValueError:
			self._logger.into("Can't parse tool number: [" + __cur_tool__ + "]")
		except:
			self._logger.info("Can't parse tool number: [Unexpected error:" + sys.exc_info()[0] + "]")
		return result


	def parse_endstop_states(self, states):
		self._logger.into("Endstop states: [" + states + "]")
		if len(states) == 0:
			return False
		m = re.search(r'^(\w+:.)(\w+).(\w+:.)(\w+).(\w+:.)(\w+)', states)
		if m:
			__selector__ = m.group(2).strip() == "triggered"
			__revolver__ = m.group(4).strip() == "triggered"
			__feeder__ 	 = m.group(6).strip() == "triggered"
			__feeder2__  = False # m.group(8).strip() == "triggered"
			# self._logger.info("SELECTOR end: [" + str(__selector__) +"]")
			# self._logger.info("REVOLVER end: [" + str(__revolver__) +"]")
			# self._logger.info("FEEDER   end: [" + str(__feeder__)   +"]")
			return True
		return False
		


__plugin_name__ = "Smuff Plugin"

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = SmuffPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
    	"octoprint.comm.protocol.gcode.queuing": __plugin_implementation__.extend_tool_change,
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}
	global __ser0__
	global __ser_drvr__
	global __ser_baud__

	# change the baudrate here if you have to
	__ser_baud__ = 115200
	# do __not__ change the serial port device
	__ser_drvr__ = "ttyS0"

	try:
	__ser0__ = serial.Serial("/dev/"+__ser_drvr__, __ser_baud__, timeout=5)
	# after connecting, read the response from the SMuFF
	resp = __ser0__.readline()
	# which is supposed to be 'start'
	if resp.startswith('start'):
		self._logger.info("SMuFF has sent \"start\" response")
	self._logger.info("__plugin_load__ done!")

except (OSError, serial.SerialException):
	self._logger.info("Serial port not found!")
	#pass


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
