/*
 * View model for OctoPrint-Smuff
 *
 * Author: Technik Gegg
 * License: AGPLv3
 */
$(function() {
    function SmuffViewModel(parameters) {
        var self = this;

        // assign the injected parameters, e.g.:
        self.settingsViewModel = parameters[0];
        //console.log("SMuFF ViewModel params: " + self.settingsViewModel);
        self._settings = null;
        self._isJammed = false;

        self.feederJammed = ko.pureComputed(function(){
            return self._isJammed ? "btn-danger" : "btn-primary";
        });

        self.onBeforeBinding = function() {
            self._settings = self.settingsViewModel.settings.plugins.SMuFF;
            //console.log("_settings initialized. FW-Info: {" + self._settings.firmware_info() + "}");
        };

        self.send_pgcode = function(gcode) {
            // console.log('Sending SMuFF pseudo GCode: ' + gcode);
            if($('#SMuFF-InstanceA').is(':checked'))
                OctoPrint.control.sendGcode("@SMuFF " + gcode);
            else
                OctoPrint.control.sendGcode("@SMuFF2 " + gcode);
        };

        self.get_status = function() {
            // console.log(" get_status clicked: ");
            self.send_pgcode("STATUS");
        };

        self.set_debug = function() {
            // console.log(" set_debug clicked: ");
            self.send_pgcode("DEBUG");
        };

        self.do_wipe = function() {
            // console.log(" do_wipe clicked: ");
            self.send_pgcode("WIPE");
        };

        self.do_cut = function() {
            // console.log(" do_cut clicked: ");
            self.send_pgcode("CUT");
        };

        self.do_lid_open = function() {
            // console.log(" lid_open clicked: ");
            self.send_pgcode("SERVOOPEN");
        };

        self.do_lid_close = function() {
            // console.log(" lid_close clicked: ");
            self.send_pgcode("SERVOCLOSE");
        };

        self.do_motors_off = function() {
            // console.log(" motors_off clicked: ");
            self.send_pgcode("MOTORS");
        };

        self.do_unjam = function() {
            // console.log(" do_unjam clicked: ");
            self.send_pgcode("UNJAM");
        };

        self.do_reset_stats = function() {
            // console.log(" do_reset_stats clicked: ");
            self.send_pgcode("RESETAVG");
        };

        self.do_reset = function() {
            // console.log(" do_reset clicked: ");
            self.send_pgcode("RESET");
        };

        self.onDataUpdaterPluginMessage = function(plugin, message) {
            if(plugin !== "SMuFF") {
                return;
            }
            if(message.tool != null) {
                // console.log(" tool: " + message.tool);
                if(message.tool == '-1')
                    message.tool = 'T--'
                $('#SMuFF_setting_tool').text(message.tool);
                $('#SMuFF_navbar_tool').text(message.tool);
            }
            if(message.toolCount != null) {
                $('#SMuFF_tool_count').text(message.toolCount);
            }
            if(message.feeder != null) {
                // console.log(" feeder: " + message.feeder);
                var _cls = message.feeder ? "fa fa-check-circle" : "fa fa-times-circle";
                $('#SMuFF_setting_feeder').prop('class', _cls);
                $('#SMuFF_navbar_feeder').prop('class', _cls);
            }
            if(message.feeder2 != null) {
                // console.log(" feeder2: " + message.feeder2);
                var _cls = message.feeder2 ? "fa fa-check-circle" : "fa fa-times-circle";
                $('#SMuFF_setting_feeder2').prop('class', _cls);
                $('#SMuFF_navbar_feeder2').prop('class', _cls);
            }
            if(message.fw_info != null) {
                // console.log(" fw info: " + message.fw_info);
                $('#SMuFF_setting_firmware').text(message.fw_info);
            }
            if(message.conn != null) {
                // console.log(" conn: " + message.conn);
                $('#SMuFF_navbar_item').removeClass('navbar-item-conn navbar-item-disc navbar-item-jammed');
                $('#SMuFF_navbar_item').addClass(message.conn ? 'navbar-item-conn' :'navbar-item-disc');
            }
            if(message.jammed != null) {
                // console.log(" jammed: " + message.jammed);
                self._isJammed = message.jammed;
                $('#SMuFF_navbar_item').removeClass('navbar-item-conn navbar-item-disc navbar-item-jammed');
                $('#SMuFF_navbar_item').addClass(self._isJammed ? 'navbar-item-jammed' :'navbar-item-conn');
                $('#smuff-btn-unjam').removeClass('btn-danger btn-primary');
                $('#smuff-btn-unjam').addClass(self._isJammed ? 'btn-danger' :'btn-primary');
            }
            if(message.toolB != null) {
                // console.log(" tool B: " + message.toolB);
                if(message.toolB == '-1')
                    message.toolB = 'T--'
                $('#SMuFF2_setting_tool').text(message.toolB);
                $('#SMuFF2_navbar_tool').text(message.toolB);
            }
            if(message.toolCountB != null) {
                $('#SMuFF2_tool_count').text(message.toolCountB);
            }
            if(message.feederB != null) {
                // console.log(" feeder B: " + message.feederB);
                var _cls = message.feederB ? "fa fa-check-circle" : "fa fa-times-circle";
                $('#SMuFF2_setting_feeder').prop('class', _cls);
                $('#SMuFF2_navbar_feeder').prop('class', _cls);
            }
            if(message.feeder2B != null) {
                // console.log(" feeder2 B: " + message.feeder2B);
                var _cls = message.feeder2B ? "fa fa-check-circle" : "fa fa-times-circle";
                $('#SMuFF2_setting_feeder2').prop('class', _cls);
                $('#SMuFF2_navbar_feeder2').prop('class', _cls);
            }
            if(message.fw_infoB != null) {
                // console.log(" fw info B: " + message.fw_infoB);
                $('#SMuFF2_setting_firmware').text(message.fw_infoB);
            }
            if(message.connB != null) {
                // console.log(" conn B: " + message.connB);
                $('#SMuFF2_navbar_item').removeClass('navbar-item-conn navbar-item-disc navbar-item-jammed');
                $('#SMuFF2_navbar_item').addClass(message.connB ? 'navbar-item-conn' :'navbar-item-disc');
            }
            if(message.jammedB != null) {
                // console.log(" jammed B: " + message.jammedB);
                self._isJammedB = message.jammedB;
                $('#SMuFF2_navbar_item').removeClass('navbar-item-conn navbar-item-disc navbar-item-jammed');
                $('#SMuFF2_navbar_item').addClass(self._isJammedB ? 'navbar-item-jammed' :'navbar-item-conn');
                $('#smuff2-btn-unjam').removeClass('btn-danger btn-primary');
                $('#smuff2-btn-unjam').addClass(self._isJammedB ? 'btn-danger' :'btn-primary');
            }
            if(message.terminal != null) {
                // console.log(" output: " + message.terminal);
                $('#SMuFF-output').append('<span class="smuff-msg">'+message.terminal+'</span>');
                $('#SMuFF-output').scrollTop($('#SMuFF-output')[0].scrollHeight); // auto scroll to end
            }
        };

    }

    /* view model class, parameters for constructor, container to bind to
     * Please see http://docs.octoprint.org/en/master/plugins/viewmodels.html#registering-custom-viewmodels for more details
     * and a full list of the available options.
     */
    OCTOPRINT_VIEWMODELS.push({
        construct: SmuffViewModel,
        // ViewModels your plugin depends on, e.g. loginStateViewModel, settingsViewModel, ...
        dependencies: [ "settingsViewModel" ],
        // Elements to bind to, e.g. #settings_plugin_SMuFF, #tab_plugin_SMuFF, ...
        elements: [ "#settings_plugin_SMuFF", "#navbar_plugin_SMuFF", "#tab_plugin_SMuFF" ]
    });
});
