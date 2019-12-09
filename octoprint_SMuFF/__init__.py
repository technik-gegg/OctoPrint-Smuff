#coding=utf-8

from __future__ import absolute_import

import octoprint.plugin
import serial			# we need this for the serial communcation with the SMuFF
import os, fnmatch

class SmuffPlugin(octoprint.plugin.SettingsPlugin,
                  octoprint.plugin.AssetPlugin,
                  octoprint.plugin.TemplatePlugin):


	def get_settings_defaults(self):
        self._logger.info("SMuFF plugin loaded, getting defaults")

		# after connecting, read the response from the SMuFF
		resp = __ser0__.readline()
		# which is supposed to be 'start'
		if resp.startswith('start'):
			self._logger.info("SMuFF has sent \"start\" response")
			# if start was received, read out the firmware info for later use
		else:
			self._logger.info("No response from SMuFF [" + resp + "]")

		__ser0__.timeout = 1

		params = dict(
			firmware_info=["No data. Please check connection!"],
			baudrate=[__ser_baud__]
			tty=["Not found. Please enable the UART on your Raspi!"]
		)

		__fw_info__ = self.send_and_wait("M115")
		if __fw_info__:
			params['firmware_info'] = __fw_info__
		drvr = self.find_file(__ser_drvr__, "/dev")
		if len(drvr) > 0:
            params['tty'] = "Found! (/dev/" + __ser_drvr__ +")"
		return  params


        def get_template_configs(self):
            return [
                dict(type="settings", custom_bindings=False)
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


	def extend_tool_change(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
		if gcode and gcode.startswith('T'):
			self._logger.info("Sending tool change: " + cmd)
			self.send_and_wait(cmd)
		return None


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
					prev_resp = response
					if prev_resp:
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


__plugin_name__ = "Smuff Plugin"

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = SmuffPlugin()

	global __fw_info__
	__fw_info__ = "?"

        global __ser0__
        global __ser_drvr__
        global __ser_baud__

		# change the baudrate here if you have to
        __ser_baud__ = 115200
        __ser_drvr__ = "ttyS0"
        __ser0__ = serial.Serial("/dev/"+__ser_drvr__, __ser_baud__, timeout=5)


	global __plugin_hooks__
	__plugin_hooks__ = {
       	"octoprint.comm.protocol.gcode.queuing": __plugin_implementation__.extend_tool_change,
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}


def __plugin_unload__():
	if __ser0__.is_open:
		__ser0__.close()


def __plugin_disabled():
	if __ser0__.is_open:
		__ser0__.close()
