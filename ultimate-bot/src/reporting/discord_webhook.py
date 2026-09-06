import asyncio
import logging
import time
import aiohttp

class DiscordWebhook:
    def __init__(self, webhook_url, cooldown=30):
        self.webhook_url = webhook_url
        self.cooldown = cooldown
        self.last_send = 0
        self.queue = []
        self.logger = logging.getLogger(__name__)
        self._flush_task = None
        if webhook_url:
            self._flush_task = asyncio.create_task(self._flush_queue())

    async def send(self, message="", title=None, embed=None, color=0x00ff00):
        now = time.time()
        if now - self.last_send < self.cooldown and not embed:
            self.queue.append((message, title, color))
            return
        to_send = self.queue.copy()
        self.queue = []
        if to_send:
            combined = "\n".join(m[0] for m in to_send)
            await self._post_chunked(combined, to_send[0][1], to_send[0][2])
        else:
            await self._post_chunked(message, title, color, embed)
        self.last_send = now

    async def _flush_queue(self):
        while True:
            await asyncio.sleep(1)
            if self.queue and time.time() - self.last_send >= self.cooldown:
                to_send = self.queue.copy()
                self.queue = []
                combined = "\n".join(m[0] for m in to_send)
                await self._post_chunked(combined, to_send[0][1], to_send[0][2])
                self.last_send = time.time()

    async def _post_chunked(self, message, title, color, embed=None):
        if len(message) <= 1900:
            await self._post(message, title, color, embed)
        else:
            for i in range(0, len(message), 1900):
                await self._post(message[i:i+1900], title, color, embed)

    async def _post(self, message, title, color, embed=None):
        if not self.webhook_url:
            return
        data = {"content": message}
        if title or embed:
            embeds = [embed] if embed else [{"title": title, "description": message, "color": color}]
            data["embeds"] = embeds
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.webhook_url, json=data) as resp:
                        if resp.status < 400:
                            return
                        self.logger.error(f"Webhook failed (attempt {attempt+1}): {resp.status}")
            except Exception as e:
                self.logger.error(f"Webhook exception (attempt {attempt+1}): {e}")
            await asyncio.sleep(1)

    async def close(self):
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
