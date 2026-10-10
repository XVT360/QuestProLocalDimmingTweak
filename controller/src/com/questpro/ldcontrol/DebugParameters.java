package com.questpro.ldcontrol;

/** Bounds for the pinned native pipeline, shared by GUI controls and validation. */
final class DebugParameters {
    static final int MAX_X = 8, MAX_Y = 15, MAX_GAUSSIAN = 9;
    static final float MAX_SMOOTH_WEIGHT = 0.3f;

    static boolean valid(int x, int y, int gaussian, int smooth, float weight) {
        return x >= 0 && x <= MAX_X && y >= 0 && y <= MAX_Y && gaussian >= 0 && gaussian <= MAX_GAUSSIAN &&
                (smooth == 0 || smooth == 1) && Float.isFinite(weight) && weight >= 0 && weight <= MAX_SMOOTH_WEIGHT;
    }
}
