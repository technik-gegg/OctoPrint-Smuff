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
        // self.loginStateViewModel = parameters[0];
        self.settingsViewModel = parameters[0];
        self._settings = null;

        self.onBeforeBinding = function() {
            // Make plugin setting access a little more terse
            self._settings = self.settingsViewModel.settings.plugins.SMuFF;
            console.log("_settings initialized. FW-Info: {" + self._settings.firmware_info + "}");
        };

        self.onDataUpdaterPluginMessage = function(plugin, message) {
            if(plugin !== "SMuFF") {
                return;
            }
            console.log("DataUpdaterPluginMessage for: [" + plugin + "] message: " + message.type);
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
        elements: [ "#settings_plugin_SMuFF" ]
    });
});
