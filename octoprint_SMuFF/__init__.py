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
import re

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
SETPURGE 		= "SETPURGE"
RESETPURGE 		= "RESETPURGE"
PURGE 			= "PURGE"
LOG 			= "LOG"
FORCERESUME		= "FORCERESUME"

T_IGNORE_FORCERESUME = "Printer not pausing, FORCERESUME ignored"

class SmuffPlugin(octoprint.plugin.SettingsPlugin,
                  octoprint.plugin.AssetPlugin,
                  octoprint.plugin.TemplatePlugin,
				  octoprint.plugin.StartupPlugin,
				  octoprint.plugin.EventHandlerPlugin,
				  octoprint.plugin.ShutdownPlugin):

	def __init__(self, logger):
		self._log = logger
		self.SCA = smuff_core.SmuffCore(logger, IS_KLIPPER, self.smuffStatusCallbackA, self.smuffResponseCallbackA)
		self.SCB = smuff_core.SmuffCore(logger, IS_KLIPPER, self.smuffStatusCallbackB, self.smuffResponseCallbackB)
		self.activeInstance = "A"
		self._octoprintTool = ""
		self._purgeAmount = 0
		self._mustPurgeAfterChange = False
		self._reset()

	def _reset(self):
		pass

	def smuffStatusCallbackA(self, active):
		if hasattr(self, "_plugin_manager"):
			tool 	= self.SCA.curTool		if active else -1
			toolCount = self.SCA.toolCount	if active else -1
			feeder 	= self.SCA.feeder		if active else False
			feeder2	= self.SCA.feeder2		if active else False
			info 	= self.SCA.fwInfo		if active else ""
			conn	= self.SCA.isConnected	if active else False
			jammed 	= self.SCA.isJammed		if active else False
			self._plugin_manager.send_plugin_message(self._identifier, {'type': 'status', 'tool': tool, 'feeder': feeder, 'feeder2': feeder2, 'fw_info': info, 'conn': conn, 'jammed': jammed, 'toolCount': toolCount })
			if not self.SCA.isConnected:
				self._setResponse("Not connected", True, self.SCA)
		pass

	def smuffStatusCallbackB(self, active):
		if hasattr(self, "_plugin_manager"):
			if self._settings.get_boolean(["hasIDEX"]):
				toolB 	= self.SCB.curTool		if active else -1
				toolCountB = self.SCB.toolCount	if active else -1
				feederB = self.SCB.feeder		if active else False
				feeder2B= self.SCB.feeder2		if active else False
				infoB 	= self.SCB.fwInfo		if active else ""
				connB	= self.SCB.isConnected	if active else False
				jammedB = self.SCB.isJammed		if active else False
				self._plugin_manager.send_plugin_message(self._identifier, {'type': 'status', 'toolB': toolB, 'feederB': feederB, 'feeder2B': feeder2B, 'fw_infoB': infoB, 'connB': connB, 'jammedB': jammedB, 'toolCountB': toolCountB })
				if not self.SCB.isConnected:
					self._setResponse("Not connected", True, self.SCB)
		pass

	def smuffResponseCallbackA(self, message):
		self._setResponse(message, False, self.SCA)

	def smuffResponseCallbackB(self, message):
		self._setResponse(message, False, self.SCB)
	#------------------------------------------------------------------------------
	# OctoPrint plugin functions
	#------------------------------------------------------------------------------

	#
	# ShutdownPlugin mixin
	#
	def on_startup(self, host, port):
		self._log.info("Yeah... starting up...")

	def on_shutdown(self):
		self.SCA.close_serial()
		self.SCB.close_serial()
		self._log.debug("Booo... shutting down...")

	#
	# StartupPlugin mixin
	#
	def on_after_startup(self):
		self.SCA.serialPort 	= "/dev/{0}".format(self._settings.get(["tty"]))
		self.SCA.baudrate 		= self._settings.get_int(["baudrate"])
		self.SCA.cmdTimeout 	= self._settings.get_int(["timeout1"])
		self.SCA.tcTimeout 		= self._settings.get_int(["timeout2"])
		self.SCA.wdTimeout 		= self.SCA.tcTimeout * 2
		self.SCA.timeout 		= self.SCA.tcTimeout * 2
		self.SCA.connect_SMuFF()

		self.SCB.serialPort 	="/dev/{0}".format(self._settings.get(["ttyB"]))
		if self.SCB.serialPort and self._settings.get_boolean(["hasIDEX"]):
			self.SCB.baudrate 		= self._settings.get_int(["baudrateB"])
			self.SCB.cmdTimeout 	= self.SCA.cmdTimeout
			self.SCB.tcTimeout 		= self.SCA.tcTimeout
			self.SCB.wdTimeout 		= self.SCA.wdTimeout
			self.SCB.timeout 		= self.SCA.timeout
			self.SCB.connect_SMuFF()

	#
	# EventHandler mixin
	#
	def on_event(self, event, payload):
		#self._log.debug("Event: [" + event + ", {0}".format(payload) + "]")
		if event == Events.SHUTDOWN:
			self._log.debug("Shutting down, closing serial")
			self.SCA.close_serial()
			self.SCB.close_serial()

	#
	# SettingsPlugin mixin
	#
	def get_settings_version(self):
		return 3

	def get_settings_defaults(self):
		self._log.debug("SMuFF plugin loaded, getting defaults")
		params = dict(
			firmware_info	= "No data. Please check connection!",
			baudrate		= DEFAULT_BAUD,
			tty 			= "ttySMuFF",
			tool			= self.SCA.curTool,
			toolCount 		= self.SCA.toolCount,
			selector_end	= self.SCA.selector,
			revolver_end	= self.SCA.revolver,
			feeder_end		= self.SCA.feeder,
			feeder2_end		= self.SCA.feeder2,
			timeout1		= 30,
			timeout2		= 90,
			autoload 		= True,
			hasIDEX			= False,
			firmware_infoB	= "No data. Please check connection!",
			baudrateB		= DEFAULT_BAUD,
			ttyB 			= "",
			toolB			= self.SCB.curTool,
			toolCountB 		= self.SCB.toolCount,
			selector_endB	= self.SCB.selector,
			revolver_endB	= self.SCB.revolver,
			feeder_endB		= self.SCB.feeder,
			feeder2_endB	= self.SCB.feeder2,
			activeInstance 	= "A"
		)
		return  params

	def on_settings_migrate(self, target, current):
		if current == None or target < current:
			self._log.debug("Migrating old settings...")
			self._settings.save()


	def on_settings_save(self, data):
		self._log.debug("Settings->save: data {0}".format(data))
		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

		# did the settings change?
		if "baudrate" in data or "tty" in data:
			self.SCA.close_serial()
			self.SCA.serialPort 	= "/dev/{0}".format(self._settings.get(["tty"]))
			self.SCA.baudrate 		= self._settings.get_int(["baudrate"])
			# reconnect SMuFF A on the new port (with new baudrate)
			self.SCA.reconnect_SMuFF()

		if "baudrateB" in data or "ttyB" in data:
			if self._settings.get_boolean(["hasIDEX"]):
				self.SCB.close_serial()
				self.SCB.serialPort 	= "/dev/{0}".format(self._settings.get(["ttyB"]))
				self.SCB.baudrate 		= self._settings.get_int(["baudrateB"])
				# reconnect SMuFF B on the new port (with new baudrate)
				self.SCB.reconnect_SMuFF()
			else:
				self.SCB.close_serial()


	def get_template_configs(self):
		# self._log.debug("Settings-Template was requested")
		if self._settings.get_boolean(["hasIDEX"]):
			return [
				dict(type="settings", 	custom_bindings=True,  template="SMuFF_settings.jinja2"),
				dict(type="navbar", 	custom_bindings=True,  template="SMuFF-IDX_navbar.jinja2"),
				dict(type="tab", 		custom_bindings=True,  template="SMuFF-IDX_tab.jinja2", name="SMuFF")
			]
		else:
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
				param1 = tmp[2]
			if len(tmp) > 3:
				param2 = tmp[3]
			if len(tmp) > 4:
				param3 = tmp[4]
		return action, param1, param2, param3

	#
	# GCode hooks
	#
	def extend_tool_queuing(self, comm_instance, phase, cmd, cmd_type, gcode, subcode, tags, *args, **kwargs):
		#self._log.debug("Processing tool queuing: [ Cmd: {0}, Type: {1}, Tags: {2} ]".format(cmd, str(cmd_type), str(tags)))

		if gcode and gcode.startswith(smuff_core.TOOL):
			self._log.debug("OctoPrint current tool: {0}".format(comm_instance._currentTool))

			instance = self.SCA
			toolnew = -1
			tool = instance.parse_tool_number(cmd)
			toolcount = instance.toolCount
			self._log.debug("CMD: {0}; ToolCount [A]: {1}; New Tool: {2}".format(cmd, toolcount, tool))
			if tool == -1:
				return
			self._octoprintTool = cmd
			# is the tool required on the 2nd SMUFF?
			if tool >= toolcount:
				#if so, adjust instance and tool number
				instance = self.SCB
				toolnew = tool - toolcount
				self._log.debug("ToolCount [B]: {0}; RealTool on [B]: {1}".format(instance.toolCount, toolnew))
				cmd = "{0}{1}".format(smuff_core.TOOL, toolnew)
				self._log.debug("Using 2nd SMuFF, tool: {0} changed to {1}".format(tool, cmd))

			self.activeInstance = ("A" if instance == self.SCA else "B")

			# if the tool that's already loaded is addressed, ignore the filament change
			if cmd == instance.curTool and instance.feeder:
				self._log.info("Current tool {0} equals {1} -- no tool change needed".format(cmd, instance.curTool))
				self._setResponse("Tool already selected", True, instance)
				return
			instance.isAligned = False
			# replace the tool change command Tx with @SMuFF Tx
			if toolnew == -1:
				return [ AT_SMUFF + " " + cmd ]
			else:
				return [ AT_SMUFF + "2 " + cmd ]

		# handle SMuFF pseudo GCodes
		if cmd and cmd.startswith(AT_SMUFF):
			action, v1, v2, v3 = self._split_cmd(cmd)
			self._log.debug("QUEUE>> Cmd: {0}  Action: {1}  Params: {2}; {3}; {4}".format(cmd, str(action), str(v1), str(v2), str(v3)))

			instance = self.SCA
			if cmd.startswith(AT_SMUFF+"2"):		# command is @SMUFF2, handle 2nd device
				instance = self.SCB

			# @SMuFF MOTORS
			if action and action == MOTORS:
				# send a servo command to SMuFF
				instance.send_SMuFF_and_wait(smuff_core.MOTORSOFF)
				self._setResponse(smuff_core.T_MOTORS_OFF, True, instance)
				return

			# @SMuFF FAN
			if action and action == FAN:
				# send a fan command to SMuFF
				instance.send_SMuFF_and_wait(smuff_core.FAN_ON if v1 == 1 else smuff_core.FAN_OFF)
				self._setResponse(smuff_core.T_FAN.format("ON" if v1 == 1 else "OFF"), True, instance)
				return

			# @SMuFF DEBUG
			if action and action == DEBUG:
				# toggle debug state
				instance.dumpRawData = not instance.dumpRawData
				self._setResponse(smuff_core.T_DUMP_RAW.format("ON" if instance.dumpRawData else "OFF"), True, instance)
				return

			# @SMuFF SERVO
			if action and action == SERVO:
				# send a servo command to SMuFF
				instance.send_SMuFF_and_wait(smuff_core.SETSERVO.format(str(v1), str(v2)))
				self._setResponse(smuff_core.T_POSITIONING.format(v1, v2), True, instance)
				return

			# @SMuFF SERVOOPEN
			if action and action == SERVOOPEN:
				# send a servo open command to SMuFF
				self._setResponse(smuff_core.T_OPENING_LID, True, instance)
				instance.send_SMuFF_and_wait(smuff_core.LIDOPEN)
				return

			# @SMuFF SERVOCLOSE
			if action and action == SERVOCLOSE:
				# send a servo close command to SMuFF
				self._setResponse(smuff_core.T_CLOSING_LID, True, instance)
				instance.send_SMuFF_and_wait(smuff_core.LIDCLOSE)
				return

			# @SMuFF CUT
			if action and action == CUTFIL:
				# send a cut command to SMuFF
				self._setResponse(smuff_core.T_CUTTING, True, instance)
				instance.send_SMuFF_and_wait(smuff_core.CUT)
				return

			# @SMuFF STATUS
			if action and action == STATUS:
				self._setResponse(instance.get_states(), False, instance)
				return

			# @SMuFF UNJAM
			if action and action == UNJAM:
				# send a un-jam command to SMuFF
				instance.send_SMuFF_and_wait(smuff_core.UNJAM)
				self._setResponse(smuff_core.T_UNJAMMED, True, instance)
				return

			# @SMuFF RESET
			if action and action == RESET:
				# send a reset command to SMuFF
				instance.send_SMuFF_and_wait(smuff_core.RESET)
				self._setResponse(smuff_core.T_RESET, False, instance)
				return

			# @SMuFF UNLOAD
			if action and action == UNLOAD:
				# send a M701 command to SMuFF
				instance.send_SMuFF_and_wait(smuff_core.UNLOADFIL)
				self._setResponse(smuff_core.T_UNLOADING, False, instance)
				return

			# @SMuFF RELOAD
			if action and action == RELOAD:
				# send a M700 command to SMuFF
				instance.send_SMuFF_and_wait(smuff_core.LOADFIL)
				self._setResponse(smuff_core.T_RELOADING, False, instance)
				return

			# @SMuFF RESETAVG
			if action and action == RESETAVG:
				# reset tool change counters / average
				instance.reset_avg()
				self._setResponse(smuff_core.T_RESETAVG, False, instance)
				return

			# @SMuFF SETPURGE
			if action and action == SETPURGE:
				# store the amount for later in PURGE
				self._purgeAmount = v1
				self._mustPurgeAfterChange = True
				self._setResponse(smuff_core.T_SET_PURGE.format(str(self._purgeAmount)), True, instance)
				return

			# @SMuFF RESETPURGE
			if action and action == RESETPURGE:
				# reset purge flag
				self._purgeAmount = 0
				self._mustPurgeAfterChange = False
				self._setResponse(smuff_core.T_RESET_PURGE, True, instance)
				return

			# @SMuFF PURGE
			if action and action == PURGE:
				# the real purge command
				gcode = smuff_core.EXTRUDE.format(self._purgeAmount, v1)
				self._setResponse(smuff_core.T_PURGING.format(str(self._purgeAmount), v1), True, instance)
				self._purgeAmount = 0
				self._mustPurgeAfterChange = False
				return gcode

			# @SMuFF LOG
			if action and action == LOG:
				self._log.debug(str(v1))
				return

			# @SMuFF FORCERESUME
			if action and action == FORCERESUME:
				self._log.debug("Force Resume requested")
				return

	def extend_tool_sending(self, comm_instance, phase, cmd, cmd_type, gcode, subcode, tags, *args, **kwargs):

		if gcode and gcode.startswith(smuff_core.TOOL):
			# ignore default Tx commands
			return

		# check for the replaced tool change command
		if cmd and cmd.startswith(AT_SMUFF):
			action, v1, v2, v3 = self._split_cmd(cmd)
			self._log.debug("SEND>> Cmd: {0}  Action: {1}  Params: {2}; {3}; {4}".format(cmd, str(action), str(v1), str(v2), str(v3)))

			instance = self.SCA
			if cmd.startswith(AT_SMUFF+"2"):		# command is @SMUFF2, handle 2nd device
				instance = self.SCB
				self.activeInstance ="B"

			if self.activeInstance == "B":
				instance = self.SCB
				self._log.debug("Switched instance to [B]...")

			# @SMuFF WIPE
			if action and action == WIPENOZZLE:
				# send a wipe command to SMuFF
				self._setResponse(smuff_core.T_WIPING, True, instance)
				instance.send_SMuFF_and_wait(smuff_core.WIPE)
				return

			# @SMuFF FORCERESUME
			if action and action == FORCERESUME:
				if self._printer.is_pausing():
					self._log.debug("SMuFF load-state: {0}".format(instance.loadState))
					instance.stop_tc_timer()
					# send the default OctoPrint "After Tool Change" script to the printer
					self._printer.script("afterToolChange")
					continuePrint = True
					self._printer.set_job_on_hold(False)
				else:
					self._setResponse(T_IGNORE_FORCERESUME, True, instance)
					self._log.info(T_IGNORE_FORCERESUME)
				return

			# @SMuFF T0...T99
			if action and action.startswith(smuff_core.TOOL):
				try:
					if self._printer.set_job_on_hold(True, False):
						try:
							# determine if the current tool is to be incremented or decremented
							# in order to achieve an automatic tool swap on filament runout
							# in junction with a decent filament runout plugin.
							# A "@SMUFF T++" command will use the next tool, a "@SMUFF T--" the previous
							if action == "T++" or action == "T--":
								try:
									actTool = instance.get_active_tool()
									maxTools = instance.toolCount
									# on "++" increment the current tool number
									if action[1:] == "++":
										if actTool+1 == maxTools:
											# use tool 0 if the active tool is the last one available
											action = smuff_core.TOOL + "0"
										else:
											action = smuff_core.TOOL + str(actTool+1)
									# on "--" decrement the current tool number
									elif action[1:] == "--":
										if actTool > 0:
											action = smuff_core.TOOL + str(actTool-1)
										else:
											# use last tool to avoid an underrun
											action = smuff_core.TOOL + str(maxTools-1)
								except Exception as err:
									errmsg = "Can't determine next/previous tool number! (Error: {})".format(err)
									self._log.error(errmsg)
									self._setResponse(errmsg, True, instance)

							# store the new tool for later
							instance.pendingTool = str(action)
							# check if there's filament loaded
							if instance.feeder:
								self._log.debug("SEND>> calling script 'beforeToolChange'")
								# if so, send the OctoPrints default "Before Tool Change" script to the printer
								self._printer.script("beforeToolChange")
							else:
								# not loaded, nothing to retract, so send the tool change to the SMuFF
								if instance == self.SCA:
									self._log.debug("SEND>> calling SMuFF LOAD [A]")
									self._printer.commands(AT_SMUFF + " " + LOAD)
								else:
									self._log.debug("SEND>> calling SMuFF LOAD [B]")
									self._printer.commands(AT_SMUFF + "2 " + LOAD)

						except UnknownScript as err:
							errmsg = "Script 'beforeToolChange' not found! (Error: {})".format(err)
							self._log.error(errmsg)
							self._setResponse(errmsg, True, instance)

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
					self._setResponse(errmsg, True, instance)
					self._log.error(errmsg)

			# @SMuFF LOAD
			if action and action == LOAD:
				# no tool change needed if pending tool is -1
				if instance.pendingTool == -1 or (str(instance.pendingTool) == str(instance.curTool) and instance.feeder):
					self._log.debug("Tool already set, skipping @SMuFF LOAD request...")
					return

				try:
					continuePrint = False
					instance.start_tc_timer()

					with self._printer.job_on_hold():
						try:
							self._log.debug("SEND>> LOAD{3}: Feeder:  {0}, Pending: {1}, Current: {2}".format(str(instance.feeder), str(instance.pendingTool), str(instance.curTool), " [A]" if instance == self.SCA else " [B]"))

							autoload = self._settings.get_boolean(["autoload"])
							# send a tool change command to SMuFF
							res = instance.send_SMuFF_and_wait(str(instance.pendingTool) + (smuff_core.AUTOLOAD if autoload else ""))
							# make sure there's no garbage in the received string - filter for 'Tx' only, ignore the rest
							match = re.search(r'^T\d+', res)
							if match != None:
								res = match[0]
							# do we have the tool requested now?
							if str(res) == str(instance.pendingTool):
								instance.set_tool()
								comm_instance._currentTool = instance.parse_tool_number(self._octoprintTool)
								# check if filament has been loaded
								if instance.loadState == 2 or instance.loadState == 3:
									self._log.debug("SEND>> calling script 'afterToolChange'")
									# send the default OctoPrint "After Tool Change" script to the printer
									self._printer.script("afterToolChange")
									continuePrint = True
								else:
									self._log.warning("Tool load failed, retrying ({0} is in feeder state: {1})".format(res, instance.loadState))
							else:
								# not the result we expected, do it all again
								self._log.warning("Tool change failed, retrying (<{0}> not <{1}>)".format(res, instance.pendingTool))

						except UnknownScript as err:
							# shouldn't happen at all, since we're using default OctoPrint scripts
							# but you never know
							errmsg = "Script 'afterToolChange' not found! (Error: {})".format(err)
							self._log.error(errmsg)
							self._setResponse(errmsg, True, instance)

						finally:
							duration = instance.stop_tc_timer()
							self._setResponse("Tool change took {:4.2f} secs.".format(duration), True, instance)
							if continuePrint:
								try:
									# now is the time to release the hold and continue printing
									self._printer.set_job_on_hold(False)
								except RuntimeError as err:
									# might happen if the printer is offline
									errmsg = "Can't unpause printer because: {})".format(err)
									self._setResponse(errmsg, True, instance)
									self._log.error(errmsg)
				except RuntimeError as err:
					# might happen if the printer is offline
					errmsg = "Can't put printer on pause because: {})".format(err)
					self._setResponse(errmsg, True, instance)
					self._log.error(errmsg)

	def extend_script_variables(self, comm_instance, script_type, script_name, *args, **kwargs):
		self._log.debug("Script variable request for type='{0}' and script='{1}'".format(script_type, script_name))
		vars = dict(
			mustPurge=self._mustPurgeAfterChange,
			purgeAmount=self._purgeAmount
			)
		self._log.debug("Returning: mustPurge='{0}', purgeAmount='{1}'".format(vars["mustPurge"], vars["purgeAmount"]))
		return None, None, vars

	def extend_gcode_received(self, comm_instance, line, *args, **kwargs):
		# Refresh the current tool in OctoPrint on each command coming from the printer - just in case
		# This is needed because OctoPrint manages the current tool itself and it might try to swap
		# tools because of the wrong information.
		if self._octoprintTool == -1:
			comm_instance._currentTool = self.SCA.parse_tool_number(self.SCA.curTool)
		else:
			comm_instance._currentTool = self.SCA.parse_tool_number(self._octoprintTool)
		# don't process any of the GCodes received further
		return line

	#
	# Send a response (text) to the OctoPrint Terminal
	#
	def _setResponse(self, response, addPrefix = False, instance = None):
		fromInst = ""
		if self._settings.get_boolean(["hasIDEX"]) and not instance == None:
			fromInst = " [ A ]  " if instance == self.SCA else " [ B ]  "
		if response != "":
			if hasattr(self, "_plugin_manager"):
				self._plugin_manager.send_plugin_message(self._identifier, {'terminal': fromInst + response })


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

