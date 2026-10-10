package com.questpro.ldcontrol;

import java.util.LinkedHashMap;
import java.util.Map;

final class ControllerState {
    final Map<String, String> props = new LinkedHashMap<>();
    final Map<String, String> frame = new LinkedHashMap<>();

    ControllerState(String text) {
        for (String line : text.split("\\r?\\n")) {
            if (line.startsWith("status ")) {
                Map<String, String> candidate = new LinkedHashMap<>();
                for (String token : line.split("\\s+")) put(candidate, token);
                if (candidate.get("pid") != null && candidate.get("pid").equals(props.get("runtime_pid"))) {
                    frame.clear();
                    frame.putAll(candidate);
                }
            } else put(props, line);
        }
    }

    private static void put(Map<String, String> map, String token) {
        int at = token.indexOf('=');
        if (at > 0) map.put(token.substring(0, at), token.substring(at + 1).trim());
    }

    String value(String key, String fallback) { return props.containsKey(key) ? props.get(key) : fallback; }
    int integer(String key, int fallback) {
        try { return Integer.parseInt(value(key, "")); } catch (Exception e) { return fallback; }
    }
    float decimal(String key, float fallback) {
        try {
            float number = Float.parseFloat(value(key, ""));
            return Float.isFinite(number) ? number : fallback;
        } catch (Exception e) { return fallback; }
    }
    boolean ready() {
        return "1".equals(frame.get("ready")) && integer("runtime_pid", 0) > 1;
    }
    boolean usable() {
        return "0.5.0".equals(value("version", "")) && integer("module_disabled", 1) == 0 &&
                integer("module_update_pending", 1) == 0;
    }
    boolean active() { return integer("enable", 0) == 1 && integer("bypass", 1) == 0; }
    boolean canEnable() { return usable() && ready() && integer("plan_valid", 0) == 1; }
    boolean saved() { return integer("settings_saved", 0) == 1 && integer("settings_valid", 0) == 1; }
    boolean savedMatches() { return saved() && integer("settings_match", 0) == 1; }
}
