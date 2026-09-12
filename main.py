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

MIN_FILE_SIZE_MB = 50
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

async def process_and_forward(client, target, msg, bot_label="Bot"):
    if not msg:
        return False

    msg_key = f"{msg.chat_id}_{msg.id}"
    if msg_key in seen_messages:
        return False

    # Debug details
    has_media = bool(msg.media)
    file_obj = getattr(msg, "file", None)
    text_preview = (msg.text or "").replace("\n", " ")[:60]
    logging.info(f"[{bot_label}] Processing Msg ID {msg.id} | Has Media: {has_media} | Text: '{text_preview}'")

    # Agar media nahi hai
    if not has_media or not file_obj:
        logging.info(f"[{bot_label}] Skipped Msg ID {msg.id}: Media file nahi mili (Sirf text/button message hai).")
        return False

    size_bytes = getattr(file_obj, "size", 0) or 0
    size_mb = size_bytes / (1024 * 1024)
    file_name = getattr(file_obj, "name", None) or f"file_{msg.id}"

    logging.info(f"[{bot_label}] File Found: '{file_name}' | Size: {size_mb:.2f} MB")

    if size_mb < MIN_FILE_SIZE_MB:
        logging.info(f"[{bot_label}] Skipped Msg ID {msg.id}: Size ({size_mb:.2f} MB) < {MIN_FILE_SIZE_MB} MB limit.")
        return False

    attempts = 0
    while attempts < 3:
        try:
            await client.forward_messages(target, msg)
            seen_messages.add(msg_key)
            logging.info(f"==> [SUCCESS FORWARDED] '{file_name}' ({size_mb:.2f} MB) to Target Channel!")
            await asyncio.sleep(2)
            return True
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 2)
            attempts += 1
        except Exception as e:
            logging.error(f"Error forwarding Msg {msg.id}: {e}")
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

    bot_ids = set()
    for username in SOURCE_BOTS:
        try:
            entity = await client.get_entity(username)
            bot_ids.add(entity.id)
            logging.info(f"Resolved bot: @{username} (ID: {entity.id})")
        except Exception as e:
            logging.error(f"Could not resolve @{username}: {e}")

    @client.on(events.NewMessage)
    async def incoming_handler(event):
        sender_id = event.sender_id
        chat_id = event.chat_id

        if chat_id in bot_ids or sender_id in bot_ids:
            sender = await event.get_sender()
            bot_name = getattr(sender, "username", str(chat_id))
            logging.info(f"[TRIGGER] New message from @{bot_name} (Chat: {chat_id}, Msg ID: {event.id})")
            await process_and_forward(client, target, event.message, f"@{bot_name}")

    logging.info(">>> BOT LISTENER ACTIVE: WAITING FOR MOVIES <<<")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
