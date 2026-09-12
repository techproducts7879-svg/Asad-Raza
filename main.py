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

# Dono bots aur woh Channel ID jahan se trigger aa rahe hain
SOURCE_BOTS = ["ZWMZOhubot", "ARXMOnpbot"]
SOURCE_CHATS = [-1002405808647]  # Jo logs mein channel ID aayi
TARGET_CHAT = -1004320100002

MIN_FILE_SIZE_MB = 20  # Limit 20MB kar di taake chhoti test files bhi pass hon
seen_messages = set()

async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    server = web.Application()
    server.router.add_get("/", handle_ping)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def process_and_forward(client, target, msg, label="Chat"):
    if not msg:
        return False

    msg_key = f"{msg.chat_id}_{msg.id}"
    if msg_key in seen_messages:
        return False

    # Check media presence
    has_file = bool(getattr(msg, "file", None))
    text_content = (msg.text or "").strip().replace("\n", " ")[:50]

    logging.info(f"[{label}] ID:{msg.id} | Has File:{has_file} | Text:'{text_content}'")

    if not has_file:
        logging.info(f"[{label}] Skipped: Koi video/document file attach nahi thi.")
        return False

    size_bytes = getattr(msg.file, "size", 0) or 0
    size_mb = size_bytes / (1024 * 1024)
    file_name = getattr(msg.file, "name", None) or f"video_{msg.id}"

    logging.info(f"[{label}] FILE DETECTED: '{file_name}' ({size_mb:.2f} MB)")

    if size_mb < MIN_FILE_SIZE_MB:
        logging.info(f"[{label}] Skipped: Size {size_mb:.2f} MB < {MIN_FILE_SIZE_MB} MB.")
        return False

    # Forward
    attempts = 0
    while attempts < 3:
        try:
            await client.forward_messages(target, msg)
            seen_messages.add(msg_key)
            logging.info(f"===> [SUCCESS] '{file_name}' TARGET CHANNEL PAR FORWARD HO GAYI!")
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

    # Allowed IDs list (Bots + Channel)
    allowed_ids = set(SOURCE_CHATS)
    for username in SOURCE_BOTS:
        try:
            entity = await client.get_entity(username)
            allowed_ids.add(entity.id)
            logging.info(f"Resolved bot: @{username} (ID: {entity.id})")
        except Exception as e:
            logging.error(f"Could not resolve @{username}: {e}")

    @client.on(events.NewMessage)
    async def incoming_handler(event):
        chat_id = event.chat_id
        sender_id = event.sender_id

        # Agar message hamare bots ya source channel se aaya ho
        if chat_id in allowed_ids or sender_id in allowed_ids:
            sender = await event.get_sender()
            sender_title = getattr(sender, "username", None) or getattr(sender, "title", str(chat_id))
            await process_and_forward(client, target, event.message, sender_title)

    logging.info(">>> LISTENER ACTIVE: WAITING FOR FILES <<<")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
