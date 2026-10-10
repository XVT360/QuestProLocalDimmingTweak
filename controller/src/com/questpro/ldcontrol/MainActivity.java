package com.questpro.ldcontrol;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Only the confirmed Runtime action restarts the process; launch is read-only. */
public final class MainActivity extends Activity {
    private static final String MOD = "/data/adb/modules/questpro_local_dimming_030";
    private static final String LD = MOD + "/bin/ldctl";
    private static final String HELPER = "sh " + MOD + "/controller.sh";
    private static final int BG = Color.rgb(21, 23, 26);
    private static final int TEXT = Color.rgb(236, 239, 242);
    private static final int MUTED = Color.rgb(170, 177, 185);
    private static final int ACCENT = Color.rgb(79, 190, 158);
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final ExecutorService emergencyIo = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private final List<View> controls = new ArrayList<>();
    private ControllerState state;
    private TextView connection;
    private TextView counters;
    private TextView message;
    private TextView savedStatus;
    private TextView debugStatus;
    private Switch enable;
    private CheckBox live;
    private RadioGroup sampler;
    private final int[] samplerIds = new int[4];
    private Button prepare;
    private Button recover;
    private NumericControl blend;
    private NumericControl threshold;
    private NumericControl gamma;
    private NumericControl dilateX;
    private NumericControl dilateY;
    private NumericControl gaussian;
    private NumericControl smoothWeight;
    private Switch smooth;
    private boolean smoothDirty;
    private boolean updating;
    private boolean resumed;
    private boolean busy;
    private boolean reading;
    private boolean rollingBack;
    private boolean destroyed;
    private int generation;

    private final Runnable poll = new Runnable() {
        @Override public void run() {
            if (!resumed || destroyed) return;
            refresh();
            main.postDelayed(this, 2000);
        }
    };

