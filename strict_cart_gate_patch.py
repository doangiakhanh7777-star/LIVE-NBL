"""Strict pre-LIVE cart gate for scheduled sales.

A sales schedule may start only after its own bundle preparation completed and a
separate cart check explicitly read >0 products. Unknown cart counts are never
accepted. The old fallback that allowed a LIVE to start with an unrelated cart
after three bundle failures is disabled.
"""
import time


def install():
    from studio_panel import StudioPanel

    if getattr(StudioPanel, "_nbl_strict_cart_gate_patch", False):
        return

    original_poll = StudioPanel.poll_cart

    def _clear_strict(cart):
        cart.pop("strict_prepared_bundle", None)
        cart.pop("strict_prepared_at", None)
        cart.pop("strict_verified_count", None)
        cart.pop("strict_verified_at", None)

    def strict_cart_ready(self, j):
        if j.get("no_sales"):
            return True
        cart = j.setdefault("cart", dict(state="none", attempts=0, next=0))

        # Special case only for a LIVE that was already started by hand. This
        # lets preflight end/postpone that existing LIVE; it does NOT authorize a
        # new LIVE start.
        if (cart.get("probe") or {}).get("live") is True:
            return True

        try:
            wanted = int(j.get("bundle_index") or 0)
            prepared = int(cart.get("strict_prepared_bundle"))
            count = int(cart.get("strict_verified_count") or 0)
        except (TypeError, ValueError):
            prepared = -1
            count = 0

        ok = (
            cart.get("state") == "ready"
            and cart.get("verified") is True
            and prepared == wanted
            and count > 0
            and not cart.get("fallback")
        )
        if ok:
            return True

        if not cart.get("waiting_noted") or not str(j.get("error", "")).startswith("Chờ giỏ"):
            cart["waiting_noted"] = True
            j["error"] = "Chờ xác nhận giỏ của đúng lịch có sản phẩm (>0) mới phát LIVE"
        return False

    def poll_cart(self, now):
        # Never use the legacy fallback "old cart still has products => go LIVE".
        # After three real bundle failures the job must remain blocked.
        for j in self.jobs:
            if j.get("no_sales") or j.get("state") not in ("pending", "start_retry"):
                continue
            cart = j.setdefault("cart", dict(state="none", attempts=0, next=0))
            if cart.get("state") == "failed" and int(cart.get("attempts", 0) or 0) >= 3:
                cart["fallback_checked"] = True

            # A ready cart saved by an older build has no proof that it belongs
            # to this schedule. Re-prepare it once under the strict gate.
            if cart.get("state") == "ready" and "strict_prepared_bundle" not in cart:
                cart.update(state="none", verified=False, attempts=0, next=0)
                cart.pop("fallback", None)
                cart.pop("gave_up", None)
                _clear_strict(cart)
                j["error"] = "Giỏ cũ chưa có xác nhận an toàn; NBL sẽ chuẩn bị lại trước khi LIVE"

        before = {}
        for j in self.jobs:
            cart = j.get("cart") or {}
            before[j.get("id")] = {
                "state": cart.get("state"),
                "command": cart.get("command"),
                "kind": cart.get("kind"),
            }

        original_poll(self, now)

        for j in self.jobs:
            if j.get("no_sales"):
                continue
            cart = j.setdefault("cart", dict(state="none", attempts=0, next=0))
            old = before.get(j.get("id"), {})
            old_kind = old.get("kind")
            old_command = old.get("command")

            # The schedule's own prepare_bundle command completed successfully.
            # Force one independent cart-count check before start, even if the
            # bundle was added less than two minutes before the scheduled time.
            if old_kind == "add" and old_command and cart.get("state") == "ready" and not cart.get("fallback"):
                try:
                    wanted = int(j.get("bundle_index") or 0)
                except (TypeError, ValueError):
                    wanted = 0
                cart["strict_prepared_bundle"] = wanted
                cart["strict_prepared_at"] = time.time()
                cart["strict_verified_count"] = 0
                cart.pop("strict_verified_at", None)
                cart["verified"] = False
                cart.pop("waiting_noted", None)

            # For a check that just completed, trust only an explicit positive
            # product count. count=-1 means "could not read" and must NOT start.
            if old_kind == "check" and old_command:
                count = -1
                try:
                    p = self.profile(j["profile"])
                    _session, client = self.client(p)
                    result = self.owner.bridge.snapshot().get(client, {}).get("control", {})
                    if result.get("id") == old_command and result.get("state") == "done":
                        count = int(float(result.get("count", "-1")))
                except Exception:
                    count = -1

                try:
                    wanted = int(j.get("bundle_index") or 0)
                    prepared = int(cart.get("strict_prepared_bundle"))
                except (TypeError, ValueError):
                    wanted, prepared = 0, -1

                if count > 0 and cart.get("state") == "ready" and prepared == wanted:
                    cart["strict_verified_count"] = count
                    cart["strict_verified_at"] = time.time()
                    cart["verified"] = True
                    cart.pop("waiting_noted", None)
                    if str(j.get("error", "")).startswith("Chờ giỏ"):
                        j["error"] = ""
                elif count < 0 and cart.get("state") == "ready":
                    # Unknown is a failure, not success. Let the existing retry
                    # + controlled dashboard reload logic recover it.
                    cart["verified"] = False
                    cart["state"] = "none"
                    _clear_strict(cart)
                    self.cart_failed(j, cart, "Không xác nhận được số sản phẩm trong giỏ sau khi thêm; không cho LIVE", now)
                else:
                    cart["verified"] = False
                    cart.pop("strict_verified_count", None)
                    cart.pop("strict_verified_at", None)

            # If the stock code reached its three-failure terminal path, make the
            # strict reason explicit and keep the schedule blocked until it ends.
            if cart.get("state") == "failed" and int(cart.get("attempts", 0) or 0) >= 3:
                cart["gave_up"] = True
                cart["verified"] = False
                _clear_strict(cart)
                j["error"] = "KHÔNG PHÁT: chưa chuẩn bị và xác nhận được giỏ hàng của đúng lịch sau 3 lần"

    StudioPanel.poll_cart = poll_cart
    StudioPanel.cart_ready = strict_cart_ready
    StudioPanel._nbl_strict_cart_gate_patch = True
