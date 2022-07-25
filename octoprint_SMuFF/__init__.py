#---------------------------------------------------------------------------------------------
# SMuFF OctoPrint Plugin
#---------------------------------------------------------------------------------------------
#
# Copyright (C) 2020-2022 Technik Gegg <technik.gegg@gmail.com>
#
# This file may be distributed under the terms of the GNU AGPLv3 license.
#
#
# This plugin implements the communication to the SMuFF for tool changing
# very similar to the Klipper module.

#coding=utf-8

from __future__ import absolute_import
from multiprocessing import connection
from sqlite3 import connect

from octoprint.printer import UnknownScript
from octoprint.events import Events

from . import smuff_core

import octoprint.plugin
import logging

LOGGER			= "octoprint.plugins.SMuFF"
DEFAULT_BAUD	= 115200
IS_KLIPPER		= False 				# flag has to be set to True for Klipper

AT_SMUFF 		= "@SMuFF"				# prefix for pseudo GCode for SMuFF functions
DEBUG			= "DEBUG"
LOAD 			= "LOAD"
UNLOAD 			= "UNLOAD"
RELOAD 			= "RELOAD"
SERVO			= "SERVO"
SERVOOPEN		= "SERVOOPEN"
SERVOCLOSE		= "SERVOCLOSE"
WIPENOZZLE		= "WIPE"
CUTFIL			= "CUT"
MOTORS			= "MOTORS"
FAN				= "FAN"
STATUS 			= "STATUS"
UNJAM 			= "UNJAM"
RESET 			= "RESET"
RESETAVG 		= "RESETAVG"

