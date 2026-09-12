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

API_ID = int(os.getenv("API_ID", 2040))
API_HASH = os.getenv("API_HASH", "b18441a1ff607e10a989891a5462e627")
SESSION_STRING = os.getenv(
    "SESSION_STRING",
    "1BJWap1wBuxV86N3P8lf2W02MQPXDRY3cqSond8FiP8kNyH_r1OFhzmkWuePBnt2aRvAkcBG3Nu5xEDPkohzKOPCvQSJWLN_t3lVDDPIXG6nu35JcVdnt1PuYfk-FKgPgkx-3vfiQ36HanRfnNRAhSf5WNp2ILybaX0LBH90in9feIWBp54zoV_rCg25PThe3NTpzS8pTtznQAFb43obscqg9eA2Gw5Ybi5sMrMsqs6Z5H9vWJzkVczUq77J0p3A9HiVpQLmlgqnQQ_R0ppbn4Vka9gshQB-nfBwsfjfR6tW19rccNAN_KPZ5QUlpXcob7RaiBy7_zaGFNBqjXDe2Os_3TxSQL3c="
)

# Source group/channel jahan se continuous updates aa rahi hain aur bots
SOURCE_CHATS = [-1002405808647]
SOURCE_BOTS = ["ZWMZOhubot", "ARXMOnpbot"]
TARGET_CHAT = -1004320100002

MIN_FILE_SIZE_MB = 10
seen_messages = set()

# Keep-alive web server
async def handle_ping(request):
    return web.Response(text="Movie Forwarder Bot is Active!")

async def start_web_server():
    server = web.Application()
    server.router.add_get("/", handle_ping)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Keep-alive web server started on port {port}")

async def process_and_forward(client, target, msg, source_label="Source"):
    if not msg:
        return False

    msg_key = f"{msg.chat_id}_{msg.id}"
    if msg_key in seen_messages:
        return False

    # Check file/media
    file_obj = getattr(msg, "file", None)
    if not file_obj:
        return False

    size_bytes = getattr(file_obj, "size", 0) or 0
    size_mb = size_bytes / (1024 * 1024)
    file_name = getattr(file_obj, "name", None) or f"movie_{msg.id}"

    logging.info(f"[{source_label}] MOVIE/FILE FOUND: '{file_name}' | Size: {size_mb:.2f} MB")

    if size_mb < MIN_FILE_SIZE_MB:
        logging.info(f"[{source_label}] Skipped: File size ({size_mb:.2f} MB) < {MIN_FILE_SIZE_MB} MB limit.")
        return False

    attempts = 0
    while attempts < 3:
        try:
            await client.forward_messages(target, msg)
            seen_messages.add(msg_key)
            logging.info(f"===> [SUCCESS] '{file_name}' ({size_mb:.2f} MB) FORWARDED TO TARGET CHANNEL!")
            await asyncio.sleep(2)
            return True
        except FloodWaitError as e:
            wait_time = e.seconds + 2
            logging.warning(f"FloodWait hit! Pausing for {wait_time}s...")
            await asyncio.sleep(wait_time)
            attempts += 1
        except Exception as e:
            logging.error(f"Forwarding error on Msg {msg.id}: {e}")
            attempts += 1
            await asyncio.sleep(2)

    return False

async def main():
    await start_web_server()

    client = TelegramClient(
        StringSession(SESSION_STRING),
        API_ID,
        API_HASH,
        sequential_updates=True
    )
    await client.start()
    logging.info("Telegram Client Connected.")

    target = await client.get_entity(TARGET_CHAT)

    # Allowed targets
    allowed_ids = set(SOURCE_CHATS)
    for username in SOURCE_BOTS:
        try:
            entity = await client.get_entity(username)
            allowed_ids.add(entity.id)
            logging.info(f"Resolved bot: @{username} (ID: {entity.id})")
        except Exception as e:
            logging.error(f"Could not resolve @{username}: {e}")

    # Startup sync: Source channel ke aakhri 15 messages check karein agar koi file pari ho
    logging.info("Checking last 15 messages from source channel...")
    for chat_id in SOURCE_CHATS:
        try:
            async for message in client.iter_messages(chat_id, limit=15):
                await process_and_forward(client, target, message, f"Startup-Channel-{chat_id}")
        except Exception as e:
            logging.error(f"Startup scan error for {chat_id}: {e}")

    # Real-Time Event Listener
    @client.on(events.NewMessage)
    async def incoming_handler(event):
        chat_id = event.chat_id
        sender_id = event.sender_id

        # Channel, bot ya private chat sab se aane wali files capture karein
        if chat_id in allowed_ids or sender_id in allowed_ids or event.is_private:
            if event.message and event.message.file:
                sender = await event.get_sender()
                sender_label = getattr(sender, "username", None) or getattr(sender, "title", str(chat_id))
                await process_and_forward(client, target, event.message, sender_label)

    logging.info(">>> BOT LISTENER ACTIVE: WAITING FOR MOVIES <<<")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
