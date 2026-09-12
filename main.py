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

# Source group/channel jahan updates aa rahi hain
SOURCE_CHAT_ID = -1002405808647
TARGET_CHAT_ID = -1004320100002

MIN_FILE_SIZE_MB = 10
seen_messages = set()

# Keep-alive web server
async def handle_ping(request):
    return web.Response(text="Bot active and listening!")

async def start_web_server():
    server = web.Application()
    server.router.add_get("/", handle_ping)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Keep-alive web server active on port {port}")

async def process_and_forward(client, target_entity, msg):
    if not msg:
        return False

    msg_key = f"{msg.chat_id}_{msg.id}"
    if msg_key in seen_messages:
        return False

    file_obj = getattr(msg, "file", None)
    if not file_obj:
        logging.info(f"[POST ID:{msg.id}] Text post without media. Skipping.")
        return False

    size_bytes = getattr(file_obj, "size", 0) or 0
    size_mb = size_bytes / (1024 * 1024)
    file_name = getattr(file_obj, "name", None) or f"movie_{msg.id}"

    logging.info(f"[MEDIA DETECTED] Name: '{file_name}' | Size: {size_mb:.2f} MB")

    if size_mb < MIN_FILE_SIZE_MB:
        logging.info(f"[SKIPPED] Size ({size_mb:.2f} MB) is below {MIN_FILE_SIZE_MB} MB limit.")
        return False

    attempts = 0
    while attempts < 3:
        try:
            await client.forward_messages(target_entity, msg)
            seen_messages.add(msg_key)
            logging.info(f"===> [SUCCESS] '{file_name}' ({size_mb:.2f} MB) FORWARDED TO TARGET!")
            await asyncio.sleep(2)
            return True
        except FloodWaitError as e:
            logging.warning(f"FloodWait hit: sleeping for {e.seconds + 2}s")
            await asyncio.sleep(e.seconds + 2)
            attempts += 1
        except Exception as e:
            logging.error(f"Forwarding error on Msg {msg.id}: {e}")
            attempts += 1
            await asyncio.sleep(2)

    return False

async def main():
    await start_web_server()

    # Client initialize
    client = TelegramClient(
        StringSession(SESSION_STRING),
        API_ID,
        API_HASH
    )
    await client.start()
    logging.info("Telegram Client Connected.")

    # 1. Source & Target entities ko accurately resolve aur cache karein
    try:
        source_entity = await client.get_entity(SOURCE_CHAT_ID)
        logging.info(f"Source entity resolved: {getattr(source_entity, 'title', SOURCE_CHAT_ID)}")
    except Exception as e:
        logging.error(f"Source channel resolve error: {e}")
        source_entity = SOURCE_CHAT_ID

    try:
        target_entity = await client.get_entity(TARGET_CHAT_ID)
        logging.info(f"Target entity resolved: {getattr(target_entity, 'title', TARGET_CHAT_ID)}")
    except Exception as e:
        logging.error(f"Target channel resolve error: {e}")
        target_entity = TARGET_CHAT_ID

    # 2. Startup catch-up: Aakhri 10 messages check karein
    logging.info("Checking last 10 messages from source channel on startup...")
    try:
        async for msg in client.iter_messages(source_entity, limit=10):
            await process_and_forward(client, target_entity, msg)
    except Exception as e:
        logging.error(f"Startup scan error: {e}")

    # 3. Direct Channel Event Listener (Entity bound)
    @client.on(events.NewMessage(chats=source_entity))
    async def channel_post_handler(event):
        logging.info(f"[NEW INCOMING POST] ID: {event.id} in source channel!")
        await process_and_forward(client, target_entity, event.message)

    logging.info(">>> PRODUCTION LISTENER ATTACHED TO SOURCE CHANNEL <<<")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
