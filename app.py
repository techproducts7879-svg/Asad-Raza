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

# Multiple Source Bots
SOURCE_BOTS = ["ZWMZOhubot", "ARXMOnpbot"]

# Target Storage Channel (Movimaza_log)
TARGET_CHAT = -1004320100002

# Filters
MIN_FILE_SIZE_MB = 50
CACHE_FILE = "transferred_files.txt"

# Set to store unique signatures: "filename_filesize"
seen_signatures = set()

def get_file_signature(message):
    """File name aur size ka unique signature banata hai"""
    if not message.file:
        return None
    name = getattr(message.file, "name", None) or "unnamed_video"
    size = message.file.size or 0
    return f"{name}_{size}"

def load_cached_signatures():
    """Disk cache se pehle se transfer shuda files load karein"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                sig = line.strip()
                if sig:
                    seen_signatures.add(sig)
    logging.info(f"Loaded {len(seen_signatures)} file signatures from local cache.")

def record_signature(signature):
    """Nayi signature ko cache aur set mein save karein"""
    seen_signatures.add(signature)
    try:
        with open(CACHE_FILE, "a", encoding="utf-8") as f:
            f.write(signature + "\n")
    except Exception as e:
        logging.error(f"Error saving signature to file: {e}")

# Dummy Web Server for Cloud Deployment Keep-Alive
async def handle_ping(request):
    return web.Response(text="Multi-Bot Movie Forwarder Running with Duplicate Filter!")

async def start_web_server():
    server = web.Application()
    server.router.add_get("/", handle_ping)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.getenv("PORT", 7860))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server active on port {port}")

async def main():
    await start_web_server()
    load_cached_signatures()

    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()
    logging.info("Telegram Client connected to 24/7 Multi-Bot Listener!")

    target = await client.get_entity(TARGET_CHAT)

    # 1. Target Channel ki existing files ko scan karke signatures add karein
    logging.info("Scanning target channel Movimaza_log to detect existing files...")
    target_scan_count = 0
    async for msg in client.iter_messages(target, limit=1000):
        sig = get_file_signature(msg)
        if sig:
            seen_signatures.add(sig)
            target_scan_count += 1
    logging.info(f"Pre-scan complete. {target_scan_count} existing target files cached against duplicates.")

    # Source bots resolve karein
    source_entities = []
    for bot_username in SOURCE_BOTS:
        try:
            entity = await client.get_entity(bot_username)
            source_entities.append(entity)
            logging.info(f"Resolved source bot: @{bot_username}")
        except Exception as e:
            logging.error(f"Could not resolve bot @{bot_username}: {e}")

    # 2. Startup Sync with Duplicate Check
    for source in source_entities:
        bot_name = getattr(source, "username", str(source.id))
        logging.info(f"Syncing recent messages from @{bot_name}...")
        try:
            async for message in client.iter_messages(source, limit=50):
                if message.file:
                    size_mb = (message.file.size or 0) / (1024 * 1024)
                    if (message.video or message.document) and size_mb >= MIN_FILE_SIZE_MB:
                        sig = get_file_signature(message)
                        if sig in seen_signatures:
                            logging.info(f"Skipping duplicate file: {sig}")
                            continue

                        try:
                            await client.send_message(target, message)
                            record_signature(sig)
                            logging.info(f"Synced & Forwarded: {getattr(message.file, 'name', 'File')} ({size_mb:.2f} MB)")
                            await asyncio.sleep(2.5)
                        except FloodWaitError as e:
                            await asyncio.sleep(e.seconds + 2)
                        except Exception as ex:
                            logging.error(f"Sync message error: {ex}")
        except Exception as err:
            logging.error(f"Error syncing history for @{bot_name}: {err}")

    # 3. Live Listener with Duplicate Filter
    @client.on(events.NewMessage(chats=source_entities))
    async def handler(event):
        msg = event.message
        if msg.file:
            size_mb = (msg.file.size or 0) / (1024 * 1024)
            if (msg.video or msg.document) and size_mb >= MIN_FILE_SIZE_MB:
                sig = get_file_signature(msg)
                
                # Duplicate Check
                if sig in seen_signatures:
                    logging.info(f"[DUPLICATE BLOCKED] Already forwarded: {sig}")
                    return

                sender = await event.get_sender()
                sender_name = getattr(sender, "username", "Unknown Bot")
                file_name = getattr(msg.file, "name", "Video File")
                logging.info(f"New unique movie from @{sender_name}: {file_name} ({size_mb:.2f} MB)")

                success = False
                while not success:
                    try:
                        await client.send_message(target, msg)
                        record_signature(sig)
                        logging.info(f"Transferred successfully to Movimaza_log: '{file_name}'")
                        success = True
                        await asyncio.sleep(2)
                    except FloodWaitError as e:
                        logging.warning(f"FloodWait: sleeping {e.seconds}s...")
                        await asyncio.sleep(e.seconds + 2)
                    except Exception as err:
                        logging.error(f"Forward error: {err}")
                        success = True

    logging.info("Live monitoring started. Duplicate filter ACTIVE for both bots.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