class SmuffPlugin(octoprint.plugin.SettingsPlugin,
                  octoprint.plugin.AssetPlugin,
                  octoprint.plugin.TemplatePlugin,
				  octoprint.plugin.StartupPlugin,
				  octoprint.plugin.EventHandlerPlugin,
				  octoprint.plugin.ShutdownPlugin):

	def __init__(self, logger):
		self._log = logger
		self.SC = smuff_core.SmuffCore(logger, IS_KLIPPER, self.smuffStatusCallback, self.smuffResponseCallback)
		self._reset()

	def _reset(self):
		pass

	def smuffStatusCallback(self, active):
		if hasattr(self, "_plugin_manager"):
			tool 	= self.SC.curTool 		if active else -1
			feeder 	= self.SC.feeder 		if active else False
			feeder2	= self.SC.feeder2 		if active else False
			info 	= self.SC.fwInfo 		if active else ""
			conn	= self.SC.isConnected 	if active else False
			jammed 	= self.SC.isJammed 		if active else False
			self._plugin_manager.send_plugin_message(self._identifier, {'type': 'status', 'tool': tool, 'feeder': feeder, 'feeder2': feeder2, 'fw_info': info, 'conn': conn, 'jammed': jammed })
			if not self.SC.isConnected:
				self._setResponse("Not connected", True)
		pass

	def smuffResponseCallback(self, message):
		self._setResponse(message, False)
	#------------------------------------------------------------------------------
	# OctoPrint plugin functions
	#------------------------------------------------------------------------------

	#
	# ShutdownPlugin mixin
	#
	def on_startup(self, host, port):
		self._log.info("Yeah... starting up...")

	def on_shutdown(self):
		self.SC.close_serial()
		self._log.debug("Booo... shutting down...")

	#
	# StartupPlugin mixin
	#
	def on_after_startup(self):
		self.SC.serialPort 		= "/dev/{}".format(self._settings.get(["tty"]))
		self.SC.baudrate 		= self._settings.get_int(["baudrate"])
		self.SC.cmdTimeout 		= self._settings.get_int(["timeout1"])
		self.SC.tcTimeout 		= self._settings.get_int(["timeout2"])
		self.SC.wdTimeout 		= self.SC.tcTimeout * 2
		self.SC.timeout 		= self.SC.tcTimeout * 2
		self.SC.connect_SMuFF()

	#
	# EventHandler mixin
	#
	def on_event(self, event, payload):
		#self._log.debug("Event: [" + event + ", {0}".format(payload) + "]")
		if event == Events.SHUTDOWN:
			self._log.debug("Shutting down, closing serial")
			self.SC.close_serial()

	#
	# SettingsPlugin mixin
	#
	def get_settings_version(self):
		return 2

	def get_settings_defaults(self):
		self._log.debug("SMuFF plugin loaded, getting defaults")
		params = dict(
			firmware_info	= "No data. Please check connection!",
			baudrate		= DEFAULT_BAUD,
			tty 			= "ttySMuFF",
			tool			= self.SC.curTool,
			selector_end	= self.SC.selector,
			revolver_end	= self.SC.revolver,
			feeder_end		= self.SC.feeder,
			feeder2_end		= self.SC.feeder2,
			timeout1		= 30,
			timeout2		= 90,
			autoload 		= True
		)
		return  params

	def on_settings_migrate(self, target, current):
		if current == None or target < current:
			self._log.debug("Migrating old settings...")
			self._settings.save()


	def on_settings_save(self, data):
		baud_now = self._settings.get_int(["baudrate"])
		port_now = self._settings.get(["tty"])
		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

		baud_new = self._settings.get_int(["baudrate"])
		port_new = self._settings.get(["tty"])
		self._log.debug("Settings saved: Baudrate: {0} -> {1}  Port: {2} -> {3}".format(baud_now, baud_new, port_now, port_new))
		# did the settings change?
		if not port_new == port_now or not baud_new == baud_now:
			# reconnect on the new port (with new baudrate)
			self.SC.reconnect_SMuFF()

	def get_template_configs(self):
		# self._log.debug("Settings-Template was requested")
		return [
			dict(type="settings", 	custom_bindings=True,  template="SMuFF_settings.jinja2"),
			dict(type="navbar", 	custom_bindings=True,  template="SMuFF_navbar.jinja2"),
			dict(type="tab", 		custom_bindings=True,  template="SMuFF_tab.jinja2", name="SMuFF")
		]

	#
	# AssetPlugin mixin
	#
	def get_assets(self):
		return dict(
			js=["js/SMuFF.js"],
			css=["css/SMuFF.css"],
			less=["less/SMuFF.less"]
		)

	#
	# Softwareupdate hook
	#
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

	#
	# Split up a command into action and its parameters (up to 3)
	#
	def _split_cmd(self, cmd):
		action = None
		param1 = None
		param2 = None
		param3 = None

		tmp = cmd.split()

		if len(tmp):
			action = tmp[1].upper()
			if len(tmp) > 2:
				param1 = int(tmp[2])
			if len(tmp) > 3:
				param2 = int(tmp[3])
			if len(tmp) > 4:
				param3 = int(tmp[4])
		return action, param1, param2, param3

	#
	# GCode hooks
	#
	def extend_tool_queuing(self, comm_instance, phase, cmd, cmd_type, gcode, subcode, tags, *args, **kwargs):
		#self._log.debug("Processing tool queuing: [ Cmd: {0}, Type: {1}, Tags: {2} ]".format(cmd, str(cmd_type), str(tags)))

		if gcode and gcode.startswith(smuff_core.TOOL):
			self._log.debug("OctoPrint current tool: {0}".format(comm_instance._currentTool))

			# if the tool that's already loaded is addressed, ignore the filament change
			if cmd == self.SC.curTool and self.SC.feeder:
				self._log.info("Current tool {0} equals {1} -- no tool change needed".format(cmd, self.SC.curTool))
				self._setResponse("Tool already selected", True)
				return
			self.SC.isAligned = False
			# replace the tool change command Tx with @SMuFF Tx
			return [ AT_SMUFF + " " + cmd ]

		# handle SMuFF pseudo GCodes
		if cmd and cmd.startswith(AT_SMUFF):
			action, v1, v2, v3 = self._split_cmd(cmd)
			self._log.debug("1>> Cmd: {0}  Action: {1}  Params: {2}; {3}; {4}".format(cmd, str(action), str(v1), str(v2), str(v3)))

			# @SMuFF MOTORS
			if action and action == MOTORS:
				# send a servo command to SMuFF
				self.SC.send_SMuFF_and_wait(smuff_core.MOTORSOFF)
				self._setResponse(smuff_core.T_MOTORS_OFF, True)
				return

			# @SMuFF FAN
			if action and action == FAN:
				# send a fan command to SMuFF
				self.SC.send_SMuFF_and_wait(smuff_core.FAN_ON if v1 == 1 else smuff_core.FAN_OFF)
				self._setResponse(smuff_core.T_FAN.format("ON" if v1 == 1 else "OFF"), True)
				return

			# @SMuFF DEBUG
			if action and action == DEBUG:
				# toggle debug state
				self.SC.dumpRawData = not self.SC.dumpRawData
				self._setResponse(smuff_core.T_DUMP_RAW.format("ON" if self.SC.dumpRawData else "OFF"), True)
				return

			# @SMuFF SERVO
			if action and action == SERVO:
				# send a servo command to SMuFF
				self.SC.send_SMuFF_and_wait(smuff_core.SETSERVO.format(str(v1), str(v2)))
				self._setResponse(smuff_core.T_POSITIONING.format(v1, v2), True)
				return

			# @SMuFF SERVOOPEN
			if action and action == SERVOOPEN:
				# send a servo open command to SMuFF
				self._setResponse(smuff_core.T_OPENING_LID, True)
				self.SC.send_SMuFF_and_wait(smuff_core.LIDOPEN)
				return

			# @SMuFF SERVOCLOSE
			if action and action == SERVOCLOSE:
				# send a servo close command to SMuFF
				self._setResponse(smuff_core.T_CLOSING_LID, True)
				self.SC.send_SMuFF_and_wait(smuff_core.LIDCLOSE)
				return

			# @SMuFF WIPE
			if action and action == WIPENOZZLE:
				# send a wipe command to SMuFF
				self._setResponse(smuff_core.T_WIPING, True)
				self.SC.send_SMuFF_and_wait(smuff_core.WIPE)
				return

			# @SMuFF CUT
			if action and action == CUTFIL:
				# send a cut command to SMuFF
				self._setResponse(smuff_core.T_CUTTING, True)
				self.SC.send_SMuFF_and_wait(smuff_core.CUT)
				return

			# @SMuFF STATUS
			if action and action == STATUS:
				self._setResponse(self.SC.get_states(), False)
				return

			# @SMuFF UNJAM
			if action and action == UNJAM:
				# send a un-jam command to SMuFF
				self.SC.send_SMuFF_and_wait(smuff_core.UNJAM)
				self._setResponse(smuff_core.T_UNJAMMED, True)
				return

			# @SMuFF RESET
			if action and action == RESET:
				# send a reset command to SMuFF
				self.SC.send_SMuFF_and_wait(smuff_core.RESET)
				self._setResponse(smuff_core.T_RESET, False)
				return

			# @SMuFF UNLOAD
			if action and action == UNLOAD:
				# send a M701 command to SMuFF
				self.SC.send_SMuFF_and_wait(smuff_core.UNLOADFIL)
				self._setResponse(smuff_core.T_UNLOADING, False)
				return

			# @SMuFF RELOAD
			if action and action == RELOAD:
				# send a M700 command to SMuFF
				self.SC.send_SMuFF_and_wait(smuff_core.LOADFIL)
				self._setResponse(smuff_core.T_RELOADING, False)
				return

			# @SMuFF RESETAVG
			if action and action == RESETAVG:
				# reset tool change counters / average
				self.SC.reset_avg()
				return

	def extend_tool_sending(self, comm_instance, phase, cmd, cmd_type, gcode, subcode, tags, *args, **kwargs):

		if gcode and gcode.startswith(smuff_core.TOOL):
			# ignore default Tx commands
			return

		# check for the replaced tool change command
		if cmd and cmd.startswith(AT_SMUFF):
			action, v1, v2, v3 = self._split_cmd(cmd)
			self._log.debug("2>> Cmd: {0}  Action: {1}  Params: {2}; {3}; {4}".format(cmd, str(action), str(v1), str(v2), str(v3)))

			# @SMuFF T0...T99
			if action and action.startswith(smuff_core.TOOL):
				try:
					if self._printer.set_job_on_hold(True, False):
						self.SC.start_tc_timer()
						try:
							# store the new tool for later
							self.SC.pendingTool = str(action)
							# check if there's filament loaded
							if self.SC.feeder:
								self._log.debug("2>> calling script 'beforeToolChange'")
								# if so, send the OctoPrints default "Before Tool Change" script to the printer
								self._printer.script("beforeToolChange")
							else:
								self._log.debug("2>> calling SMuFF LOAD")
								# not loaded, nothing to retract, so send the tool change to the SMuFF
								self._printer.commands(AT_SMUFF + " " + LOAD)

						except UnknownScript as err:
							errmsg = "Script 'beforeToolChange' not found! (Error: {})".format(err)
							self._log.error(errmsg)
							self._setResponse(errmsg, True)

						finally:
							# Notice:
							# 	self._printer.set_job_on_hold(False)
							# must not be called here since the whole tool change procedure
							# isn't finished yet. Setting it now would unpause OctoPrint
							# and continue printing without filament!
							pass
				except RuntimeError as err:
					# might happen if the printer is offline
					errmsg = "Can't put printer on pause because: {})".format(err)
					self._setResponse(errmsg, True)
					self._log.error(errmsg)

			# @SMuFF LOAD
			if action and action == LOAD:
				try:
					continuePrint = False
					with self._printer.job_on_hold():
						try:
							self._log.debug("1>> LOAD: Feeder:  {0}, Pending: {1}, Current: {2}".format(str(self.SC.feeder), str(self.SC.pendingTool), str(self.SC.curTool)))

							autoload = self._settings.get_boolean(["autoload"])
							# send a tool change command to SMuFF
							res = self.SC.send_SMuFF_and_wait(self.SC.pendingTool + (smuff_core.AUTOLOAD if autoload else ""))
							# do we have the tool requested now?
							if str(res) == str(self.SC.pendingTool):
								self.SC.setTool()
								comm_instance._currentTool = self.SC.parse_tool_number(self.SC.curTool)
								# check if filament has been loaded
								if self.SC.loadState == 2 or self.SC.loadState == 3:
									self._log.debug("2>> calling script 'afterToolChange'")
									# send the default OctoPrint "After Tool Change" script to the printer
									self._printer.script("afterToolChange")
									continuePrint = True
								else:
									self._log.warning("Tool load failed, retrying ({0} is in feeder state: {1})".format(res, self.SC.loadState))
							else:
								# not the result we expected, do it all again
								self._log.warning("Tool change failed, retrying (<{0}> not <{1}>)".format(res, self.SC.pendingTool))

						except UnknownScript as err:
							# shouldn't happen at all, since we're using default OctoPrint scripts
							# but you never know
							errmsg = "Script 'afterToolChange' not found! (Error: {})".format(err)
							self._log.error(errmsg)
							self._setResponse(errmsg, True)

						finally:
							duration = self.SC.stop_tc_timer()
							self._setResponse("Toolchange took {:4.2f} secs.".format(duration), True)
							if continuePrint:
								try:
									# now is the time to release the hold and continue printing
									self._printer.set_job_on_hold(False)
								except RuntimeError as err:
									# might happen if the printer is offline
									errmsg = "Can't unpause printer because: {})".format(err)
									self._setResponse(errmsg, True)
									self._log.error(errmsg)
				except RuntimeError as err:
					# might happen if the printer is offline
					errmsg = "Can't put printer on pause because: {})".format(err)
					self._setResponse(errmsg, True)
					self._log.error(errmsg)

	def extend_script_variables(self, comm_instance, script_type, script_name, *args, **kwargs):
		return None

	def extend_gcode_received(self, comm_instance, line, *args, **kwargs):
		# Refresh the current tool in OctoPrint on each command coming from the printer - just in case
		# This is needed because OctoPrint manages the current tool itself and it might try to swap
		# tools because of the wrong information.
		comm_instance._currentTool = self.SC.parse_tool_number(self.SC.curTool)
		# don't process any of the GCodes received
		return line

	#
	# Send a response (text) to the OctoPrint Terminal
	#
	def _setResponse(self, response, addPrefix = False):
		if response != "":
			if hasattr(self, "_plugin_manager"):
				self._plugin_manager.send_plugin_message(self._identifier, {'terminal':  response })


