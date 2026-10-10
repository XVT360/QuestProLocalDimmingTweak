#!/system/bin/sh
if [ "$(getprop ro.product.device)" != seacliff ]; then
  abort "Unsupported headset: this module requires Quest Pro (seacliff)."
fi
case "$(getprop ro.product.cpu.abilist)" in
  *arm64-v8a*) ;;
  *) abort "Unsupported CPU: this module requires ARM64." ;;
esac
# Inspect the installed runtime APKs; never use an author's device serial,
# build-directory path or fixed PID. Magisk provides BusyBox unzip/sha256sum.
# com.oculus.vrruntimeservice is the process name, not the APK package name.
runtime_paths=$(pm path com.oculus.systemdriver 2>/dev/null)
compatible=0
while IFS= read -r line; do
  case "$line" in
    package:*)
      runtime_apk=${line#package:}
      runtime_hash=$(unzip -p "$runtime_apk" lib/arm64-v8a/libvrruntimeservice.so 2>/dev/null | sha256sum)
      runtime_hash=${runtime_hash%% *}
      if [ "$runtime_hash" = 0ffc0216e3904307d8504e4080c4481db2d29030d4bdccfcef462e3809846b11 ]; then
        compatible=1
        break
      fi
      ;;
  esac
done <<EOF
$runtime_paths
EOF
if [ "$compatible" != 1 ]; then
  abort "Unsupported or unreadable Runtime image. Installation stopped; firmware checks are required."
fi
ui_print "Quest Pro Sampler/LUT 0.5.0: installed disabled"
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
