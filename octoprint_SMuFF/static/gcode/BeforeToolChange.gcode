{# 
Execute this code only if the printer has configured more than one extruder to prevent any tool change attempts in a single extruder configuration
#}
{% printer_profile.extruder.count > 1 %}
{#
plugins.SMuFF.tool
last_position.t
#}

M83					; set extruder to relative mode (important)
G1 E-5 F12000		; retract 5 mm fast to avoid oozing
G91					; switch to relative positioning
G1 Z15 F8000		; lift nozzle
G90					; switch back to absolute positioning
G1 X-25 Y160 F15000	; move to change position
G0 E-720 F6000		; Retract filament
M400				; wait for move to complete
G4 P500				; pause 500 ms 

; tool change will start here
{% endif %}