#------------------------------------------------------------------------------
# Helper functions
#------------------------------------------------------------------------------

def get_pi_model(_log):
	# get Pi model from cpuinfo
	model = 4
	try:
		f = open("/proc/cpuinfo","r")
		for line in f:
			if line.startswith("Model"):
				if line.find("Pi 4") == -1:
					model = 3
				_log.info("Running on Pi {}".format(model))
		f.close()
	except:
		_log.info("Can't read cpuinfo, assuming  Pi 3")
		model = 3
	return model

#------------------------------------------------------------------------------
# Main plugin functions
#------------------------------------------------------------------------------
__plugin_name__ 		= "SMuFF Plugin"
__plugin_pythoncompat__ = ">=3, <4"

def __plugin_load__():
	global __plugin_implementation__
	global __plugin_hooks__

	logger = logging.getLogger(LOGGER)
	__plugin_implementation__ = SmuffPlugin(logger)
	__plugin_hooks__ = {
		"octoprint.comm.protocol.gcode.received":		__plugin_implementation__.extend_gcode_received,
		"octoprint.comm.protocol.scripts": 				__plugin_implementation__.extend_script_variables,
		"octoprint.comm.protocol.gcode.sending": 		__plugin_implementation__.extend_tool_sending,
		"octoprint.comm.protocol.gcode.queuing": 		__plugin_implementation__.extend_tool_queuing,
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}

def __plugin_unload__():
	__plugin_implementation__.on_shutdown()

def __plugin_disabled():
	__plugin_implementation__.on_shutdown()

