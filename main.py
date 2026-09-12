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

SOURCE_BOTS = ["ZWMZOhubot", "ARXMOnpbot"]
TARGET_CHAT = -1004320100002

MIN_FILE_SIZE_MB = 10  # 10MB limit taake har file catch ho
seen_messages = set()

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

async def process_and_forward(client, target, msg, sender_label="Unknown"):
    if not msg:
        return False

    msg_key = f"{msg.chat_id}_{msg.id}"
    if msg_key in seen_messages:
        return False

    # Media presence check
    if not msg.file:
        return False

    size_bytes = getattr(msg.file, "size", 0) or 0
    size_mb = size_bytes / (1024 * 1024)
    file_name = getattr(msg.file, "name", None) or f"movie_{msg.id}"

    if size_mb < MIN_FILE_SIZE_MB:
        return False

    attempts = 0
    while attempts < 3:
        try:
            await client.forward_messages(target, msg)
            seen_messages.add(msg_key)
            logging.info(f"===> [SUCCESS] '{file_name}' ({size_mb:.2f} MB) FROM {sender_label} FORWARDED!")
            await asyncio.sleep(2)
            return True
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 2)
            attempts += 1
        except Exception as e:
            logging.error(f"Forward error: {e}")
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

    # Allowed Bot IDs resolve
    bot_ids = set()
    for username in SOURCE_BOTS:
        try:
            entity = await client.get_entity(username)
            bot_ids.add(entity.id)
            logging.info(f"Resolved bot: @{username} (ID: {entity.id})")
        except Exception as e:
            logging.error(f"Could not resolve @{username}: {e}")

    # Listener: Private DM check (agar bot ne direct aapko file bheji)
    @client.on(events.NewMessage)
    async def incoming_handler(event):
        sender_id = event.sender_id
        chat_id = event.chat_id

        # Agar message bot ki taraf se ho ya bot ki private chat mein aaya ho
        if event.is_private or sender_id in bot_ids or chat_id in bot_ids:
            if event.message and event.message.file:
                sender = await event.get_sender()
                name = getattr(sender, "username", str(sender_id))
                await process_and_forward(client, target, event.message, f"@{name}")

    logging.info(">>> LISTENER ACTIVE: WAITING FOR ACTUAL MEDIA FILES <<<")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