    @Override protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        setContentView(buildUi());
        updateAvailability();
    }

    @Override protected void onResume() {
        super.onResume();
        resumed = true;
        main.removeCallbacks(poll);
        main.post(poll);
    }

    @Override protected void onPause() {
        resumed = false;
        main.removeCallbacks(poll);
        super.onPause();
    }

    @Override protected void onDestroy() {
        destroyed = true;
        main.removeCallbacks(poll);
        // Complete queued rollback even if the activity is closed.
        io.shutdown();
        emergencyIo.shutdown();
        super.onDestroy();
    }

    private View buildUi() {
        LinearLayout page = column();
        page.setBackgroundColor(BG);
        page.setPadding(dp(16), dp(8), dp(16), 0);
        LinearLayout toolbar = row();
        TextView title = text("Quest Pro LD Control", 19, TEXT);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        title.setMaxLines(1);
        title.setAutoSizeTextTypeUniformWithConfiguration(13, 19, 1, android.util.TypedValue.COMPLEX_UNIT_SP);
        toolbar.addView(title, new LinearLayout.LayoutParams(0, dp(52), 1));
        ImageButton refresh = new ImageButton(this);
        refresh.setImageResource(android.R.drawable.ic_popup_sync);
        refresh.setImageTintList(ColorStateList.valueOf(TEXT));
        refresh.setBackgroundColor(Color.TRANSPARENT);
        refresh.setContentDescription("Refresh status");
        refresh.setTooltipText(refresh.getContentDescription());
        refresh.setOnClickListener(v -> refresh());
        toolbar.addView(refresh, size(48, 48));
        page.addView(toolbar);
        connection = text("Reading root status", 14, MUTED);
        connection.setMaxLines(3);
        connection.setEllipsize(TextUtils.TruncateAt.END);
        page.addView(connection, new LinearLayout.LayoutParams(-1, -2));
        counters = text("PID --   Samples --   LUT --   Rejected --", 12, MUTED);
        counters.setTypeface(Typeface.MONOSPACE);
        counters.setMaxLines(3);
        counters.setEllipsize(TextUtils.TruncateAt.END);
        page.addView(counters, size(-1, 64));
        LinearLayout safety = row();
        enable = new Switch(this);
        enable.setText("Enable replacement");
        enable.setTextColor(TEXT);
        enable.setTextSize(15);
        enable.setOnCheckedChangeListener((button, checked) -> {
            if (updating) return;
            if (!checked) { emergency(false); return; }
            runCommand(HELPER + " enable", "Replacement enabled", () -> { });
        });
        safety.addView(enable, new LinearLayout.LayoutParams(0, dp(56), 1));
        Button stop = button("Emergency restore", android.R.drawable.ic_menu_close_clear_cancel, v -> emergency(true));
        stop.setTextColor(Color.rgb(255, 191, 180));
        safety.addView(stop, size(172, 64));
        page.addView(safety);
        message = text("", 13, ACCENT);
        message.setMaxLines(3);
        message.setEllipsize(TextUtils.TruncateAt.END);
        page.addView(message, new LinearLayout.LayoutParams(-1, -2));
        ScrollView scroll = new ScrollView(this);
        LinearLayout content = column();
        content.setPadding(0, 0, 0, dp(16));
        scroll.addView(content);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));

        LinearLayout liveRow = row();
        live = new CheckBox(this);
        live.setText("Apply and save live");
        live.setTextColor(TEXT);
        live.setTextSize(14);
        live.setChecked(true);
        liveRow.addView(live, new LinearLayout.LayoutParams(0, dp(48), 1));
        Button apply = button("Apply and save", android.R.drawable.ic_menu_save, v -> applyParameters());
        controls.add(apply);
        liveRow.addView(apply, size(160, 56));
        content.addView(liveRow);
        savedStatus = text("Reading saved settings", 13, MUTED);
        content.addView(savedStatus, new LinearLayout.LayoutParams(-1, -2));
        Button saveCurrent = button("Save current settings", android.R.drawable.ic_menu_save,
                v -> runCommand(HELPER + " save", "Current settings saved", () -> { }));
        controls.add(saveCurrent);
        content.addView(saveCurrent, size(-1, 48));
        TextView saveHelp = text("Tuning is restored after reboot. Prepare the Hook and enable replacement manually.", 13, MUTED);
        content.addView(saveHelp, new LinearLayout.LayoutParams(-1, -2));
        section(content, "Sampling");
        sampler = new RadioGroup(this);
        sampler.setOrientation(RadioGroup.HORIZONTAL);
        String[] names = {"Native", "Mean", "Peak", "Blend"};
        for (int i = 0; i < names.length; ++i) {
            RadioButton mode = new RadioButton(this);
            samplerIds[i] = View.generateViewId();
            mode.setId(samplerIds[i]);
            mode.setText(names[i]);
            mode.setTextColor(TEXT);
            mode.setTextSize(13);
            mode.setPadding(0, 0, 0, 0);
            mode.setButtonTintList(ColorStateList.valueOf(ACCENT));
            sampler.addView(mode, new RadioGroup.LayoutParams(0, dp(52), 1));
            controls.add(mode);
        }
        sampler.setOnCheckedChangeListener((group, id) -> {
            if (!updating && live.isChecked()) applySampler();
        });
        content.addView(sampler);
        blend = new NumericControl(this, "Peak weight", 0, 1, 0.01f, 0.25f, 2);
        blend.setCommit(() -> {
            if (live.isChecked()) {
                updating = true;
                sampler.check(samplerIds[3]);
                updating = false;
                applySampler();
            }
        });
        content.addView(blend);
        section(content, "LUT");
        Button nativeLut = button("Native LUT", android.R.drawable.ic_menu_revert,
                v -> runCommand(LD + " lut-native", "Native LUT restored and saved", () -> {
                    threshold.clearDraft(); gamma.clearDraft();
                }));
        controls.add(nativeLut);
        content.addView(nativeLut, size(-1, 48));
        threshold = new NumericControl(this, "Saturation threshold", 1, 255, 1, 20, 0);
        gamma = new NumericControl(this, "Gamma", 0.1f, 8, 0.01f, 1, 2);
        threshold.setCommit(() -> { if (live.isChecked()) applyCurve(); });
        gamma.setCommit(() -> { if (live.isChecked()) applyCurve(); });
        content.addView(threshold);
        content.addView(gamma);
        Button reset = button("Restore and save native sampling / LUT", android.R.drawable.ic_menu_revert,
                v -> runCommand(LD + " reset", "Native sampling / LUT restored and saved", () -> {
                    blend.clearDraft(); threshold.clearDraft(); gamma.clearDraft();
                }));
        controls.add(reset);
        content.addView(reset, size(-1, 52));
        section(content, "Native pipeline controls");
        debugStatus = text("Reading native pipeline settings", 13, MUTED);
        content.addView(debugStatus, new LinearLayout.LayoutParams(-1, -2));
        TextView debugHelp = text("These settings affect the native pipeline without enabling replacement or restarting Runtime.", 13, MUTED);
        content.addView(debugHelp, new LinearLayout.LayoutParams(-1, -2));
        dilateX = new NumericControl(this, "Dilation X (default 1)", 0, DebugParameters.MAX_X, 1, 1, 0);
        dilateY = new NumericControl(this, "Dilation Y (default 2)", 0, DebugParameters.MAX_Y, 1, 2, 0);
        gaussian = new NumericControl(this, "Gaussian (default 3)", 0, DebugParameters.MAX_GAUSSIAN, 1, 3, 0);
        dilateX.setCommit(() -> { if (live.isChecked()) applyDebug(); });
        dilateY.setCommit(() -> { if (live.isChecked()) applyDebug(); });
        gaussian.setCommit(() -> { if (live.isChecked()) applyDebug(); });
        content.addView(dilateX);
        content.addView(dilateY);
        content.addView(gaussian);
        LinearLayout gaussianQuick = row();
        for (int i = 0; i <= 4; ++i) {
            final int chosen = i;
            Button preset = button(String.valueOf(i), 0, v -> gaussian.choose(chosen));
            controls.add(preset);
            gaussianQuick.addView(preset, new LinearLayout.LayoutParams(0, dp(48), 1));
        }
        content.addView(gaussianQuick);
        TextView gaussianHelp = text("0: Gaussian off. 1: no additional spreading. 2 / 4 can noticeably change brightness. Values 5..9 are available but their headset effects are untested.", 12, MUTED);
        content.addView(gaussianHelp, new LinearLayout.LayoutParams(-1, -2));
        smooth = new Switch(this);
        smooth.setText("Native temporal smoothing (on by default)");
        smooth.setTextColor(TEXT);
        smooth.setTextSize(14);
        smooth.setOnCheckedChangeListener((button, checked) -> {
            if (updating) return;
            smoothDirty = true;
            if (live.isChecked()) applyDebug();
        });
        controls.add(smooth);
        content.addView(smooth, size(-1, 52));
        smoothWeight = new NumericControl(this, "Smoothing weight (maximum 0.30)", 0,
                DebugParameters.MAX_SMOOTH_WEIGHT, 0.01f, 0.3f, 2);
        smoothWeight.setCommit(() -> { if (live.isChecked()) applyDebug(); });
        content.addView(smoothWeight);
        TextView smoothHelp = text("Lower weights retain more history; 0 retains the previous value. The default and maximum are 0.30. Changing this setting has not been tested on the headset.", 12, MUTED);
        content.addView(smoothHelp, new LinearLayout.LayoutParams(-1, -2));
        Button debugReset = button("Restore and save native pipeline defaults", android.R.drawable.ic_menu_revert,
                v -> runCommand(LD + " debug-reset", "Native pipeline defaults saved", this::clearDebugDrafts));
        controls.add(debugReset);
        content.addView(debugReset, size(-1, 52));
        Button resetAll = button("Restore and save all native defaults", android.R.drawable.ic_menu_revert,
                v -> runCommand(LD + " reset-all", "All native defaults restored and saved", () -> {
                    blend.clearDraft(); threshold.clearDraft(); gamma.clearDraft(); clearDebugDrafts();
                }));
        controls.add(resetAll);
        content.addView(resetAll, size(-1, 52));
        section(content, "Runtime");
        prepare = button("Prepare Hook and restart Runtime", android.R.drawable.ic_popup_sync,
                v -> confirmRestart(true));
        recover = button("Recover native and restart Runtime", android.R.drawable.ic_menu_revert,
                v -> confirmRestart(false));
        content.addView(prepare, size(-1, 52));
        content.addView(recover, size(-1, 52));
        return page;
    }

    private void confirmRestart(boolean hook) {
        new AlertDialog.Builder(this)
                .setTitle(hook ? "Prepare Hook" : "Recover native Runtime")
                .setMessage(hook ?
                        "Replacement will be disabled before Runtime restarts. Virtual Desktop will disconnect and the display may briefly go blank. The Hook starts in native passthrough; enable replacement manually when ready." :
                        "Replacement and the Hook will be disabled before Runtime restarts. Virtual Desktop will disconnect and the display may briefly go blank.")
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Restart Runtime", (dialog, which) -> runCommand(
                        HELPER + (hook ? " prepare" : " recover"),
                        "Runtime restart requested; waiting for status", () -> {
                            state = null;
                            connection.setText("Waiting for Runtime to restart");
                        }))
                .show();
    }

    private int selectedSampler() {
        for (int i = 0; i < samplerIds.length; ++i)
            if (sampler.getCheckedRadioButtonId() == samplerIds[i]) return i;
        return 0;
    }

    private String samplerCommand() {
        String[] modes = {"native", "mean", "peak", "blend"};
        int index = selectedSampler();
        return LD + " sampler " + modes[index] + (index == 3 ? " " + blend.argument() : "");
    }

    private void applySampler() {
        if (!blend.validateDraft()) return;
        runCommand(samplerCommand(), "Sampling updated and saved", () -> blend.clearDraft());
    }

    private void applyCurve() {
        if (!threshold.validateDraft() || !gamma.validateDraft()) return;
        runCommand(LD + " lut-curve " + threshold.argument() + " " + gamma.argument(),
                "LUT updated and saved", () -> { threshold.clearDraft(); gamma.clearDraft(); });
    }

    private boolean validDebugDraft() {
        return dilateX.validateDraft() && dilateY.validateDraft() && gaussian.validateDraft() && smoothWeight.validateDraft() &&
                DebugParameters.valid((int) dilateX.number(), (int) dilateY.number(), (int) gaussian.number(),
                        smooth.isChecked() ? 1 : 0, smoothWeight.number());
    }

    private String debugArguments() {
        return dilateX.argument() + " " + dilateY.argument() + " " + gaussian.argument() + " " +
                (smooth.isChecked() ? "1" : "0") + " " + smoothWeight.argument();
    }

    private void clearDebugDrafts() {
        dilateX.clearDraft(); dilateY.clearDraft(); gaussian.clearDraft(); smoothWeight.clearDraft(); smoothDirty = false;
    }

    private void applyDebug() {
        if (updating || !validDebugDraft()) return;
        runCommand(LD + " debug " + debugArguments(), "Native pipeline settings applied and saved", this::clearDebugDrafts);
    }

    private void applyParameters() {
        if (!blend.validateDraft() || !threshold.validateDraft() || !gamma.validateDraft() || !validDebugDraft()) return;
        boolean curve = threshold.dirty() || gamma.dirty();
        String[] modes = {"native", "mean", "peak", "blend"};
        String command = LD + " apply " + modes[selectedSampler()] + " " + blend.argument() + " " +
                (curve ? "curve " + threshold.argument() + " " + gamma.argument() : "keep") + " " + debugArguments();
        runCommand(command, "All tuning applied and saved", () -> {
            blend.clearDraft(); threshold.clearDraft(); gamma.clearDraft(); clearDebugDrafts();
        });
    }

    private void refresh() {
        if (destroyed || reading || busy || rollingBack) return;
        reading = true;
        int started = generation;
        io.execute(() -> {
            RootRunner.Result read = RootRunner.run(HELPER + " status");
            main.post(() -> {
                reading = false;
                if (destroyed || started != generation || busy || rollingBack) return;
                if (read.ok()) { state = new ControllerState(read.output); renderState(); }
                else {
                    state = null;
                    connection.setText("Root / module temporarily unavailable");
                    connection.setTextColor(Color.rgb(230, 179, 104));
                    counters.setText("Waiting for root access to become available");
                    message.setText(errorMessage(read));
                }
                updateAvailability();
            });
        });
    }

    private void renderState() {
        boolean ready = state.ready();
        String label = !state.usable() ? "Install the module and reboot" :
                ready ? (state.active() ? "Replacement active" : "Hook ready; native passthrough") :
                "Hook not ready; native pipeline active";
        connection.setText(label + "   " + state.value("version", ""));
        connection.setTextColor(ready ? ACCENT : MUTED);
        counters.setText(String.format(Locale.US, "PID %s   Config %s\nSamples %s   LUT %s\nRejected %s",
                state.value("runtime_pid", "--"), state.value("seq", "--"),
                state.frame.getOrDefault("sample_writes", "--"), state.frame.getOrDefault("lut_writes", "--"),
                state.frame.getOrDefault("rejected", "--")));
        updating = true;
        enable.setChecked(state.active());
        if (live.isChecked()) {
            int mode = state.integer("sampler", 0);
            if (mode >= 0 && mode < 4) sampler.check(samplerIds[mode]);
        } else if (sampler.getCheckedRadioButtonId() == -1) {
            sampler.check(samplerIds[Math.max(0, Math.min(3, state.integer("sampler", 0)))]);
        }
        updating = false;
        blend.sync(state.decimal("peak_weight", 0));
        threshold.sync(state.decimal("lut_threshold", 20));
        gamma.sync(state.decimal("lut_gamma", 1));
        updating = true;
        if (!smoothDirty) smooth.setChecked(state.integer("debug_smooth", 1) != 0);
        updating = false;
        dilateX.sync(state.integer("debug_dilate_x", 1));
        dilateY.sync(state.integer("debug_dilate_y", 2));
        gaussian.sync(state.integer("debug_gaussian", 3));
        smoothWeight.sync(state.decimal("debug_smooth_weight", 0.3f));
        savedStatus.setText(state.savedMatches() ? "All tuning saved; matches current settings" :
                state.saved() ? "Saved snapshot exists; current changes are unsaved" :
                state.integer("settings_saved", 0) == 1 ? "Saved snapshot is invalid; apply settings again" : "No saved snapshot; adjust or apply to save");
        debugStatus.setText("Current X=" + state.value("debug_dilate_x", "1") + "  Y=" + state.value("debug_dilate_y", "2") +
                "  Gaussian=" + state.value("debug_gaussian", "3") + "\nsmooth=" + state.value("debug_smooth", "1") +
                "  weight=" + String.format(Locale.US, "%.2f", state.decimal("debug_smooth_weight", 0.3f)) +
                (state.integer("debug_valid", 0) == 1 ? "" : " (out of range; restore defaults)"));
    }

    private void updateAvailability() {
        boolean available = state != null && state.usable() && !busy && !rollingBack;
        for (View control : controls) control.setEnabled(available);
        if (blend != null) {
            blend.setControlsEnabled(available);
            threshold.setControlsEnabled(available);
            gamma.setControlsEnabled(available);
            dilateX.setControlsEnabled(available);
            dilateY.setControlsEnabled(available);
            gaussian.setControlsEnabled(available);
            smoothWeight.setControlsEnabled(available);
        }
        if (enable != null) enable.setEnabled(!busy && !rollingBack && state != null &&
                (state.active() || state.canEnable()));
        if (prepare != null) {
            boolean running = available && state.integer("runtime_pid", 0) > 1;
            prepare.setEnabled(running && !state.ready());
            recover.setEnabled(running);
        }
    }

    private void runCommand(String command, String success, Runnable after) {
        if (destroyed || busy || rollingBack) return;
        busy = true;
        ++generation;
        message.setText("Applying settings");
        updateAvailability();
        int started = generation;
        io.execute(() -> {
            RootRunner.Result run = RootRunner.run(command);
            main.post(() -> {
                busy = false;
                if (destroyed || started != generation) return;
                if (run.ok()) { after.run(); message.setText(success); }
                else message.setText(errorMessage(run));
                updateAvailability();
                refresh();
            });
        });
    }

    private void emergency(boolean restoreDebug) {
        if (destroyed || rollingBack) return;
        rollingBack = true;
        ++generation;
        updating = true;
        enable.setChecked(false);
        updating = false;
        message.setText("Emergency restore in progress");
        updateAvailability();
        // Queue the second disable now, so closing the activity cannot drop it.
        String rollback = HELPER + (restoreDebug ? " rollback" : " disable");
        emergencyIo.execute(() -> RootRunner.run(rollback));
        io.execute(() -> {
            RootRunner.Result last = RootRunner.run(rollback);
            main.post(() -> {
                rollingBack = false;
                busy = false;
                if (destroyed) return;
                if (last.ok() && restoreDebug) clearDebugDrafts();
                message.setText(last.ok() ? (restoreDebug ? "Replacement disabled; native defaults restored and saved" : "Replacement disabled") : errorMessage(last));
                updateAvailability();
                refresh();
            });
        });
    }

    private String errorMessage(RootRunner.Result result) {
        String error = result.output.trim();
        return "Command failed (" + result.code + "): " +
                (error.isEmpty() ? "root permission denied or command timed out" : error.substring(0, Math.min(140, error.length())));
    }

    private void section(LinearLayout parent, String title) {
        View divider = new View(this);
        divider.setBackgroundColor(Color.rgb(57, 61, 66));
        LinearLayout.LayoutParams separator = new LinearLayout.LayoutParams(-1, dp(1));
        separator.setMargins(0, dp(12), 0, dp(10));
        parent.addView(divider, separator);
        TextView label = text(title, 16, TEXT);
        label.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        parent.addView(label, size(-1, 32));
    }

    private Button button(String label, int icon, View.OnClickListener click) {
        Button view = new Button(this);
        view.setText(label);
        view.setTextColor(TEXT);
        view.setTextSize(13);
        view.setAllCaps(false);
        view.setMaxLines(3);
        view.setAutoSizeTextTypeUniformWithConfiguration(10, 13, 1, android.util.TypedValue.COMPLEX_UNIT_SP);
        view.setMinimumWidth(0);
        view.setPadding(dp(8), 0, dp(8), 0);
        view.setCompoundDrawablesWithIntrinsicBounds(icon, 0, 0, 0);
        view.setCompoundDrawableTintList(ColorStateList.valueOf(MUTED));
        view.setCompoundDrawablePadding(dp(8));
        view.setOnClickListener(click);
        return view;
    }

    private LinearLayout column() {
        LinearLayout view = new LinearLayout(this);
        view.setOrientation(LinearLayout.VERTICAL);
        return view;
    }

    private LinearLayout row() {
        LinearLayout view = new LinearLayout(this);
        view.setOrientation(LinearLayout.HORIZONTAL);
        view.setGravity(Gravity.CENTER_VERTICAL);
        return view;
    }

    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        view.setGravity(Gravity.CENTER_VERTICAL);
        return view;
    }

    private LinearLayout.LayoutParams size(int width, int height) {
        return new LinearLayout.LayoutParams(width < 0 ? width : dp(width), height < 0 ? height : dp(height));
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
