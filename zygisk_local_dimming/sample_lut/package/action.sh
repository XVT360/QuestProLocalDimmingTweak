#!/system/bin/sh
echo "Opening Quest Pro Local Dimming controls"
if pm path com.questpro.ldcontrol >/dev/null 2>&1; then
  am start -n com.questpro.ldcontrol/.MainActivity
  result=$?
  if [ "$result" -eq 0 ]; then
    echo "Controller launched. Use Emergency restore for immediate rollback."
  else
    echo "Controller launch failed. Open QuestPro LD Control from the headset app list."
  fi
else
  echo "Controller app is not installed. Install /sdcard/Download/QuestProLDControl.apk once."
  echo "Then reopen this module action or launch QuestPro LD Control from the app list."
fi
