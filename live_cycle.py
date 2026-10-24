"""Confirmed OBS output transitions; no API or credentials for TikTok LIVE Studio."""
import math




class LiveCycle:
    def __init__(self):
        self.state='idle'; self.deadline=0; self.live_seconds=0; self.rest_seconds=0
        self.repeat=False; self.owned=False
        self.video_lost_at=None;self.obs_lost_at=None

    def begin(self, now, live_seconds, rest_seconds, repeat):
        if self.state!='idle':raise ValueError('Lịch LIVE đang chạy.')
        if not all(math.isfinite(x) for x in (live_seconds,rest_seconds)) or live_seconds<30 or rest_seconds<10:
            raise ValueError('LIVE tối thiểu 30 giây; nghỉ tối thiểu 10 giây.')
        self.live_seconds=live_seconds; self.rest_seconds=rest_seconds; self.repeat=repeat
        self.state='prepare';self.deadline=now+15;self.owned=False
        self.video_lost_at=None;self.obs_lost_at=None

    def tick(self, now, video_ready, output_active, output_fresh):
        if self.state=='idle':return None
        if self.state=='prepare':
            if output_fresh and output_active:raise RuntimeError('OBS đang phát; dừng lịch để không chiếm phiên hiện tại.')
            if video_ready and output_fresh and not output_active:
                self.state='starting';self.deadline=now+15;self.owned=True;return 'start'
        elif self.state=='starting':
            if output_fresh and output_active:
                self.state='live';self.deadline=now+self.live_seconds
        elif self.state=='live':
            if output_fresh and not output_active:raise RuntimeError('OBS đã ngừng phát ngoài lịch.')
            if video_ready:self.video_lost_at=None
            elif self.video_lost_at is None:self.video_lost_at=now
            if output_fresh:self.obs_lost_at=None
            elif self.obs_lost_at is None:self.obs_lost_at=now
            if self.video_lost_at is not None and now-self.video_lost_at>=5:raise RuntimeError('Nguồn video mất tín hiệu quá 5 giây; đã hủy lịch và gửi dừng OBS.')
            if self.obs_lost_at is not None and now-self.obs_lost_at>=10:raise RuntimeError('OBS không cập nhật trạng thái quá 10 giây; đã hủy lịch và gửi dừng OBS.')
            if now>=self.deadline:self.state='stopping';self.deadline=now+15;return 'stop'
            return None
        elif self.state=='stopping':
            if output_fresh and not output_active:
                self.owned=False
                self.state='rest' if self.repeat else 'idle';self.deadline=now+self.rest_seconds
                return 'video_stop'
        elif self.state=='rest':
            if now>=self.deadline:
                self.state='prepare';self.deadline=now+15;return 'shuffle_play'
            return None
        if now>=self.deadline:raise RuntimeError('Quá hạn xác nhận video/OBS; lịch LIVE đã dừng.')
        return None

    def cancel(self):
        owned=self.owned;self.state='idle';self.owned=False;self.video_lost_at=None;self.obs_lost_at=None;return owned
