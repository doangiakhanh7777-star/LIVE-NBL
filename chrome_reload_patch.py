"""Add one narrowly-scoped ChromeBridge command for reloading the paired
TikTok Shop LIVE product dashboard.

The stock bridge deliberately accepts a fixed command allow-list. Keeping this
as a runtime patch avoids changing the existing start/stop/cart command paths.
"""
import time
import uuid


def install():
    from chrome_bridge import ChromeBridge

    if getattr(ChromeBridge, "_nbl_reload_patch", False):
        return

    original = ChromeBridge.command

    def command(self, client, payload):
        if payload.get("action") != "reload_dashboard":
            return original(self, client, payload)
        if payload.get("module") != "all":
            raise ValueError("Mục không hợp lệ.")

        with self.lock:
            if self.closing:
                raise ValueError("App đang đóng; không nhận lệnh tải lại trang.")
            if client not in self.clients:
                raise ValueError("Tab đã mất kết nối.")
            self.prune_commands()
            state = self.clients[client]
            if len(state["queue"]) >= 20:
                raise ValueError("Hàng đợi đầy.")

            ttl = 15
            item = {
                **payload,
                "id": uuid.uuid4().hex,
                "expires": time.monotonic() + ttl,
                "deadline": time.time() + ttl,
            }
            state["queue"].append(item)
            self.pending_commands[item["id"]] = dict(
                client=client,
                action="reload_dashboard",
                module="all",
                expires=item["expires"],
            )
            for old in list(self.pending_commands):
                if len(self.pending_commands) <= 500:
                    break
                if self.pending_commands[old]["action"] != "stop":
                    self.pending_commands.pop(old, None)
            return item["id"]

    ChromeBridge.command = command
    ChromeBridge._nbl_reload_patch = True
