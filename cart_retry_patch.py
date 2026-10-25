"""Safe cart retry enhancement for NBL LIVE.

After a real pre-LIVE cart failure, reload only the paired TikTok Shop LIVE
product dashboard, then let the existing scheduler retry the cart. Never reload
when the latest Studio probe says the nick is LIVE.
"""
import time


def install():
    from studio_panel import StudioPanel

    if getattr(StudioPanel, "_nbl_cart_reload_patch", False):
        return

    original = StudioPanel.cart_failed

    def cart_failed(self, j, cart, reason, now, transient=False):
        original(self, j, cart, reason, now, transient=transient)

        # Chrome busy is already retried by the stock logic and is not a real
        # failure, so do not reload the page for it.
        if transient:
            return

        attempts = int(cart.get("attempts", 0) or 0)
        if attempts < 1 or attempts >= 3:
            return
        if j.get("state") not in ("pending", "start_retry"):
            return

        # The scheduler probes Studio before touching the cart. Only reload
        # while that recent probe explicitly says the nick is NOT LIVE.
        probe = cart.get("probe") or {}
        if probe.get("live") is not False:
            return
        if now - float(probe.get("at", 0) or 0) > 120:
            return
        if cart.get("reload_after_failure") == attempts:
            return

        try:
            p = self.profile(j["profile"])
            if not p:
                return
            session, client = self.client(p)
            self.owner.bridge.command(
                client,
                dict(
                    action="reload_dashboard",
                    module="all",
                    expectedAccount=session.get("chrome_binding", {}).get("account") or p.get("name", ""),
                ),
            )
            cart["reload_after_failure"] = attempts
            # The existing retry interval is 1-5 minutes. After a controlled
            # reload, retry sooner while still keeping enough time for the page
            # and content script to come back.
            cart["next"] = now + 10
            self.notify(
                j,
                "cart_reload",
                "Đã yêu cầu tải lại trang giỏ TikTok Shop sau lần thêm giỏ lỗi "
                + str(attempts)
                + "/3; sẽ thử thêm lại sau khoảng 10 giây.",
                "hoat_dong",
            )
            try:
                self.save()
                self.render()
            except Exception:
                pass
        except Exception as exc:
            self.owner.log("Giỏ hàng: chưa tải lại được trang Chrome: " + str(exc)[:300])

    StudioPanel.cart_failed = cart_failed
    StudioPanel._nbl_cart_reload_patch = True
