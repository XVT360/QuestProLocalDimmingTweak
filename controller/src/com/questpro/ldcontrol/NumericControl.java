package com.questpro.ldcontrol;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.text.InputType;
import android.view.Gravity;
import android.view.inputmethod.EditorInfo;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;

import java.util.Locale;

final class NumericControl extends LinearLayout {
    private final float minimum, maximum, step;
    private final int digits;
    private final SeekBar seek;
    private final EditText input;
    private final ImageButton minus, plus;
    private Runnable commit = () -> { };
    private float value;
    private boolean dirty, dragging, syncing;

    NumericControl(Context context, String title, float min, float max, float increment, float initial, int decimalPlaces) {
        super(context);
        minimum = min; maximum = max; step = increment; digits = decimalPlaces;
        setOrientation(VERTICAL);
        LinearLayout row = new LinearLayout(context);
        row.setGravity(Gravity.CENTER_VERTICAL);
        TextView label = new TextView(context);
        label.setText(title);
        label.setTextSize(14);
        label.setTextColor(Color.rgb(222, 227, 232));
        row.addView(label, new LayoutParams(0, dp(48), 1));
        minus = icon(context, android.R.drawable.ic_media_previous, "Decrease " + title);
        plus = icon(context, android.R.drawable.ic_media_next, "Increase " + title);
        row.addView(minus, new LayoutParams(dp(40), dp(40)));
        input = new EditText(context);
        input.setTextSize(14);
        input.setSelectAllOnFocus(true);
        input.setSingleLine(true);
        input.setGravity(Gravity.CENTER);
        input.setTextColor(Color.rgb(235, 239, 242));
        input.setInputType(InputType.TYPE_CLASS_NUMBER | (digits > 0 ? InputType.TYPE_NUMBER_FLAG_DECIMAL : 0));
        input.setImeOptions(EditorInfo.IME_ACTION_DONE);
        row.addView(input, new LayoutParams(dp(68), dp(48)));
        row.addView(plus, new LayoutParams(dp(40), dp(40)));
        addView(row);
        seek = new SeekBar(context);
        seek.setMax(Math.round((maximum - minimum) / step));
        seek.setProgressTintList(ColorStateList.valueOf(Color.rgb(79, 190, 158)));
        seek.setThumbTintList(ColorStateList.valueOf(Color.rgb(79, 190, 158)));
        addView(seek, new LayoutParams(-1, dp(40)));
        setValue(initial);
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar bar, int progress, boolean fromUser) {
                if (syncing || !fromUser) return;
                dirty = true;
                setValue(minimum + progress * step);
            }
            @Override public void onStartTrackingTouch(SeekBar bar) { dragging = true; }
            @Override public void onStopTrackingTouch(SeekBar bar) { dragging = false; commit.run(); }
        });
        minus.setOnClickListener(v -> change(value - step));
        plus.setOnClickListener(v -> change(value + step));
        input.setOnEditorActionListener((view, action, event) -> {
            if (action == EditorInfo.IME_ACTION_DONE) { readInput(true); input.clearFocus(); return true; }
            return false;
        });
        input.setOnFocusChangeListener((view, focused) -> { if (!focused) readInput(true); });
    }

    void setCommit(Runnable callback) { commit = callback; }
    boolean dirty() { return dirty; }
    void clearDraft() { dirty = false; }
    boolean validateDraft() { return readInput(false); }
    void choose(float number) { change(number); }
    float number() { return value; }
    void sync(float current) {
        if (!dirty && !dragging && !input.hasFocus() && Float.isFinite(current)) setValue(current);
    }
    void setControlsEnabled(boolean enabled) {
        seek.setEnabled(enabled); input.setEnabled(enabled); minus.setEnabled(enabled); plus.setEnabled(enabled);
        setAlpha(enabled ? 1f : 0.5f);
    }
    String argument() { return String.format(Locale.US, "%." + digits + "f", value); }

    private boolean readInput(boolean notify) {
        if (syncing) return true;
        try {
            float number = Float.parseFloat(input.getText().toString());
            if (!Float.isFinite(number) || number < minimum || number > maximum ||
                    (digits == 0 && number != Math.rint(number))) throw new NumberFormatException();
            input.setError(null);
            if (Math.abs(number - value) >= step / 2) {
                dirty = true;
                setValue(number);
                if (notify) commit.run();
            }
            else setValue(value);
            return true;
        } catch (NumberFormatException e) { input.setError(minimum + " .. " + maximum); return false; }
    }

    private void change(float number) {
        dirty = true;
        setValue(number);
        commit.run();
    }

    private void setValue(float number) {
        syncing = true;
        float limited = Math.max(minimum, Math.min(maximum, number));
        value = Math.max(minimum, Math.min(maximum,
                minimum + Math.round((limited - minimum) / step) * step));
        input.setText(argument());
        seek.setProgress(Math.round((value - minimum) / step));
        syncing = false;
    }

    private ImageButton icon(Context context, int drawable, String name) {
        ImageButton view = new ImageButton(context);
        view.setImageResource(drawable);
        view.setImageTintList(ColorStateList.valueOf(Color.rgb(200, 207, 215)));
        view.setBackgroundColor(Color.TRANSPARENT);
        view.setContentDescription(name);
        view.setTooltipText(name);
        return view;
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
