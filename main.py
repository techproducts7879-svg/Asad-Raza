import asyncio
import logging
import os
from aiohttp import web
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Credentials (API_ID aur API_HASH wahi rakhein jo session generate karte waqt use kiye thay)
API_ID = int(os.getenv("API_ID", 2040))
API_HASH = os.getenv("API_HASH", "b18441a1ff607e10a989891a5462e627")
SESSION_STRING = os.getenv(
    "SESSION_STRING",
    "1BJWap1wBuxV86N3P8lf2W02MQPXDRY3cqSond8FiP8kNyH_r1OFhzmkWuePBnt2aRvAkcBG3Nu5xEDPkohzKOPCvQSJWLN_t3lVDDPIXG6nu35JcVdnt1PuYfk-FKgPgkx-3vfiQ36HanRfnNRAhSf5WNp2ILybaX0LBH90in9feIWBp54zoV_rCg25PThe3NTpzS8pTtznQAFb43obscqg9eA2Gw5Ybi5sMrMsqs6Z5H9vWJzkVczUq77J0p3A9HiVpQLmlgqnQQ_R0ppbn4Vka9gshQB-nfBwsfjfR6tW19rccNAN_KPZ5QUlpXcob7RaiBy7_zaGFNBqjXDe2Os_3TxSQL3c="
)

SOURCE_BOTS = ["ZWMZOhubot", "ARXMOnpbot"]
TARGET_CHAT = -1004320100002

MIN_FILE_SIZE_MB = 50
seen_signatures = set()

def get_file_signature(message):
    if not message or not message.file:
        return None
    name = getattr(message.file, "name", None) or "unnamed_file"
    size = message.file.size or 0
    return f"{name}_{size}"

# Health check dummy server for Render / Koyeb
async def handle_ping(request):
    return web.Response(text="Movie Forwarder Live & Healthy!")

async def start_web_server():
    server = web.Application()
    server.router.add_get("/", handle_ping)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Keep-alive web server active on port {port}")

async def process_and_forward(client, target, msg, bot_label="Bot"):
    """Media validate karega, duplicate check karega aur safely forward karega."""
    if not msg or not msg.file:
        return False

    size_mb = (msg.file.size or 0) / (1024 * 1024)

    if (msg.video or msg.document) and size_mb >= MIN_FILE_SIZE_MB:
        sig = get_file_signature(msg)
        if sig in seen_signatures:
            return False

        file_name = getattr(msg.file, "name", "Video File")
        logging.info(f"[DETECTED] New file from {bot_label}: {file_name} ({size_mb:.2f} MB)")

        attempts = 0
        while attempts < 3:
            try:
                await client.send_message(target, msg)
                seen_signatures.add(sig)
                logging.info(f"[FORWARDED SUCCESS] '{file_name}' to target channel.")
                await asyncio.sleep(2)
                return True
            except FloodWaitError as e:
                wait_time = e.seconds + 3
                logging.warning(f"FloodWait hit! Pausing for {wait_time}s...")
                await asyncio.sleep(wait_time)
                attempts += 1
            except Exception as e:
                logging.error(f"Forwarding error on message {msg.id}: {e}")
                attempts += 1
                await asyncio.sleep(2)

    return False

async def main():
    await start_web_server()

    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()
    logging.info("Telegram Client successfully connected.")

    target = await client.get_entity(TARGET_CHAT)

    # 1. Target Channel ko pre-scan karein taake duplicate na jayein
    logging.info("Target channel scan ho raha hai...")
    count = 0
    async for msg in client.iter_messages(target, limit=500):
        sig = get_file_signature(msg)
        if sig:
            seen_signatures.add(sig)
            count += 1
    logging.info(f"Target channel pre-scan complete: {count} existing files cached.")

    # 2. Source bots resolve karein
    bot_entities = []
    bot_ids = []
    for username in SOURCE_BOTS:
        try:
            entity = await client.get_entity(username)
            bot_entities.append(entity)
            bot_ids.append(entity.id)
            logging.info(f"Resolved bot: @{username} (ID: {entity.id})")
        except Exception as e:
            logging.error(f"Entity resolve error for @{username}: {e}")

    # 3. Startup catch-up: Aakhri 10 messages check karein
    logging.info("Checking latest offline messages from bots...")
    for entity in bot_entities:
        bot_name = getattr(entity, "username", str(entity.id))
        async for message in client.iter_messages(entity, limit=10):
            await process_and_forward(client, target, message, f"@{bot_name}")

    # 4. Pure Real-Time Event Listener
    @client.on(events.NewMessage(chats=bot_ids))
    async def incoming_handler(event):
        sender = await event.get_sender()
        sender_label = getattr(sender, "username", str(event.chat_id))
        await process_and_forward(client, target, event.message, f"@{sender_label}")

    logging.info("Live real-time monitoring is active. Waiting for new messages...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
