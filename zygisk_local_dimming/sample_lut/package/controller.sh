#!/system/bin/sh
MODDIR=${0%/*}
LD="$MODDIR/bin/ldctl"
PREFIX=debug.oculus.localDimming.zl2.
LOG="$MODDIR/log/zygisk_trace.log"

fail() { echo "error=$1"; exit 1; }
[ "$(id -u)" = 0 ] || fail root_required
[ -x "$LD" ] || fail module_missing

runtime_pid() {
  runtime=$(pidof com.oculus.vrruntimeservice)
  case "$runtime" in ''|*[!0-9]*) return 1 ;; esac
  [ "$runtime" -gt 1 ] || return 1
  printf '%s' "$runtime"
}

require_module() {
  [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || fail module_disabled
  [ ! -f "$MODDIR/update" ] || fail module_update_pending
  if [ -d /data/adb/modules/questpro_local_dimming ] &&
     [ ! -f /data/adb/modules/questpro_local_dimming/disable ]; then
    fail legacy_module_enabled
  fi
}

case "$1" in
  status)
    printf 'version='; sed -n 's/^version=//p' "$MODDIR/module.prop"
    if [ -f "$MODDIR/disable" ] || [ -f "$MODDIR/remove" ]; then
      echo module_disabled=1
    else
      echo module_disabled=0
    fi
    if [ -f "$MODDIR/update" ]; then
      echo module_update_pending=1
    else
      echo module_update_pending=0
    fi
    "$LD" status || exit 1
    tail -n 20 "$MODDIR/log/boot.log" 2>/dev/null | grep '^restore_state=' | tail -n 1
    pid=$(runtime_pid) || pid=0
    echo "runtime_pid=$pid"
    tail -n 40 "$LOG" 2>/dev/null | grep "^status pid=$pid " | tail -n 1 || :
    ;;
  restore)
    require_module
    "$LD" restore
    ;;
  save)
    require_module
    "$LD" save
    ;;
  enable)
    require_module
    pid=$(runtime_pid) || fail runtime_not_running
    latest=$(tail -n 40 "$LOG" 2>/dev/null | grep "^status pid=$pid " | tail -n 1)
    case "$latest" in *' ready=1 '*) ;; *) fail hook_not_ready ;; esac
    "$LD" status | grep -q '^plan_valid=1$' || fail invalid_plan
    [ "$(runtime_pid)" = "$pid" ] || fail runtime_changed
    setprop "${PREFIX}bypass" 0 && setprop "${PREFIX}enable" 1 || {
      "$LD" disable
      fail enable_failed
    }
    echo enabled=1
    ;;
  disable)
    "$LD" disable || fail disable_failed
    setprop "${PREFIX}hook_mode" 0 || fail hook_disable_failed
    echo disabled=1
    ;;
  rollback)
    # Turn the live gates off before waiting for a serialized settings writer.
    "$LD" disable || fail disable_failed
    setprop "${PREFIX}hook_mode" 0 || fail hook_disable_failed
    "$LD" debug-reset || "$LD" reset-all || fail debug_rollback_failed
    echo rolled_back=1
    ;;
  prepare|recover)
    require_module
    pid=$(runtime_pid) || fail runtime_not_running
    "$LD" disable || fail disable_failed
    setprop "${PREFIX}hook_mode" 0 || fail hook_disable_failed
    if [ "$1" = prepare ]; then
      # Fallback if the boot worker could not run while root was unavailable.
      # All activation gates are still closed at this point.
      "$LD" restore || fail settings_restore_failed
    fi
    # Let the worker observe bypass before terminating a graphics process.
    sleep 1
    [ "$(runtime_pid)" = "$pid" ] || fail runtime_changed
    if [ "$1" = prepare ]; then
      setprop "${PREFIX}hook_mode" 1 || fail hook_enable_failed
    fi
    if ! kill -TERM "$pid"; then
      setprop "${PREFIX}hook_mode" 0
      fail restart_failed
    fi
    echo "restarting_pid=$pid"
    ;;
  *) fail unknown_command ;;
esac
