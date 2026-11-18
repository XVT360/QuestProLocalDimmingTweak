#!/system/bin/sh
# UNCHECKED LOCAL BUILD: firmware/model/ABI/runtime-SHA install gates removed.
# The native runtime code still validates mapped memory before writing hooks.
ui_print "Quest Pro Local Dimming 0.5.0 UNCHECKED: installed disabled"
ui_print "Keep previous questpro_local_dimming module disabled."
if [ -d /data/adb/modules/questpro_local_dimming ] && [ ! -f /data/adb/modules/questpro_local_dimming/disable ]; then
  abort "Disable the legacy questpro_local_dimming module and reboot before installing."
fi
mkdir -p "$MODPATH/log"
set_perm_recursive "$MODPATH" 0 0 0755 0644
set_perm "$MODPATH/bin/ldctl" 0 0 0755
set_perm "$MODPATH/service.sh" 0 0 0755
set_perm "$MODPATH/action.sh" 0 0 0755
set_perm "$MODPATH/controller.sh" 0 0 0755
set_perm "$MODPATH/log" 0 0 0700
ui_print "Saved tuning survives updates; Hook and replacement require manual activation."
if [ ! -e /data/adb/questpro_local_dimming_030/settings.bin ]; then
  # Capture the working 0.4.0 properties before the first upgrade reboot.
  # save validates/copies data only; it never sets properties or live gates.
  if "$MODPATH/bin/ldctl" save >/dev/null 2>&1; then
    ui_print "Current sampler, LUT and bounded native debug values saved."
  else
    ui_print "Current tuning could not be captured. Apply and save from the controller after reboot."
  fi
fi
if [ -f "$MODPATH/QuestProLDControl.apk" ]; then
  if pm install -r "$MODPATH/QuestProLDControl.apk" >/dev/null 2>&1; then
    ui_print "Graphical controller installed on the headset."
  else
    if mkdir -p /sdcard/Download &&
       cp "$MODPATH/QuestProLDControl.apk" /sdcard/Download/QuestProLDControl.apk &&
       chmod 0644 /sdcard/Download/QuestProLDControl.apk; then
      ui_print "Controller APK copied to Download; install it once from the headset file browser."
      ui_print "If an older controller has a different signature, decide how to migrate it before uninstalling."
    else
      ui_print "Automatic APK installation failed. Install QuestProLDControl.apk from the module ZIP manually."
    fi
  fi
fi
