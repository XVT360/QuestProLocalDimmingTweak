package com.questpro.ldcontrol;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

final class RootRunner {
    static final class Result {
        final int code;
        final String output;
        Result(int code, String output) { this.code = code; this.output = output; }
        boolean ok() { return code == 0; }
    }

    static Result run(String command) {
        return runProcess(new String[]{"su", "-c", command}, 20000);
    }

    static Result runProcess(String[] arguments, long timeoutMs) {
        Process process = null;
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try {
            process = new ProcessBuilder(arguments).redirectErrorStream(true).start();
            process.getOutputStream().close();
            final InputStream stream = process.getInputStream();
            Thread reader = new Thread(() -> {
                try {
                    byte[] bytes = new byte[2048];
                    for (int n; (n = stream.read(bytes)) >= 0;) {
                        synchronized (buffer) {
                            if (buffer.size() < 65536) buffer.write(bytes, 0, Math.min(n, 65536 - buffer.size()));
                        }
                    }
                } catch (Exception ignored) { }
            }, "ld-root-output");
            reader.setDaemon(true);
            reader.start();
            boolean complete = process.waitFor(timeoutMs, TimeUnit.MILLISECONDS);
            if (!complete) process.destroyForcibly();
            reader.join(500);
            synchronized (buffer) {
                return new Result(complete ? process.exitValue() : 124,
                        new String(buffer.toByteArray(), StandardCharsets.UTF_8));
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return new Result(130, "interrupted");
        } catch (Exception e) {
            return new Result(126, e.getClass().getSimpleName() + ": " + e.getMessage());
        } finally {
            if (process != null) {
                process.destroy();
                try { process.getInputStream().close(); } catch (Exception ignored) { }
            }
        }
    }
}
