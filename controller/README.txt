Quest Pro LD Control 0.5.0 is a separate Android controller for
questpro_local_dimming_030.

The Magisk installer attempts to install the APK. If that fails, install the
copy in /sdcard/Download once. Grant it root in Magisk, and open it from the
module action button or headset app list after later reboots.
Opening the app only reads status. Runtime sampler, blend weight, saturation
threshold (1..255), and gamma (0.1..8) can be adjusted without a restart.
Live apply and save commits slider changes on release; numeric inputs and
steppers are supported. Turn it off to edit before Apply and save.

After a reboot, wait for Singularity to restore root. Use Prepare Hook and
restart Runtime, confirm the VD disconnect, and wait for Hook ready. This
deliberate action first disables replacement, then sets hook_mode=1 and sends
TERM to the single verified Runtime PID. Replacement stays off until the user
enables it. No automatic root, restart, hook or replacement activation is performed.
Closing the replacement switch sets enable=0, bypass=1 and hook_mode=0. Existing bridges stay
mapped in native passthrough. Recover native and restart Runtime removes the
bridge by starting a new process with hook_mode=0; it requires confirmation.
Sampler and LUT reset commands do not change native debug parameters.

Native debug controls: Dilate X 0..8 (default 1), Dilate Y 0..15 (default 2),
Gaussian 0..9 (default 3), smooth on/off (default on), and smooth.weight
0..0.30 (default and ceiling 0.30). The exact binary32 ceiling is 0x3e99999a.
Gaussian 5..9 optical effects are unverified. Lower weights retain more history;
0 preserves history indefinitely while smoothing is enabled.

Each successful apply/reset saves sampler, blend weight, actual LUT bytes,
known curve metadata and debug values in root-only
/data/adb/questpro_local_dimming_030/settings.bin. Storage survives module
updates. Native debug parameters affect the original pipeline even when
replacement is off. Saved sampler/LUT plans still require manual activation.
Opening the GUI only reads status. The background boot worker retries restore
for up to five minutes; Prepare does a final restore before restarting Runtime.
Save current running values adopts externally tuned properties without edits.
Emergency restore closes the gates first, restores/saves native debug defaults,
and repeats after an in-flight command. Valid sampler/LUT choices remain saved.
If the plan is invalid it resets all tuning. All parameters restore native and
save resets the sampler, LUT and debug; ordinary resets never activate/restart.
