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


API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")

SOURCE_CHAT_ID = -1002405808647
TARGET_CHAT_ID = -1004320100002

MIN_FILE_SIZE_MB = 10

seen_messages = set()


# --------------------------------------------------
# KEEP ALIVE SERVER
# --------------------------------------------------

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
        f"Keep-alive web server active on port {port}"
    )


# --------------------------------------------------
# PROCESS MESSAGE
# --------------------------------------------------

async def process_and_forward(client, target_entity, msg):

    if not msg:
        return False

    msg_key = f"{msg.chat_id}_{msg.id}"

    if msg_key in seen_messages:
        logging.info(
            f"[DUPLICATE] Message {msg.id} already processed."
        )
        return False

    # ----------------------------------------------
    # CHECK MEDIA
    # ----------------------------------------------

    if not msg.media:
        logging.info(
            f"[SKIPPED] Message {msg.id} has no media."
        )
        return False

    file_obj = getattr(msg, "file", None)

    if not file_obj:
        logging.info(
            f"[SKIPPED] Message {msg.id} media has no file object."
        )
        return False

    # ----------------------------------------------
    # FILE SIZE
    # ----------------------------------------------

    size_bytes = getattr(file_obj, "size", None)

    if not size_bytes:
        logging.warning(
            f"[SKIPPED] Message {msg.id}: unable to determine file size."
        )
        return False

    size_mb = size_bytes / (1024 * 1024)

    file_name = (
        getattr(file_obj, "name", None)
        or f"media_{msg.id}"
    )

    logging.info(
        f"[MEDIA] ID={msg.id} "
        f"Name='{file_name}' "
        f"Size={size_mb:.2f} MB"
    )

    # ----------------------------------------------
    # SIZE FILTER
    # ----------------------------------------------

    if size_mb < MIN_FILE_SIZE_MB:

        logging.info(
            f"[SKIPPED] {file_name} "
            f"is below {MIN_FILE_SIZE_MB} MB."
        )

        return False

    # ----------------------------------------------
    # FORWARD
    # ----------------------------------------------

    for attempt in range(1, 4):

        try:

            logging.info(
                f"[FORWARD] Attempt {attempt}/3 "
                f"for message {msg.id}"
            )

            result = await client.forward_messages(
                target_entity,
                msg
            )

            seen_messages.add(msg_key)

            logging.info(
                f"[SUCCESS] Message {msg.id} "
                f"forwarded successfully."
            )

            logging.info(
                f"[TARGET RESULT] {result}"
            )

            return True

        except FloodWaitError as e:

            wait_time = e.seconds + 2

            logging.warning(
                f"[FLOOD WAIT] Telegram requested "
                f"{wait_time}s wait."
            )

            await asyncio.sleep(wait_time)

        except Exception as e:

            logging.exception(
                f"[FORWARD ERROR] "
                f"Message {msg.id}: {e}"
            )

            await asyncio.sleep(2)

    logging.error(
        f"[FAILED] Could not forward message {msg.id}"
    )

    return False


# --------------------------------------------------
# MAIN
# --------------------------------------------------

async def main():

    await start_web_server()

    # ----------------------------------------------
    # VALIDATE ENVIRONMENT
    # ----------------------------------------------

    if not API_ID:
        raise RuntimeError("API_ID is missing.")

    if not API_HASH:
        raise RuntimeError("API_HASH is missing.")

    if not SESSION_STRING:
        raise RuntimeError("SESSION_STRING is missing.")

    # ----------------------------------------------
    # TELEGRAM CLIENT
    # ----------------------------------------------

    client = TelegramClient(
        StringSession(SESSION_STRING),
        API_ID,
        API_HASH
    )

    await client.start()

    logging.info(
        "[TELEGRAM] Client connected successfully."
    )

    # ----------------------------------------------
    # RESOLVE SOURCE
    # ----------------------------------------------

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
            "[SOURCE] Could not resolve source chat."
        )

        await client.disconnect()
        return

    # ----------------------------------------------
    # RESOLVE TARGET
    # ----------------------------------------------

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
            "[TARGET] Could not resolve target chat."
        )

        await client.disconnect()
        return

    # ----------------------------------------------
    # VERIFY ACCESS
    # ----------------------------------------------

    logging.info(
        "[VERIFY] Source ID: %s",
        getattr(source_entity, "id", "unknown")
    )

    logging.info(
        "[VERIFY] Target ID: %s",
        getattr(target_entity, "id", "unknown")
    )

    # ----------------------------------------------
    # STARTUP CATCH-UP
    # ----------------------------------------------

    logging.info(
        "[STARTUP] Checking last 10 messages..."
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
            "[STARTUP] Message scan failed."
        )

    # ----------------------------------------------
    # NEW MESSAGE LISTENER
    # ----------------------------------------------

    @client.on(events.NewMessage)
    async def channel_post_handler(event):

        try:

            incoming_chat_id = event.chat_id

            logging.info(
                "[EVENT] New message detected. "
                f"chat_id={incoming_chat_id}, "
                f"message_id={event.id}"
            )

            # --------------------------------------
            # ONLY SOURCE CHAT
            # --------------------------------------

            if incoming_chat_id != SOURCE_CHAT_ID:

                logging.info(
                    "[EVENT] Message is not from source. Ignoring."
                )

                return

            logging.info(
                f"[SOURCE EVENT] New message {event.id}"
            )

            await process_and_forward(
                client,
                target_entity,
                event.message
            )

        except Exception:

            logging.exception(
                "[EVENT] Handler crashed."
            )

    logging.info(
        "=============================================="
    )

    logging.info(
        "LISTENER ACTIVE"
    )

    logging.info(
        f"SOURCE: {SOURCE_CHAT_ID}"
    )

    logging.info(
        f"TARGET: {TARGET_CHAT_ID}"
    )

    logging.info(
        "Waiting for new Telegram messages..."
    )

    logging.info(
        "=============================================="
    )

    await client.run_until_disconnected()


# --------------------------------------------------
# ENTRY POINT
# --------------------------------------------------

if __name__ == "__main__":
    asyncio.run(main())
