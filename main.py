from tkinter import messagebox
from anyio import create_task_group
from dotenv import load_dotenv
import asyncio
import aiofiles
import async_timeout
import gui
import time
import argparse
import logging
import os
import json


load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('watchdog_logger')

MINECHAT_HOST = 'minechat.dvmn.org'
MINECHAT_READ_PORT = 5000
MINECHAT_SEND_PORT = 5050
MINECHAT_ACCESS_TOKEN = os.getenv('MINECHAT_ACCESS_TOKEN')
HISTORY_FILEPATH = './minechat.history'
CONNECTION_TIMEOUT = 3


class InvalidToken(Exception):
    pass


async def authorize(host, port, token):
    reader, writer = await asyncio.open_connection(host, port)
    await reader.readline()
    writer.write(f'{token}\n'.encode())
    await writer.drain()
    answer = await reader.readline()

    answer = json.loads(answer.decode())
    if answer is None:
        writer.close()
        await writer.wait_closed()
        raise InvalidToken

    nickname = answer['nickname']
    return reader, writer, nickname


async def send_msgs(host, port, token, sending_queue, status_updates_queue,
        watchdog_queue):
    try:
        reader, writer, nickname = await authorize(host, port, token)
    except InvalidToken:
        messagebox.showerror('Неверный токен', 'Проверьте токен. Сервер неузнал его.')
        raise ConnectionError

    status_updates_queue.put_nowait(gui.NicknameReceived(nickname))
    watchdog_queue.put_nowait('Authorization done.')
    status_updates_queue.put_nowait(gui.SendingConnectionStateChanged.ESTABLISHED)
    while True:
        msg = await sending_queue.get()
        writer.write(f'{msg}\n\n'.encode())
        await writer.drain()
        watchdog_queue.put_nowait('Message sent.')


async def read_msgs(host, port, history_filepath, messages_queue,
        status_updates_queue, save_queue, watchdog_queue):
    await loading_messages_history(history_filepath, messages_queue)

    reader, writer = await asyncio.open_connection(host, port)
    status_updates_queue.put_nowait(gui.ReadConnectionStateChanged.ESTABLISHED)
    while True:
        msg = await reader.readline()
        messages_queue.put_nowait(msg.decode())
        save_queue.put_nowait(msg.decode())
        watchdog_queue.put_nowait('New message in chat.')


async def save_messages(filepath, save_queue):
    while True:
        msg = await save_queue.get()
        async with aiofiles.open(filepath, 'a') as f:
            await f.write(msg)


async def watch_for_connection(watchdog_queue):
    while True:
        try:
            async with async_timeout.timeout(CONNECTION_TIMEOUT):
                msg = await watchdog_queue.get()
        except asyncio.TimeoutError:
            status_updates_queue.put_nowait(gui.ReadConnectionStateChanged.CLOSED)
            logger.debug(f'[{time.time()}] {CONNECTION_TIMEOUT}s timeout is elapsed.')
            raise ConnectionError

        logger.debug(f'[{time.time()}] Connection is alive. {msg}')


async def loading_messages_history(filepath, messages_queue):
    try:
        async with aiofiles.open(filepath, 'r') as f:
            msgs = await f.readlines()
    except FileNotFoundError:
        return

    if msgs:
        [messages_queue.put_nowait(msg) for msg in msgs]


async def handle_connection(messages_queue, sending_queue, status_updates_queue,
        save_queue, watchdog_queue):
    async with create_task_group() as task_group:
        await task_group.spawn(read_msgs, MINECHAT_HOST, MINECHAT_READ_PORT,
                HISTORY_FILEPATH, messages_queue, status_updates_queue,
                save_queue, watchdog_queue)

        await task_group.spawn(send_msgs, MINECHAT_HOST, MINECHAT_SEND_PORT,
            MINECHAT_ACCESS_TOKEN, sending_queue, status_updates_queue, watchdog_queue)

        await task_group.spawn(save_messages, HISTORY_FILEPATH, save_queue)

        await task_group.spawn(watch_for_connection, watchdog_queue)


async def main():
    messages_queue = asyncio.Queue()
    sending_queue = asyncio.Queue()
    save_queue = asyncio.Queue()
    status_updates_queue = asyncio.Queue()
    watchdog_queue = asyncio.Queue()

    await asyncio.gather(
        handle_connection(messages_queue, sending_queue, status_updates_queue,
            save_queue, watchdog_queue),
        gui.draw(messages_queue, sending_queue, status_updates_queue)
    )


if __name__ == '__main__':
    asyncio.run(main())
