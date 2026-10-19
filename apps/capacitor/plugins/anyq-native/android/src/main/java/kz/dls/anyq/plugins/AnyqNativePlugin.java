package kz.dls.anyq.plugins;

import android.Manifest;
import android.content.ContentValues;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;

@CapacitorPlugin(
    name = "AnyqNative",
    permissions = {
        @Permission(strings = { Manifest.permission.RECORD_AUDIO }, alias = "microphone"),
        @Permission(strings = { Manifest.permission.WRITE_EXTERNAL_STORAGE }, alias = "storage")
    }
)
public class AnyqNativePlugin extends Plugin {

    @PluginMethod
    public void requestMicrophone(PluginCall call) {
        if (getPermissionState("microphone") == PermissionState.GRANTED) {
            resolveGranted(call, true);
            return;
        }
        requestPermissionForAlias("microphone", call, "microphoneCallback");
    }

    @PermissionCallback
    private void microphoneCallback(PluginCall call) {
        resolveGranted(call, getPermissionState("microphone") == PermissionState.GRANTED);
    }

    @PluginMethod
    public void openExternal(PluginCall call) {
        String url = call.getString("url");
        if (url == null || !(url.startsWith("https://") || url.startsWith("http://"))) {
            call.reject("Only http(s) URLs can be opened");
            return;
        }
        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        getContext().startActivity(intent);
        call.resolve();
    }

    @PluginMethod
    public void saveFile(PluginCall call) {
        String filename = safeName(call.getString("filename"));
        String data = call.getString("data");
        String mime = call.getString("mime", "application/octet-stream");
        if (filename == null || data == null || data.isEmpty()) {
            call.reject("filename and data are required");
            return;
        }
        byte[] bytes;
        try {
            bytes = Base64.decode(data, Base64.DEFAULT);
        } catch (IllegalArgumentException error) {
            call.reject("data is not base64");
            return;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            saveDownloads(call, filename, mime, bytes);
            return;
        }
        if (getPermissionState("storage") != PermissionState.GRANTED) {
            requestPermissionForAlias("storage", call, "storageCallback");
            return;
        }
        saveLegacy(call, filename, bytes);
    }

    @PermissionCallback
    private void storageCallback(PluginCall call) {
        if (getPermissionState("storage") != PermissionState.GRANTED) {
            call.reject("Storage permission was denied");
            return;
        }
        String filename = safeName(call.getString("filename"));
        String data = call.getString("data");
        if (filename == null || data == null) {
            call.reject("filename and data are required");
            return;
        }
        saveLegacy(call, filename, Base64.decode(data, Base64.DEFAULT));
    }

    private void saveDownloads(PluginCall call, String filename, String mime, byte[] bytes) {
        ContentValues values = new ContentValues();
        values.put(MediaStore.Downloads.DISPLAY_NAME, filename);
        values.put(MediaStore.Downloads.MIME_TYPE, mime);
        values.put(MediaStore.Downloads.IS_PENDING, 1);
        Uri item = getContext().getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
        if (item == null) {
            call.reject("Could not create the download");
            return;
        }
        try (OutputStream out = getContext().getContentResolver().openOutputStream(item)) {
            if (out == null) {
                call.reject("Could not open the download");
                return;
            }
            out.write(bytes);
        } catch (IOException error) {
            call.reject("Could not write the download", error);
            return;
        }
        values.clear();
        values.put(MediaStore.Downloads.IS_PENDING, 0);
        getContext().getContentResolver().update(item, values, null, null);
        JSObject result = new JSObject();
        result.put("uri", item.toString());
        call.resolve(result);
    }

    private void saveLegacy(PluginCall call, String filename, byte[] bytes) {
        File dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
        if (!dir.exists() && !dir.mkdirs()) {
            call.reject("Could not open Downloads");
            return;
        }
        File file = new File(dir, filename);
        try (FileOutputStream out = new FileOutputStream(file)) {
            out.write(bytes);
        } catch (IOException error) {
            call.reject("Could not write the download", error);
            return;
        }
        JSObject result = new JSObject();
        result.put("uri", Uri.fromFile(file).toString());
        call.resolve(result);
    }

    private void resolveGranted(PluginCall call, boolean granted) {
        JSObject result = new JSObject();
        result.put("granted", granted);
        call.resolve(result);
    }

    private String safeName(String filename) {
        if (filename == null) return null;
        String cleaned = filename.replace("\\", "_").replace("/", "_").replace("..", "_").trim();
        if (cleaned.isEmpty()) return "download";
        return cleaned;
    }
}
