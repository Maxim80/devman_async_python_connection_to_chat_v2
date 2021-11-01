from tkinter import messagebox
from anyio import create_task_group
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import asyncio
import aiofiles
import async_timeout
import socket
import gui
import time
import argparse
import logging
import os
import json


load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('watchdog_logger')

HOST = 'minechat.dvmn.org'
READ_PORT = 5000
SEND_PORT = 5050
MINECHAT_ACCESS_TOKEN = os.getenv('MINECHAT_ACCESS_TOKEN')
HISTORY_FILEPATH = './minechat.history'
CONNECTION_TIMEOUT = 3


class InvalidToken(Exception):
    pass


def reconnect(func):
    async def wrapped(*args, **kwargs):
        while True:
            try:
                await func(*args, **kwargs)
            except ConnectionError:
                await asyncio.sleep(CONNECTION_TIMEOUT)
                continue
            except socket.gaierror:
                await asyncio.sleep(CONNECTION_TIMEOUT)
                continue

    return wrapped


@asynccontextmanager
async def create_connection(host, send_port, read_port, status_updates_queue):
    status_updates_queue.put_nowait(gui.ReadConnectionStateChanged.INITIATED)
    r_reader, r_writer = await asyncio.open_connection(host, read_port)
    status_updates_queue.put_nowait(gui.ReadConnectionStateChanged.ESTABLISHED)

    status_updates_queue.put_nowait(gui.SendingConnectionStateChanged.INITIATED)
    s_reader, s_writer = await asyncio.open_connection(host, send_port)
    status_updates_queue.put_nowait(gui.SendingConnectionStateChanged.ESTABLISHED)

    try:
        yield s_reader, s_writer, r_reader, r_writer
    finally:
        s_writer.close()
        await s_writer.wait_closed()
        r_writer.close()
        await r_writer.wait_closed()
        status_updates_queue.put_nowait(gui.ReadConnectionStateChanged.CLOSED)
        status_updates_queue.put_nowait(gui.SendingConnectionStateChanged.CLOSED)


async def authorize(reader, writer, token, watchdog_queue, status_updates_queue):
    await reader.readline()
    writer.write(f'{token}\n'.encode())
    await writer.drain()
    answer = await reader.readline()
    answer = json.loads(answer.decode())
    if answer is None:
        raise InvalidToken

    nickname = answer['nickname']
    watchdog_queue.put_nowait('Authorization done.')
    status_updates_queue.put_nowait(gui.NicknameReceived(nickname))


async def send_msgs(writer, sending_queue, watchdog_queue):
    while True:
        msg = await sending_queue.get()
        writer.write(f'{msg}\n\n'.encode())
        await writer.drain()
        watchdog_queue.put_nowait('Message sent.')


async def read_msgs(reader, messages_queue, save_queue, watchdog_queue):

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


async def watch_for_connection(watchdog_queue, status_updates_queue):
    while True:
        try:
            async with async_timeout.timeout(CONNECTION_TIMEOUT):
                msg = await watchdog_queue.get()
        except asyncio.TimeoutError:
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


async def checking_connection(reader, writer, watchdog_queue):
    msg = '\n'.encode()
    while True:
        writer.write(msg)
        await writer.drain()
        answer = await reader.readline()
        watchdog_queue.put_nowait(answer.decode())
        await asyncio.sleep(5)


@reconnect
async def handle_connection(messages_queue, sending_queue, status_updates_queue,
        save_queue, watchdog_queue):

    async with create_connection(HOST, SEND_PORT, READ_PORT, status_updates_queue) as connect:
        s_reader, s_writer, r_reader, _ = connect

        await authorize(s_reader, s_writer, MINECHAT_ACCESS_TOKEN, watchdog_queue, status_updates_queue)

        async with create_task_group() as task_group:
            await task_group.spawn(send_msgs, s_writer, sending_queue, watchdog_queue)
            await task_group.spawn(read_msgs, r_reader, messages_queue, save_queue, watchdog_queue)
            await task_group.spawn(save_messages, HISTORY_FILEPATH, save_queue)
            await task_group.spawn(watch_for_connection, watchdog_queue, status_updates_queue)
            await task_group.spawn(checking_connection, s_reader, s_writer, watchdog_queue)


async def main():
    messages_queue = asyncio.Queue()
    sending_queue = asyncio.Queue()
    save_queue = asyncio.Queue()
    status_updates_queue = asyncio.Queue()
    watchdog_queue = asyncio.Queue()

    await loading_messages_history(HISTORY_FILEPATH, messages_queue)

    async with create_task_group() as task_group:
        await task_group.spawn(handle_connection, messages_queue, sending_queue,
            status_updates_queue, save_queue, watchdog_queue)
        await task_group.spawn(gui.draw, messages_queue, sending_queue, status_updates_queue)


if __name__ == '__main__':
    asyncio.run(main())
