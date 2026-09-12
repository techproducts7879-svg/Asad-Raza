import asyncio
import logging
import os

from aiohttp import web
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from telethon.tl.types import (
    MessageMediaDocument,
    MessageMediaPhoto,
)


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# =========================================================
# CONFIG
# =========================================================

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")

SOURCE_CHAT_ID = -1002405808647
TARGET_CHAT_ID = -1004320100002

MIN_FILE_SIZE_MB = 10

seen_messages = set()


# =========================================================
# KEEP ALIVE SERVER
# =========================================================

async def handle_ping(request):
    return web.Response(text="Bot active and listening!")


async def start_web_server():

    app = web.Application()

    app.router.add_get("/", handle_ping)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "10000"))

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    logging.info(
        f"[WEB] Keep-alive server running on port {port}"
    )


# =========================================================
# MEDIA INFORMATION
# =========================================================

def get_media_info(msg):

    media = getattr(msg, "media", None)

    if not media:
        return None

    # Telegram document
    if isinstance(media, MessageMediaDocument):

        document = getattr(media, "document", None)

        if not document:
            return None

        size = getattr(document, "size", 0) or 0

        attributes = getattr(document, "attributes", []) or []

        file_name = None
        is_video = False

        for attribute in attributes:

            # Document filename
            if hasattr(attribute, "file_name"):
                file_name = attribute.file_name

            # Video attribute
            if attribute.__class__.__name__ == "DocumentAttributeVideo":
                is_video = True

        if not file_name:
            file_name = f"media_{msg.id}"

        return {
            "type": "document",
            "size": size,
            "name": file_name,
            "is_video": is_video,
        }

    # Telegram photo
    if isinstance(media, MessageMediaPhoto):

        return {
            "type": "photo",
            "size": 0,
            "name": f"photo_{msg.id}",
            "is_video": False,
        }

    return None


# =========================================================
# PROCESS + FORWARD
# =========================================================

async def process_and_forward(
    client,
    target_entity,
    msg
):

    if not msg:
        return False

    msg_key = f"{msg.chat_id}_{msg.id}"

    if msg_key in seen_messages:

        logging.info(
            f"[DUPLICATE] Message {msg.id} already processed."
        )

        return False

    # -----------------------------------------------------
    # MEDIA
    # -----------------------------------------------------

    media_info = get_media_info(msg)

    if not media_info:

        logging.info(
            f"[SKIPPED] Message {msg.id} "
            f"has no supported media."
        )

        return False

    file_name = media_info["name"]
    size_bytes = media_info["size"]
    media_type = media_info["type"]

    # -----------------------------------------------------
    # SIZE
    # -----------------------------------------------------

    if size_bytes:

        size_mb = size_bytes / (1024 * 1024)

    else:

        size_mb = 0

    logging.info(
        f"[MEDIA DETECTED] "
        f"ID={msg.id} "
        f"Type={media_type} "
        f"Name='{file_name}' "
        f"Size={size_mb:.2f} MB"
    )

    # -----------------------------------------------------
    # SIZE FILTER
    # -----------------------------------------------------

    if size_bytes and size_mb < MIN_FILE_SIZE_MB:

        logging.info(
            f"[SKIPPED] '{file_name}' "
            f"is only {size_mb:.2f} MB "
            f"(minimum {MIN_FILE_SIZE_MB} MB)."
        )

        return False

    # -----------------------------------------------------
    # FORWARD
    # -----------------------------------------------------

    for attempt in range(1, 4):

        try:

            logging.info(
                f"[FORWARD] Message {msg.id} "
                f"attempt {attempt}/3"
            )

            result = await client.forward_messages(
                entity=target_entity,
                messages=msg
            )

            seen_messages.add(msg_key)

            logging.info(
                f"[SUCCESS] '{file_name}' "
                f"successfully forwarded "
                f"to target."
            )

            return True

        except FloodWaitError as e:

            wait_seconds = e.seconds + 2

            logging.warning(
                f"[FLOOD WAIT] Telegram requires "
                f"{wait_seconds}s."
            )

            await asyncio.sleep(wait_seconds)

        except Exception as e:

            logging.exception(
                f"[FORWARD ERROR] "
                f"Message {msg.id}: {e}"
            )

            await asyncio.sleep(2)

    logging.error(
        f"[FAILED] Message {msg.id} "
        f"could not be forwarded."
    )

    return False


