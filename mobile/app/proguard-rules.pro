-keep class vn.nbl.live.** { *; }

# 4.3.13: window.NBL.keepScreen() goi tu trang
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
-keepattributes JavascriptInterface
