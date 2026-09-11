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

# Credentials
API_ID = int(os.getenv("API_ID", 2040))
API_HASH = os.getenv("API_HASH", "b18441a1ff607e10a989891a5462e627")
SESSION_STRING = os.getenv(
    "SESSION_STRING",
    "1BJWap1wBu05PbKX2xWJ74yjJIWCa2nSl_GJvcizlzyx_7teJwy_U7UelH-t9aAyhdnxrNkXC9GdeT-TUQbTgFXBJ2vkTNrxOmb1VLWoiKJ0UU2paBNJvGfyiyM-0eZTIdQodlOO3qmO-S7wb_CDRb2A47GE-fJ4YItbbUGlXfvpA1JaGTfED-J95V5_Zk8Dug36m8d2lAot3XLeUjoQvDHs_QwisWit6qbRbiwZFscLQODnK-Laq4tZlDCTRL_QDz01iJcphChAnNk75iBxdFpbMXplTqZaFe0Qy7aJYw2sroLrwQCcdr1ANb8mwN6OCApae_3NKurvWjUF48Xcs7TfNslsLeP4="
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

# Health check dummy server
async def handle_ping(request):
    return web.Response(text="Movie Forwarder Active & Polling!")

async def start_web_server():
    server = web.Application()
    server.router.add_get("/", handle_ping)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Keep-alive web server started on port {port}")

async def process_and_forward(client, target, msg, bot_label="Bot"):
    """Validates media, duplicate check, and forwards."""
    if not msg or not msg.file:
        return False

    size_mb = (msg.file.size or 0) / (1024 * 1024)
    # Filter: Videos/Documents greater than MIN_FILE_SIZE_MB
    if (msg.video or msg.document) and size_mb >= MIN_FILE_SIZE_MB:
        sig = get_file_signature(msg)
        if sig in seen_signatures:
            return False

        file_name = getattr(msg.file, "name", "Video File")
        logging.info(f"[DETECTED] New movie from {bot_label}: {file_name} ({size_mb:.2f} MB)")

        success = False
        attempts = 0
        while not success and attempts < 3:
            try:
                await client.send_message(target, msg)
                seen_signatures.add(sig)
                logging.info(f"[FORWARDED SUCCESS] '{file_name}' to Movimaza_log")
                success = True
                await asyncio.sleep(2)
                return True
            except FloodWaitError as e:
                logging.warning(f"FloodWait hit! Waiting {e.seconds + 2}s...")
                await asyncio.sleep(e.seconds + 2)
                attempts += 1
            except Exception as e:
                logging.error(f"Failed to forward message {msg.id}: {e}")
                attempts += 1
                await asyncio.sleep(1)
    return False

async def poll_bots_loop(client, target, bot_entities):
    """Fallback background poller: Har 4 second baad dono bots ki latest chat check karega"""
    logging.info("Background active-polling loop started.")
    while True:
        try:
            for entity in bot_entities:
                bot_name = getattr(entity, "username", str(entity.id))
                # Check last 5 messages
                async for message in client.iter_messages(entity, limit=5):
                    await process_and_forward(client, target, message, f"@{bot_name}")
        except Exception as err:
            logging.error(f"Error in poll loop: {err}")
        
        await asyncio.sleep(4)

async def main():
    await start_web_server()

    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()
    logging.info("Telegram Client connected!")

    target = await client.get_entity(TARGET_CHAT)

    # 1. Pre-scan existing target channel to avoid duplicates
    logging.info("Pre-scanning target channel Movimaza_log...")
    count = 0
    async for msg in client.iter_messages(target, limit=1000):
        sig = get_file_signature(msg)
        if sig:
            seen_signatures.add(sig)
            count += 1
    logging.info(f"Target channel pre-scan done. {count} files cached.")

    # 2. Resolve bot entities & numeric IDs
    bot_entities = []
    bot_ids = set()
    for username in SOURCE_BOTS:
        try:
            entity = await client.get_entity(username)
            bot_entities.append(entity)
            bot_ids.add(entity.id)
            logging.info(f"Resolved bot: @{username} (ID: {entity.id})")
        except Exception as e:
            logging.error(f"Could not resolve @{username}: {e}")

    # 3. Live Real-Time Event Listener (Exact ID Match)
    @client.on(events.NewMessage(chats=list(bot_ids)))
    async def incoming_handler(event):
        sender = await event.get_sender()
        sender_label = getattr(sender, "username", str(event.chat_id))
        await process_and_forward(client, target, event.message, f"@{sender_label}")

    # 4. Poller task start karein taake koi bhi message miss na ho
    asyncio.create_task(poll_bots_loop(client, target, bot_entities))

    logging.info("Multi-bot 24/7 listener + Poller ACTIVE.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