# =========================================================
# MAIN
# =========================================================

async def main():

    await start_web_server()

    # -----------------------------------------------------
    # ENVIRONMENT CHECK
    # -----------------------------------------------------

    if not API_ID:
        raise RuntimeError(
            "API_ID environment variable is missing."
        )

    if not API_HASH:
        raise RuntimeError(
            "API_HASH environment variable is missing."
        )

    if not SESSION_STRING:
        raise RuntimeError(
            "SESSION_STRING environment variable is missing."
        )

    # -----------------------------------------------------
    # TELEGRAM CLIENT
    # -----------------------------------------------------

    client = TelegramClient(
        StringSession(SESSION_STRING),
        API_ID,
        API_HASH
    )

    await client.start()

    logging.info(
        "[TELEGRAM] Client connected."
    )

    # -----------------------------------------------------
    # SOURCE
    # -----------------------------------------------------

    try:

        source_entity = await client.get_entity(
            SOURCE_CHAT_ID
        )

        logging.info(
            "[SOURCE] Resolved: %s",
            getattr(
                source_entity,
                "title",
                SOURCE_CHAT_ID
            )
        )

    except Exception:

        logging.exception(
            "[SOURCE] Could not resolve source."
        )

        await client.disconnect()
        return

    # -----------------------------------------------------
    # TARGET
    # -----------------------------------------------------

    try:

        target_entity = await client.get_entity(
            TARGET_CHAT_ID
        )

        logging.info(
            "[TARGET] Resolved: %s",
            getattr(
                target_entity,
                "title",
                TARGET_CHAT_ID
            )
        )

    except Exception:

        logging.exception(
            "[TARGET] Could not resolve target."
        )

        await client.disconnect()
        return

    # -----------------------------------------------------
    # STARTUP SCAN
    # -----------------------------------------------------

    logging.info(
        "[STARTUP] Checking latest 10 messages..."
    )

    try:

        async for msg in client.iter_messages(
            source_entity,
            limit=10
        ):

            await process_and_forward(
                client,
                target_entity,
                msg
            )

    except Exception:

        logging.exception(
            "[STARTUP] Scan failed."
        )

    # -----------------------------------------------------
    # NEW MESSAGE LISTENER
    # -----------------------------------------------------

    @client.on(events.NewMessage)
    async def channel_post_handler(event):

        try:

            logging.info(
                f"[EVENT] New message "
                f"chat_id={event.chat_id} "
                f"message_id={event.id}"
            )

            # Only source channel
            if event.chat_id != SOURCE_CHAT_ID:

                logging.info(
                    "[EVENT] Not source channel. Ignoring."
                )

                return

            msg = event.message

            logging.info(
                f"[SOURCE EVENT] "
                f"Message {msg.id}"
            )

            await process_and_forward(
                client,
                target_entity,
                msg
            )

        except Exception:

            logging.exception(
                "[EVENT] Handler error."
            )

    # -----------------------------------------------------
    # READY
    # -----------------------------------------------------

    logging.info("=" * 60)
    logging.info("TELEGRAM MOVIE FORWARDER IS READY")
    logging.info(f"SOURCE: {SOURCE_CHAT_ID}")
    logging.info(f"TARGET: {TARGET_CHAT_ID}")
    logging.info(
        f"MINIMUM FILE SIZE: {MIN_FILE_SIZE_MB} MB"
    )
    logging.info("Waiting for new messages...")
    logging.info("=" * 60)

    await client.run_until_disconnected()


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    asyncio.run(main())
