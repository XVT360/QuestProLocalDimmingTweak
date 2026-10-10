#!/system/bin/sh
MODDIR=${0%/*}
mkdir -p "$MODDIR/log"
chmod 0700 "$MODDIR/log" 2>/dev/null
printf 'sampler_lut 0.5.0 boot; delayed settings restore; no runtime restart\n' > "$MODDIR/log/boot.log"
# Run in the background so waiting for Singularity/root never blocks boot.
# Only bounded data restoration is authorized here; Runtime and all live
# activation gates remain under the user's manual control.
(
  attempt=0
  while [ "$attempt" -lt 60 ]; do
    attempt=$((attempt + 1))
    if [ -f "$MODDIR/disable" ] || [ -f "$MODDIR/remove" ] || [ -f "$MODDIR/update" ]; then
      echo restore_state=module_unavailable >> "$MODDIR/log/boot.log"
      exit 0
    fi
    if [ "$(getprop sys.boot_completed)" = 1 ] && [ "$(id -u)" = 0 ]; then
      sh "$MODDIR/controller.sh" restore >> "$MODDIR/log/boot.log" 2>&1
      result=$?
      case "$result" in
        0|2|3) exit 0 ;; # success, invalid file, or manual activation: no retry
      esac
    fi
    sleep 5
  done
  echo restore_state=timed_out >> "$MODDIR/log/boot.log"
) </dev/null >/dev/null 2>&1 &
exit 0
