package vn.nbl.live;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import org.json.JSONObject;

/** NBL LIVE trên điện thoại: giao diện trong assets/index.html, nói chuyện với NBL trên PC qua Tailscale. */
public class MainActivity extends Activity {
    private static final int PICK_VIDEO = 4313;
    private WebView web;
    private boolean ready;
    private String pending;
    private ValueCallback<Uri[]> picker;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        // 4.3.13: <input type="file" accept="video/*"> mở trình chọn video của Android
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (picker != null) picker.onReceiveValue(null);
                picker = callback;
                Intent pick = new Intent(Intent.ACTION_GET_CONTENT);
                pick.addCategory(Intent.CATEGORY_OPENABLE);
                pick.setType("video/*");
                pick.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
                try {
                    startActivityForResult(Intent.createChooser(pick, "Chọn video gửi vào NBL"), PICK_VIDEO);
                } catch (ActivityNotFoundException e) {
                    picker = null;
                    return false;
                }
                return true;
            }
        });
        web.addJavascriptInterface(new Bridge(), "NBL");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                ready = true;
                if (pending != null) { pair(pending); pending = null; }
            }
        });
        setContentView(web);
        if (state != null) web.restoreState(state);
        else web.loadUrl("file:///android_asset/index.html");
        handle(getIntent());
    }

    @Override
    protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != PICK_VIDEO || picker == null) return;
        Uri[] uris = null;
        if (result == RESULT_OK && data != null) {
            if (data.getClipData() != null) {
                int n = data.getClipData().getItemCount();
                uris = new Uri[n];
                for (int i = 0; i < n; i++) uris[i] = data.getClipData().getItemAt(i).getUri();
            } else if (data.getData() != null) {
                uris = new Uri[]{data.getData()};
            }
        }
        picker.onReceiveValue(uris);
        picker = null;
    }

    /** window.NBL trong trang: giữ màn hình sáng khi đang gửi video. */
    private class Bridge {
        @JavascriptInterface
        public void keepScreen(final boolean on) {
            runOnUiThread(() -> {
                if (on) getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            });
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handle(intent);
    }

    private void handle(Intent intent) {
        Uri data = intent == null ? null : intent.getData();
        if (data == null || !"nblive".equals(data.getScheme())) return;
        if (ready) pair(data.toString()); else pending = data.toString();
    }

    private void pair(String link) {
        web.evaluateJavascript("window.nblPair && window.nblPair(" + JSONObject.quote(link) + ")", null);
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }
}
