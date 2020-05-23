{# 
Execute this code only if the printer has configured more than one extruder to prevent any tool change attempts in a single extruder configuration
#}
{% printer_profile.extruder.count > 1 %}

G1 E50 F1500		; Extrude slowly from Selector into the bowden tube
G1 E600 F12000	; Extrude to hotend (fast)
G1 E55 F300		; Extrude down to nozzle (slow)
G1 E100 F240		; Purge out old filament
M400			; wait for move to finish
G1 S3			; pause 3 sec.

; continue printing
{% endif %}